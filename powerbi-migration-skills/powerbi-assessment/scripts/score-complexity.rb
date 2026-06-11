#!/usr/bin/env ruby
# Phase 3 (Power BI): derive per-report migration-effort and DAX-convertibility
# scores from inventory.json (written by fabric-inventory.py) and emit
# complexity.json.
#
# Power BI's complexity lives in TWO places — the semantic model (DAX measures,
# calc columns, calc tables, RLS, DirectQuery) and the report (page/visual
# count, custom visuals). A report inherits its model's DAX burden via
# dataset_id. This is RICHER than Tableau's single-.twb scan: there the model
# and the viz are the same file; here they're separate artifacts.
#
# DAX-convertibility buckets (from research/dax-to-sigma-coverage.md +
# fixtures/MANIFEST.md), assigned per-measure by fabric-inventory.py:
#   a = mechanical (direct/near-direct Sigma formula rewrite)   ~70% of measures
#   b = restructuring (needs grouped element / parallel join / pre-aggregate)
#   c = no Sigma equivalent (dynamic context swap, path hierarchies)
#
# These map onto the same four-tier vocabulary tableau-assessment uses so the
# downstream renderer/shortlist code is shared:
#   a → auto      b → manual      c → unhandled
# (Power BI has no "hint" tier analog — DAX bucket-a is already mechanical, so
#  n_hint stays 0; the column is kept for renderer/shortlist compatibility.)
#
# Per-report migration-effort score = f(DAX bucket mix, visual complexity,
# calc tables, RLS). Higher cost = harder.
#
# Usage:  ruby scripts/score-complexity.rb --out /tmp/pbi-assessment-<tenant>
# Reads:  <out>/inventory.json
# Writes: <out>/complexity.json   (keyed by report id, tableau-compatible shape)

require 'json'
require 'optparse'

opts = {}
OptionParser.new { |p| p.on('--out DIR') { |v| opts[:out] = v } }.parse!
abort('--out required') unless opts[:out]

inv = JSON.parse(File.read(File.join(opts[:out], 'inventory.json')))

models_by_id = (inv['semantic_models'] || []).each_with_object({}) { |m, h| h[m['id']] = m }

complexity = {}
(inv['reports'] || []).each do |rep|
  model = models_by_id[rep['dataset_id']] || {}
  buckets = model['dax_buckets'] || { 'a' => 0, 'b' => 0, 'c' => 0 }
  a = buckets['a'].to_i
  b = buckets['b'].to_i
  c = buckets['c'].to_i

  calc_tables = model['calc_table_count'].to_i
  rls = model['rls_role_count'].to_i
  dq  = model['directquery_tables'].to_i
  visuals = rep['visual_count'].to_i
  pages   = rep['page_count'].to_i
  custom_visuals = (rep['custom_visuals'] || []).size

  # Map DAX buckets → tableau-compatible feature tiers.
  n_auto      = a
  n_hint      = 0
  n_manual    = b + calc_tables + rls          # restructuring + structural model surface
  n_unhandled = c + custom_visuals             # no-equivalent DAX + unsupported custom visuals

  features = []
  features << { 'name' => 'dax_mechanical',   'status' => 'auto',      'count' => a } if a.positive?
  features << { 'name' => 'dax_restructure',  'status' => 'manual',    'count' => b } if b.positive?
  features << { 'name' => 'dax_no_equiv',     'status' => 'unhandled', 'count' => c } if c.positive?
  features << { 'name' => 'calc_tables',      'status' => 'manual',    'count' => calc_tables } if calc_tables.positive?
  features << { 'name' => 'rls_roles',        'status' => 'manual',    'count' => rls } if rls.positive?
  features << { 'name' => 'directquery_tables', 'status' => 'auto',    'count' => dq } if dq.positive?
  features << { 'name' => 'custom_visuals',   'status' => 'unhandled', 'count' => custom_visuals } if custom_visuals.positive?

  complexity[rep['id']] = {
    'name'           => rep['name'],
    'workspace'      => rep['workspace'],
    'model_name'     => model['name'],
    'pages'          => pages,
    'visuals'        => visuals,
    'visual_kinds'   => rep['visual_kinds'] || {},
    'measure_count'  => model['measure_count'].to_i,
    'calc_column_count' => model['calc_column_count'].to_i,
    'calc_table_count'  => calc_tables,
    'rls_role_count'    => rls,
    'directquery_tables' => dq,
    'warehouse_sources' => model['warehouse_sources'] || [],
    'dax_buckets'    => { 'a' => a, 'b' => b, 'c' => c },
    'twb_size_kb'    => 0, # n/a for PBI; kept for renderer compat
    'n_features'     => n_auto + n_hint + n_manual + n_unhandled,
    'n_auto'         => n_auto,
    'n_hint'         => n_hint,
    'n_manual'       => n_manual,
    'n_unhandled'    => n_unhandled,
    'features'       => features
  }
end

File.write(File.join(opts[:out], 'complexity.json'), JSON.pretty_generate(complexity))
puts "wrote complexity.json (#{complexity.size} reports)"
puts
printf "%-44s %5s %5s %5s %5s %5s %5s\n", 'Report', 'pg', 'vis', 'meas', 'dax-a', 'dax-b', 'dax-c'
complexity.each_value do |r|
  d = r['dax_buckets']
  printf "%-44s %5d %5d %5d %5d %5d %5d\n",
    (r['name'] || '')[0, 43], r['pages'], r['visuals'], r['measure_count'],
    d['a'], d['b'], d['c']
end
