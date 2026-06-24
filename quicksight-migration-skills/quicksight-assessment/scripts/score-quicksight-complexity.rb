#!/usr/bin/env ruby
# Phase 3 (QuickSight): derive per-analysis migration-effort and convertibility
# scores from inventory.json (written by quicksight-inventory.py) and emit
# complexity.json.
#
# QuickSight's complexity lives in TWO places — the analysis (visual-kind mix,
# calc fields, parameters, FilterGroups, layout shape) and its datasets
# (source type, custom-sql, joins, data-prep transforms, RLS/CLS). An analysis
# inherits its datasets' burden via dataset_ids.
#
# Convertibility buckets (grounded in refs/migration-test-slate.md):
#   easy   → auto      (built visual + mechanical calc + relational/customsql source)
#   medium → manual    (mid-catalog visual / restructuring calc / joins+transforms / params+filtergroups / RLS)
#   hard   → unhandled (window-table-calc funcs / map+sankey+insight+custom+plugin visuals / free-form+section layout / dataset-of-datasets)
#
# These map onto the same four-tier vocabulary tableau-assessment uses so the
# downstream renderer/shortlist code is shared:
#   easy → auto      medium → manual      hard → unhandled
# (no "hint" tier analog — n_hint stays 0; kept for renderer/shortlist compat.)
#
# Usage:  ruby scripts/score-quicksight-complexity.rb --out /tmp/qs-assessment-<acct>
# Reads:  <out>/inventory.json
# Writes: <out>/complexity.json   (keyed by analysis id, tableau-compatible shape)

require 'json'
require 'optparse'

opts = {}
OptionParser.new { |p| p.on('--out DIR') { |v| opts[:out] = v } }.parse!
abort('--out required') unless opts[:out]

inv = JSON.parse(File.read(File.join(opts[:out], 'inventory.json')))

datasets_by_id = (inv['datasets'] || []).each_with_object({}) { |d, h| h[d['id']] = d }

complexity = {}
(inv['analyses'] || []).each do |an|
  buckets = an['calc_buckets'] || { 'a' => 0, 'b' => 0, 'c' => 0 }
  ca = buckets['a'].to_i
  cb = buckets['b'].to_i
  cc = buckets['c'].to_i

  visuals_built     = an['visuals_built'].to_i
  visuals_mid       = an['visuals_mid'].to_i
  visuals_unhandled = an['visuals_unhandled'].to_i
  window_calcs      = an['window_calc_count'].to_i
  params            = an['parameter_count'].to_i
  filter_groups     = an['filter_group_count'].to_i
  free_form         = an['free_form_sheets'].to_i
  section_based     = an['section_based_sheets'].to_i
  sheets            = an['sheet_count'].to_i
  visuals           = an['visual_count'].to_i

  # roll up dataset-level burden
  ds = (an['dataset_ids'] || []).map { |id| datasets_by_id[id] }.compact
  ds_custom_sql = ds.count { |d| d['has_custom_sql'] }
  ds_joins      = ds.count { |d| d['has_joins'] }
  ds_transforms = ds.sum { |d| d['transform_count'].to_i }
  ds_rls        = ds.count { |d| d['rls_enabled'] }
  ds_cls        = ds.count { |d| d['cls_enabled'] }
  ds_exotic_src = ds.count { |d| (d['physical_kinds'] || []).any? { |k| %w[S3Source].include?(k) } }

  # Map → tableau-compatible feature tiers.
  n_auto      = ca + visuals_built
  n_hint      = 0
  n_manual    = cb + visuals_mid + ds_joins + (ds_transforms.positive? ? 1 : 0) +
                (params.positive? ? 1 : 0) + ds_rls + ds_cls
  n_unhandled = cc + visuals_unhandled + free_form + section_based +
                (filter_groups.positive? ? 1 : 0) + ds_exotic_src

  features = []
  features << { 'name' => 'calc_mechanical', 'status' => 'auto',      'count' => ca } if ca.positive?
  features << { 'name' => 'calc_restructure', 'status' => 'manual',   'count' => cb } if cb.positive?
  features << { 'name' => 'calc_window',      'status' => 'unhandled', 'count' => cc } if cc.positive?
  features << { 'name' => 'visuals_built',    'status' => 'auto',      'count' => visuals_built } if visuals_built.positive?
  features << { 'name' => 'visuals_rebuild',  'status' => 'manual',    'count' => visuals_mid } if visuals_mid.positive?
  features << { 'name' => 'visuals_exotic',   'status' => 'unhandled', 'count' => visuals_unhandled } if visuals_unhandled.positive?
  features << { 'name' => 'dataset_joins',    'status' => 'manual',    'count' => ds_joins } if ds_joins.positive?
  features << { 'name' => 'dataset_transforms', 'status' => 'manual',  'count' => ds_transforms } if ds_transforms.positive?
  features << { 'name' => 'parameters',       'status' => 'manual',    'count' => params } if params.positive?
  features << { 'name' => 'filter_groups',    'status' => 'unhandled', 'count' => filter_groups } if filter_groups.positive?
  features << { 'name' => 'rls_cls',          'status' => 'manual',    'count' => ds_rls + ds_cls } if (ds_rls + ds_cls).positive?
  features << { 'name' => 'free_form_layout', 'status' => 'unhandled', 'count' => free_form + section_based } if (free_form + section_based).positive?
  features << { 'name' => 'exotic_source',    'status' => 'unhandled', 'count' => ds_exotic_src } if ds_exotic_src.positive?

  source_types = ds.flat_map { |d| d['physical_kinds'] || [] }.uniq.sort

  complexity[an['id']] = {
    'name'              => an['name'],
    'sheets'            => sheets,
    'visuals'           => visuals,
    'visual_kinds'      => an['visual_kinds'] || {},
    'calc_field_count'  => an['calc_field_count'].to_i,
    'window_calc_count' => window_calcs,
    'parameter_count'   => params,
    'filter_group_count' => filter_groups,
    'dataset_count'     => ds.size,
    'dataset_source_types' => source_types,
    'has_custom_sql'    => ds_custom_sql.positive?,
    'has_joins'         => ds_joins.positive?,
    'rls_role_count'    => ds_rls,
    'cls_count'         => ds_cls,
    'calc_buckets'      => { 'a' => ca, 'b' => cb, 'c' => cc },
    'twb_size_kb'       => 0, # n/a; kept for renderer compat
    'n_features'        => n_auto + n_hint + n_manual + n_unhandled,
    'n_auto'            => n_auto,
    'n_hint'            => n_hint,
    'n_manual'          => n_manual,
    'n_unhandled'       => n_unhandled,
    'features'          => features
  }
end

File.write(File.join(opts[:out], 'complexity.json'), JSON.pretty_generate(complexity))
puts "wrote complexity.json (#{complexity.size} analyses)"
puts
printf "%-40s %4s %4s %5s %4s %5s %5s\n", 'Analysis', 'sht', 'vis', 'calc', 'win', 'manl', 'unhd'
complexity.each_value do |r|
  printf "%-40s %4d %4d %5d %4d %5d %5d\n",
    (r['name'] || '')[0, 39], r['sheets'], r['visuals'], r['calc_field_count'],
    r['window_calc_count'], r['n_manual'], r['n_unhandled']
end
