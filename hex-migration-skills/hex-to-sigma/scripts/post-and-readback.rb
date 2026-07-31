#!/usr/bin/env ruby
# frozen_string_literal: true
#
# POST a Sigma data-model or workbook spec (from convert_dm.py / convert_workbook.py),
# read it back, and run the mandatory hard gates before declaring anything done.
# Pattern ported from the quicksight-to-sigma / powerbi-to-sigma / tableau-to-sigma
# post-and-readback.rb scripts — this script has no source-tool-specific logic in
# it (confirmed while researching this skill: those three are near-identical), so
# it's reused near-verbatim rather than reinvented.
#
# Usage:
#   eval "$(python3 scripts/get_token.py --print-export)"
#   ruby scripts/post-and-readback.rb --type datamodel --spec dm.json --out dm-map.json
#   ruby scripts/post-and-readback.rb --type workbook  --spec wb.json --out wb-map.json

require 'net/http'
require 'uri'
require 'json'
require 'yaml'
require 'date'
require 'time'
require 'optparse'
require 'fileutils'

opts = {}
OptionParser.new do |p|
  p.on('--type T', %w[datamodel workbook]) { |v| opts[:type] = v }
  p.on('--spec P')    { |v| opts[:spec] = v }
  p.on('--out P')     { |v| opts[:out]  = v }
  p.on('--workdir P', 'Per-conversion working dir (default: dir of --spec).') { |v| opts[:workdir] = v }
  p.on('--skip-layout-lint') { opts[:skip_lint] = true }
  p.on('--update-id ID', 'PUT the spec to this existing id instead of POSTing new (retry-safe).') { |v| opts[:update_id] = v }
end.parse!
%i[type spec out].each { |k| abort("missing --#{k}") unless opts[k] }
opts[:workdir] ||= File.dirname(File.expand_path(opts[:spec]))
FileUtils.mkdir_p(opts[:workdir])

$LOAD_PATH.unshift File.expand_path('lib', __dir__)
require 'sigma_rest'

POST_PATH = opts[:type] == 'datamodel' ? '/v2/dataModels/spec'    : '/v2/workbooks/spec'
GET_PATH  = opts[:type] == 'datamodel' ? '/v2/dataModels/%s/spec' : '/v2/workbooks/%s/spec'
ID_FIELD  = opts[:type] == 'datamodel' ? 'dataModelId'            : 'workbookId'

# convert_dm.py / convert_workbook.py emit {"dataModel"|"workbook": <spec>, "warnings": [...], "stats": {...}}
# — unwrap to the bare spec before POSTing.
raw = JSON.parse(File.read(opts[:spec]))
spec = raw['dataModel'] || raw['workbook'] || raw

# Orphan-prevention: workbook POSTs are create-only. Track ids posted in this
# conversion so a re-run PUTs (updates) instead of orphaning a prior attempt.
posted_log = File.join(opts[:workdir], 'posted-workbooks.jsonl') if opts[:type] == 'workbook'
prior_ids = []
if posted_log && File.exist?(posted_log)
  prior_ids = File.readlines(posted_log).filter_map { |l| JSON.parse(l)['id'] rescue nil }
end
update_id = opts[:update_id] || (prior_ids.last if opts[:type] == 'workbook' && prior_ids.any?)

if update_id
  warn "UPDATE mode: PUT #{opts[:type]} #{update_id} (no new #{opts[:type]} created)"
  resp = Sigma.request(:put, format(GET_PATH, update_id), body: spec.to_json)
  oid = resp[ID_FIELD] || update_id
  warn "PUT ok: #{ID_FIELD}=#{oid}"
else
  resp = Sigma.request(:post, POST_PATH, body: spec.to_json)
  oid = resp[ID_FIELD] or abort("POST failed: #{resp.inspect}")
  warn "POST ok: #{ID_FIELD}=#{oid}"
  if posted_log
    File.open(posted_log, 'a') { |f| f.puts(JSON.generate({ 'id' => oid, 'ran_at' => Time.now.utc.iso8601 })) }
  end
end

# Read back the spec with server-assigned ids.
readback = Sigma.request(:get, format(GET_PATH, oid))

out = {
  ID_FIELD => oid,
  'pages' => (readback['pages'] || []).map do |p|
    {
      'id' => p['id'], 'name' => p['name'],
      'elements' => (p['elements'] || []).map { |e| { 'id' => e['id'], 'kind' => e['kind'], 'name' => e['name'] } }
    }
  end
}
File.write(opts[:out], JSON.pretty_generate(out))
puts JSON.pretty_generate(out)

# Universal silent-error guard (same as every sibling skill): scan every
# column's resolved type via /columns and fail loudly on type == "error" —
# a formula that compiles at POST but fails at query time.
columns_path = opts[:type] == 'datamodel' ? "/v2/dataModels/#{oid}/columns" : "/v2/workbooks/#{oid}/columns"
cols = Sigma.request(:get, columns_path) rescue nil
if cols
  error_columns = (cols['entries'] || []).select { |c| c.dig('type', 'type') == 'error' }
  if error_columns.any?
    warn "\n========================================"
    warn "FAIL — #{error_columns.size} column(s) compiled to type \"error\":"
    error_columns.each { |c| warn "  [element=#{c['elementId']}] #{c['label']} (#{c['columnId']}): #{c['formula']}" }
    warn 'Common cause for this skill: the [Custom SQL/<column>] source-prefix assumption'
    warn '(see converter/convert_workbook.py module docstring) didn\'t match what Sigma'
    warn 'actually assigned this element — read back the DM element\'s real column labels'
    warn 'and fix the formula prefix.'
    warn '========================================'
    exit(2)
  end
  warn "column-type guard: #{(cols['entries'] || []).size} columns clean (no `error` types)"
else
  warn 'WARN: could not fetch /columns for the type guard — skipping'
end

# Layout-quality lint (vendored byte-identical from shared/lib/layout_lint.rb).
if opts[:type] == 'workbook' && !opts[:skip_lint]
  require_relative 'lib/layout_lint'
  violations = LayoutLint.lint(readback)
  if violations.any?
    warn "\n========================================"
    warn "FAIL — layout lint: #{violations.size} violation(s):"
    violations.each { |v| warn "  - #{v}" }
    warn 'The workbook DID post — fix with PUT /v2/workbooks/<id>/spec (re-POSTing orphans it).'
    warn '========================================'
    exit(3)
  end
  warn 'layout lint: clean'
end

if opts[:type] == 'workbook'
  warn ''
  warn '================================================================'
  warn 'NEXT STEP (MANDATORY): verify data parity vs the Hex source'
  warn '================================================================'
  warn 'Column-type guard passing means formulas RESOLVE — it does NOT mean'
  warn 'the numbers match. Re-run the SQL cell'"'"'s query directly against the'
  warn 'shared warehouse and diff against each element'"'"'s Sigma value, then:'
  warn "  ruby scripts/assert-phase6-ran.rb --workdir #{opts[:workdir]} --workbook-id #{oid}"
  warn '================================================================'
end
