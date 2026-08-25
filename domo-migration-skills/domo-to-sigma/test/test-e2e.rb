#!/usr/bin/env ruby
# End-to-end integration test (offline): synthetic Domo discovery →
# build-dm.rb → build-workbook.rb → qa-check.rb. Proves the deterministic pipeline
# composes and that the Phase-5e gate BOTH catches the KPI count-of-id bug and
# passes once corrected via kpi-overrides.json. (Final assembly via the reused
# build-workbook-spec.rb needs live creds, so it's out of scope here.)
#
#   ruby test/test-e2e.rb

require 'json'
require 'fileutils'
require 'tmpdir'

SKILL = File.expand_path('..', __dir__)
SCRIPTS = File.join(SKILL, 'scripts')
$failures = 0
def ok(c, m) if c then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}" end end

Dir.mktmpdir('domo-e2e') do |dir|
  # build-dm.rb enforces the Step-0 environment gate; this e2e test exercises
  # build LOGIC, not the environment, so waive it explicitly — keeps the suite
  # hermetic on a machine (e.g. CI) that never ran the doctor.
  env = { 'DOMO_DISCOVERY_DIR' => dir,
          'SIGMA_SKIP_DOCTOR_GATE' => 'e2e: environment not under test' }
  w = ->(name, obj) { File.write(File.join(dir, name), JSON.generate(obj)) }
  run = ->(script, *args) { system(env, 'ruby', File.join(SCRIPTS, script), *args, out: File::NULL, err: File::NULL) }

  # ---- synthetic discovery -------------------------------------------------
  w.call('datasets.json', [{ 'id' => 'ds1', 'name' => 'Orders', 'schema' => { 'columns' => [
    { 'name' => 'project_id', 'type' => 'STRING' }, { 'name' => 'project_name', 'type' => 'STRING' },
    { 'name' => 'region', 'type' => 'STRING' }, { 'name' => 'sales_amount', 'type' => 'DECIMAL' }] } }])
  w.call('formulas.json', [{ 'id' => 'calculation_1', 'name' => 'full_region', 'class' => 'projection',
                             'scope' => 'dataset', 'dataSourceId' => 'ds1',
                             'sigmaFormula' => 'Concat([Region], " ", [Project Name])' }])
  w.call('cards.json', [
    { 'id' => 'k1', 'title' => 'Total Sales', 'datasetId' => 'ds1', 'chartType' => 'badge_singlevalue',
      'sigmaKindHint' => 'kpi-chart', 'groupBy' => [], 'columns' => [{ 'column' => 'sales_amount', 'aggregation' => 'SUM' }],
      'summaryNumber' => { 'column' => 'sales_amount', 'aggregation' => 'SUM', 'label' => 'Total Sales',
                           'format' => { 'type' => 'CURRENCY' }, '_defaultCountSuspect' => false }, 'filters' => [] },
    { 'id' => 'b1', 'title' => 'Sales by Region', 'datasetId' => 'ds1', 'chartType' => 'badge_vert_bar',
      'sigmaKindHint' => 'bar-chart', 'groupBy' => ['region'],
      'columns' => [{ 'column' => 'region' }, { 'column' => 'sales_amount', 'aggregation' => 'SUM', 'alias' => 'Sales' }],
      'filters' => [{ 'column' => 'region', 'operator' => 'IN', 'values' => ['West'] }] },
    { 'id' => 't1', 'title' => 'Projects', 'datasetId' => 'ds1', 'chartType' => 'badge_datagrid',
      'sigmaKindHint' => 'table', 'groupBy' => [],
      'columns' => [{ 'column' => 'project_name' }, { 'column' => 'sales_amount', 'aggregation' => 'SUM' }], 'filters' => [] },
    { 'id' => 'k2', 'title' => '# Projects', 'datasetId' => 'ds1', 'chartType' => 'badge_singlevalue',
      'sigmaKindHint' => 'kpi-chart', 'groupBy' => [], 'columns' => [{ 'column' => 'project_id', 'aggregation' => 'COUNT' }],
      'summaryNumber' => { 'column' => 'project_id', 'aggregation' => 'COUNT', '_defaultCountSuspect' => true }, 'filters' => [] },
  ])
  w.call('pages.json', [{ 'id' => 'p1', 'title' => 'Overview', 'cardIds' => %w[k1 b1 t1 k2] }])
  w.call('dataset-map.json', { 'ds1' => { 'connectionId' => 'conn-1', 'database' => 'DB', 'schema' => 'SCH', 'table' => 'ORDERS' } })

  # ---- Phase 3: build-dm ---------------------------------------------------
  ok(run.call('build-dm.rb'), 'build-dm.rb ran')
  dm = JSON.parse(File.read(File.join(dir, 'dm-spec.json')))
  el = dm['pages'][0]['elements'][0]
  ok(dm['schemaVersion'] == 1, 'DM schemaVersion 1')
  ok(el['source'] == { 'connectionId' => 'conn-1', 'kind' => 'warehouse-table', 'path' => %w[DB SCH ORDERS] }, 'DM warehouse-table source')
  ok(el['columns'].any? { |c| c['formula'] == '[ORDERS/Sales Amount]' }, 'DM base column clean display name')
  ok(el['columns'].any? { |c| c['name'] == 'Full Region' }, 'DM projection Beast Mode → calc column')

  # ---- Phase 5: build-workbook (no overrides) ------------------------------
  ok(run.call('build-workbook.rb'), 'build-workbook.rb ran')
  cs = JSON.parse(File.read(File.join(dir, 'chart-specs.json')))
  ok(cs['pages'].is_a?(Array) && cs['pages'][0]['elements'], 'chart-specs shape matches build-workbook-spec input (pages[].elements)')
  els = cs['pages'][0]['elements']
  kpi = els.find { |e| e['id'] == 'el-k1' }
  ok(kpi['kind'] == 'kpi-chart' && kpi['columns'][0]['formula'] == 'Sum([Master/Sales Amount])', '#1 KPI = Sum of measure (not Count of id)')
  ok(kpi['value']['columnId'] == kpi['columns'][0]['id'], '#1 KPI binds via value.columnId')
  bar = els.find { |e| e['id'] == 'el-b1' }
  ok(bar['kind'] == 'bar-chart', '#7 bar card → bar-chart (not table+dataBars)')
  ok(bar.dig('xAxis', 'format', 'marks') == 'none' && bar.dig('yAxis', 'format', 'marks') == 'none', '#8 gridlines off')
  ok(bar['columns'][1]['name'] == 'Sales', '#4 measure label uses Domo alias')
  tbl = els.find { |e| e['id'] == 'el-t1' }
  ok(tbl['columns'].any? { |c| c.dig('style', 'textWrap') == 'wrap' }, '#5 table text column wraps')
  ctrl = els.find { |e| e['kind'] == 'control' }
  ok(ctrl && ctrl['filters'][0]['source']['elementId'] == 'master', '#2 control fans out via master')
  warns = JSON.parse(File.read(File.join(dir, 'warnings.json')))
  ok(warns.any? { |x| x['warning'].include?('row-key') }, '#1 COUNT-of-id KPI surfaced as a warning')

  # ---- Phase 5e: qa-check catches the uncorrected bad KPI ------------------
  ok(!run.call('qa-check.rb', '--in', File.join(dir, 'chart-specs.json')), 'qa-check.rb FAILS on uncorrected count-of-id KPI (gate works)')

  # ---- correct it via kpi-overrides.json, rebuild, qa-check passes ---------
  w.call('kpi-overrides.json', { 'k2' => { 'column' => 'sales_amount', 'aggregation' => 'SUM' } })
  ok(run.call('build-workbook.rb'), 'build-workbook.rb re-ran with overrides')
  ok(run.call('qa-check.rb', '--in', File.join(dir, 'chart-specs.json')), 'qa-check.rb PASSES after kpi-overrides fix')
end

puts
if $failures.zero? then puts "ALL PASS"; exit 0 else puts "#{$failures} FAILURE(S)"; exit 1 end
