#!/usr/bin/env ruby
# Parity gate (MANDATORY) — verify Sigma chart values match the Looker source.
#
# The EXPECTED side comes from Looker itself (`POST /queries/run/json` /
# run_inline_query for the tile's explore+fields — ground truth) or, when live
# Looker access is gone (offline/fixture runs), from the warehouse: re-aggregate
# the master element's warehouse rows per the SOURCE LookML measure definitions
# (type: sum / count_distinct / number-ratio …). The ACTUAL side is the built
# Sigma element. This script orchestrates both passes and writes the
# parity-final.json sentinel that assert-phase6-ran.rb (the hard gate) requires.
# Two-pass design mirrors quicksight's phase6-parity-quicksight.rb /
# thoughtspot's phase6-parity-thoughtspot.rb.
#
# PASS 1 — read the workbook spec, enumerate chart elements, emit per-chart
# fetch instructions:
#
#   ruby scripts/phase6-parity-looker.rb --workdir <dir> --workbook-id <wb>
#
#   Writes <workdir>/parity-plan.json (+ wb-readback.json) and prints, per chart:
#     - the mcp__sigma-mcp-v2__query call for the Sigma ACTUAL rows
#     - a reminder to fetch EXPECTED rows from Looker (inline query) or the
#       warehouse with the same dimension + aggregation
#
#   The agent (or scripts/migrate-looker.py, which scripts this whole flow —
#   fetching BOTH sides per chart in a bounded 4-wide thread pool, see
#   LOOKER_PARITY_WORKERS) then writes two JSON files keyed by chart name, each
#   { "<chart name>": [[dim, val], ...], ... } :
#     <workdir>/parity-expected.json   (Looker / warehouse ground truth)
#     <workdir>/parity-actuals.json    (Sigma element rows)
#   KPI charts have no dimension — use [[null, <value>]].
#
# PASS 2 — finalize:
#
#   ruby scripts/phase6-parity-looker.rb --workdir <dir> --finalize \
#     [--expected <workdir>/parity-expected.json] \
#     [--actuals  <workdir>/parity-actuals.json] \
#     [--extract-mode] [--extract-tol 0.30]
#
#   Runs verify-parity.rb, prints the pass/fail summary, writes
#   parity-final.txt + parity-final.json (the hard-gate sentinel).
#
# Plain `table` / `text` elements aren't auto-planned (no single dim/measure
# axis) — query-verify tables manually and note it in the migration report.

require 'json'
require 'optparse'
require 'open3'
require 'time'

opts = { extract_mode: false, extract_tol: 0.30, finalize: false }
OptionParser.new do |p|
  p.on('--workdir DIR')          { |v| opts[:dir] = v }
  p.on('--workbook-id ID')       { |v| opts[:wb] = v }
  p.on('--finalize')             { opts[:finalize] = true }
  p.on('--expected PATH')        { |v| opts[:expected] = v }
  p.on('--actuals PATH')         { |v| opts[:actuals] = v }
  p.on('--extract-mode')         { opts[:extract_mode] = true }
  p.on('--extract-tol F', Float) { |v| opts[:extract_tol] = v }
end.parse!
abort('missing --workdir') unless opts[:dir]

plan_path = File.join(opts[:dir], 'parity-plan.json')

def parse_spec(body)
  JSON.parse(body)
rescue JSON::ParserError
  require 'yaml'
  require 'date'
  YAML.safe_load(body, permitted_classes: [Date, Time]) || {}
end

# Resolve the (dim, val) columns for a chart element, by kind. Returns
# [[dim_id, dim_name], [val_id, val_name]] (dim pair nil for KPI) or nil if not
# plannable. The IDs matter: sigma-mcp-v2 workbook queries resolve COLUMN IDS, not
# display labels — SQL emitted against display names fails to resolve.
def chart_columns(el)
  cols = el['columns'] || []
  by_id = cols.each_with_object({}) { |c, h| h[c['id']] = c['name'] }
  case el['kind']
  when 'kpi-chart'
    vid = el.dig('value', 'columnId') || el.dig('value', 'id')
    by_id[vid] && [nil, [vid, by_id[vid]]]
  when 'pie-chart', 'donut-chart'
    did = el.dig('color', 'id') || el.dig('color', 'columnId')
    vid = el.dig('value', 'id') || el.dig('value', 'columnId')
    by_id[did] && by_id[vid] ? [[did, by_id[did]], [vid, by_id[vid]]] : nil
  else # bar-chart, line-chart, area-chart, combo-chart, scatter-chart, ...
    did = el.dig('xAxis', 'columnId')
    vid = Array(el.dig('yAxis', 'columnIds')).first
    vid = vid['columnId'] if vid.is_a?(Hash) # combo dual-axis object form
    by_id[did] && by_id[vid] ? [[did, by_id[did]], [vid, by_id[vid]]] : nil
  end
end

if !opts[:finalize]
  abort('--workbook-id required for pass 1') unless opts[:wb]
  $LOAD_PATH.unshift File.expand_path('lib', __dir__)
  require 'sigma_rest'

  warn "Parity PASS 1: reading workbook spec #{opts[:wb]}"
  # binary:true returns the raw body — the spec endpoint answers in YAML even
  # when asked for JSON, so parse both.
  raw = Sigma.request(:get, "/v2/workbooks/#{opts[:wb]}/spec", binary: true)
  spec = parse_spec(raw)
  File.write(File.join(opts[:dir], 'wb-readback.json'), JSON.pretty_generate(spec))

  charts = []
  Array(spec['pages']).each do |page|
    Array(page['elements']).each do |el|
      next unless el['kind'].to_s.end_with?('-chart')
      pairs = chart_columns(el)
      next unless pairs
      charts << { 'chart' => el['name'], 'sigma_element_id' => el['id'],
                  'kind' => el['kind'],
                  'sigma_columns' => pairs.compact.map { |id_name| id_name[1] },
                  'sigma_column_ids' => pairs.compact.map { |id_name| id_name[0] },
                  'workbook_id' => opts[:wb] }
    end
  end
  abort('no plannable chart elements found in the workbook spec') if charts.empty?

  File.write(plan_path, JSON.pretty_generate({ 'charts' => charts }))

  puts ''
  puts '=' * 70
  puts 'PARITY PASS 1 — fetch ACTUAL (Sigma) and EXPECTED (Looker/warehouse)'
  puts '=' * 70
  puts ''
  puts 'For each chart: run the mcp__sigma-mcp-v2__query below for the Sigma'
  puts 'ACTUAL rows, and fetch the EXPECTED rows from Looker via'
  puts 'POST /queries/run/json (the tile\'s model/explore/fields — ground'
  puts 'truth) or, offline, by re-aggregating the master element\'s warehouse'
  puts 'rows per the SOURCE LookML measure definitions.'
  puts '(scripts/migrate-looker.py automates BOTH sides of this fetch.)'
  puts 'Write both files, then re-run with --finalize:'
  puts "  #{opts[:dir]}/parity-expected.json  { \"<chart>\": [[dim, val], ...] }"
  puts "  #{opts[:dir]}/parity-actuals.json   { \"<chart>\": [[dim, val], ...] }"
  puts 'KPI charts: a single row [[null, <value>]].'
  puts ''
  charts.each_with_index do |c, i|
    # Query by COLUMN ID (sigma-mcp-v2 can't resolve display labels in workbook
    # queries); the display names ride along in a trailing SQL comment for readability.
    ids = c['sigma_column_ids']
    names = c['sigma_columns']
    sql = if ids.length >= 2
            %(SELECT "#{ids[0]}" AS dim, "#{ids[1]}" AS val FROM "workbook"."#{c['sigma_element_id']}" ORDER BY dim NULLS FIRST -- dim: #{names[0]}, val: #{names[1]})
          else
            %(SELECT "#{ids[0]}" AS val FROM "workbook"."#{c['sigma_element_id']}" -- val: #{names[0]})
          end
    puts "  [#{i + 1}/#{charts.length}] #{c['chart']} (#{c['kind']})"
    puts "    mcp__sigma-mcp-v2__query  type=workbook  workbookId=#{opts[:wb]}"
    puts "    sql=#{sql.inspect}"
    puts ''
  end
  puts '=' * 70
  exit 0
end

# PASS 2 — finalize
abort("plan not found at #{plan_path}; run pass 1 first") unless File.exist?(plan_path)
opts[:expected] ||= File.join(opts[:dir], 'parity-expected.json')
opts[:actuals]  ||= File.join(opts[:dir], 'parity-actuals.json')
abort("expected file missing: #{opts[:expected]}") unless File.exist?(opts[:expected])
abort("actuals file missing: #{opts[:actuals]}")   unless File.exist?(opts[:actuals])

plan = JSON.parse(File.read(plan_path))
expected = JSON.parse(File.read(opts[:expected]))
actuals  = JSON.parse(File.read(opts[:actuals]))

warn "Parity PASS 2: injecting expected (#{expected.size}) + actuals (#{actuals.size}) → #{plan_path}"
plan['charts'].each do |c|
  c['expected'] = expected[c['chart']] if expected[c['chart']]
  c['actual']   = { 'rows' => actuals[c['chart']] } if actuals[c['chart']]
end
File.write(plan_path, JSON.pretty_generate(plan))

missing = plan['charts'].reject { |c| c['expected'] && c['actual'] }
missing.each { |c| warn "WARN: no expected/actual rows supplied for #{c['chart'].inspect} — it will DIVERGE" }

warn "Parity PASS 2: running verifier (#{opts[:extract_mode] ? 'extract-mode' : 'strict'})"
verifier_args = ['ruby', File.join(__dir__, 'verify-parity.rb'), '--plan', plan_path]
verifier_args.concat(['--extract-mode', '--extract-tol', opts[:extract_tol].to_s]) if opts[:extract_mode]
out, err, status = Open3.capture3(*verifier_args)
puts out
warn err unless err.empty?
File.write(File.join(opts[:dir], 'parity-final.txt'), out)

# Hard-gate sentinel consumed by assert-phase6-ran.rb (same contract as the
# tableau-to-sigma Phase 6 sentinel — see beads-sigma-4pm for why it exists).
total  = plan['charts'].size
passed = out.scan(/^PASS\s+\[[^\]]+\]\s+(.+)$/).flatten.map(&:strip)
failed = out.scan(/^DIVERGE\s+\[[^\]]+\]\s+(.+)$/).flatten.map(&:strip)
summary = {
  'workbook_id'  => plan.dig('charts', 0, 'workbook_id'),
  'ran_at'       => Time.now.utc.iso8601,
  'mode'         => opts[:extract_mode] ? 'extract' : 'strict',
  'extract_tol'  => opts[:extract_mode] ? opts[:extract_tol] : nil,
  'charts_total' => total,
  'charts_pass'  => passed.size,
  'charts_fail'  => failed.size,
  'pass_names'   => passed,
  'fail_names'   => failed,
  'status'       => (status.success? && total > 0 && passed.size == total) ? 'PASS' : 'FAIL'
}
summary_path = File.join(opts[:dir], 'parity-final.json')
File.write(summary_path, JSON.pretty_generate(summary))
warn "wrote #{summary_path} (status=#{summary['status']} #{summary['charts_pass']}/#{summary['charts_total']})"
exit(status.success? ? 0 : 2)
