#!/usr/bin/env ruby
# Phase 6 (MANDATORY) — verify Sigma chart values match Tableau view CSVs.
#
# Two-pass workflow because Sigma's REST API doesn't expose a synchronous
# chart-data endpoint (filed as a separate Sigma API gap ticket). The skill
# uses the MCP V2 query tool to fetch actuals, then the script verifies.
#
# PASS 1 — emit the parity plan + per-chart MCP query instructions:
#
#   ruby scripts/phase6-parity.rb --tableau /tmp/<name> --workbook-id <wb>
#     [--rename "Tableau name=Sigma name" ...]
#     [--extract-mode] [--extract-tol 0.30]
#
#   Writes /tmp/<name>/parity-plan.json (with sigma_sql per chart)
#   Prints exact mcp__sigma-mcp-v2__query calls the agent should run, one
#   per chart, then re-invoke this script with --finalize.
#
# PASS 2 — finalize with the actuals the agent collected:
#
#   ruby scripts/phase6-parity.rb --tableau /tmp/<name> --finalize \
#     --actuals /tmp/<name>/parity-actuals.json
#     [--extract-mode] [--extract-tol 0.30]
#
#   actuals.json shape:
#     { "<Sigma chart name>": [[dim, val], [dim, val], ...], ... }
#
#   Runs verify-parity.rb, prints pass/fail summary, writes parity-final.json.

require 'json'
require 'net/http'
require 'uri'
require 'optparse'
require 'base64'
require 'open3'
require 'time'

opts = { extract_mode: false, extract_tol: 0.30, renames: [], finalize: false }
OptionParser.new do |p|
  p.on('--tableau DIR')          { |v| opts[:tab] = v }
  p.on('--workbook-id ID')       { |v| opts[:wb] = v }
  p.on('--out PATH')             { |v| opts[:out] = v }
  p.on('--extract-mode')         { opts[:extract_mode] = true }
  p.on('--extract-tol F', Float) { |v| opts[:extract_tol] = v }
  p.on('--rename PAIR', 'Tableau-name=Sigma-name (repeat)') { |v| opts[:renames] << v }
  p.on('--dashboard-layout PATH', 'parse-twb-layout output for the tile census (default <tableau-dir>/dashboard-layout.json)') { |v| opts[:dash_layout] = v }
  p.on('--finalize')             { opts[:finalize] = true }
  p.on('--actuals PATH', 'JSON: { "<chart name>": [[dim, val], ...] } — for --finalize') { |v| opts[:actuals] = v }
end.parse!
abort('missing --tableau') unless opts[:tab]
opts[:out] ||= File.join(opts[:tab], 'parity-final.txt')

if opts[:finalize]
  abort('--actuals required with --finalize') unless opts[:actuals]
else
  abort('--workbook-id required for pass 1') unless opts[:wb]
end

BASE = ENV.fetch('SIGMA_BASE_URL')
$LOAD_PATH.unshift File.expand_path('lib', __dir__)
require 'sigma_rest'

# Sigma.request handles initial token fetch + 401-retry-with-refresh
# transparently. Phase 6 is the longest pass in the pipeline; tokens
# routinely expire mid-run on big workbooks.
def http_json(path)
  Sigma.request(:get, path)
end

plan_path = File.join(opts[:tab], 'parity-plan.json')

if !opts[:finalize]
  # PASS 1 — build plan + emit per-chart MCP instructions
  warn "Phase 6 PASS 1: reading workbook spec #{opts[:wb]}"
  spec = http_json("/v2/workbooks/#{opts[:wb]}/spec")
  File.write(File.join(opts[:tab], 'wb-readback.json'), JSON.pretty_generate(spec))

  warn "Phase 6 PASS 1: building parity plan"
  plan_args = ['ruby', File.join(__dir__, 'auto-parity-plan.rb'),
               '--tableau', opts[:tab],
               '--workbook-spec', File.join(opts[:tab], 'wb-readback.json'),
               '--out', plan_path]
  opts[:renames].each { |r| plan_args.concat(['--rename', r]) }
  out, err, status = Open3.capture3(*plan_args)
  warn out unless out.empty?
  warn err unless err.empty?
  abort('auto-parity-plan failed') unless status.success?

  plan = JSON.parse(File.read(plan_path))

  # Pooled Sigma-side actuals collection (collect-parity-actuals.rb): the
  # element CSV export serves every chart kind except pivot-tables, N-wide,
  # under sigma_rest's auto-refresh. Only the genuinely agent-mediated charts
  # (pivot grids) are printed as MCP instructions below.
  actuals_path = File.join(opts[:tab], 'parity-actuals.json')
  t_collect = Time.now
  coll_out, coll_err, coll_st = Open3.capture3(
    'ruby', File.join(__dir__, 'collect-parity-actuals.rb'),
    '--plan', plan_path, '--workbook-id', opts[:wb],
    '--workbook-spec', File.join(opts[:tab], 'wb-readback.json'),
    '--out', actuals_path)
  puts coll_out unless coll_out.empty?
  warn coll_err unless coll_err.empty?
  warn 'collect-parity-actuals failed — ALL charts fall back to agent-mediated MCP queries' unless coll_st.success?
  collected = (JSON.parse(File.read(actuals_path)) rescue {}) if File.exist?(actuals_path)
  collected ||= {}
  remaining = plan['charts'].reject { |c| collected.key?(c['chart']) && (c['sigma_columns'] || []).length >= 1 }
                            .select { |c| (c['sigma_columns'] || []).length >= 1 }
  warn format('parity collection: %d/%d chart(s) pooled in %.1fs; %d agent-mediated',
              collected.size, plan['charts'].size, Time.now - t_collect, remaining.size)

  # Emit per-chart MCP instructions for the REMAINDER only.
  puts ""
  puts "=" * 70
  puts "PHASE 6 PASS 1 OUTPUT — Sigma chart data fetch instructions"
  puts "=" * 70
  puts ""
  if remaining.empty?
    puts "ALL #{collected.size} chart actuals were collected by the pooled exporter —"
    puts "#{actuals_path} is complete. No MCP queries needed."
  else
    puts "The pooled exporter filled #{actuals_path} for #{collected.size} chart(s)."
    puts "Agent: run ONE mcp__sigma-mcp-v2__query call per REMAINING chart below and"
    puts "MERGE the results into that same file (shape:"
    puts '  { "<Sigma chart name>": [[dim, val], [dim, val], ...], ... } ).'
  end
  puts ""
  puts "Then re-run:"
  puts "  ruby scripts/phase6-parity.rb --tableau #{opts[:tab]} \\"
  puts "    --finalize --actuals #{actuals_path}#{opts[:extract_mode] ? ' \\\n    --extract-mode --extract-tol ' + opts[:extract_tol].to_s : ''}"
  puts ""
  remaining.each_with_index do |c, i|
    cols = c['sigma_columns'] || []
    # KPIs are single-column (value only) — they MUST be queried too (bead
    # s6fo: the >=2 guard silently dropped every KPI from the actuals fetch).
    sel = cols.each_with_index.map { |col, j| %("#{col}" AS f#{j}) }.join(', ')
    sql = %(SELECT #{sel} FROM "workbook"."#{c['sigma_element_id']}" ORDER BY f0 NULLS FIRST)
    puts "  [#{i + 1}/#{remaining.length}] #{c['chart']}"
    puts "    mcp__sigma-mcp-v2__query  type=workbook  workbookId=#{opts[:wb]}"
    puts "    sql=#{sql.inspect}"
    puts ""
  end
  puts "=" * 70
  exit 0
end

# PASS 2 — finalize: inject actuals + run verifier
abort("plan not found at #{plan_path}; run pass 1 first") unless File.exist?(plan_path)
plan = JSON.parse(File.read(plan_path))
actuals = JSON.parse(File.read(opts[:actuals]))

warn "Phase 6 PASS 2: injecting actuals (#{actuals.size} charts) → #{plan_path}"
plan['charts'].each do |c|
  a = actuals[c['chart']]
  c['actual'] = { 'rows' => a } if a
end
File.write(plan_path, JSON.pretty_generate(plan))

warn "Phase 6 PASS 2: running verifier (#{opts[:extract_mode] ? 'extract-mode' : 'strict'})"
verifier_args = ['ruby', File.join(__dir__, 'verify-parity.rb'),
                 '--plan', plan_path]
if opts[:extract_mode]
  verifier_args.concat(['--extract-mode', '--extract-tol', opts[:extract_tol].to_s])
end
out, err, status = Open3.capture3(*verifier_args)
puts out
warn err unless err.empty?
File.write(opts[:out], out)

# Hard-gate sentinel — parity-final.json. assert-phase6-ran.rb checks this file
# to confirm Phase 6 actually ran. Without this sentinel, a subagent can skip
# Phase 6 entirely and still self-report GREEN (the historic loophole that
# masked the cluster follower regression on 2026-05-22, see beads-sigma-4pm).
summary_path = File.join(opts[:tab], 'parity-final.json')
total = plan['charts'].size
passed_chart_names = out.scan(/^PASS\s+\[[^\]]+\]\s+(.+)$/).flatten
failed_chart_names = out.scan(/^DIVERGE\s+\[[^\]]+\]\s+(.+)$/).flatten

# ---- Tile census (bead gjhe) ------------------------------------------------
# Compare the Tableau dashboard's chart-zone count against the charts that made
# it into the parity plan. A zone that rendered in the source dashboard but has
# no matching Sigma chart (empty view CSV silently dropped the tile, or an
# unexplained rename) used to slip through every gate — the workbook shipped
# with N-1 charts and parity still reported PASS. assert-phase6-ran.rb gate 5
# fails on unmatched zones unless --allow-missing-tiles explains them.
tile_census = nil
dash_layout_path = opts[:dash_layout] || File.join(opts[:tab], 'dashboard-layout.json')
if File.exist?(dash_layout_path)
  dash_layout = JSON.parse(File.read(dash_layout_path)) rescue nil
  if dash_layout.is_a?(Array)
    zone_names = dash_layout.flat_map { |d| d['zones'] || [] }
                            .select { |zz| zz['kind'] == 'chart' && !zz['caption'].to_s.strip.empty? }
                            .map { |zz| zz['caption'].strip }
                            .uniq
    norm = ->(s) { s.to_s.downcase.gsub(/[^a-z0-9]/, '') }
    matched = plan['charts'].flat_map { |c| [c['tableau_view'], c['chart']] }.compact.map(&norm)
    unmatched = zone_names.reject { |zn| matched.include?(norm.call(zn)) }
    tile_census = {
      'zones_total'          => zone_names.size,
      'charts_built'         => plan['charts'].size,
      'zones_unmatched'      => unmatched.size,
      'unmatched_zone_names' => unmatched
    }
    warn "tile census: #{zone_names.size} dashboard zone(s), #{plan['charts'].size} chart(s) in parity plan, #{unmatched.size} unmatched" \
         "#{unmatched.any? ? " — UNMATCHED: #{unmatched.join(', ')}" : ''}"
  else
    warn "tile census skipped: #{dash_layout_path} is not a parse-twb-layout array"
  end
else
  warn "tile census skipped: no dashboard layout at #{dash_layout_path} (pass --dashboard-layout to enable)"
end
summary = {
  'workbook_id'  => plan.dig('charts', 0, 'workbook_id') ||
                    (File.exist?(File.join(opts[:tab], 'wb-readback.json')) ?
                       JSON.parse(File.read(File.join(opts[:tab], 'wb-readback.json')))['workbookId'] : nil),
  'ran_at'       => Time.now.utc.iso8601,
  'mode'         => opts[:extract_mode] ? 'extract' : 'strict',
  'extract_tol'  => opts[:extract_mode] ? opts[:extract_tol] : nil,
  'charts_total' => total,
  'charts_pass'  => passed_chart_names.size,
  'charts_fail'  => failed_chart_names.size,
  'pass_names'   => passed_chart_names,
  'fail_names'   => failed_chart_names,
  'status'       => (status.success? && total > 0 && passed_chart_names.size == total) ? 'PASS' : 'FAIL'
}
summary['tile_census'] = tile_census if tile_census
File.write(summary_path, JSON.pretty_generate(summary))
warn "wrote #{summary_path} (status=#{summary['status']} #{summary['charts_pass']}/#{summary['charts_total']})"
exit(status.success? ? 0 : 2)
