#!/usr/bin/env ruby
# Unit tests for build-dm.rb helpers (display_name, build_element). No network.
#   ruby test/test-build-dm.rb

require_relative '../scripts/build-dm'

$failures = 0
def eq(a, b, m) if a == b then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}\n    exp #{b.inspect}\n    got #{a.inspect}" end end

puts "== display_name (fixes raw snake_case labels) =="
eq(display_name('order_date'), 'Order Date', 'snake_case → Title Case')
eq(display_name('OrderDate'),  'Order Date', 'camelCase → Title Case')
eq(display_name('project_id'), 'Project Id', 'project_id → Project Id')
eq(display_name('FY2024'),     'FY 2024',    'letter/digit boundary')
eq(display_name('HTMLParser'), 'HTML Parser','acronym boundary')
eq(display_name(display_name('order_date')), 'Order Date', 'idempotent (case-safe sibling refs)')

puts "== build_element =="
ds = { 'id' => 'ds-1', 'name' => 'Orders',
       'schema' => { 'columns' => [
         { 'name' => 'project_id', 'type' => 'STRING' },
         { 'name' => 'sales_amount', 'type' => 'DECIMAL' },
         { 'name' => 'order_date', 'type' => 'DATE' } ] } }
map = { 'connectionId' => 'conn-1', 'database' => 'DB', 'schema' => 'SCH', 'table' => 'ORDERS' }
proj = [{ 'name' => 'full_region', 'sigmaFormula' => 'Concat([City], ", ", [State])', 'class' => 'projection' }]
el = build_element(ds, map, proj)

eq(el['kind'], 'table', 'element kind table')
eq(el['source'], { 'connectionId' => 'conn-1', 'kind' => 'warehouse-table', 'path' => %w[DB SCH ORDERS] }, 'warehouse-table source path')
eq(el['columns'][0]['formula'], '[ORDERS/Project Id]', 'base column formula uses table-prefixed display name')
# A Sigma column `format` keys on **kind**, never `type`, and there is no `date`
# kind — `datetime` + formatString covers it. This assertion previously encoded
# the bug ({'type' => 'date'}), which Sigma rejects outright:
#   POST /v2/dataModels/spec ->
#   "pages[0].elements[0].columns[8].format: Missing \"kind\" field"
# so ANY source DATE column failed the whole data-model POST (live-validated
# 2026-07-30; see refs/live-validation-2026-07-30.md).
eq(el['columns'][2]['format'], { 'kind' => 'datetime', 'formatString' => '%Y-%m-%d' },
   'date column format uses kind:datetime (never type:date — Sigma rejects that)')
calc = el['columns'].find { |c| c['name'] == 'Full Region' }
eq(!calc.nil?, true, 'projection Beast Mode added as DM calc column')
eq(calc['formula'], 'Concat([City], ", ", [State])', 'calc column carries translated sigmaFormula')
eq(el['order'].size, el['columns'].size, 'order lists every column')

puts "== connection-id placeholder when unmapped =="
el2 = build_element(ds, {}, [])
eq(el2['source']['connectionId'], '<CONNECTION_ID>', 'unmapped → placeholder connectionId (flagged, not guessed)')

# ---------------------------------------------------------------------------
# Task 1 (2026-07-30 live validation): auto-fill dataset-map.json from Domo's
# connector stream configuration. All offline — no credentials, no network;
# fetch_stream_config itself is never called here, only the pure helpers and
# autofill_dataset_map with a stubbed `fetcher:`.

puts "== stream_config_hash (flatten Domo's configuration[] shape) =="
raw_conf = [
  { 'streamId' => 13, 'category' => 'STREAM', 'name' => 'databaseName', 'type' => 'string', 'value' => 'SALESDB' },
  { 'streamId' => 13, 'category' => 'STREAM', 'name' => 'schemaName',   'type' => 'string', 'value' => 'PUBLIC' },
  { 'streamId' => 13, 'category' => 'STREAM', 'name' => 'tableName',    'type' => 'string', 'value' => 'ORDERS' },
]
eq(stream_config_hash(raw_conf),
   { 'databaseName' => 'SALESDB', 'schemaName' => 'PUBLIC', 'tableName' => 'ORDERS' },
   'configuration[] flattened to a name=>value Hash')
eq(stream_config_hash(nil), {}, 'nil configuration -> {} (never raises)')

puts "== derive_map_entry: connector-backed DataSet (real table) =="
ds_conn = { 'id' => 'ds-conn', 'name' => 'Orders Feed' }
conf_table = { 'databaseName' => 'SALESDB', 'schemaName' => 'PUBLIC', 'tableName' => 'ORDERS' }
entry_conn = derive_map_entry(ds_conn, conf_table)
eq(entry_conn['_source'], 'domo-stream-config', 'connector-backed -> domo-stream-config')
eq(entry_conn['database'], 'SALESDB', 'database derived from stream config')
eq(entry_conn['schema'],   'PUBLIC',  'schema derived from stream config')
eq(entry_conn['table'],    'ORDERS',  'table derived from stream config')
eq(entry_conn['connectionId'], '', 'connectionId NEVER derived — stays blank even for a connector-backed DataSet')

puts "== derive_map_entry: query-only (custom-SQL report) stream — no table guessed =="
conf_query = { 'databaseName' => 'SALESDB', 'schemaName' => 'PUBLIC', 'query' => 'SELECT * FROM v_orders_report' }
entry_query = derive_map_entry(ds_conn, conf_query)
eq(entry_query['_source'], 'domo-stream-config-query-only', 'query-only stream flagged, not treated as a table')
eq(entry_query['table'], nil, 'no table guessed for a query-only stream')
eq(entry_query['_query'], 'SELECT * FROM v_orders_report', 'SQL recorded for human review')
eq(entry_query.key?('_note'), true, 'a human-facing note is attached')

puts "== derive_map_entry: non-connector DataSet (landed data, no warehouse source) =="
ds_landed = { 'id' => 'ds-landed', 'name' => 'Webform Upload' }
entry_landed = derive_map_entry(ds_landed, {})
eq(entry_landed['_source'], 'domo-landed-data', 'no stream config -> flagged as landed data')
eq(entry_landed['table'], nil, 'no table guessed for landed data (honest, not a bogus mapping)')
eq(entry_landed['database'], nil, 'no database guessed for landed data')

puts "== autofill_dataset_map: fills a brand-new entry via the stubbed fetcher (offline seam) =="
ds_by_id = { 'ds-conn' => ds_conn, 'ds-landed' => ds_landed }
fake_configs = { 'ds-conn' => conf_table, 'ds-landed' => {} }
stub_fetcher = ->(id) { fake_configs[id] }
merged, filled = autofill_dataset_map({}, ds_by_id, %w[ds-conn ds-landed], fetcher: stub_fetcher)
eq(filled, 2, 'both brand-new entries counted as filled')
eq(merged['ds-conn']['table'], 'ORDERS', 'ds-conn auto-filled via the stub fetcher, not real network')
eq(merged['ds-landed']['_source'], 'domo-landed-data', 'ds-landed correctly flagged, not fabricated')

puts "== autofill_dataset_map: never clobbers a complete hand-authored entry =="
hand_authored = { 'ds-conn' => { 'connectionId' => 'conn-99', 'database' => 'HANDDB',
                                 'schema' => 'HANDSCHEMA', 'table' => 'HAND_TABLE', 'name' => 'Hand Named' } }
never_called = ->(_id) { raise 'fetcher must NOT be called for a complete hand-authored entry' }
merged2, filled2 = autofill_dataset_map(hand_authored, ds_by_id, %w[ds-conn], fetcher: never_called)
eq(filled2, 0, 'complete hand-authored entry is not touched')
eq(merged2['ds-conn']['table'], 'HAND_TABLE', 'hand-authored table survives untouched')
eq(merged2['ds-conn']['database'], 'HANDDB', 'hand-authored database survives untouched')

puts "== autofill_dataset_map: fills a PARTIAL entry but preserves its connectionId =="
partial = { 'ds-conn' => { 'connectionId' => 'conn-99', 'database' => '', 'schema' => '', 'table' => '' } }
merged3, filled3 = autofill_dataset_map(partial, ds_by_id, %w[ds-conn], fetcher: stub_fetcher)
eq(filled3, 1, 'partial entry (blank table) IS re-derived')
eq(merged3['ds-conn']['table'], 'ORDERS', 'blank table auto-filled from stream config')
eq(merged3['ds-conn']['connectionId'], 'conn-99', 'human-supplied connectionId preserved — never invented, never clobbered')

puts "== placeholder_table: build_element never fabricates a table for flagged entries =="
el_query  = build_element(ds, entry_query,  [])
el_landed = build_element(ds, entry_landed, [])
eq(el_query['source']['path'].last,  '<TABLE:QUERY_ONLY_NEEDS_HUMAN>',        'query-only entry -> unmistakable sentinel, not a guessed table')
eq(el_landed['source']['path'].last, '<TABLE:LANDED_DATA_NO_WAREHOUSE_SOURCE>', 'landed-data entry -> unmistakable sentinel, not the DataSet display name')

puts
if $failures.zero? then puts "ALL PASS"; exit 0 else puts "#{$failures} FAILURE(S)"; exit 1 end
