#!/usr/bin/env ruby
# Unit tests for build-workbook.rb — the fixes for feedback #1,#2,#5,#7,#8.
#   ruby test/test-build-workbook.rb

require_relative '../scripts/build-workbook'
require 'tmpdir'

# Temporarily override a top-level constant for the duration of a block, then
# ALWAYS restore it — even on assertion failure — mirroring the with_domo_stub
# pattern in test-discover.rb. Ruby warns on constant reassignment; silence it
# locally rather than suppressing warnings globally.
def stub_const(name, value)
  target = Object
  existed = target.const_defined?(name)
  old = target.const_get(name) if existed
  silence_warnings { target.send(:remove_const, name) if target.const_defined?(name); target.const_set(name, value) }
  yield
ensure
  silence_warnings do
    target.send(:remove_const, name) if target.const_defined?(name)
    target.const_set(name, old) if existed
  end
end

def silence_warnings
  old_verbose = $VERBOSE
  $VERBOSE = nil
  yield
ensure
  $VERBOSE = old_verbose
end

$failures = 0
def eq(a, b, m) if a == b then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}\n    exp #{b.inspect}\n    got #{a.inspect}" end end
def ok(c, m) eq(!!c, true, m) end

puts "== #1 KPI: measure aggregate w/ source prefix + value.columnId =="
$warnings = []
kpi = build_kpi({ 'id' => 'c1', 'title' => 'Revenue',
                  'summaryNumber' => { 'column' => 'sales_amount', 'aggregation' => 'SUM',
                                       'label' => 'Total Revenue', 'format' => { 'type' => 'CURRENCY' },
                                       '_defaultCountSuspect' => false } }, {})
eq(kpi['kind'], 'kpi-chart', 'kind kpi-chart')
eq(kpi['columns'][0]['formula'], 'Sum([Master/Sales Amount])', 'value = Sum of measure, source-prefixed (NOT Count of id)')
eq(kpi['value'], { 'columnId' => kpi['columns'][0]['id'] }, 'value uses columnId (not id)')
eq(kpi['columns'][0]['format'], { 'kind' => 'number', 'decimalPlaces' => 0 }, 'currency format carried (proven decimalPlaces shape, not a d3 formatString)')

puts "== #1 KPI: COUNT-of-id (Domo table default) is flagged, not silent =="
$warnings = []
kpi2 = build_kpi({ 'id' => 'c2', 'title' => 'Projects',
                   'summaryNumber' => { 'column' => 'project_id', 'aggregation' => 'COUNT',
                                        '_defaultCountSuspect' => true } }, {})
ok($warnings.any? { |w| w['warning'].include?('row-key') && w['warning'].include?('kpi-overrides') }, 'COUNT-of-id KPI warned + override hint')
eq(kpi2['columns'][0]['formula'], 'Count([Master/Project Id])', 'still emits faithfully (surfaced, not dropped)')

puts "== #1 KPI: kpi-overrides.json corrects the measure deterministically =="
$warnings = []
kpi3 = build_kpi({ 'id' => 'c2', 'title' => 'Projects',
                   'summaryNumber' => { 'column' => 'project_id', 'aggregation' => 'COUNT', '_defaultCountSuspect' => true } },
                 { 'c2' => { 'column' => 'budget', 'aggregation' => 'SUM' } })
eq(kpi3['columns'][0]['formula'], 'Sum([Master/Budget])', 'override swaps to the intended measure')
ok($warnings.empty?, 'no warning once overridden')

puts "== #7 + #8 bar chart: real bar-chart, gridlines off =="
$warnings = []
bar = build_element({ 'id' => 'c3', 'title' => 'Sales by Region', 'chartType' => 'badge_vert_bar',
                      'sigmaKindHint' => 'bar-chart',
                      'groupBy' => ['store_region'],
                      'columns' => [ { 'column' => 'store_region' },
                                     { 'column' => 'sales_amount', 'aggregation' => 'SUM', 'alias' => 'Sales' } ] }, {})
eq(bar['kind'], 'bar-chart', '#7 bar card → bar-chart element (NOT table+dataBars)')
ok(bar['columns'].none? { |c| c['id'].to_s.start_with?('cf') }, 'no conditionalFormats/dataBars on a bar chart')
eq(bar['xAxis']['format'], { 'marks' => 'none' }, '#8 x-axis gridlines off')
eq(bar['yAxis']['format'], { 'marks' => 'none' }, '#8 y-axis gridlines off')
eq(bar['columns'][0]['formula'], '[Master/Store Region]', 'dimension references master')
eq(bar['columns'][1]['formula'], 'Sum([Master/Sales Amount])', 'measure aggregated + master-ref')
eq(bar['columns'][1]['name'], 'Sales', 'measure label uses Domo alias (fixes raw names #4)')

puts "== #5 table: text wrap on dimension columns; dataBars only when declared =="
tbl = build_element({ 'id' => 'c4', 'title' => 'Projects', 'chartType' => 'badge_table',
                      'sigmaKindHint' => 'table',
                      'columns' => [ { 'column' => 'project_name' },
                                     { 'column' => 'amount', 'aggregation' => 'SUM' } ],
                      'conditionalFormats' => [] }, {})
eq(tbl['kind'], 'table', 'badge_table (the REAL token — badge_datagrid does not exist) → table')
eq(tbl['columns'][0]['style'], { 'textWrap' => 'wrap' }, '#5 text column wraps')
ok(!tbl.key?('conditionalFormats'), 'no dataBars when the card declared none')

tbl2 = build_element({ 'id' => 'c5', 'title' => 'T', 'chartType' => 'badge_table', 'sigmaKindHint' => 'table',
                       'columns' => [ { 'column' => 'region' }, { 'column' => 'amt', 'aggregation' => 'SUM' } ],
                       'conditionalFormats' => [{ 'format' => { 'dataBar' => true } }] }, {})
eq(tbl2['conditionalFormats'].first['type'], 'dataBars', 'dataBars kept when the Domo table declared them')

puts "== Rule 0: single-value summary card → KPI even if chartType is table =="
$warnings = []
r0 = build_element({ 'id' => 'c6', 'title' => 'One Number', 'chartType' => 'badge_table',
                     'sigmaKindHint' => 'table', 'groupBy' => [], 'columns' => [{ 'column' => 'total', 'aggregation' => 'SUM' }],
                     'summaryNumber' => { 'column' => 'total', 'aggregation' => 'SUM' } }, {})
eq(r0['kind'], 'kpi-chart', 'summary-number table card → KPI, not a grid')

puts "== #2 controls: one per distinct filter column, bound to shared master =="
ctrls = build_controls([
  { 'id' => 'a', 'filters' => [{ 'column' => 'region', 'operator' => 'IN', 'values' => %w[W E] }] },
  { 'id' => 'b', 'filters' => [{ 'column' => 'region' }, { 'column' => 'status' }] },
])
eq(ctrls.size, 2, 'deduped to distinct filter columns (region, status)')
eq(ctrls[0]['filters'], [{ 'source' => { 'kind' => 'table', 'elementId' => 'master' }, 'columnId' => 'm-region' }],
   'control binds to master column → fans out to every element (fixes fall-off)')

puts "== Phase-5 geometry gate: warn when a page's cards carry no x/y =="
$warnings = []
warn_missing_geometry('Overview', [{ 'id' => 'c7', 'title' => 'No Geometry' }, { 'id' => 'c8' }])
ok($warnings.any? { |w| w['warning'].include?("no grid geometry for page 'Overview'") && w['warning'].include?('single-column stack') },
   "page with no card x/y warns loudly (Task 1's merge_geometry never ran / found nothing)")

$warnings = []
warn_missing_geometry('Overview', [{ 'id' => 'c9', 'x' => 0, 'y' => 0, 'w' => 3, 'h' => 2 }, { 'id' => 'c10' }])
ok($warnings.empty?, 'no warning once at least one card on the page carries geometry')

$warnings = []
warn_missing_geometry('Empty', [])
ok($warnings.empty?, 'no warning for an empty page (nothing to place)')

puts "== Problem 2: chartType is an EXACT-match strict enum, not a substring match =="
$warnings = []
# badge_line_bar is a COMBO chart but contains the substring 'badge_line' — the
# old doc's substring rule would have mis-routed this to line-chart.
combo = build_element({ 'id' => 'c11', 'title' => 'Revenue vs Target', 'chartType' => 'badge_line_bar',
                        'columns' => [ { 'column' => 'month' },
                                       { 'column' => 'revenue', 'aggregation' => 'SUM', 'alias' => 'Revenue' },
                                       { 'column' => 'target', 'aggregation' => 'SUM', 'alias' => 'Target' } ] }, {})
eq(combo['kind'], 'combo-chart', 'badge_line_bar → combo-chart, NOT line-chart (substring "badge_line" would mis-route it)')
eq(combo['yAxis']['columnIds'],
   [ { 'columnId' => combo['columns'][1]['id'], 'type' => 'bar' },
     { 'columnId' => combo['columns'][2]['id'], 'type' => 'line' } ],
   'first measure renders as the bar series, second as the line series')

# badge_symbol_bar contains the substring '_bar' — must be combo-chart, not bar-chart.
$warnings = []
symbar = build_element({ 'id' => 'c12', 'title' => 'Actual vs Marker', 'chartType' => 'badge_symbol_bar',
                         'columns' => [ { 'column' => 'region' },
                                        { 'column' => 'actual', 'aggregation' => 'SUM' },
                                        { 'column' => 'marker', 'aggregation' => 'SUM' } ] }, {})
eq(symbar['kind'], 'combo-chart', 'badge_symbol_bar → combo-chart, NOT bar-chart (substring "_bar" would mis-route it)')
eq(symbar['yAxis']['columnIds'][1]['type'], 'scatter', 'the symbol overlay renders as a scatter series')

puts "== Problem 1: fabricated chartType tokens are flagged, never silently mapped =="
$warnings = []
fab = build_element({ 'id' => 'c13', 'title' => 'Old Table Card', 'chartType' => 'badge_datagrid',
                      'columns' => [ { 'column' => 'name' }, { 'column' => 'amt', 'aggregation' => 'SUM' } ] }, {})
ok($warnings.any? { |w| w['warning'].include?('not a valid Domo ChartType') && w['warning'].include?('badge_table') },
   'badge_datagrid (confirmed-invalid enum value) is flagged, naming the real replacement token')
ok(!fab.nil?, 'a fabricated-token card still emits SOME element — never a silent drop')

puts "== Problem 3: newly-mapped chart types resolve to the VERIFIED Sigma kind =="
$warnings = []
stacked = build_element({ 'id' => 'c14', 'title' => 'Sales by Region (stacked)', 'chartType' => 'badge_vert_stackedbar',
                          'columns' => [ { 'column' => 'region' }, { 'column' => 'sales', 'aggregation' => 'SUM' } ] }, {})
eq(stacked['kind'], 'bar-chart', 'badge_vert_stackedbar → bar-chart')
eq(stacked['stacking'], 'stacked', 'badge_vert_stackedbar carries stacking:stacked')

pct = build_element({ 'id' => 'c15', 'title' => 'Share of Total', 'chartType' => 'badge_horiz_100pct',
                      'columns' => [ { 'column' => 'segment' }, { 'column' => 'share', 'aggregation' => 'SUM' } ] }, {})
eq(pct['orientation'], 'horizontal', 'badge_horiz_100pct is horizontal')
eq(pct['stacking'], 'normalized', 'badge_horiz_100pct is the percent-stacked variant')

donut = build_element({ 'id' => 'c16', 'title' => 'Mix', 'chartType' => 'badge_donut',
                        'columns' => [ { 'column' => 'family' }, { 'column' => 'sales', 'aggregation' => 'SUM' } ] }, {})
eq(donut['kind'], 'donut-chart', 'badge_donut → donut-chart')
eq(donut['value'], { 'id' => donut['columns'].last['id'] }, 'donut value uses value.id (opposite of KPI columnId)')
ok(!donut.key?('xAxis') && !donut.key?('yAxis'), 'donut/pie carry value/color, NOT xAxis/yAxis (fixes the old broken shape)')

pie = build_element({ 'id' => 'c17', 'title' => 'Share', 'chartType' => 'badge_pie',
                      'columns' => [ { 'column' => 'family' }, { 'column' => 'sales', 'aggregation' => 'SUM' } ] }, {})
eq(pie['kind'], 'pie-chart', 'badge_pie → pie-chart (Sigma has a distinct pie-chart kind, not just donut)')

puts "== Problem 3: no-native-equivalent chart types warn loudly + degrade honestly (never a silent bar-chart) =="
$warnings = []
wc = build_element({ 'id' => 'c18', 'title' => 'Top Terms', 'chartType' => 'badge_word_cloud',
                     'columns' => [ { 'column' => 'term' }, { 'column' => 'freq', 'aggregation' => 'SUM' } ] }, {})
eq(wc['kind'], 'table', 'badge_word_cloud degrades to a table (no word-cloud kind exists in Sigma)')
ok($warnings.any? { |w| w['warning'].include?('no native Sigma equivalent') && w['warning'].include?('word cloud') && w['warning'].include?('plugin') },
   'the word-cloud gap is flagged loudly, naming the gap and the custom-plugin follow-up')

$warnings = []
gauge = build_element({ 'id' => 'c19', 'title' => 'Quota Attainment', 'chartType' => 'badge_filledgauge',
                        'summaryNumber' => { 'column' => 'attainment', 'aggregation' => 'SUM', 'label' => 'Attainment' },
                        'columns' => [ { 'column' => 'attainment', 'aggregation' => 'SUM' },
                                       { 'column' => 'target', 'aggregation' => 'SUM' } ] }, {})
eq(gauge['kind'], 'kpi-chart', 'badge_filledgauge degrades to kpi-chart (gauge is a CONFIRMED-INVALID Sigma kind)')
ok($warnings.any? { |w| w['warning'].include?('no native Sigma equivalent') && w['warning'].include?('gauge') }, 'the gauge gap is flagged loudly')

$warnings = []
nogauge = build_element({ 'id' => 'c19b', 'title' => 'Orphan Gauge', 'chartType' => 'badge_filledgauge',
                          'columns' => [] }, {})
eq(nogauge['kind'], 'table', 'a gauge card with no summaryNumber still emits an element (table) — never silently dropped')
ok($warnings.any? { |w| w['warning'].include?('not silently dropped') }, 'the missing-summaryNumber gauge case is flagged')

puts "== badge_map: region-map when the geography column is classifiable, honest table fallback otherwise =="
$warnings = []
geomap = build_element({ 'id' => 'c20', 'title' => 'Sales by State', 'chartType' => 'badge_map',
                         'columns' => [ { 'column' => 'store_state' }, { 'column' => 'sales', 'aggregation' => 'SUM' } ] }, {})
eq(geomap['kind'], 'region-map', 'badge_map with a recognizable state column → region-map')
eq(geomap['region']['regionType'], 'us-state', 'regionType inferred from the column name')

$warnings = []
badgeo = build_element({ 'id' => 'c21', 'title' => 'Custom Territory Map', 'chartType' => 'badge_map',
                         'columns' => [ { 'column' => 'sales_territory_code' }, { 'column' => 'sales', 'aggregation' => 'SUM' } ] }, {})
eq(badgeo['kind'], 'table', 'badge_map with an unclassifiable geography → honest table fallback, not a broken map spec')
ok($warnings.any? { |w| w['warning'].include?('no native Sigma equivalent') }, 'the unclassifiable geography is flagged, not silently dropped')

puts "== split_cols honors Domo's own column->visual-role `mapping` vocabulary when present =="
dims, meas = split_cols({ 'columns' => [ { 'column' => 'region', 'mapping' => 'ITEM' },
                                         { 'column' => 'revenue', 'mapping' => 'VALUE' } ] })
eq(dims.map { |c| c['column'] }, ['region'], 'ITEM-mapped column is a dimension even with no aggregation/groupBy present')
eq(meas.map { |c| c['column'] }, ['revenue'], 'VALUE-mapped column is a measure even with no aggregation present (fails under the old aggregation-only heuristic)')

puts "== bead 2ef7: card['limit'] -> Sigma top-n element filter (table) =="
$warnings = []
topn = build_element({ 'id' => 'c22', 'title' => 'Order Detail (Top 25)', 'chartType' => 'badge_table',
                       'sigmaKindHint' => 'table', 'limit' => 25,
                       'columns' => [ { 'column' => 'order_id' },
                                      { 'column' => 'net_revenue', 'aggregation' => 'SUM', 'alias' => 'Net Revenue' } ] }, {})
eq(topn['kind'], 'table', 'still a table element')
ok(topn.key?('filters'), 'limit produced an element filter')
eq(topn['filters'].first['kind'], 'top-n', 'filter kind is top-n')
eq(topn['filters'].first['rankingFunction'], 'rank', 'rankingFunction is rank')
eq(topn['filters'].first['mode'], 'top-n', 'mode is top-n')
eq(topn['filters'].first['rowCount'], 25, 'rowCount carries the Domo limit as a NUMBER LITERAL')
eq(topn['filters'].first['columnId'], topn['columns'].last['id'], 'ranks by the measure column (Net Revenue), not the dimension')

puts "== bead 2ef7: no limit declared -> no filters key at all =="
no_topn = build_element({ 'id' => 'c23', 'title' => 'All Orders', 'chartType' => 'badge_table',
                          'sigmaKindHint' => 'table',
                          'columns' => [ { 'column' => 'order_id' },
                                         { 'column' => 'net_revenue', 'aggregation' => 'SUM' } ] }, {})
ok(!no_topn.key?('filters'), 'no limit -> no filters key (never emit an empty/default top-n)')

puts "== bead 2ef7: limit with no measure column -> no filter (nothing to rank by)" \
     ' — never crash, never emit a columnId:nil filter =='
no_measure = build_element({ 'id' => 'c24', 'title' => 'Dim Only', 'chartType' => 'badge_table',
                             'sigmaKindHint' => 'table', 'limit' => 10,
                             'columns' => [ { 'column' => 'order_id' } ] }, {})
ok(!no_measure.key?('filters'), 'no measure column -> no top-n filter emitted')

puts "== bead ziht: dataset_element_map resolves datasetId -> live DM element =="
Dir.mktmpdir do |dir|
  dm_spec_path = File.join(dir, 'dm-spec.json')
  dm_ids_path  = File.join(dir, 'dm-ids.json')
  File.write(dm_spec_path, JSON.generate('pages' => [{ 'elements' => [
    { 'id' => 'el-fact-1', 'name' => 'Order Fact', '_datasetId' => 'ds-fact' },
    { 'id' => 'el-dim-1',  'name' => 'Customer Dim', '_datasetId' => 'ds-dim' },
  ] }]))
  File.write(dm_ids_path, JSON.generate('dataModelId' => 'dm-live-1', 'pages' => [{ 'elements' => [
    { 'id' => 'el-fact-1', 'name' => 'Order Fact', 'columnLabels' => ['Order Id', 'Region'] },
    { 'id' => 'el-dim-1',  'name' => 'Customer Dim', 'columnLabels' => ['Customer Id', 'Segment'] },
  ] }]))
  stub_const('DM_SPEC_PATH', dm_spec_path) do
    stub_const('DM_IDS_PATH', dm_ids_path) do
      $ds_element_map = nil # force recompute against this dir's fixtures
      map = dataset_element_map
      eq(map.keys.sort, %w[ds-dim ds-fact], 'both datasets resolved')
      eq(map['ds-dim']['id'], 'el-dim-1', 'ds-dim resolves to its own live element, not the fact')

      $sub_masters = {}
      sm = sub_master_for('ds-dim')
      ok(!sm.nil?, 'sub-master built for a resolvable dataset')
      eq(sm['kind'], 'table', 'sub-master is a table element')
      eq(sm['visibleAsSource'], false, 'sub-master is hidden, like the primary master')
      eq(sm['source'], { 'kind' => 'data-model', 'dataModelId' => 'dm-live-1', 'elementId' => 'el-dim-1' },
         'sub-master sources the LIVE DM element for ds-dim, dataModelId included')
      eq(sm['columns'].map { |c| c['name'] }, ['Customer Id', 'Segment'], 'auto-passthrough of the DM element\'s own columns')
      eq(sm['columns'].first['formula'], '[Customer Dim/Customer Id]', 'column formula qualifies by the DM element\'s own name')

      ok(sub_master_for('ds-dim').equal?(sm), 'memoized — a second call returns the SAME object, not a rebuild')
      eq($ds_element_map.dig('ds-nope'), nil, 'unknown dataset -> nil, not an exception')
      ok(sub_master_for('ds-nope').nil?, 'sub_master_for on an unresolvable dataset -> nil (caller falls back to today\'s skip)')
    end
  end
end

puts "== live-found 2026-07-31: a NAMELESS DM element (build-dm.rb's rule 3 — no element-level " \
     'name) still resolves a real sub-master formula, not "[/Col]" (an invalid, empty-table-name formula) =='
Dir.mktmpdir do |dir|
  dm_spec_path = File.join(dir, 'dm-spec.json')
  dm_ids_path  = File.join(dir, 'dm-ids.json')
  # Mirrors build-dm.rb's REAL output shape: no element-level `name`, plus the
  # warehouse-table `source.path` build-workbook-spec.rb's own name-fallback
  # already reads for the primary master.
  File.write(dm_spec_path, JSON.generate('pages' => [{ 'elements' => [
    { 'id' => 'el-dim-1', '_datasetId' => 'ds-dim',
      'source' => { 'kind' => 'warehouse-table', 'path' => %w[CSA TJ CUSTOMER_DIM] } },
  ] }]))
  File.write(dm_ids_path, JSON.generate('dataModelId' => 'dm-live-1', 'pages' => [{ 'elements' => [
    { 'id' => 'el-dim-1', 'name' => nil, 'columnLabels' => ['Customer Id', 'Region'] },
  ] }]))
  stub_const('DM_SPEC_PATH', dm_spec_path) do
    stub_const('DM_IDS_PATH', dm_ids_path) do
      $ds_element_map = nil
      $sub_masters = {}
      sm = sub_master_for('ds-dim')
      ok(!sm.nil?, 'sub-master still built for a nameless DM element')
      eq(sm['name'], 'Master (CUSTOMER_DIM)', "falls back to the warehouse table's own name (last path segment), " \
                                              'the SAME resolution build-workbook-spec.rb uses for the primary master')
      eq(sm['columns'].first['formula'], '[CUSTOMER_DIM/Customer Id]',
         'formula is correctly table-qualified — never "[/Customer Id]" (an invalid, empty-table-name formula ' \
         'that would 400 the whole workbook POST)')
    end
  end
end

puts "== bead ziht: dataset_element_map degrades to {} when the inputs are absent (offline / unit-test default) =="
stub_const('DM_SPEC_PATH', '/nonexistent/dm-spec.json') do
  stub_const('DM_IDS_PATH', nil) do
    $ds_element_map = nil
    eq(dataset_element_map, {}, 'no dm-spec/dm-ids -> empty map, never an exception')
  end
end

puts "== stub_const restores a constant whose ORIGINAL value was falsy (nil), not just truthy ones =="
# DM_IDS_PATH's real original value in THIS offline test run is nil (nothing sets
# DOMO_DM_IDS_PATH in the environment) — exactly the real-world case that used to
# defeat restore-on-`ensure`'s old `if old` guard (nil is falsy, so the constant was
# left REMOVED rather than restored to nil).
ok(Object.const_defined?(:DM_IDS_PATH), 'DM_IDS_PATH is defined before the stub (as nil, since DOMO_DM_IDS_PATH is unset)')
eq(DM_IDS_PATH, nil, 'sanity: DM_IDS_PATH really is nil in this offline test env')
stub_const('DM_IDS_PATH', '/tmp/whatever-dm-ids.json') do
  eq(DM_IDS_PATH, '/tmp/whatever-dm-ids.json', 'stubbed value visible inside the block')
end
ok(Object.const_defined?(:DM_IDS_PATH), 'DM_IDS_PATH still defined after stub block exits (regression: used to vanish when the original value was nil/falsy)')
eq(DM_IDS_PATH, nil, 'restored to its original nil value, not left undefined')

puts "== bead 08sf: build_summary_companion mirrors build_kpi but with a distinct id =="
kpi_card = { 'id' => 'c29', 'title' => 'Revenue by Channel',
             'summaryNumber' => { 'column' => 'net_revenue', 'aggregation' => 'SUM', 'label' => 'Total Revenue' } }
companion = build_summary_companion(kpi_card, {})
ok(!companion.nil?, 'companion built when the summary number has a resolvable column')
eq(companion['kind'], 'kpi-chart', 'companion is a kpi-chart element')
eq(companion['name'], 'Total Revenue', 'companion carries the summary number\'s own label')
eq(companion['id'], "#{eid(kpi_card)}-summary",
   'companion id is the primary element\'s id + a -summary suffix (never collides with it)')

no_col_card = { 'id' => 'c30', 'title' => 'Orders', 'summaryNumber' => { 'column' => '', 'aggregation' => 'COUNT' } }
ok(build_summary_companion(no_col_card, {}).nil?,
   'nil when the summary number has no resolvable column (mirrors build_kpi\'s own "return nil unless col")')

puts "== M1 (final review, minor): retarget_to_submaster! must NOT fabricate a 'source' key on " \
     'an element that never had one (build_image) =='
img_el = { 'id' => 'el-img1', 'kind' => 'image', 'url' => 'data:image/png;base64,AAAA' }
sm_fixture = { 'id' => 'master-ds-dim', 'name' => 'Master (Customer Dim)' }
retarget_to_submaster!(img_el, sm_fixture)
ok(!img_el.key?('source'), "an image element (no 'source' key to begin with) still has none after retargeting " \
                            '— no bogus source fabricated (M1)')
eq(img_el['url'], 'data:image/png;base64,AAAA', "the image element's other fields are untouched")

chart_el = { 'id' => 'el-c1', 'kind' => 'bar-chart', 'source' => { 'kind' => 'table', 'elementId' => 'master' } }
retarget_to_submaster!(chart_el, sm_fixture)
eq(chart_el['source'], { 'kind' => 'table', 'elementId' => 'master-ds-dim' },
   'an element that DOES carry a source key still gets retargeted normally (unchanged behavior)')

puts "== live-found 2026-07-31: retarget_to_submaster! must not raise FrozenError on a " \
     'shared frozen constant (AXIS_OFF) nested inside an axis-chart element =='
axis_el = { 'id' => 'el-axis1', 'kind' => 'bar-chart',
            'source' => { 'kind' => 'table', 'elementId' => 'master' },
            'columns' => [{ 'id' => 'd-region', 'formula' => '[Master/Region]' }],
            'xAxis' => { 'columnId' => 'd-region', 'format' => AXIS_OFF },
            'yAxis' => { 'columnIds' => ['m-count'], 'format' => AXIS_OFF } }
retarget_to_submaster!(axis_el, sm_fixture)
ok(true, 'retargeting an element referencing the frozen AXIS_OFF constant does not raise FrozenError')
eq(axis_el['columns'].first['formula'], '[Master (Customer Dim)/Region]', 'the real formula ref is still rewritten')
eq(axis_el['xAxis']['format'], AXIS_OFF, "the frozen shared format hash is left as-is (never a rewrite target)")
ok(AXIS_OFF.frozen?, 'sanity: AXIS_OFF itself is still frozen (unmutated) after being walked')

puts "== bead ziht: a card on a non-dominant DataSet routes to its own sub-master " \
     '(not skipped) once a live DM element is resolvable =='
Dir.mktmpdir do |dir|
  dm_spec_path = File.join(dir, 'dm-spec.json')
  dm_ids_path  = File.join(dir, 'dm-ids.json')
  File.write(dm_spec_path, JSON.generate('pages' => [{ 'elements' => [
    { 'id' => 'el-dim-1', 'name' => 'Customer Dim', '_datasetId' => 'ds-dim' },
  ] }]))
  File.write(dm_ids_path, JSON.generate('dataModelId' => 'dm-live-1', 'pages' => [{ 'elements' => [
    { 'id' => 'el-dim-1', 'name' => 'Customer Dim', 'columnLabels' => ['Region', 'Segment'] },
  ] }]))
  stub_const('DM_SPEC_PATH', dm_spec_path) do
    stub_const('DM_IDS_PATH', dm_ids_path) do
      $ds_element_map = nil
      $sub_masters = {}
      $warnings = []
      routed = build_element({ 'id' => 'c25', 'title' => 'Customers by Region', 'chartType' => 'badge_table',
                               'sigmaKindHint' => 'table', 'datasetId' => 'ds-dim',
                               'columns' => [ { 'column' => 'region' } ] }, {}, 'ds-fact')
      ok(!routed.nil?, 'card is NOT skipped — a live sub-master was resolvable')
      eq(routed['source'], { 'kind' => 'table', 'elementId' => 'master-ds-dim' }, 'routed to its own sub-master, not the shared master')
      eq(routed['columns'].first['formula'], '[Master (Customer Dim)/Region]', 'formula re-qualified to the sub-master\'s namespace')
      ok($warnings.any? { |w| w['warning'].include?('routed to sub-master') }, 'routing is reported, not silent')
      ok($sub_masters.key?('ds-dim'), 'the sub-master was registered for the main block to emit under data_elements')
    end
  end
end

puts "== bead ziht: unresolvable DataSet still falls back to today's warn+SKIP =="
$ds_element_map = {}
$sub_masters = {}
$warnings = []
skipped = build_element({ 'id' => 'c26', 'title' => 'Orphan Dataset Card', 'chartType' => 'badge_table',
                          'sigmaKindHint' => 'table', 'datasetId' => 'ds-unknown',
                          'columns' => [ { 'column' => 'x' } ] }, {}, 'ds-fact')
ok(skipped.nil?, 'still nil when no live DM element is resolvable for the DataSet (unchanged fallback)')
ok($warnings.any? { |w| w['warning'].include?('SKIPPED') }, 'still warns loudly on fallback')

puts "== bead ziht: build_controls skips (warns) a filter bound to a non-dominant DataSet\'s column " \
     'rather than 400ing the whole POST binding it to the wrong master =='
$warnings = []
ctrls2 = build_controls([
  { 'id' => 'c27', 'datasetId' => 'ds-fact', 'filters' => [{ 'column' => 'region' }] },
  { 'id' => 'c28', 'datasetId' => 'ds-dim',  'filters' => [{ 'column' => 'segment' }] },
], 'ds-fact')
eq(ctrls2.size, 1, 'only the dominant-dataset filter becomes a control')
eq(ctrls2.first['controlId'], 'Region', 'the surviving control is the dominant-dataset one')
ok($warnings.any? { |w| w['warning'].include?('control filter') && w['warning'].include?('SKIPPED') },
   'the non-dominant control is reported, not silently dropped')

puts "== bead 08sf: a chart/table card with a summaryNumber gets a companion KPI via " \
     'build_element, not just a warning =='
$warnings = []
$companion_elements = []
chart_with_summary = build_element({ 'id' => 'c31', 'title' => 'Revenue by Channel', 'chartType' => 'badge_vert_bar',
                                     'sigmaKindHint' => 'bar-chart',
                                     'groupBy' => ['channel'],
                                     'columns' => [ { 'column' => 'channel' },
                                                    { 'column' => 'net_revenue', 'aggregation' => 'SUM', 'alias' => 'Net Revenue' } ],
                                     'summaryNumber' => { 'column' => 'net_revenue', 'aggregation' => 'SUM', 'label' => 'Total Revenue' } }, {})
eq(chart_with_summary['kind'], 'bar-chart', 'the primary element is still the bar chart, unchanged')
eq($companion_elements.size, 1, 'exactly one companion KPI was produced')
companion = $companion_elements.first
eq(companion['kind'], 'kpi-chart', 'companion is a kpi-chart element')
eq(companion['name'], 'Total Revenue', 'companion carries the summary number\'s own label')
ok(companion['id'] != chart_with_summary['id'], 'companion has a DISTINCT id from the primary element (no duplicate-id 400)')
ok($warnings.any? { |w| w['warning'].include?('companion KPI element') }, 'the companion is reported, not silent')

puts "== bead 08sf: a card whose summaryNumber has no resolvable column still just warns " \
     '(no crash, no half-built companion) =='
$warnings = []
$companion_elements = []
# NOTE (task-5 self-review fix): a genuinely blank ('') summaryNumber column, with
# only 1 total column and no groupBy, trips Rule 0's is_kpi check (unchanged, and
# correctly so — see the Rule-0 test right below) BEFORE this code ever runs, and
# even bypassing Rule 0, build_element_body's own outer guard
# (`!sn['column'].to_s.empty?`) requires a raw non-blank column before it will even
# attempt build_summary_companion. So a literal '' can never reach the "companion
# could not be built" branch this test targets. A second (non-KPI-triggering)
# column keeps this off the Rule-0 path, and a whitespace-only column (' ') passes
# the outer guard's raw `.empty?` check while still failing
# build_summary_companion's stricter `.strip.empty?` check — genuinely exercising
# "column present but not resolvable", exactly the case this test names.
no_companion = build_element({ 'id' => 'c32', 'title' => 'Orders', 'chartType' => 'badge_table',
                               'sigmaKindHint' => 'table',
                               'columns' => [ { 'column' => 'order_id' },
                                              { 'column' => 'amount', 'aggregation' => 'SUM' } ],
                               'summaryNumber' => { 'column' => ' ', 'aggregation' => 'COUNT' } }, {})
ok(!no_companion.nil?, 'primary element still built')
eq($companion_elements.size, 0, 'no companion when the summary number has no resolvable column')
ok($warnings.any? { |w| w['warning'].include?('NOT represented') }, 'still warns loudly on the unresolvable case (unchanged existing behavior)')

puts "== bead 08sf: Rule 0 (summary IS the whole card) still short-circuits to a single " \
     'KPI, no companion (unchanged) =='
$warnings = []
$companion_elements = []
rule0 = build_element({ 'id' => 'c33', 'title' => 'One Number', 'chartType' => 'badge_table',
                        'sigmaKindHint' => 'table', 'groupBy' => [], 'columns' => [{ 'column' => 'total', 'aggregation' => 'SUM' }],
                        'summaryNumber' => { 'column' => 'total', 'aggregation' => 'SUM' } }, {})
eq(rule0['kind'], 'kpi-chart', 'Rule 0 still routes straight to a single KPI')
eq($companion_elements.size, 0, 'no companion is produced for a Rule-0 card (it IS the KPI, not a chart+companion)')

puts "== C1 (final review, Critical): a ROUTED card whose PRIMARY element fails to build " \
     'must NOT leak its companion KPI un-retargeted into $companion_elements =='
Dir.mktmpdir do |dir|
  dm_spec_path = File.join(dir, 'dm-spec.json')
  dm_ids_path  = File.join(dir, 'dm-ids.json')
  File.write(dm_spec_path, JSON.generate('pages' => [{ 'elements' => [
    { 'id' => 'el-dim-1', 'name' => 'Customer Dim', '_datasetId' => 'ds-dim' },
  ] }]))
  File.write(dm_ids_path, JSON.generate('dataModelId' => 'dm-live-1', 'pages' => [{ 'elements' => [
    { 'id' => 'el-dim-1', 'name' => 'Customer Dim', 'columnLabels' => ['Region', 'Segment'] },
  ] }]))
  stub_const('DM_SPEC_PATH', dm_spec_path) do
    stub_const('DM_IDS_PATH', dm_ids_path) do
      $ds_element_map = nil
      $sub_masters = {}
      $warnings = []
      $companion_elements = []
      before_companions = $companion_elements.length

      # Routed to ds-dim's sub-master (resolvable, per the fixture above), so
      # this DOES take the routing path (not the warn+SKIP "unresolvable
      # DataSet" fallback). Two non-aggregated dimension columns (no
      # 'aggregation', no groupBy/mapping signal) means split_cols resolves
      # ZERO measures, so build_axis_chart's own "could not resolve both a
      # dimension and a measure" guard fires and returns nil for the PRIMARY
      # element — while the card ALSO carries a resolvable summaryNumber, so
      # build_element_body has a companion ready to go before it discovers
      # the primary failed.
      failed = build_element({ 'id' => 'c34', 'title' => 'Customers (no measure)', 'chartType' => 'badge_vert_bar',
                               'datasetId' => 'ds-dim',
                               'columns' => [ { 'column' => 'region' }, { 'column' => 'segment' } ],
                               'summaryNumber' => { 'column' => 'net_revenue', 'aggregation' => 'SUM',
                                                    'label' => 'Total Revenue' } },
                             {}, 'ds-fact')

      ok(failed.nil?, 'build_element still returns nil when the routed primary element failed to build')
      eq($companion_elements.length, before_companions,
         '$companion_elements did NOT grow — the companion built during the failed attempt was ' \
         'dropped, never leaked un-retargeted against the shared master (C1)')

      # M3: the warning sequence must not claim a companion "represents" a
      # card whose primary element was actually dropped.
      ok(!$warnings.any? { |w| w['warning'].include?('ALSO represented') },
         'the misleading "ALSO represented" warning does NOT fire when the primary failed to build (M3)')
      ok($warnings.any? { |w| w['warning'].include?('was NOT emitted') && w['warning'].include?('failed to build') },
         'a warning explains the companion was dropped BECAUSE the primary failed (M3)')
    end
  end
end

puts "== bead 08sf follow-up (live-found 2026-07-31): build_kpi inlines an aggregate " \
     'Beast Mode summary number instead of referencing a non-existent DM column =='
$translated_bms = {
  'calculation_margin' => { 'id' => 'calculation_margin', 'name' => 'Margin Pct',
                            'class' => 'aggregate',
                            'sigmaFormula' => 'If(Sum([Net Revenue]) = 0, 0, Sum([Gross Profit]) / Sum([Net Revenue]))' },
}
calc_kpi = build_kpi({ 'id' => 'c34', 'title' => 'Margin % by Channel',
                       'summaryNumber' => { 'column' => 'Margin Pct', 'beastModeId' => 'calculation_margin',
                                            '_isCalc' => true, 'label' => 'Margin Pct' } }, {})
ok(!calc_kpi.nil?, 'KPI still built for an aggregate-calc summary number')
eq(calc_kpi['columns'][0]['formula'],
   'If(Sum([Master/Net Revenue]) = 0, 0, Sum([Master/Gross Profit]) / Sum([Master/Net Revenue]))',
   'formula is the INLINED, masterized Beast Mode expression — NOT Sum([Master/Margin Pct]), ' \
   'a column that does not exist and would 400 the whole workbook POST')
eq(calc_kpi['value'], { 'columnId' => calc_kpi['columns'][0]['id'] }, "value.columnId matches the inlined column's own id")
$translated_bms = nil

puts "== bead 08sf follow-up: a kpi-overrides.json entry still bypasses Beast Mode inlining =="
override_kpi = build_kpi({ 'id' => 'c34', 'title' => 'Margin % by Channel',
                           'summaryNumber' => { 'column' => 'Margin Pct', 'beastModeId' => 'calculation_margin',
                                                '_isCalc' => true } },
                         { 'c34' => { 'column' => 'net_revenue', 'aggregation' => 'SUM' } })
eq(override_kpi['columns'][0]['formula'], 'Sum([Master/Net Revenue])', 'override still wins over the calc inlining')

puts
if $failures.zero? then puts "ALL PASS"; exit 0 else puts "#{$failures} FAILURE(S)"; exit 1 end
