#!/usr/bin/env ruby
# Phase 6 (QuickSight): compose migration-plan.json — the input contract the
# assessment hands to the `quicksight-to-sigma` conversion skill.
#
# Adapted from powerbi-assessment/scripts/migration-plan.rb. Differences:
#   - per-ANALYSIS (not report); the analysis inherits its datasets' source
#     types + data-prep + RLS via dataset_ids.
#   - DM clusters are formed on SHARED DATASET — analyses that reference the same
#     QuickSight dataset share a Sigma data model by construction (the clean,
#     reliable signal, like Power BI's shared-model clustering). Analyses with
#     overlapping dataset sets are merged into one cluster.
#
# recommended_path values:
#   "quicksight-to-sigma"            → analysis ready for conversion
#   "quicksight-to-sigma-with-scout" → has window calcs / exotic visuals / free-form; needs a design decision first
#   "retire"                         → zero views (only when usage supplied); recommend not migrating
#   "blocked"                        → > 5 manual/unhandled features; manual rework first
#
# Usage:  ruby scripts/migration-plan.rb --out /tmp/qs-assessment-<acct>
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

datasets_by_id   = (inventory['datasets'] || []).each_with_object({}) { |d, h| h[d['id']] = d }
analysis_dsids   = (inventory['analyses'] || []).each_with_object({}) { |a, h| h[a['id']] = (a['dataset_ids'] || []) }
analyses = shortlist['analyses'] || []

analysis_entries = analyses.map do |r|
  aid = r['id']
  cx = complexity[aid] || {}
  manual = cx['n_manual'].to_i
  unhandled = cx['n_unhandled'].to_i
  ds_ids = analysis_dsids[aid] || []
  src_types = ds_ids.flat_map { |id| (datasets_by_id[id] || {})['physical_kinds'] || [] }.uniq.sort

  recommended_path =
    case r['tag']
    when 'retire'          then 'retire'
    when 'needs-gap-scout' then 'quicksight-to-sigma-with-scout'
    else
      (manual + unhandled) > 5 ? 'blocked' : 'quicksight-to-sigma'
    end

  blockers = []
  blockers << "#{unhandled} unhandled feature(s) (window calc / exotic visual / free-form layout / FilterGroups)" if unhandled.positive?
  blockers << "#{manual} restructuring/join/transform/RLS/param feature(s)" if manual.positive?
  blockers << 'no views (retire)' if r['tag'] == 'retire'

  {
    'analysisId'        => aid,
    'name'              => r['name'],
    'dataset_ids'       => ds_ids,
    'dataset_source_types' => src_types,
    'recommended_path'  => recommended_path,
    'priority_tier'     => r['tag'],
    'score'             => r['score'],
    'views'             => r['views'],
    'calc_buckets'      => r['calc_buckets'],
    'blockers'          => blockers
  }
end

# --- DM clustering: shared dataset ------------------------------------------
# Analyses referencing the same dataset MUST share a Sigma data model. Union
# analyses by overlapping dataset sets into clusters.
clusterable = analysis_entries.select do |r|
  %w[quicksight-to-sigma quicksight-to-sigma-with-scout].include?(r['recommended_path'])
end

# union-find over dataset overlap
parent = {}
find = lambda { |x| parent[x] = (parent[x] == x ? x : find.call(parent[x])); parent[x] }
clusterable.each { |r| parent[r['analysisId']] = r['analysisId'] }
by_dataset = Hash.new { |h, k| h[k] = [] }
clusterable.each { |r| (r['dataset_ids'].empty? ? ["no-ds-#{r['analysisId']}"] : r['dataset_ids']).each { |d| by_dataset[d] << r['analysisId'] } }
by_dataset.each_value do |aids|
  aids.each_cons(2) { |a, b| parent[find.call(a)] = find.call(b) }
end

groups = Hash.new { |h, k| h[k] = [] }
clusterable.each { |r| groups[find.call(r['analysisId'])] << r }

clusters = groups.values.each_with_index.map do |members, i|
  ds_ids = members.flat_map { |m| m['dataset_ids'] }.uniq.sort
  ds_names = ds_ids.map { |id| (datasets_by_id[id] || {})['name'] }.compact
  src = members.flat_map { |m| m['dataset_source_types'] }.uniq.sort
  label = (ds_names.first || members.first['name'] || 'misc').downcase.gsub(/[^a-z0-9]+/, '-')[0, 24]
  cluster_id = "cluster-#{(i + 1).to_s.rjust(2, '0')}-#{label}"
  members.each { |m| m['cluster_id'] = cluster_id }
  {
    'id'                => cluster_id,
    'dataset_ids'       => ds_ids,
    'dataset_names'     => ds_names,
    'analysisIds'       => members.map { |m| m['analysisId'] },
    'analysis_names'    => members.map { |m| m['name'] },
    'shared_source_types' => src,
    'cluster_size'      => members.size
  }
end

by_path = analysis_entries.group_by { |r| r['recommended_path'] }
suggested_batch = analysis_entries
  .select { |r| r['recommended_path'] == 'quicksight-to-sigma' }
  .sort_by { |r| -(r['score'].to_f) }
  .first(8)
  .map { |r| { 'analysisId' => r['analysisId'], 'name' => r['name'], 'cluster_id' => r['cluster_id'] } }

result = {
  'analyses'    => analysis_entries,
  'dm_clusters' => clusters,
  'summary' => {
    'analyses_total'      => analysis_entries.size,
    'analyses_ready'      => (by_path['quicksight-to-sigma']            || []).size,
    'analyses_need_scout' => (by_path['quicksight-to-sigma-with-scout'] || []).size,
    'analyses_blocked'    => (by_path['blocked']                        || []).size,
    'analyses_retire'     => (by_path['retire']                         || []).size,
    'cluster_count'       => clusters.size,
    'usage_available'     => shortlist['usage_available'] == true,
    'suggested_batch'     => suggested_batch
  }
}

File.write(File.join(opts[:out], 'migration-plan.json'), JSON.pretty_generate(result))
s = result['summary']
puts "wrote migration-plan.json"
puts "analyses total: #{s['analyses_total']}"
puts "  ready for quicksight-to-sigma: #{s['analyses_ready']}"
puts "  need gap-scout:                #{s['analyses_need_scout']}"
puts "  blocked:                       #{s['analyses_blocked']}"
puts "  retire:                        #{s['analyses_retire']}"
puts "DM clusters: #{s['cluster_count']}"
clusters.each { |c| puts "  #{c['id']}: #{c['cluster_size']} analysis(es), datasets=#{c['dataset_names'].join(', ')}" }
puts
puts "suggested first batch (top #{suggested_batch.size} by score):"
suggested_batch.each_with_index { |r, i| puts "  #{i + 1}. #{r['name']} (cluster: #{r['cluster_id'] || '-'})" }
