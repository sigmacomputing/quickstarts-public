#!/usr/bin/env ruby
# Phase 6 (Power BI): compose migration-plan.json — the input contract the
# assessment hands to the `powerbi-to-sigma` conversion skill.
#
# Mirrors tableau-assessment/scripts/migration-plan.rb. Differences:
#   - per-REPORT (not workbook); the report inherits its model's warehouse
#     sources + DAX burden via dataset_id.
#   - DM clusters are formed on SHARED SEMANTIC MODEL (reports off the same
#     model obviously share a DM) AND, across models, on shared warehouse
#     sources. Power BI's model-is-the-DM mapping makes "same model = same
#     cluster" the dominant, reliable signal — much cleaner than Tableau's
#     .twb-table-set Jaccard.
#
# recommended_path values:
#   "powerbi-to-sigma"            → report ready for conversion
#   "powerbi-to-sigma-with-scout" → has no-equivalent DAX / custom visuals; needs design decision first
#   "retire"                      → zero views (admin-mode only); recommend not migrating
#   "blocked"                     → > 5 manual/unhandled features; manual rework first
#
# Usage:  ruby scripts/migration-plan.rb --out /tmp/pbi-assessment-<tenant>
# Reads:  <out>/shortlist.json, <out>/complexity.json, <out>/inventory.json
# Writes: <out>/migration-plan.json

require 'json'
require 'optparse'
require 'set'

opts = {}
OptionParser.new { |p| p.on('--out DIR') { |v| opts[:out] = v } }.parse!
abort('--out required') unless opts[:out]

shortlist  = JSON.parse(File.read(File.join(opts[:out], 'shortlist.json')))
complexity = JSON.parse(File.read(File.join(opts[:out], 'complexity.json')))
inventory  = JSON.parse(File.read(File.join(opts[:out], 'inventory.json')))

models_by_id = (inventory['semantic_models'] || []).each_with_object({}) { |m, h| h[m['id']] = m }
report_dataset = (inventory['reports'] || []).each_with_object({}) { |r, h| h[r['id']] = r['dataset_id'] }
reports = shortlist['reports'] || []

report_entries = reports.map do |r|
  rid = r['id']
  cx = complexity[rid] || {}
  manual = cx['n_manual'].to_i
  unhandled = cx['n_unhandled'].to_i
  ds_id = report_dataset[rid]
  model = models_by_id[ds_id] || {}

  recommended_path =
    case r['tag']
    when 'retire'          then 'retire'
    when 'needs-gap-scout' then 'powerbi-to-sigma-with-scout'
    else
      (manual + unhandled) > 5 ? 'blocked' : 'powerbi-to-sigma'
    end

  blockers = []
  blockers << "#{unhandled} unhandled feature(s) (no-equivalent DAX / custom visual)" if unhandled.positive?
  blockers << "#{manual} restructuring/RLS/calc-table feature(s)" if manual.positive?
  blockers << 'no views (retire)' if r['tag'] == 'retire'

  {
    'reportId'         => rid,
    'name'             => r['name'],
    'workspace'        => r['workspace'],
    'dataset_id'       => ds_id,
    'model_name'       => model['name'],
    'recommended_path' => recommended_path,
    'priority_tier'    => r['tag'],
    'score'            => r['score'],
    'views'            => r['views'],
    'warehouse_sources' => model['warehouse_sources'] || [],
    'dax_buckets'      => r['dax_buckets'],
    'blockers'         => blockers
  }
end

# --- DM clustering: primary key = shared semantic model -----------------------
# Reports off the same model MUST share a Sigma data model. Then merge model-
# level clusters that share a warehouse source (so two models reading the same
# Snowflake account get co-located for DM reuse).
clusterable = report_entries.select do |r|
  %w[powerbi-to-sigma powerbi-to-sigma-with-scout].include?(r['recommended_path'])
end

by_model = clusterable.group_by { |r| r['dataset_id'] || "no-model-#{r['reportId']}" }
clusters = by_model.map.with_index do |(ds_id, members), i|
  model = models_by_id[ds_id] || {}
  wh = members.flat_map { |m| m['warehouse_sources'] }.uniq.sort
  cluster_id = "cluster-#{(i + 1).to_s.rjust(2, '0')}-#{(model['name'] || 'misc').downcase.gsub(/[^a-z0-9]+/, '-')[0, 24]}"
  members.each { |m| m['cluster_id'] = cluster_id }
  {
    'id'                => cluster_id,
    'dataset_id'        => ds_id,
    'model_name'        => model['name'],
    'reportIds'         => members.map { |m| m['reportId'] },
    'report_names'      => members.map { |m| m['name'] },
    'shared_warehouse_sources' => wh,
    'cluster_size'      => members.size
  }
end

by_path = report_entries.group_by { |r| r['recommended_path'] }
suggested_batch = report_entries
  .select { |r| r['recommended_path'] == 'powerbi-to-sigma' }
  .sort_by { |r| -(r['score'].to_f) }
  .first(8)
  .map { |r| { 'reportId' => r['reportId'], 'name' => r['name'], 'cluster_id' => r['cluster_id'] } }

result = {
  'reports'     => report_entries,
  'dm_clusters' => clusters,
  'summary' => {
    'reports_total'             => report_entries.size,
    'reports_ready'             => (by_path['powerbi-to-sigma']           || []).size,
    'reports_need_scout'        => (by_path['powerbi-to-sigma-with-scout'] || []).size,
    'reports_blocked'           => (by_path['blocked']                     || []).size,
    'reports_retire'            => (by_path['retire']                      || []).size,
    'cluster_count'             => clusters.size,
    'usage_available'           => shortlist['usage_available'] == true,
    'suggested_batch'           => suggested_batch
  }
}

File.write(File.join(opts[:out], 'migration-plan.json'), JSON.pretty_generate(result))
s = result['summary']
puts "wrote migration-plan.json"
puts "reports total: #{s['reports_total']}"
puts "  ready for powerbi-to-sigma: #{s['reports_ready']}"
puts "  need gap-scout:             #{s['reports_need_scout']}"
puts "  blocked:                    #{s['reports_blocked']}"
puts "  retire:                     #{s['reports_retire']}"
puts "DM clusters: #{s['cluster_count']}"
clusters.each { |c| puts "  #{c['id']}: #{c['cluster_size']} report(s), model='#{c['model_name']}'" }
puts
puts "suggested first batch (top #{suggested_batch.size} by score):"
suggested_batch.each_with_index { |r, i| puts "  #{i + 1}. #{r['name']} (cluster: #{r['cluster_id'] || '-'})" }
