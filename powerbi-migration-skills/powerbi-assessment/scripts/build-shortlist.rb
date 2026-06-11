#!/usr/bin/env ruby
# Phase 4 (Power BI): cross-tabulate per-report usage with per-report complexity
# and emit a value/cost-ranked migration shortlist.
#
# Mirrors tableau-assessment/scripts/build-shortlist.rb. Same scoring shape so
# the readout renderer is shared. The difference is the VALUE signal source:
#
#   - If Fabric-admin usage IS available (usage.json from probe-admin.rb's
#     Activity Events pull), value = views × √(distinct_users) — exactly the
#     tableau formula.
#   - If usage is UNAVAILABLE (no Fabric Administrator role — the common case),
#     value falls back to a complexity-only proxy: value = 10 × (pages +
#     visuals/4), so the shortlist still ranks "bigger / richer reports first"
#     even though we can't see who looks at them. The readout is then a
#     COMPLEXITY-ONLY shortlist and says so.
#
#   cost  = 10·unhandled + 3·manual + 1·hint      (same weights as tableau)
#   score = value / (1 + cost)
#
# Tags (same vocabulary as tableau-assessment):
#   usage available AND views == 0                → "retire"
#   unhandled >= 1                                → "needs-gap-scout"
#   score >= 20 and (manual + unhandled) == 0     → "migrate-first"
#   score >= 10                                   → "easy-win"
#   else                                          → "moderate"
#
# Usage:  ruby scripts/build-shortlist.rb --out /tmp/pbi-assessment-<tenant>
# Reads:  <out>/inventory.json, <out>/complexity.json, [<out>/usage.json]
# Writes: <out>/shortlist.json

require 'json'
require 'optparse'

opts = {}
OptionParser.new { |p| p.on('--out DIR') { |v| opts[:out] = v } }.parse!
abort('--out required') unless opts[:out]

inventory  = JSON.parse(File.read(File.join(opts[:out], 'inventory.json')))
complexity = JSON.parse(File.read(File.join(opts[:out], 'complexity.json')))

usage_path = File.join(opts[:out], 'usage.json')
usage = File.exist?(usage_path) ? JSON.parse(File.read(usage_path)) : nil
usage_available = !usage.nil? && usage['available'] != false

# usage.json (when admin) shape: { "available": true,
#   "by_report": { "<reportId>": { "views": N, "users": M } } }
usage_by_id = {}
if usage_available && usage['by_report']
  usage_by_id = usage['by_report']
end

rows = []
complexity.each do |rid, r|
  u = usage_by_id[rid]
  views = u ? u['views'].to_i : nil
  users = u ? u['users'].to_i : nil

  cost = r['n_unhandled'].to_i * 10 + r['n_manual'].to_i * 3 + r['n_hint'].to_i * 1

  value =
    if usage_available && views
      views * Math.sqrt([users || 1, 1].max).to_f
    else
      # complexity-only proxy: bigger / richer reports rank first
      10.0 * (r['pages'].to_i + r['visuals'].to_i / 4.0)
    end
  score = value / (1 + cost).to_f

  tag =
    if usage_available && views && views.zero?
      'retire'
    elsif r['n_unhandled'].to_i >= 1
      'needs-gap-scout'
    elsif score >= 20 && (r['n_manual'].to_i + r['n_unhandled'].to_i).zero?
      'migrate-first'
    elsif score >= 10
      'easy-win'
    else
      'moderate'
    end

  rows << {
    'name'       => r['name'],
    'id'         => rid,
    'workspace'  => r['workspace'],
    'model_name' => r['model_name'],
    'views'      => views,
    'users'      => users,
    'pages'      => r['pages'],
    'visuals'    => r['visuals'],
    'auto'       => r['n_auto'],
    'hint'       => r['n_hint'],
    'manual'     => r['n_manual'],
    'unhandled'  => r['n_unhandled'],
    'dax_buckets' => r['dax_buckets'],
    'value'      => value.round(1),
    'cost'       => cost,
    'score'      => score.round(2),
    'tag'        => tag
  }
end

rows.sort_by! { |r| -r['score'] }

result = {
  'usage_available' => usage_available,
  'value_basis'     => usage_available ? 'activity-events (views × √users)' : 'complexity-only proxy (pages + visuals/4)',
  'reports'         => rows
}

File.write(File.join(opts[:out], 'shortlist.json'), JSON.pretty_generate(result))
puts "wrote shortlist.json (#{rows.size} reports, value_basis=#{result['value_basis']})"
puts
printf "%-42s %6s %5s %5s %7s %s\n", 'Report', 'views', 'manl', 'unhd', 'score', 'tag'
rows.each do |r|
  printf "%-42s %6s %5d %5d %7.2f %s\n",
    (r['name'] || '')[0, 41], (r['views'] || '-').to_s, r['manual'], r['unhandled'], r['score'], r['tag']
end
