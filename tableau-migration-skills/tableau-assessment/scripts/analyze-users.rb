#!/usr/bin/env ruby
# Phase 2: User-population segmentation + migration impact analysis.
#
# Reads:
#   <out>/raw-ts-users.json        (from a TS Users MCP query — see SKILL.md)
#   <out>/raw-ts-events-per-user.json (from a TS Events per-user query)
#   <out>/shortlist.json           (which workbooks are in the pilot)
#
# Writes:
#   <out>/users.json — segmented user population + per-user migration coverage
#
# Usage: ruby scripts/analyze-users.rb --out /tmp/assessment-<site>

require 'json'
require 'optparse'
require 'set'

opts = {}
OptionParser.new do |p|
  p.on('--out DIR') { |v| opts[:out] = v }
end.parse!
abort('--out required') unless opts[:out]

ts_users  = JSON.parse(File.read(File.join(opts[:out], 'raw-ts-users.json')))['data']
ts_events = JSON.parse(File.read(File.join(opts[:out], 'raw-ts-events-per-user.json')))['data']
shortlist = File.exist?(File.join(opts[:out], 'shortlist.json')) ?
              JSON.parse(File.read(File.join(opts[:out], 'shortlist.json'))) : []

# Build pilot set — top-5 by score, and an extended set (top-15)
pilot_names    = shortlist.first(5).map  { |r| r['name'] }.to_set
extended_names = shortlist.first(15).map { |r| r['name'] }.to_set
shortlist_by_tag = shortlist.group_by { |r| r['tag'] }
needs_review_names = (shortlist_by_tag['needs-gap-scout'] || []).map { |r| r['name'] }.to_set

# Aggregate per-user access map
accesses_by_user = Hash.new { |h, k| h[k] = {} }
ts_events.each do |e|
  u = e['Actor User Name']
  w = e['Workbook Name']
  accesses_by_user[u][w] = (accesses_by_user[u][w] || 0) + e['accesses'].to_i
end

# ----- Segment classification -----
def segment_for(u, total_access)
  days = u['days_since'].to_i
  owned = u['owned_wb'].to_i
  if u['access_views'].to_i.zero? && u['traffic_views'].to_i.zero? && owned.zero?
    return 'never_logged_in'
  end
  if days >= 60
    return 'dormant'
  end
  if owned >= 3 && total_access >= 30
    return 'power_user'
  end
  if owned >= 3
    return 'active_creator'
  end
  if total_access >= 30
    return 'heavy_consumer'
  end
  if total_access >= 5
    return 'casual'
  end
  if total_access >= 1
    return 'light'
  end
  if owned >= 1
    return 'creator_no_consumption'
  end
  'inactive'
end

SEGMENT_LABELS = {
  'power_user'             => 'Power user (creates and consumes)',
  'active_creator'         => 'Active creator',
  'heavy_consumer'         => 'Heavy consumer',
  'casual'                 => 'Casual user',
  'light'                  => 'Light user',
  'creator_no_consumption' => 'Creator (no recent consumption)',
  'dormant'                => 'Dormant (no login in 60+ days)',
  'never_logged_in'        => 'Never logged in',
  'inactive'               => 'Inactive (no activity)'
}

# Workbook ownership map (workbook → list of accessors): inverse of accesses_by_user
accessors_by_workbook = Hash.new { |h, k| h[k] = [] }
accesses_by_user.each do |user, wbs|
  wbs.each { |wb, n| accessors_by_workbook[wb] << user if n.positive? }
end

# ----- Build per-user records -----
users = ts_users.map do |u|
  email = u['User Email']
  access_map = accesses_by_user[email] || {}
  total = access_map.values.sum
  pilot_accesses = access_map.select { |w, _| pilot_names.include?(w) }.values.sum
  pilot_pct = total.zero? ? 0.0 : (pilot_accesses.to_f / total * 100).round(1)

  # Unique workbooks: ones only this user accessed
  unique_wbs = access_map.keys.select { |w| accessors_by_workbook[w].size == 1 }

  # Coverage bucket
  coverage =
    if total.zero?
      'no_activity'
    elsif pilot_pct >= 90
      'fully_covered'
    elsif pilot_pct >= 30
      'partially_covered'
    else
      'not_covered'
    end

  # ---- License decommission: smallest set of workbooks covering ≥90% of user's activity ----
  if total.positive?
    sorted = access_map.sort_by { |_, n| -n }
    cum = 0
    min_set = []
    sorted.each do |wb, n|
      min_set << wb
      cum += n
      break if cum.to_f / total * 100 >= 90
    end
    min_set_coverage = (cum.to_f / total * 100).round
    missing_from_pilot = min_set - pilot_names.to_a
    missing_from_extended = min_set - extended_names.to_a
    blocked_by_review = min_set & needs_review_names.to_a

    decommission_tier =
      if !blocked_by_review.empty?
        'tier_3_needs_review'   # depends on review-required workbook(s)
      elsif missing_from_pilot.empty?
        'tier_1_pilot'           # all covered by current top-5
      elsif missing_from_extended.empty?
        'tier_2_extended'        # covered by extended top-15
      else
        'tier_4_long_tail'       # needs workbooks beyond the current shortlist
      end
  else
    min_set = []
    min_set_coverage = 0
    missing_from_pilot = []
    missing_from_extended = []
    blocked_by_review = []
    decommission_tier = 'no_activity'
  end

  {
    'email'             => email,
    'license_type'      => u['User License Type'],
    'site_role'         => u['User Site Role'],
    'days_since_login'  => u['days_since'].to_i,
    'last_login_date'   => u['Last Login Date'],
    'owned_workbooks'   => u['owned_wb'].to_i,
    'owned_views'       => u['owned_views'].to_i,
    'traffic_to_owned_views' => u['traffic_views'].to_i,
    'total_accesses'    => total,
    'distinct_workbooks_accessed' => access_map.size,
    'segment'           => segment_for(u, total),
    'pilot_coverage_pct'=> pilot_pct,
    'pilot_coverage_bucket' => coverage,
    'unique_workbooks_accessed' => unique_wbs,  # only-this-user
    'top_workbook_accesses' => access_map.sort_by { |_, n| -n }.first(5).map { |w, n| { 'workbook' => w, 'accesses' => n } },
    # Decommission analysis
    'minimal_coverage_workbooks' => min_set,
    'minimal_coverage_count'     => min_set.size,
    'minimal_coverage_pct'       => min_set_coverage,
    'missing_from_pilot'         => missing_from_pilot,
    'missing_from_extended'      => missing_from_extended,
    'blocked_by_review_workbooks'=> blocked_by_review,
    'decommission_tier'          => decommission_tier
  }
end

# ----- Summary -----
by_segment = users.group_by { |u| u['segment'] }
by_coverage = users.group_by { |u| u['pilot_coverage_bucket'] }

by_tier = users.group_by { |u| u['decommission_tier'] }

# ---- Narrow-audience workbook detection ----
# Workbooks with meaningful absolute usage but concentrated on 1-2 users.
narrow_audience_workbooks = []
wb_total_accesses = Hash.new(0)
wb_user_accesses  = Hash.new { |h, k| h[k] = {} }
accesses_by_user.each do |user, wbs|
  wbs.each do |wb, n|
    wb_total_accesses[wb] += n
    wb_user_accesses[wb][user] = n
  end
end
wb_total_accesses.each do |wb, total|
  next if total < 5     # threshold for "meaningful usage"
  users_set = wb_user_accesses[wb]
  next if users_set.size > 3
  top_user, top_n = users_set.max_by { |_, n| n }
  share_pct = (top_n.to_f / total * 100).round
  next if share_pct < 70
  narrow_audience_workbooks << {
    'workbook'        => wb,
    'total_accesses'  => total,
    'distinct_users'  => users_set.size,
    'primary_user'    => top_user,
    'primary_user_share_pct' => share_pct,
    'all_users'       => users_set.sort_by { |_, n| -n }.map { |u, n| { 'user' => u, 'accesses' => n } }
  }
end
narrow_audience_workbooks.sort_by! { |w| -w['total_accesses'] }

# ---- License decommission summary ----
tier_labels = {
  'tier_1_pilot'        => 'Tier 1 — covered by current pilot (top 5)',
  'tier_2_extended'     => 'Tier 2 — covered if pilot extends to top 15',
  'tier_3_needs_review' => 'Tier 3 — depends on review-required workbook',
  'tier_4_long_tail'    => 'Tier 4 — needs workbooks beyond current shortlist',
  'no_activity'         => 'No activity — already a no-op'
}

decommission_summary = {
  'tier_labels' => tier_labels,
  'by_tier' => tier_labels.keys.each_with_object({}) { |k, h| h[k] = (by_tier[k] || []).size },
  'narrow_audience_workbook_count' => narrow_audience_workbooks.size,
  # Counts of seats decommissionable per tier
  'seats_decommissionable_in_pilot'    => (by_tier['tier_1_pilot']        || []).size,
  'seats_decommissionable_in_extended' => (by_tier['tier_1_pilot']        || []).size + (by_tier['tier_2_extended'] || []).size
}

summary = {
  'users_total' => users.size,
  'by_segment'  => SEGMENT_LABELS.keys.each_with_object({}) { |k, h| h[k] = (by_segment[k] || []).size },
  'pilot_coverage' => {
    'users_fully_covered'    => (by_coverage['fully_covered']     || []).size,
    'users_partially_covered'=> (by_coverage['partially_covered'] || []).size,
    'users_not_covered'      => (by_coverage['not_covered']       || []).size,
    'users_no_activity'      => (by_coverage['no_activity']       || []).size
  },
  'avg_pilot_coverage_pct' => (users.empty? ? 0 :
    (users.reject { |u| u['pilot_coverage_bucket'] == 'no_activity' }
          .map { |u| u['pilot_coverage_pct'] }
          .then { |arr| arr.empty? ? 0 : (arr.sum / arr.size.to_f) }).round(1)),
  'segment_labels' => SEGMENT_LABELS,
  'decommission'   => decommission_summary
}

result = {
  'summary' => summary,
  'users'   => users,
  'narrow_audience_workbooks' => narrow_audience_workbooks
}
out_path = File.join(opts[:out], 'users.json')
File.write(out_path, JSON.pretty_generate(result))
puts "wrote #{out_path}"
puts "  users:                #{summary['users_total']}"
SEGMENT_LABELS.each_key do |k|
  n = summary['by_segment'][k]
  puts "    #{SEGMENT_LABELS[k].ljust(40)} #{n}" if n.positive?
end
puts "  pilot coverage:"
puts "    fully (≥90%):     #{summary.dig('pilot_coverage', 'users_fully_covered')}"
puts "    partial (30-90%): #{summary.dig('pilot_coverage', 'users_partially_covered')}"
puts "    not covered:      #{summary.dig('pilot_coverage', 'users_not_covered')}"
puts "    no activity:      #{summary.dig('pilot_coverage', 'users_no_activity')}"
puts "  avg pilot coverage: #{summary['avg_pilot_coverage_pct']}%"
puts "  decommission tiers:"
tier_labels.each do |k, label|
  n = decommission_summary['by_tier'][k]
  puts "    #{label.ljust(50)} #{n}" if n.positive?
end
puts "  narrow-audience workbooks (≥70% concentration): #{narrow_audience_workbooks.size}"
