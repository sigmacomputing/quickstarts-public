#!/usr/bin/env ruby
# frozen_string_literal: true
#
# probe-controls.rb — live flip test proving a workbook's controls actually
# filter what they claim to. OPTIONAL Phase 6 step (not the mandatory inner
# loop): run it after the control lint (gate 7) passes when you want runtime
# evidence, after repairing control wiring on a live workbook, or whenever a
# control's reach was wired by hand.
#
# SHARED script, vendored byte-identical into every covered plugin's scripts/
# (md5 discipline — same as scripts/lib/control_lint.rb, which it reuses).
#
# What it does, per control:
#   1. computes the control's reach (filter targets + [controlId] formula
#      references, expanded through source.elementId chains —
#      ControlLint.controls_report)
#   2. exports one IN-closure queryable element as CSV twice via
#      POST /v2/workbooks/{id}/export — once with no `parameters` (the saved
#      control defaults) and once with parameters:{<controlId>: <flip value>}.
#      The two CSVs MUST differ, or the control is wired but inert -> FAIL.
#   3. with --check-out-of-closure: also exports one same-page queryable
#      element OUTSIDE the closure with and without the parameter — those
#      MUST be identical (the flip must not leak) -> FAIL if they differ
#      (the closure walk missed an edge; fix control_lint, not the workbook).
#
# Flip-value selection ("first non-default value"):
#   --value <controlId>=<value> beats everything (repeatable).
#   Otherwise: the control's value-source column (source.columnId, falling
#   back to the first filter target's columnId) is resolved to its display
#   label via GET /v2/workbooks/{id}/columns, that element is exported once,
#   and the first distinct value of that column NOT in the control's saved
#   defaults (`values`) is used. switch controls flip true<->false. Controls
#   whose value cannot be auto-picked (date ranges, numeric sliders, missing
#   labels) are SKIPped with a NOTE — pass --value for those.
#
# MCP / export-API note (verified empirically 2026-06-12 on tj-wells-1989):
# the Sigma MCP query path (mcp__sigma-mcp-v2__query / claude.ai Sigma MCP)
# evaluates workbook elements WITH the saved control defaults applied and
# exposes NO parameter mechanism to set a control value. The REST export API
# (POST /v2/workbooks/{id}/export with "parameters": {"<controlId>": "<val>"})
# is the ONLY programmatic way to exercise a non-default control value —
# which is why this probe is built on export, not MCP. (MCP is still fine for
# default-state parity checks — Phase 6 uses it for exactly that.)
#
# Usage:
#   ruby scripts/probe-controls.rb --workbook-id <id> \
#     [--control <controlId>]        # probe just one control (repeatable)
#     [--value <controlId>=<value>]  # explicit flip value (repeatable)
#     [--check-out-of-closure]       # also assert the flip does NOT leak
#     [--out DIR]                    # CSV evidence dir (default /tmp/probe-controls-<id>)
#     [--timeout SECS]               # export poll timeout per CSV (default 90)
#
# Exit codes: 0 = every probed control flips correctly (skips allowed);
#             1 = at least one FAIL; 2 = no control could be probed at all.
require 'json'
require 'csv'
require 'optparse'
require 'net/http'
require 'uri'
require 'fileutils'

$LOAD_PATH.unshift File.expand_path('lib', __dir__)
require 'sigma_rest'
require 'control_lint'

opts = { values: {}, controls: [], timeout: 90 }
OptionParser.new do |p|
  p.on('--workbook-id ID')        { |v| opts[:wb] = v }
  p.on('--control CID')           { |v| opts[:controls] << v }
  p.on('--value SPEC', '<controlId>=<value>') do |v|
    cid, val = v.split('=', 2)
    abort "bad --value #{v.inspect} (want <controlId>=<value>)" unless cid && val
    opts[:values][cid] = val
  end
  p.on('--check-out-of-closure')  { opts[:check_out] = true }
  p.on('--out DIR')               { |v| opts[:out] = v }
  p.on('--timeout SECS', Integer) { |v| opts[:timeout] = v }
end.parse!
abort('--workbook-id required') unless opts[:wb]
WB = opts[:wb]
OUT = opts[:out] || "/tmp/probe-controls-#{WB}"
FileUtils.mkdir_p(OUT)

# --- Sigma plumbing ---------------------------------------------------------

def fetch_spec(wb)
  body = Sigma.request(:get, "/v2/workbooks/#{wb}/spec", accept: 'application/json')
  return body if body.is_a?(Hash)
  require 'yaml'
  require 'date'
  YAML.safe_load(body.to_s, permitted_classes: [Date, Time]) || {}
end

# Export an element as CSV (optionally with control parameters), poll the
# query download until ready, return the CSV text. Raises on timeout/error.
def export_csv(wb, element_id, params, timeout)
  body = { 'elementId' => element_id, 'format' => { 'type' => 'csv' } }
  body['parameters'] = params if params && !params.empty?
  res = Sigma.request(:post, "/v2/workbooks/#{wb}/export", body: JSON.generate(body))
  qid = res.is_a?(Hash) && res['queryId']
  raise "export request failed: #{res.inspect}" unless qid
  deadline = Time.now + timeout
  loop do
    uri = URI("#{Sigma.base_url}/v2/query/#{qid}/download")
    req = Net::HTTP::Get.new(uri)
    req['Authorization'] = "Bearer #{Sigma.auth_token}"
    r = Net::HTTP.start(uri.host, uri.port, use_ssl: true, read_timeout: 60) { |h| h.request(req) }
    return r.body if r.code.to_i == 200
    raise "export download failed: HTTP #{r.code} #{r.body.to_s[0, 300]}" if r.code.to_i >= 400 && r.code.to_i != 404
    raise "export timed out after #{timeout}s (queryId=#{qid})" if Time.now > deadline
    sleep 2
  end
end

# Row-order-insensitive CSV signature (filters change row SETS; ordering noise
# must not mask or fake a flip).
def csv_sig(text)
  text.to_s.lines.map(&:chomp).sort
end

# --- reach + element metadata ------------------------------------------------

spec  = fetch_spec(WB)
elems = ControlLint.elements(spec)
rows  = ControlLint.controls_report(spec)
rows.select! { |r| opts[:controls].include?(r[:control_id]) } if opts[:controls].any?
abort "no controls found in workbook #{WB}#{opts[:controls].any? ? " matching #{opts[:controls].inspect}" : ''}" if rows.empty?

cols = Sigma.request(:get, "/v2/workbooks/#{WB}/columns")
col_label = {} # [elementId, columnId] -> display label
(cols && cols['entries'] || []).each do |c|
  col_label[[c['elementId'], c['columnId']]] = c['label'] if c['elementId'] && c['columnId']
end

baseline_cache = {}
get_baseline = lambda do |eid|
  baseline_cache[eid] ||= export_csv(WB, eid, nil, opts[:timeout])
end

# Pick the flip value for a control (returns [value, note] — value nil = skip).
pick_value = lambda do |r|
  el = elems[r[:control_element_id]][:el]
  cid = r[:control_id]
  return [opts[:values][cid], 'explicit --value'] if opts[:values].key?(cid)
  defaults = Array(el['values']).map(&:to_s)
  case el['controlType'].to_s
  when 'switch'
    return [(defaults.first.to_s.downcase == 'true' ? 'false' : 'true'), 'switch flip']
  when 'list', 'segmented', 'text'
    src = el['source']
    src = src['source'].merge('columnId' => src['columnId']) if src.is_a?(Hash) && src['kind'] == 'source' && src['source'].is_a?(Hash)
    src = (el['filters'] || []).map { |f| f.is_a?(Hash) ? (f['source'] || {}).merge('columnId' => f['columnId']) : nil }.compact.first if !src.is_a?(Hash) || !src['columnId']
    return [nil, 'no value-source column resolvable — pass --value'] unless src.is_a?(Hash) && src['elementId'] && src['columnId']
    label = col_label[[src['elementId'], src['columnId']]]
    return [nil, "no /columns label for #{src['elementId']}/#{src['columnId']} — pass --value"] unless label
    csv = CSV.parse(get_baseline.call(src['elementId']), headers: true)
    return [nil, "column #{label.inspect} not in export of #{src['elementId']} — pass --value"] unless csv.headers.include?(label)
    distinct = csv.map { |row| row[label] }.compact.map(&:to_s).reject(&:empty?).uniq
    val = distinct.find { |v| !defaults.include?(v) }
    val ? [val, "auto-picked from #{label.inspect}"] : [nil, 'no non-default value found — pass --value']
  else
    [nil, "controlType=#{el['controlType'].inspect} has no auto flip value — pass --value"]
  end
end

# --- probe loop ----------------------------------------------------------------

failures = 0
probed = 0
results = []
rows.each do |r|
  cid = r[:control_id]
  ctl = "#{r[:name].inspect} [#{cid}]"
  if r[:reach].empty?
    results << { control: cid, result: 'FAIL', note: 'dead control — empty reach (run the control lint)' }
    failures += 1
    next
  end

  in_el = (r[:reach] & r[:page_queryable]).first ||
          r[:reach].find { |e| elems[e] && ControlLint::QUERYABLE.include?(elems[e][:kind]) }
  if in_el.nil?
    results << { control: cid, result: 'SKIP', note: 'no queryable element in closure' }
    next
  end

  val, note = pick_value.call(r)
  if val.nil?
    results << { control: cid, result: 'SKIP', note: note }
    next
  end

  probed += 1
  base = get_baseline.call(in_el)
  flip = export_csv(WB, in_el, { cid => val }, opts[:timeout])
  File.write(File.join(OUT, "#{cid}--#{in_el}--base.csv"), base)
  File.write(File.join(OUT, "#{cid}--#{in_el}--flip.csv"), flip)
  changed = csv_sig(base) != csv_sig(flip)
  if changed
    results << { control: cid, result: 'PASS', element: in_el, value: val,
                 note: "#{note}; in-closure export differs (#{base.lines.count - 1} -> #{flip.lines.count - 1} rows)" }
  else
    failures += 1
    results << { control: cid, result: 'FAIL', element: in_el, value: val,
                 note: "#{note}; in-closure export IDENTICAL with #{cid}=#{val.inspect} — control is wired but inert" }
  end

  next unless opts[:check_out]
  out_el = r[:uncovered].find { |e| elems[e] && ControlLint::QUERYABLE.include?(elems[e][:kind]) }
  if out_el.nil?
    results << { control: cid, result: 'OK', note: 'out-of-closure: none on page (full reach) — nothing to check' }
  else
    obase = get_baseline.call(out_el)
    oflip = export_csv(WB, out_el, { cid => val }, opts[:timeout])
    File.write(File.join(OUT, "#{cid}--#{out_el}--out-base.csv"), obase)
    File.write(File.join(OUT, "#{cid}--#{out_el}--out-flip.csv"), oflip)
    if csv_sig(obase) == csv_sig(oflip)
      results << { control: cid, result: 'OK', element: out_el, note: 'out-of-closure export unchanged (no leak)' }
    else
      failures += 1
      results << { control: cid, result: 'FAIL', element: out_el,
                   note: 'out-of-closure export CHANGED — the closure walk missed an edge (fix control_lint, not the workbook)' }
    end
  end
end

puts format('%-22s %-6s %-34s %s', 'CONTROL', 'RESULT', 'ELEMENT', 'NOTE')
results.each do |x|
  puts format('%-22s %-6s %-34s %s', x[:control], x[:result], x[:element] || '-', [x[:value] && "flip=#{x[:value].inspect}", x[:note]].compact.join('; '))
end
File.write(File.join(OUT, 'probe-results.json'), JSON.pretty_generate(results))
puts "evidence: #{OUT}/ (CSVs + probe-results.json)"

exit 1 if failures.positive?
exit 2 if probed.zero?
exit 0
