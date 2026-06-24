#!/usr/bin/env ruby
# Phase 4 (QuickSight): cross-tabulate per-analysis usage with per-analysis
# complexity and emit a value/cost-ranked migration shortlist.
#
# Adapted from powerbi-assessment/scripts/build-shortlist.rb — same scoring
# shape + tag vocabulary so the readout renderer is shared. The VALUE signal:
#
#   - QuickSight has no per-analysis view-count API on the standard surface, so
#     value defaults to a complexity-only proxy: value = 10 × (sheets +
#     visuals/4), ranking "bigger / richer analyses first".
#   - If the agent supplied usage.json (e.g. CloudTrail / CloudWatch-derived
#     view counts, optional), value = views × √(distinct_users) — the tableau/
#     powerbi formula.
#
#   cost  = 10·unhandled + 3·manual + 1·hint      (same weights as the others)
#   score = value / (1 + cost)
#
# Tags (same vocabulary as powerbi/tableau-assessment):
#   usage available AND views == 0                → "retire"
#   unhandled >= 1                                → "needs-gap-scout"
#   score >= 20 and (manual + unhandled) == 0     → "migrate-first"
#   score >= 10                                   → "easy-win"
#   else                                          → "moderate"
#
# Usage:  ruby scripts/build-shortlist.rb --out /tmp/qs-assessment-<acct>
# Reads:  <out>/inventory.json, <out>/complexity.json, [<out>/usage.json]
# Writes: <out>/shortlist.json

require 'json'
require 'optparse'

opts = {}
OptionParser.new { |p| p.on('--out DIR') { |v| opts[:out] = v } }.parse!
abort('--out required') unless opts[:out]

complexity = JSON.parse(File.read(File.join(opts[:out], 'complexity.json')))

usage_path = File.join(opts[:out], 'usage.json')
usage = File.exist?(usage_path) ? JSON.parse(File.read(usage_path)) : nil
usage_available = !usage.nil? && usage['available'] != false

# usage.json (when supplied) shape: { "available": true,
#   "by_analysis": { "<analysisId>": { "views": N, "users": M } } }
usage_by_id = {}
usage_by_id = usage['by_analysis'] if usage_available && usage['by_analysis']

rows = []
complexity.each do |aid, r|
  u = usage_by_id[aid]
  views = u ? u['views'].to_i : nil
  users = u ? u['users'].to_i : nil

  cost = r['n_unhandled'].to_i * 10 + r['n_manual'].to_i * 3 + r['n_hint'].to_i * 1

  value =
    if usage_available && views
      views * Math.sqrt([users || 1, 1].max).to_f
    else
      # complexity-only proxy: bigger / richer analyses rank first
      10.0 * (r['sheets'].to_i + r['visuals'].to_i / 4.0)
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
    'name'        => r['name'],
    'id'          => aid,
    'sheets'      => r['sheets'],
    'visuals'     => r['visuals'],
    'views'       => views,
    'users'       => users,
    'auto'        => r['n_auto'],
    'hint'        => r['n_hint'],
    'manual'      => r['n_manual'],
    'unhandled'   => r['n_unhandled'],
    'calc_buckets' => r['calc_buckets'],
    'dataset_source_types' => r['dataset_source_types'],
    'value'       => value.round(1),
    'cost'        => cost,
    'score'       => score.round(2),
    'tag'         => tag
  }
end

rows.sort_by! { |r| -r['score'] }

result = {
  'usage_available' => usage_available,
  'value_basis'     => usage_available ? 'usage (views × √users)' : 'complexity-only proxy (sheets + visuals/4)',
  'analyses'        => rows
}

File.write(File.join(opts[:out], 'shortlist.json'), JSON.pretty_generate(result))
puts "wrote shortlist.json (#{rows.size} analyses, value_basis=#{result['value_basis']})"
puts
printf "%-40s %6s %5s %5s %7s %s\n", 'Analysis', 'views', 'manl', 'unhd', 'score', 'tag'
rows.each do |r|
  printf "%-40s %6s %5d %5d %7.2f %s\n",
    (r['name'] || '')[0, 39], (r['views'] || '-').to_s, r['manual'], r['unhandled'], r['score'], r['tag']
end
