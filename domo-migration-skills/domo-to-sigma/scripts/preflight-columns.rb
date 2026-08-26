#!/usr/bin/env ruby
# Phase 2.9 — DM column pre-flight (bead m655). Checks every mapped dataset's
# Domo columns against the REAL warehouse table's schema (a live Sigma
# catalog lookup) before build-dm.rb (Phase 3) ever constructs dm-spec.json.
# Never auto-applies a fix — see docs/superpowers/specs/2026-07-31-domo-dm-
# column-preflight-design.md for the full design and rationale.
#
#   ruby scripts/preflight-columns.rb        # → discovery/column-preflight.json
#     exit 0 = every used dataset's Domo columns are covered (present in the
#              warehouse table, or already excludeColumns/columnOverrides'd
#              in dataset-map.json)
#     exit 1 = at least one dataset still has an unresolved column, or a live
#              fetch error — see the report for names + any auto-suggested
#              columnOverrides
#
# Requires SIGMA_BASE_URL + a Sigma bearer token (SIGMA_API_TOKEN, or
# SIGMA_CLIENT_ID/SIGMA_CLIENT_SECRET for scripts/lib/sigma_rest.rb to
# self-mint) — same credential story as put-layout.rb and post-and-readback.rb.
# Does not attempt a live call for any dataset whose dataset-map.json entry
# isn't fully resolved yet (no connectionId/table, or a domo-stream-config-
# query-only / domo-landed-data _source) — build-dm.rb's own existing
# warnings already cover those. That dataset is still RECORDED in the report
# as 'skipped' (never dropped) — see run_preflight below; a dataset that
# cannot be checked (no dataset-map.json entry, no datasets.json schema, or a
# live fetch/lookup error) is recorded as 'error' and forces exit 1, so a
# report can never again look "clean" while having covered almost nothing
# (bead m655 post-mortem: a live run's report had one key out of ten used
# datasets and still printed "clean").

require 'json'
require 'fileutils'
require 'uri'
require 'net/http'
require_relative 'lib/column_preflight'
require_relative 'lib/sigma_rest'
include ColumnPreflight

OUT = ENV['DOMO_DISCOVERY_DIR'] || File.expand_path('../discovery', __dir__)

# Network seam: connection_id + [db,schema,table] -> {'columns'=>[...],
# 'inode_id'=>...} or {'error'=>message} — NEVER raises, so run_preflight can
# degrade one dataset at a time instead of aborting the whole run. Covers not
# just Sigma::Error (a non-2xx HTTP response) but every other realistic live-
# call failure mode: malformed JSON (JSON::ParserError), a slow/cold catalog
# lookup (Net::OpenTimeout/Net::ReadTimeout/Timeout::Error), and DNS/connection
# failures (SocketError/Errno::ECONNREFUSED) — matching the rescue set already
# used elsewhere in this plugin (scripts/verify-anchors.rb) and by Tableau's
# sibling scripts/discover-columns.rb.
# `requester`/`lister` are injected (default: the real Sigma.request /
# Sigma.list_entries) so test/test-preflight-columns.rb can stub Sigma
# entirely, mirroring build-dm.rb's fetcher: seam for autofill_dataset_map.
def fetch_warehouse_columns(connection_id, path, requester: nil, lister: nil)
  # Bound every live call — a cold warehouse or a very wide view can otherwise
  # leave a catalog lookup blocked with no client-side cap (the "migration
  # stuck for hours" hang Tableau's sibling discover-columns.rb guards
  # against the same way). Only applies to the REAL default requester/lister
  # — tests inject their own stubs directly and bypass this entirely. Compute
  # timeout/uri lazily, ONLY when a default is actually needed: every existing
  # test passes its own requester:/lister: stubs and must keep working with no
  # SIGMA_BASE_URL set at all (Sigma.base_url raises when it's unset).
  if requester.nil? || lister.nil?
    timeout = (ENV['SIGMA_HTTP_TIMEOUT'] || '90').to_i
    uri = URI(Sigma.base_url)
  end
  requester ||= lambda do |method, p, body: nil|
    Net::HTTP.start(uri.host, uri.port, use_ssl: true,
                    open_timeout: [timeout, 30].min, read_timeout: timeout) do |http|
      Sigma.request(method, p, body: body, http: http)
    end
  end
  lister ||= lambda do |p|
    Net::HTTP.start(uri.host, uri.port, use_ssl: true,
                    open_timeout: [timeout, 30].min, read_timeout: timeout) do |http|
      Sigma.list_entries(p, http: http)
    end
  end
  # 1. Resolve the table to an inodeId. NOT GET /v2/connections/{conn}/tables
  #    — that endpoint does not exist (feedback_sigma_columns_api_endpoint).
  lookup = requester.call(:post, "/v2/connection/#{connection_id}/lookup",
                          body: JSON.generate('path' => path))
  inode = lookup.is_a?(Hash) ? lookup['inodeId'] : nil
  return { 'error' => "lookup returned no inodeId: #{lookup.inspect}" } unless inode
  unless lookup['kind'] == 'table'
    return { 'error' => "#{path.join('.')} resolved to a #{lookup['kind']}, not a table" }
  end

  # 2. List columns at /v2/connections/tables/<inodeId>/columns — connectionId
  #    is NOT in this path. Paginated; Sigma.list_entries follows nextPage to
  #    exhaustion (server default page size is 50 — an unpaginated read would
  #    silently truncate a wide table).
  entries = lister.call("/v2/connections/tables/#{inode}/columns")
  cols = entries.map do |c|
    t = c['type']
    t = t['type'] if t.is_a?(Hash) && t['type'] # type may arrive nested
    { 'name' => c['name'], 'type' => t.to_s }
  end
  { 'columns' => cols, 'inode_id' => inode }
rescue Sigma::Error => e
  # Match only the status-code position on the FIRST line (sigma_rest.rb's
  # request raises "#{METHOD} #{path} -> #{code} #{message}\n#{body}") — not
  # anywhere in the full message+body. A bare /\b404\b/ over the whole string
  # would false-positive on a genuine 500/401/403 whose JSON error body
  # happens to contain a stray "404" token (a nested error code, a referenced
  # upstream status, an unrelated ID) and mislabel it with the 404-specific
  # "sync it first" guidance instead of the real error.
  if e.message.lines.first.to_s =~ /-> 404\b/
    { 'error' => "table #{path.join('.')} not found in Sigma's catalog for connection " \
                 "#{connection_id} — sync it first: POST /v2/connections/#{connection_id}/sync " \
                 "with body {\"path\": #{JSON.generate(path)}}, then re-run." }
  else
    { 'error' => "Sigma error resolving #{path.join('.')}: #{e.message.lines.first.to_s.strip}" }
  end
rescue JSON::ParserError => e
  { 'error' => "Sigma returned malformed JSON resolving #{path.join('.')}: #{e.message}" }
rescue Net::OpenTimeout, Net::ReadTimeout, Timeout::Error => e
  { 'error' => "timeout resolving #{path.join('.')} (#{e.class}) — the warehouse catalog lookup did not return in time" }
rescue SocketError, Errno::ECONNREFUSED => e
  { 'error' => "network error resolving #{path.join('.')}: #{e.class}: #{e.message}" }
end

# Runs the full pre-flight over every used dataset. Pure orchestration —
# `fetcher` is the sole network seam (default: fetch_warehouse_columns above),
# so this is fully unit-testable offline (test/test-preflight-columns.rb
# stubs it as a whole function, bypassing Sigma entirely).
#
# datasets: discovery/datasets.json, parsed ([{'id','schema'=>{'columns'=>[...]}}]).
# ds_map:   discovery/dataset-map.json, parsed ({datasetId => {...}}).
# used:     dataset ids actually in scope (cards.json datasetIds, or every
#           discovered dataset if cards.json is empty/absent — mirrors
#           build-dm.rb's own `used` derivation).
#
# Returns [report, any_missing]. report is keyed by EVERY id in `used` — no
# id is ever dropped, on pain of repeating the exact false-clean this
# function exists to prevent (bead m655 post-mortem: a real cold run's
# report.json ended up with exactly ONE key out of 10 used datasets, all 9
# silently `next`-ed past, yet the run printed "clean"). Every entry has
# EXACTLY ONE of:
#   'missing'/'resolved_by_exclude'/'resolved_by_override'/'suggested_overrides'
#                 — actually diffed against a live warehouse-column fetch.
#   'skipped'     — legitimately not checkable yet (a SENTINEL_SOURCES entry,
#                   or connectionId/table not yet filled in) — NOT a failure;
#                   build-dm.rb's own "needs human review" warning covers it,
#                   and this key is deliberately NOT 'error' so build-dm.rb's
#                   preflight-report gate (`v['error']`) does not block on it.
#   'error'       — could not be checked at all (no dataset-map.json entry,
#                   no datasets.json schema for this id, a malformed schema,
#                   or a live fetch failure) — this DOES set any_missing, so
#                   an unchecked dataset can never be reported clean.
# any_missing is a Boolean (true if any dataset has an 'error', or a checked
# dataset still has a non-empty 'missing').
def run_preflight(datasets, ds_map, used, fetcher: method(:fetch_warehouse_columns))
  ds_by_id = datasets.each_with_object({}) { |d, h| h[d['id']] = d }
  report = {}
  any_missing = false
  used.each do |id|
    entry = ds_map[id]
    ds = ds_by_id[id]
    if entry.nil?
      report[id] = { 'error' => 'no discovery/dataset-map.json entry for this dataset id — ' \
                                 'cannot be checked' }
      any_missing = true
      next
    end
    if ds.nil?
      report[id] = { 'table' => entry['table'], 'error' => 'no discovery/datasets.json entry (missing ' \
                                 'schema) for this dataset id — cannot be checked; re-run ' \
                                 'domo-discover.rb' }
      any_missing = true
      next
    end
    if ColumnPreflight::SENTINEL_SOURCES.include?(entry['_source'])
      report[id] = { 'table' => entry['table'],
                      'skipped' => "_source is #{entry['_source']} — no warehouse table to check yet" }
      next
    end
    if entry['connectionId'].to_s.strip.empty? || entry['table'].to_s.strip.empty?
      report[id] = { 'table' => entry['table'],
                      'skipped' => 'connectionId/table not yet resolved in dataset-map.json' }
      next
    end
    schema_cols = ds.dig('schema', 'columns')
    unless schema_cols.is_a?(Array) # build-dm.rb's own ArgumentError already covers this too
      report[id] = { 'table' => entry['table'], 'error' => 'datasets.json has no schema.columns array ' \
                                 'for this dataset id — cannot be checked' }
      any_missing = true
      next
    end

    path = [entry['database'], entry['schema'], entry['table']].compact
    fetched = fetcher.call(entry['connectionId'], path)
    if fetched['error']
      report[id] = { 'table' => entry['table'], 'error' => fetched['error'] }
      any_missing = true
      next
    end

    excluded  = Array(entry['excludeColumns']).map { |s| s.to_s.upcase }
    overrides = (entry['columnOverrides'] || {}).each_with_object({}) { |(k, v), h| h[k.to_s.upcase] = v }
    entry_report = build_report_entry(entry['table'], schema_cols, fetched['columns'], excluded, overrides)
    report[id] = entry_report
    any_missing ||= !entry_report['missing'].empty?
  end
  [report, any_missing]
end

# Turns a report Hash (run_preflight's first return value) into honest counts
# for the summary line — so "clean" can never again mean "checked almost
# nothing" (the exact vacuous-pass bead m655 post-mortem found: a report with
# one key printed "clean — every used dataset's Domo columns are covered").
# Every report value has exactly one of 'missing' (a checked entry, key
# always present even when the diff found nothing), 'skipped', or 'error' —
# see run_preflight — so these three counts always add up to report.size.
def summarize_report(report)
  {
    'checked' => report.values.count { |v| v.key?('missing') },
    'skipped' => report.values.count { |v| v.key?('skipped') },
    'errored' => report.values.count { |v| v.key?('error') },
  }
end

if $PROGRAM_NAME == __FILE__
  datasets = JSON.parse(File.read(File.join(OUT, 'datasets.json'))) rescue []
  map_path = File.join(OUT, 'dataset-map.json')
  unless File.exist?(map_path)
    abort "  preflight-columns.rb: no discovery/dataset-map.json — run build-dm.rb once first " \
          '(it writes dataset-map.template.json for you to fill in), then re-run this.'
  end
  ds_map = JSON.parse(File.read(map_path))
  cards  = JSON.parse(File.read(File.join(OUT, 'cards.json'))) rescue []
  used = cards.map { |c| c['datasetId'] }.compact.uniq
  used = datasets.map { |d| d['id'] }.compact if used.empty?

  report, any_missing = run_preflight(datasets, ds_map, used)
  counts = summarize_report(report)
  summary = "#{counts['checked']} checked, #{counts['skipped']} skipped, #{counts['errored']} errored " \
            "(#{used.size} used dataset(s) total)"

  FileUtils.mkdir_p(OUT)
  File.write(File.join(OUT, 'column-preflight.json'), JSON.pretty_generate(report))
  if any_missing
    warn "\n  preflight-columns.rb: unresolved column(s) or fetch/lookup error(s) — #{summary}. See " \
         'discovery/column-preflight.json for names + any auto-suggested columnOverrides. ' \
         'Resolve via excludeColumns/columnOverrides in dataset-map.json (or fix the named ' \
         'connection/table issue), then re-run.'
    exit 1
  else
    skip_note = counts['skipped'].positive? ? " (#{counts['skipped']} skipped dataset(s) were NOT " \
                                               'checked — see discovery/column-preflight.json)' : ''
    warn "  preflight-columns.rb: clean — #{summary}. Every CHECKED dataset's Domo columns are " \
         "covered#{skip_note}."
    exit 0
  end
end
