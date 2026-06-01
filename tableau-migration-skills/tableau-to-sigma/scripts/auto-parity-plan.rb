#!/usr/bin/env ruby
# Build a parity plan automatically by matching Tableau view CSVs to Sigma
# workbook chart elements.
#
# Inputs:
#   --tableau /tmp/<name>           directory with get-workbook.json + views/<viewId>.csv
#   --workbook-spec wb-spec.json    Sigma workbook spec (after Phase 5c readback OR a manual write)
#                                   — used to pull element IDs, kinds, and column IDs
#   --out parity-plan.json          output plan (wrapped: { extract: bool, charts: [...] })
#
# Optional:
#   --rename CHART_FROM=CHART_TO    when the Sigma chart was renamed from the original Tableau title
#                                   (e.g., "Order Channel vs Ship Method=Orders by Category")
#                                   — repeatable
#
# Matching heuristic: Sigma element name == Tableau view name (exact), then loose match
# (strip punctuation, lowercase). Sigma kinds and Tableau chart_kinds are recorded for context.
#
# After running this, the agent fetches Sigma actuals via MCP or REST and edits the plan to
# add an "actual" key per chart, then runs verify-parity.rb.
#
# Or, if the SIGMA_API_TOKEN env path works, this script can pre-fetch Sigma actuals via the
# workbook query API and populate "actual" inline (best-effort; skip silently on failure).

require 'json'
require 'csv'
require 'optparse'
require 'net/http'
require 'uri'
require 'set'

opts = { renames: {} }
OptionParser.new do |p|
  p.on('--tableau DIR')          { |v| opts[:tab] = v }
  p.on('--workbook-spec PATH')   { |v| opts[:wb]  = v }
  p.on('--out PATH')             { |v| opts[:out] = v }
  p.on('--workbook-id ID')       { |v| opts[:wb_id] = v }
  p.on('--master-id ID',
       'Override the master-element ID prefix. Repeatable. ' \
       'Default: auto-detect every element where source.kind=="table" and ' \
       'elementId starts with "master" (handles multi-master specs like ' \
       'master-absences / master-employees / master-time).') { |v| (opts[:master_ids] ||= []) << v }
  p.on('--rename PAIR')          { |v| from, to = v.split('=', 2); opts[:renames][from] = to }
  p.on('--no-fetch')             {     opts[:no_fetch] = true }
end.parse!
abort('usage: --tableau DIR --workbook-spec FILE --out FILE [--workbook-id ID] [--rename A=B]') unless opts[:tab] && opts[:wb] && opts[:out]

# Load Tableau side: workbook metadata (for extract flag + view name → view id map) + CSVs
gw = JSON.parse(File.read(File.join(opts[:tab], 'get-workbook.json')))
views = gw.dig('views', 'view') || []
views = [views] unless views.is_a?(Array)

# hasExtracts on the workbook OR on the underlying datasource
extract = false
if gw['hasExtracts'] == true || gw['hasExtracts'] == 'true'
  extract = true
end
# Tableau Cloud often surfaces extracts on the workbook search result, not the get-workbook
# response — caller can re-flag via the --extract-mode CLI flag on verify-parity.rb.

view_by_name = views.each_with_object({}) { |v, h| h[v['name']] = v }

# Load Sigma side
spec = JSON.parse(File.read(opts[:wb]))

# Build the set of master-element-IDs we should treat as "the master" for
# chart matching. Either explicit via --master-id (repeatable) OR auto-detect
# from the spec: any element with kind=="table" + visibleAsSource==false +
# source.kind=="data-model" is a master. This handles multi-master workbooks
# (e.g. workforce uses master-absences / master-employees / master-time, one
# per Tableau worksheet sourcing different facts) — the previous hardcoded
# `elementId == 'master'` check returned zero matches and an incomprehensible
# "fire 0 queries" message.
master_ids =
  if opts[:master_ids] && !opts[:master_ids].empty?
    opts[:master_ids]
  else
    detected = []
    spec['pages'].each do |pg|
      pg['elements'].each do |e|
        if e['kind'] == 'table' &&
           e['visibleAsSource'] == false &&
           e.dig('source', 'kind') == 'data-model'
          detected << e['id']
        end
      end
    end
    # Legacy fallback for specs that pre-date the master/visibleAsSource shape:
    # any element whose ID literally starts with `master`.
    if detected.empty?
      spec['pages'].each do |pg|
        pg['elements'].each do |e|
          detected << e['id'] if e['id'].to_s.start_with?('master')
        end
      end
    end
    detected.uniq
  end
abort("auto-parity-plan.rb: no master element(s) detected; pass --master-id explicitly") if master_ids.empty?
warn "matching charts that source from master element(s): #{master_ids.join(', ')}"

master_id_set = master_ids.to_set
sigma_charts = []
spec['pages'].each do |pg|
  pg['elements'].each do |e|
    next unless e['source'] && master_id_set.include?(e['source']['elementId'])
    sigma_charts << e
  end
end

# Match Sigma chart → Tableau view
def normalize(s)
  s.to_s.downcase.gsub(/[^a-z0-9]/, '')
end

# Build reverse-rename map: tableau-name → sigma-name was the input;
# we want sigma-name → tableau-name for lookup.
rev_renames = opts[:renames].each_with_object({}) { |(k, v), h| h[v] = k }

plan_entries = []
sigma_charts.each do |el|
  sigma_name = el['name']
  tableau_name = rev_renames[sigma_name] || sigma_name

  view = view_by_name[tableau_name]
  view ||= view_by_name.find { |n, _| normalize(n) == normalize(tableau_name) }&.last
  if view.nil?
    warn "no Tableau view matched Sigma chart #{sigma_name.inspect} (try --rename '<Tableau title>=#{sigma_name}')"
    next
  end

  csv_path = File.join(opts[:tab], 'views', "#{view['id']}.csv")
  unless File.exist?(csv_path)
    warn "missing CSV at #{csv_path} for #{sigma_name.inspect}"
    next
  end

  rows = CSV.read(csv_path)
  next if rows.empty?
  header = rows.shift
  expected_rows = rows.map do |r|
    r.map.with_index do |v, i|
      next nil if v.nil? || v.to_s.strip.empty?
      i == 0 ? v : (begin Float(v.to_s.gsub(',', '')) rescue v end)
    end
  end

  cols = (el['columns'] || []).map { |c| c['id'] }
  entry = {
    'chart'       => sigma_name,
    'tableau_view' => tableau_name,
    'sigma_element_id' => el['id'],
    'sigma_kind'  => el['kind'],
    'sigma_columns' => cols.first(2),       # most charts: dim + measure
    'expected'    => expected_rows
  }
  if opts[:wb_id] && cols.size >= 2
    entry['sql_template'] = %(SELECT "#{cols[0]}", "#{cols[1]}" FROM "workbook"."#{el['id']}" ORDER BY 1)
    entry['workbookId'] = opts[:wb_id]
  end
  plan_entries << entry
end

# NOTE: an earlier version of this script tried to pre-fetch actuals via
# POST /v2/workbooks/{wb}/query (REST). That endpoint does NOT exist on
# Sigma's public REST API — it returns `errorcause: UnmatchedHandler` with
# an empty body, which was silently swallowed by the rescue clause. The
# canonical path to fetch chart actuals is the MCP tool
# `mcp__sigma-mcp-v2__query` (Sigma's official MCP server, which goes
# through the internal query layer). Fire it from the agent's conversation
# layer — see phase6-parity.rb for the call shape per chart, and the
# Phase 6c documentation in SKILL.md for parallel-batch guidance.
#
# This script intentionally leaves entry['actual'] unset; the agent fills
# it after running the MCP queries in parallel (single tool-use message
# with N parallel tool calls). beads-sigma-s04.
puts "  NOTE: actuals must be fetched via mcp__sigma-mcp-v2__query (MCP), not REST."
puts "        Fire all #{plan_entries.size} per-chart queries in ONE parallel tool-use batch,"
puts "        then merge the rows into the parity plan's actual.rows arrays."

# Wrap output
output = { 'extract' => extract, 'charts' => plan_entries }
File.write(opts[:out], JSON.pretty_generate(output))

puts "wrote #{opts[:out]}"
puts "  charts matched: #{plan_entries.size}"
puts "  extract flag:   #{extract}"
puts "  next: fire mcp__sigma-mcp-v2__query for each chart in parallel (one tool-use batch),"
puts "        then merge the result rows into the parity plan and run verify-parity.rb."
