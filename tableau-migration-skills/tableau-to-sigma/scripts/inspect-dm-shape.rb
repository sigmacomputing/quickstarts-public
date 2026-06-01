#!/usr/bin/env ruby
# Phase 4 pre-flight — DM denormalization plan.
#
# Why this exists: when the converter reuses an existing Sigma data model
# (Phase 1.5 hit), the workbook's `master` table sources from ONE element of
# that DM (usually the fact table). Any Tableau worksheet that references a
# dim column (Region from STORE_DIM, Category from PRODUCT_DIM, Tier from
# CUSTOMER_DIM, etc.) needs that column either (a) already denormalized onto
# the fact element, or (b) wired via Lookup() into a separate hidden master
# sourcing the dim element.
#
# The converter agent doesn't know which case applies until the workbook POST
# fails with "Cannot resolve columns on table master: dependency not found:
# formula reference customer_dim/region" — costing minutes of rework.
#
# This script inspects the DM element graph BEFORE the workbook spec is
# written, classifies each element as fact (the biggest, contains FKs) or
# dim (referenced from the fact via *_Key), and outputs a column-resolution
# plan: which columns are direct, which need Lookup, with the exact formula.
#
# Closes beads-sigma-dd7. Companion to scripts/find-or-pick-dm.rb (Phase 1.5).
#
# Usage:
#   ruby scripts/inspect-dm-shape.rb \
#     --dm-id <uuid> \
#     [--fact-element-id <id>]    # default: largest element by column count
#     --out /tmp/<name>/dm-denorm-plan.json
#
# Env: SIGMA_BASE_URL, SIGMA_API_TOKEN.
#
# Output: dm-denorm-plan.json with column_resolution map keyed by column name:
#   { "Region": { location: "dim",  dim_element: "Customer Dim",
#                  formula: "Lookup([Customer Dim/Region], [Master/Customer Key], [Customer Dim/Customer Key])" },
#     "Order Date Key": { location: "fact", formula: "[Master/Order Date Key]" } }

require 'json'
require 'yaml'
require 'net/http'
require 'uri'
require 'optparse'

opts = {}
OptionParser.new do |p|
  p.on('--dm-id ID')          { |v| opts[:dm_id]    = v }
  p.on('--fact-element-id ID'){ |v| opts[:fact_id]  = v }
  p.on('--out PATH')          { |v| opts[:out]      = v }
end.parse!
%i[dm_id out].each { |k| abort "missing --#{k.to_s.tr('_','-')}" unless opts[k] }

BASE = ENV.fetch('SIGMA_BASE_URL')
$LOAD_PATH.unshift File.expand_path('lib', __dir__)
require 'sigma_rest'

# Sigma.request auto-refreshes on 401, useful when called repeatedly across a
# cluster of conversions where the token may expire between follower runs.
spec = begin
  Sigma.request(:get, "/v2/dataModels/#{opts[:dm_id]}/spec")
rescue Sigma::Error => e
  abort "GET spec failed: #{e.message}"
end
spec = YAML.safe_load(spec, permitted_classes: [Date, Time]) if spec.is_a?(String)

elements = (spec['pages'] || []).flat_map { |p| p['elements'] || [] }
abort 'no elements on DM' if elements.empty?

# Classify: pick the fact element. The convention is "largest by column count
# AND contains the most *_Key FK columns". User can override with
# --fact-element-id.
fact = if opts[:fact_id]
         elements.find { |e| e['id'] == opts[:fact_id] }
       else
         scored = elements.map do |el|
           cols = el['columns'] || []
           fk_count = cols.count { |c| c['name'].to_s.match?(/(?:^|\s)Key$/) }
           [cols.size + fk_count * 2, el]   # fk count weighted
         end
         scored.max_by(&:first)[1]
       end
abort "no fact element resolvable" if fact.nil?

dim_elements = elements - [fact]

# Build column → location map.
column_resolution = {}

# 1. Every column on the fact element is direct.
(fact['columns'] || []).each do |c|
  next if c['name'].nil? || c['name'].empty?
  column_resolution[c['name']] = {
    'location'   => 'fact',
    'formula'    => "[Master/#{c['name']}]",
    'fact_col_id'=> c['id']
  }
end

# 2. For each dim element: find its PK (its own *_Key column matching the dim
# name), then find the matching FK on the fact element. Then map every other
# column on the dim as a Lookup.
dim_links = []
dim_elements.each do |dim|
  dim_cols = dim['columns'] || []
  next if dim_cols.empty?

  # Heuristic: PK is the first column whose name ends in " Key" (e.g.
  # "Customer Key" on Customer Dim). Sigma's auto-gen DMs follow this.
  pk = dim_cols.find { |c| c['name'].to_s.match?(/\s+Key$/) }
  unless pk
    # Some DMs use "Date Key" / "Key" without surrounding space convention.
    pk = dim_cols.find { |c| c['name'].to_s.match?(/^[A-Z][a-zA-Z]+\s*Key$/) }
  end
  next unless pk

  # Find matching FK on fact element. Match by name (case-insensitive).
  fact_fk = (fact['columns'] || []).find { |c| c['name'].to_s.downcase == pk['name'].to_s.downcase }
  next unless fact_fk

  dim_name = dim['name'].to_s
  dim_name = "Dim #{pk['name'].sub(/\s*Key$/, '').strip}" if dim_name.empty?

  dim_links << {
    'dim_element'    => { 'id' => dim['id'], 'name' => dim_name },
    'pk_on_dim'      => { 'id' => pk['id'], 'name' => pk['name'] },
    'fk_on_fact'     => { 'id' => fact_fk['id'], 'name' => fact_fk['name'] },
    'lookup_columns' => (dim_cols - [pk]).map { |c| { 'id' => c['id'], 'name' => c['name'] } }
  }

  (dim_cols - [pk]).each do |c|
    next if c['name'].nil? || c['name'].empty?
    next if column_resolution[c['name']]   # already mapped via fact — keep direct
    column_resolution[c['name']] = {
      'location'    => 'dim',
      'dim_element' => dim_name,
      'formula'     => %(Lookup([#{dim_name}/#{c['name']}], [Master/#{fact_fk['name']}], [#{dim_name}/#{pk['name']}])),
      'dim_col_id'  => c['id'],
      'fk_name'     => fact_fk['name']
    }
  end
end

# 3. Any unresolved dim elements (no matching FK) — flag them
unmatched_dims = dim_elements.reject do |d|
  dim_links.any? { |l| l['dim_element']['id'] == d['id'] }
end

result = {
  'dm_id'              => opts[:dm_id],
  'dm_name'            => spec['name'],
  'fact_element'       => { 'id' => fact['id'], 'name' => fact['name'] || 'Fact', 'column_count' => (fact['columns'] || []).size },
  'dim_links'          => dim_links,
  'unmatched_dim_elements' => unmatched_dims.map { |d| { 'id' => d['id'], 'name' => d['name'], 'column_count' => (d['columns'] || []).size } },
  'column_resolution'  => column_resolution,
  'stats'              => {
    'columns_direct' => column_resolution.count { |_, v| v['location'] == 'fact' },
    'columns_lookup' => column_resolution.count { |_, v| v['location'] == 'dim' },
    'dim_links'      => dim_links.size,
    'unmatched_dims' => unmatched_dims.size
  }
}

File.write(opts[:out], JSON.pretty_generate(result))
warn "wrote #{opts[:out]}"
warn "fact element: #{fact['name'] || fact['id']} (#{(fact['columns']||[]).size} cols)"
warn "dim links:    #{dim_links.size}"
dim_links.each do |l|
  warn "  #{l['dim_element']['name']} — FK [Master/#{l['fk_on_fact']['name']}] ↔ PK [#{l['dim_element']['name']}/#{l['pk_on_dim']['name']}], #{l['lookup_columns'].size} cols available via Lookup"
end
warn "unmatched dim elements: #{unmatched_dims.size}"
warn "column resolution: #{result['stats']['columns_direct']} direct, #{result['stats']['columns_lookup']} via Lookup"
