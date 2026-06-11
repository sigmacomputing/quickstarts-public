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

  # Emit per-chart MCP instructions
  puts ""
  puts "=" * 70
  puts "PHASE 6 PASS 1 OUTPUT — Sigma chart data fetch instructions"
  puts "=" * 70
  puts ""
  puts "Agent: run ONE mcp__sigma-mcp-v2__query call per chart below, then save"
  puts "the results to /tmp/<name>/parity-actuals.json with shape:"
  puts '  { "<Sigma chart name>": [[dim, val], [dim, val], ...], ... }'
  puts ""
  puts "Then re-run:"
  puts "  ruby scripts/phase6-parity.rb --tableau #{opts[:tab]} \\"
  puts "    --finalize --actuals #{opts[:tab]}/parity-actuals.json#{opts[:extract_mode] ? ' \\\n    --extract-mode --extract-tol ' + opts[:extract_tol].to_s : ''}"
  puts ""
  plan['charts'].each_with_index do |c, i|
    cols = c['sigma_columns'] || []
    next unless cols.length >= 2
    sql = %(SELECT "#{cols[0]}" AS dim, "#{cols[1]}" AS val FROM "workbook"."#{c['sigma_element_id']}" ORDER BY dim NULLS FIRST)
    puts "  [#{i + 1}/#{plan['charts'].length}] #{c['chart']}"
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
File.write(summary_path, JSON.pretty_generate(summary))
warn "wrote #{summary_path} (status=#{summary['status']} #{summary['charts_pass']}/#{summary['charts_total']})"
exit(status.success? ? 0 : 2)
