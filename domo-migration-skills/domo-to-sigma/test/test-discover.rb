#!/usr/bin/env ruby
# Unit tests for domo-discover.rb pure helpers (no network). Validates the
# two-shape card-def normalizer, Beast Mode classification, and summary-number
# extraction against synthetic fixtures modeled on the confirmed Domo shapes
# (Shape A = official CardDefinition, Shape B = internal analyzer definition).
#
#   ruby test/test-discover.rb
#
# discovery/ is created on load (gitignored) — harmless.

ARGV.clear                       # ensure domo-discover.rb's main flow is a no-op
require_relative '../scripts/domo-discover'
require_relative '../scripts/lib/domo_sigma_util'
require 'base64'
require 'stringio'
include DomoSigma

FIXTURE_DIR = File.join(__dir__, 'fixtures', 'domo-live-raw')
def load_fixture(name)
  JSON.parse(File.read(File.join(FIXTURE_DIR, name)))
end

# Kernel#warn writes to $stderr — swap it for a StringIO so a "warn loudly,
# never silently" assertion is an actual check, not an eyeballed log line.
def capture_stderr
  old = $stderr
  $stderr = StringIO.new
  yield
  $stderr.string
ensure
  $stderr = old
end

# Minimal stub harness for the Domo REST wrapper: temporarily override a
# module_function singleton method (Domo.foo), run the block, then ALWAYS
# restore the original — even on assertion failure — so a stub from one test
# section can never leak into a later one. Used throughout below to exercise
# the Bug 1 (card enumeration) and Bug 4 (Beast Mode classification) fallback
# logic entirely offline, with no network/credentials.
def with_domo_stub(method_name, impl)
  orig = Domo.method(method_name)
  Domo.define_singleton_method(method_name, &impl)
  yield
ensure
  Domo.define_singleton_method(method_name, &orig)
end

$failures = 0
def eq(actual, expected, msg)
  if actual == expected
    puts "  ok: #{msg}"
  else
    $failures += 1
    puts "  FAIL: #{msg}\n        expected #{expected.inspect}\n        got      #{actual.inspect}"
  end
end
def ok(cond, msg)
  eq(!!cond, true, msg)
end

puts "== sigma_kind_hint =="
eq(sigma_kind_hint('badge_vert_bar'),      'bar-chart',     'badge_vert_bar → bar-chart')
eq(sigma_kind_hint('badge_horiz_bar'),     'bar-chart',     'badge_horiz_bar → bar-chart')
eq(sigma_kind_hint('badge_xyscatterplot'), 'scatter-chart', 'badge_xyscatterplot → scatter-chart')
eq(sigma_kind_hint('badge_datagrid'),      'table',         'badge_datagrid → table')
eq(sigma_kind_hint('badge_singlevalue'),   'kpi-chart',     'badge_singlevalue → kpi-chart')
eq(sigma_kind_hint('badge_line'),          'line-chart',    'badge_line → line-chart')
eq(sigma_kind_hint('badge_pie'),           'donut-chart',   'badge_pie → donut-chart')
eq(sigma_kind_hint('badge_pivottable'),    'pivot-table',   'pivot → pivot-table')
eq(sigma_kind_hint('mystery_widget'),      nil,             'unknown → nil (read PNG)')

puts "== classify_beast_mode (heuristic, no template) =="
eq(classify_beast_mode('SUM(SUM(`Total Sales`) FIXED (BY `Region`))'), 'lod',        'FIXED → lod')
eq(classify_beast_mode('RANK() OVER(ORDER BY SUM(`Sales`) DESC)'),     'window',     'OVER → window')
eq(classify_beast_mode('sum(sum(`visits`)) over(partition by `x`)'),   'window',     'running-total OVER → window')
eq(classify_beast_mode('SUM(`IntegerColumn`)'),                         'aggregate',  'SUM(col) → aggregate')
eq(classify_beast_mode("CONCAT(`City`, ', ', `State`)"),               'projection', 'CONCAT → projection')
eq(classify_beast_mode("CASE WHEN `c` = 'x' THEN 'y' ELSE 'z' END"),   'projection', 'row-level CASE → projection')

puts "== classify_beast_mode (API flags win) =="
eq(classify_beast_mode('anything', { 'analytic' => true }),   'window',     'analytic flag → window')
eq(classify_beast_mode('anything', { 'aggregated' => true }), 'aggregate',  'aggregated flag → aggregate')
eq(classify_beast_mode('CONCAT(a,b)', { 'aggregated' => false, 'analytic' => false }), 'projection', 'no flags → projection')

puts "== normalize_card: Shape A =="
shape_a = {
  'title' => 'Revenue by Region', 'chartType' => 'badge_vert_bar', 'dataSetId' => 'ds-1',
  'chartBody' => {
    'columns' => [
      { 'column' => 'store_region', 'alias' => 'Store Region' },
      { 'column' => 'sales_amount', 'alias' => 'Sales', 'aggregation' => 'SUM',
        'format' => { 'type' => 'CURRENCY' } },
    ],
    'groupBy' => [{ 'column' => 'store_region' }],
    'orderBy' => [{ 'column' => 'sales_amount' }],
    'filters' => [{ 'column' => 'status', 'operand' => 'IN', 'values' => %w[Active Pending] }],
    'limit' => 25,
  },
  'summaryNumber' => { 'columns' => [{ 'column' => 'sales_amount', 'aggregation' => 'SUM',
                                       'alias' => 'Total Revenue', 'format' => { 'type' => 'CURRENCY' } }] },
  'calculatedFields' => [{ 'id' => 'calculation_abc', 'name' => 'Margin', 'formula' => 'SUM(`profit`)/SUM(`sales`)' }],
  'conditionalFormats' => [],
}
a = normalize_card(shape_a, 'card-A')
eq(a['_shape'], 'A', 'shape detected A')
eq(a['title'], 'Revenue by Region', 'title')
eq(a['sigmaKindHint'], 'bar-chart', 'kind hint bar-chart')
eq(a['columns'].map { |c| c['alias'] }, ['Store Region', 'Sales'], 'aliases carried (fixes raw-name bug)')
eq(a['columns'][1]['aggregation'], 'SUM', 'column aggregation')
eq(a['groupBy'], ['store_region'], 'groupBy flattened')
eq(a['orderBy'], ['sales_amount'], 'orderBy flattened')
eq(a['filters'], [{ 'column' => 'status', 'operator' => 'IN', 'values' => %w[Active Pending] }], 'filter normalized (operand→operator)')
eq(a['summaryNumber']['column'], 'sales_amount', 'summary number column')
eq(a['summaryNumber']['aggregation'], 'SUM', 'summary number aggregation')
eq(a['summaryNumber']['label'], 'Total Revenue', 'summary number label from alias')
eq(a['summaryNumber']['_defaultCountSuspect'], false, 'SUM is not a COUNT-of-id suspect')
eq(a['cardFormulas'].size, 1, 'card-local formula captured')
eq(a['limit'], 25, 'limit carried through Shape A normalization (bead 2ef7)')

puts "== normalize_card: Shape B =="
shape_b = {
  'chartType' => 'badge_datagrid', 'dataSetId' => 'ds-2',
  'definition' => {
    'dynamicTitle' => { 'text' => [{ 'type' => 'TEXT', 'text' => 'Project List' }] },
    'subscriptions' => { 'main' => {
      'columns' => [
        { 'column' => 'project_id' },
        { 'column' => 'calculation_xyz', 'formulaId' => 'calculation_xyz' },
      ],
      'filters' => [{ 'column' => 'region', 'filterType' => 'IN', 'values' => ['West'] }],
      'groupBy' => [{ 'column' => 'project_id' }],
      'orderBy' => [{ 'column' => 'project_id' }],
      'limit' => 25,
    } },
    'formulas' => [{ 'id' => 'calculation_xyz', 'name' => 'Days Open', 'formula' => 'DATEDIFF(`close`,`open`)' }],
    'conditionalFormats' => [{ 'condition' => { 'column' => 'x' }, 'format' => {} }],
  },
}
b = normalize_card(shape_b, 'card-B')
eq(b['_shape'], 'B', 'shape detected B')
eq(b['title'], 'Project List', 'title from dynamicTitle')
eq(b['sigmaKindHint'], 'table', 'kind hint table')
eq(b['columns'][1]['beastModeId'], 'calculation_xyz', 'beastModeId joined via calculation_ id')
eq(b['filters'], [{ 'column' => 'region', 'operator' => 'IN', 'values' => ['West'] }], 'filter normalized (filterType→operator)')
eq(b['groupBy'], ['project_id'], 'groupBy flattened (Shape B)')
eq(b['cardFormulas'].first['name'], 'Days Open', 'card formulas from definition.formulas')
eq(b['limit'], 25, 'limit carried through Shape B normalization (bead 2ef7)')

puts "== normalize_card: no limit declared -> key absent, not zero =="
no_limit = normalize_card({ 'chartType' => 'badge_table', 'chartBody' => { 'columns' => [{ 'column' => 'x' }] } }, 'card-C')
ok(!no_limit.key?('limit'), 'no limit key when the source declared none (compact drops nil, never defaults to 0)')

puts "== norm_summary_number: COUNT-of-id trap =="
sn = norm_summary_number({ 'columns' => [{ 'column' => 'project_id', 'aggregation' => 'COUNT' }] })
eq(sn['_defaultCountSuspect'], true, 'COUNT flagged as default-count suspect (#1 KPI bug guard)')

puts "== dig_beast_modes: dataset map + card formulas =="
ds_map = { 'calculation_ds1' => { 'id' => 'calculation_ds1', 'name' => 'DS Calc',
                                  'formula' => 'SUM(`x`)', 'templateId' => 'calculation_ds1' } }
card = { 'id' => 'c1', 'datasetId' => 'ds-2',
         'cardFormulas' => [{ 'id' => 'calculation_c1', 'name' => 'Card Calc', 'formula' => "CONCAT(`a`,`b`)" }] }
bms = dig_beast_modes(card, ds_map, {})
eq(bms.map { |x| x['scope'] }.sort, %w[card dataset], 'both dataset + card beast modes collected')
eq(bms.find { |x| x['scope'] == 'dataset' }['class'], 'aggregate', 'dataset SUM classified aggregate')
eq(bms.find { |x| x['scope'] == 'card' }['class'], 'projection', 'card CONCAT classified projection')

puts "== merge_dataset_permissions: C9 wiring (dataset_formulas permission -> datasets.json) =="
# Synthetic response shaped like Domo.dataset_formulas(dsid) — the SAME call
# already made per-card for Beast Modes (parts=core,permission,formulas). Only
# the top-level `permission` key is asserted; its inner shape is whatever a
# live instance actually returns.
synthetic_dataset_formulas_response = {
  'id' => 'ds-1',
  'properties' => { 'formulas' => { 'formulas' => {} } },
  'permission' => { 'policies' => [
    { 'id' => 'p1', 'name' => 'West only', 'predicates' => ['region = "West"'] },
  ] },
}
permission_cache = { 'ds-1' => synthetic_dataset_formulas_response['permission'] }
datasets = [
  { 'id' => 'ds-1', 'name' => 'Orders' },       # has a captured permission block
  { 'id' => 'ds-2', 'name' => 'No PDP here' },  # no entry in permission_cache
]

merged_count, out = merge_dataset_permissions(datasets, permission_cache)
eq(merged_count, 1, 'exactly one dataset record merged')
eq(out.size, 2, 'record count unchanged')
ds1 = out.find { |d| d['id'] == 'ds-1' }
ds2 = out.find { |d| d['id'] == 'ds-2' }
eq(ds1['permission'], synthetic_dataset_formulas_response['permission'], 'permission attached as-is (no reshaping)')
eq(ds2.key?('permission'), false, 'dataset with no captured permission is left untouched')

# Through the REAL normalize/merge path: detect_pdp (build-dm.rb's C9 reader)
# must find the policy on the merged record — proving the wiring actually
# reaches the existing tolerant reader, end to end.
pols = detect_pdp(ds1)
eq(pols.length, 1, 'detect_pdp finds the merged policy')
eq(pols.first['id'], 'p1', 'detect_pdp reads the policy id off the merged record')
eq(detect_pdp(ds2), [], 'detect_pdp still empty (not nil) for the untouched dataset')

puts "== merge_dataset_permissions: no captured permissions -> no-op =="
no_op_count, no_op_out = merge_dataset_permissions(datasets, {})
eq(no_op_count, 0, 'nothing merged when permission_cache is empty')
eq(no_op_out.none? { |d| d.key?('permission') }, true, 'no dataset gains a permission key')

# ===========================================================================
# Live-validation fixes (refs/live-validation-2026-07-30.md) — Bugs 1-4.
# Fixtures under test/fixtures/domo-live-raw/ are ANONYMIZED derivations of
# the real corpus (structure only — no real titles/columns/connector names).
# ===========================================================================
stacks_fixture = load_fixture('stacks-page.json')
admin_fixture  = load_fixture('cards-adminsummary.json')
public_fixture = load_fixture('cards-public.json')
v3_fixture     = load_fixture('card-definition-v3.json')
v3_beastmode_kpi_fixture = load_fixture('card-definition-v3-beastmode-kpi.json')
orig_dev_token_env = ENV['DOMO_DEV_TOKEN']

puts "== Bug 1: enumerate_page_cards — route 1 (stacks) used when it returns cards =="
with_domo_stub(:cards_for_page, ->(*_a, **_kw) { stacks_fixture }) do
  ids, meta_by_id, stacks = enumerate_page_cards('90210001')
  eq(ids.map(&:to_s).sort, stacks_fixture['cards'].map { |c| c['id'].to_s }.sort,
     'route 1 (stacks) supplies every card id — old code read the (empty) page[\'cardIds\'] instead')
  eq(stacks, stacks_fixture, 'the full stacks payload is returned for the Bug 5 geometry merge')
  eq(meta_by_id['700000001']['metadata']['chartType'], 'badge_map',
     'route 1 per-card record carries metadata.chartType (feeds Bug 3 chartType resolution)')
end

puts "== Bug 1: enumerate_page_cards — route 2 (adminsummary) used when route 1 is empty =="
ENV['DOMO_DEV_TOKEN'] = 'fake-token-for-offline-test'
with_domo_stub(:cards_for_page, ->(*_a, **_kw) { { 'cards' => [] } }) do
  with_domo_stub(:cards_adminsummary, ->(*_a, **_kw) { admin_fixture }) do
    ids, meta_by_id, stacks = enumerate_page_cards('90210001')
    eq(ids.sort, [700000005, 700000006], 'route 2 (adminsummary) card ids used as fallback')
    eq(stacks, nil, 'route 2 supplies no stacks/geometry payload (graceful degradation)')
    eq(meta_by_id['700000005']['title'], 'Metric Epsilon', 'route 2 record carries a title')
  end
end
ENV['DOMO_DEV_TOKEN'] = orig_dev_token_env

puts "== Bug 1: enumerate_page_cards — route 3 (PUBLIC) is reachable on Tier B =="
ENV.delete('DOMO_DEV_TOKEN')  # Tier B: routes 1/2 are private-gated and must not even be attempted
with_domo_stub(:list_cards, ->(*_a, **_kw) { public_fixture }) do
  ids, meta_by_id, stacks = enumerate_page_cards('90210001')
  eq(ids.sort, %w[700000007 700000008],
     'Tier B now yields a real card inventory via the public route, filtered to this page id')
  eq(stacks, nil, 'route 3 supplies no stacks/geometry payload')
  eq(meta_by_id.key?('700000009'), false, 'a card on a DIFFERENT page is excluded')
end
ENV['DOMO_DEV_TOKEN'] = orig_dev_token_env

puts "== Bug 1: Domo.list_cards caps limit at 100 (a higher limit silently returns empty on live Domo) =="
captured_query = nil
with_domo_stub(:public_get, ->(_path, query: nil, **_kw) { captured_query = query; { 'cards' => [] } }) do
  Domo.list_cards(limit: 500, offset: 0)
end
eq(captured_query[:limit], 100, 'Domo.list_cards caps the requested limit at 100 regardless of caller input')

puts "== Bug 1: Domo.cards_adminsummary — filter in BODY, pagination in QUERY params =="
captured_body, captured_query2 = nil, nil
with_domo_stub(:private_post, ->(_path, body:, query: nil) { captured_body = body; captured_query2 = query; { 'cardAdminSummaries' => [] } }) do
  Domo.cards_adminsummary('90210001', skip: 100, limit: 100)
end
eq(captured_body[:pageIds], ['90210001'], 'adminsummary filter (pageIds/orderBy/ascending) travels in the BODY')
eq([captured_query2[:skip], captured_query2[:limit]], [100, 100],
   'adminsummary pagination (skip/limit) travels in QUERY params, not the body')

puts "== Bug 3: Domo.card_definition_v3 — minimal body, no dynamicText/variables clutter =="
captured_v3_body = nil
with_domo_stub(:private_put, ->(_path, body:, query: nil) { captured_v3_body = body; {} }) do
  Domo.card_definition_v3('700000001')
end
eq(captured_v3_body, { urn: '700000001' }, 'card_definition_v3 body is just {urn: id} — confirmed sufficient live')

puts "== Bug 2: normalize_card — subscriptions.big_number is the summary number =="
stacks_meta_alpha = stacks_fixture['cards'].find { |c| c['id'] == 700000001 }
card_v3 = normalize_card(v3_fixture, '700000001', card_meta: stacks_meta_alpha)
eq(card_v3['summaryNumber'] && card_v3['summaryNumber']['column'], 'metric_alpha',
   'big_number column extracted (nil under old defn/main-summaryNumber-only code — Rule 0 never fired)')
eq(card_v3['summaryNumber'] && card_v3['summaryNumber']['aggregation'], 'SUM', 'big_number aggregation extracted')
eq(card_v3['summaryNumber'] && card_v3['summaryNumber']['label'], 'Metric Alpha in Period', 'big_number label extracted')
eq(card_v3['summaryNumber'] && card_v3['summaryNumber']['_defaultCountSuspect'], false,
   'SUM is not a COUNT-of-id default-count suspect')

puts "== Bug 2: normalize_card — main.columns[].mapping (visual-role binding) surfaced, not dropped =="
mapping_by_column = (card_v3['columns'] || []).each_with_object({}) { |c, h| h[c['column']] = c['mapping'] }
eq(mapping_by_column['category_col'], 'ITEM', 'ITEM mapping surfaced')
eq(mapping_by_column['metric_alpha'], 'VALUE', 'VALUE mapping surfaced')
eq(mapping_by_column['series_col'], 'SERIES', 'SERIES mapping surfaced')

puts "== Bug 3: normalize_card — chartType resolution precedence =="
eq(card_v3['chartType'], 'badge_map',
   'metadata.chartType (from the route-1 enumeration record) wins over definition.charts.main.chartType')
card_v3_no_meta = normalize_card(v3_fixture, '700000001')
eq(card_v3_no_meta['chartType'], 'badge_treemap',
   'with NO enumeration metadata at all, Shape B falls back to its OWN definition.charts.main.chartType ' \
   '(old code produced nil here — this chartType location did not exist in the old resolution chain)')

puts "== Bug 3: parse_card_metadata — JSON-string metadata fields double-parsed, malformed guarded =="
meta_alpha = stacks_fixture['cards'].find { |c| c['id'] == 700000001 }
parsed_alpha = parse_card_metadata(meta_alpha)
eq(parsed_alpha['columnAliases'], { 'state_col' => 'State', 'name_col' => 'Name' },
   'columnAliases JSON string double-parsed into a real Hash')
eq(parsed_alpha['summaryNumberFormat'], { 'type' => 'number', 'format' => '0.0A' },
   'SummaryNumberFormat JSON string double-parsed into a real Hash')

meta_gamma = stacks_fixture['cards'].find { |c| c['id'] == 700000003 }
parsed_gamma = parse_card_metadata(meta_gamma)
eq(parsed_gamma.key?('columnAliases'), false,
   'malformed columnAliases JSON degrades to absent — never raises and aborts discovery for one bad card')
eq(parsed_gamma['chartType'], 'badge_donut', 'chartType still read even when a sibling metadata field is malformed')

eq(card_v3['_metadata'] && card_v3['_metadata']['chartType'], 'badge_map',
   'normalize_card surfaces the parsed metadata on the card record as _metadata')
eq(card_v3['_metadata'] && card_v3['_metadata']['summaryNumberFormat'], { 'type' => 'number', 'format' => '0.0A' },
   '_metadata carries the double-parsed SummaryNumberFormat too')

puts "== Bug 4: dig_beast_modes — inline isAnalytic/isAggregatable preferred over a template fetch =="
template_calls = 0
with_domo_stub(:beast_mode_template, ->(*_a) { template_calls += 1; {} }) do
  card_inline = { 'id' => '700000001', 'datasetId' => nil, 'cardFormulas' => v3_fixture['definition']['formulas'] }
  bms = dig_beast_modes(card_inline, {}, {})
  eq(bms.find { |b| b['name'] == 'Open Rate' }['class'], 'aggregate',
     'isAggregatable:true classified aggregate straight from the inline formula (old code called fetch_template ' \
     'and would classify by the empty-hash stub instead — "projection")')
  eq(bms.find { |b| b['name'] == 'Running Total' }['class'], 'window',
     'isAnalytic:true classified window straight from the inline formula')
  eq(template_calls, 0, 'the standalone template endpoint was NOT called — inline flags were sufficient (Bug 4)')
end

puts "== Bug 4: dig_beast_modes — still falls back to the template fetch when inline flags are absent =="
template_calls2 = 0
with_domo_stub(:beast_mode_template, ->(*_a) { template_calls2 += 1; { 'analytic' => true } }) do
  ENV['DOMO_DEV_TOKEN'] = 'fake-token-for-offline-test'
  card_no_flags = { 'id' => 'c-no-flags',
                    'cardFormulas' => [{ 'id' => 'calculation_nf', 'name' => 'No Flags', 'formula' => 'anything' }] }
  bms2 = dig_beast_modes(card_no_flags, {}, {})
  eq(bms2.first['class'], 'window', 'template-fetch fallback still classifies correctly when inline flags are missing')
  eq(template_calls2, 1, 'the standalone template endpoint IS called when inline flags are absent (fallback preserved)')
  ENV['DOMO_DEV_TOKEN'] = orig_dev_token_env
end

# ===========================================================================
# Bug A (refs/live-validation-2026-07-30.md): a KPI whose measure is a Beast
# Mode extracted with NO value. Live Domo binds the summary number's measure
# by `formulaId` (with NO `column`/`aggregation` on that columns[] entry) when
# the measure is a Beast Mode — resolve it against the card's own
# definition.formulas[] and surface the Beast Mode's name, never inventing an
# aggregation the SQL already applies.
# ===========================================================================
puts "== Bug A: norm_summary_number — Beast Mode summary number resolved via formulaId =="
beastmode_card = normalize_card(v3_beastmode_kpi_fixture, '700000010')
sn_bm = beastmode_card['summaryNumber']
eq(sn_bm && sn_bm['column'], 'Metric Ratio Pct',
   "formulaId resolved against this card's OWN definition.formulas[] -> the Beast Mode's name becomes the measure " \
   '(nil under old code, which only ever read column/dataColumn/field)')
eq(sn_bm && sn_bm.key?('aggregation'), false,
   'NO aggregation is invented for a Beast Mode measure — the SQL already aggregates; wrapping it in another ' \
   'Agg(...) downstream would silently double-aggregate')
eq(sn_bm && sn_bm['_isCalc'], true, '_isCalc marks this as a calc/formula reference, not a raw warehouse column')
eq(sn_bm && sn_bm['beastModeId'], 'calculation_44444444-aaaa-bbbb-cccc-444444444444',
   'beastModeId carries the formulaId so the build step can join it against dig_beast_modes\' output')
eq(sn_bm && sn_bm['label'], 'Metric Ratio Pct', 'label still comes from the columns[] entry\'s own alias')
eq(sn_bm && sn_bm['_defaultCountSuspect'], false,
   '_defaultCountSuspect still correctly false for a Beast Mode measure (no aggregation to misread as COUNT)')

puts "== Bug A: norm_summary_number — plain-column COUNT case is UNCHANGED (no regression) =="
sn_count = norm_summary_number({ 'columns' => [{ 'column' => 'project_id', 'aggregation' => 'COUNT' }] })
eq(sn_count['_defaultCountSuspect'], true, '_defaultCountSuspect keeps working for the plain-column COUNT case')
eq(sn_count.key?('_isCalc'), false, 'a plain column is never marked _isCalc')

puts "== Bug A: norm_summary_number — an UNRESOLVED formulaId warns loudly and never leaves a nil measure =="
sn_unresolved = nil
unresolved_warning = capture_stderr do
  sn_unresolved = norm_summary_number(
    { 'columns' => [{ 'formulaId' => 'calculation_does_not_exist', 'alias' => 'Mystery KPI' }] },
    formulas: [{ 'id' => 'calculation_other', 'name' => 'Other Calc', 'formula' => 'SUM(`x`)' }],
    card_id: 'card-mystery'
  )
end
eq(sn_unresolved['column'], 'calculation_does_not_exist',
   'an unresolved formulaId falls back to the raw formulaId — never a silent nil measure')
eq(sn_unresolved.key?('_isCalc'), false, 'an unresolved formulaId is NOT marked _isCalc — we could not confirm it IS one')
ok(unresolved_warning.include?('card-mystery') && unresolved_warning.include?('calculation_does_not_exist'),
   'the warning names BOTH the card and the unresolved formulaId')

# ===========================================================================
# Bug C (refs/live-validation-2026-07-30.md): Beast Mode classification trusts
# unreliable Domo flags. Live evidence: 4/4 Beast Modes on a run reported
# isAggregatable:false, isAnalytic:false despite plainly-aggregate SQL, and
# the OLD classify_beast_mode short-circuited on `template.is_a?(Hash)` and
# never looked at the SQL at all once a flag pair was present. Fix: always
# scan the SQL; let a positive scan override a `false` flag.
# ===========================================================================
puts "== Bug C: classify_beast_mode — SQL cross-check overrides an unreliable FALSE/FALSE flag pair =="
false_flag_ratio_sql = '(CASE WHEN (SUM(`metric_denominator`) = 0) THEN 0 ELSE ' \
                        '(SUM(`metric_numerator`) / SUM(`metric_denominator`)) END )'
eq(classify_beast_mode(false_flag_ratio_sql, { 'isAnalytic' => false, 'isAggregatable' => false }), 'aggregate',
   'a CASE-wrapped ratio-of-SUMs is classified aggregate even though BOTH flags say false — the exact live ' \
   'misclassification (old code returned "projection" here)')

count_distinct_sql = '(SUM(`metric_numerator`) / COUNT(DISTINCT `metric_denominator`))'
eq(classify_beast_mode(count_distinct_sql, { 'isAnalytic' => false, 'isAggregatable' => false }), 'aggregate',
   'SUM(...) / COUNT(DISTINCT ...) with false/false flags is still classified aggregate')

window_false_flag_sql = 'ROW_NUMBER() OVER (ORDER BY `date_col`)'
eq(classify_beast_mode(window_false_flag_sql, { 'isAnalytic' => false, 'isAggregatable' => false }), 'window',
   'a ROW_NUMBER()/OVER construct is classified window even though isAnalytic says false')

mixed_flags_sql = 'RANK() OVER (ORDER BY `metric_numerator`)'
eq(classify_beast_mode(mixed_flags_sql, { 'isAnalytic' => false, 'isAggregatable' => true }), 'window',
   'a window construct wins over an aggregate hint/flag — most-specific-class-wins ordering (window > aggregate)')

puts "== Bug C: false-positive guard — a bare column that merely CONTAINS an aggregate name must not misfire =="
eq(sql_has_aggregate_call?('`SUMMARY_COLUMN` + 1'), false,
   'SUMMARY_COLUMN does not match SUM — only a function-CALL shape (name immediately followed by "(") counts')
eq(sql_has_aggregate_call?('SUM(`x`)'), true, 'a genuine SUM( call still matches')
eq(classify_beast_mode('`SUMMARY_COLUMN` + 1'), 'projection',
   'end-to-end: a column named SUMMARY_COLUMN is classified projection, never aggregate')

puts "== Bug C: dig_beast_modes end-to-end — a card-local Beast Mode with false/false flags is classified " \
     'aggregate, not projection =='
card_falseflag = {
  'id' => 'c-falseflag',
  'cardFormulas' => [
    { 'id' => 'calculation_margin', 'name' => 'Margin Pct', 'formula' => false_flag_ratio_sql,
      'isAnalytic' => false, 'isAggregatable' => false },
  ],
}
bms_falseflag = dig_beast_modes(card_falseflag, {}, {})
eq(bms_falseflag.first['class'], 'aggregate',
   'end-to-end through dig_beast_modes: isAnalytic:false/isAggregatable:false but aggregate SQL is classified ' \
   'aggregate, not projection — the exact live misclassification this bug describes')

puts "== bonus: Domo.decode_render — image.data as a nested Hash (confirmed live shape) =="
# refs/live-validation-2026-07-30.md: the render endpoint returns a JSON
# envelope {"image": {"data": "<b64>", ...}, ...} — json['image'] is a HASH,
# which is truthy in Ruby, so the old `json['image'] || ... || json.dig(
# 'image','data')` short-circuited on the Hash and never reached the real
# base64 string.
FakeRenderResponse = Struct.new(:body) do
  def [](key)
    key == 'content-type' ? 'application/json' : nil
  end
end
envelope = { 'image' => { 'data' => Base64.strict_encode64('PNGDATA'), 'notAllDataShown' => false },
             'limited' => false, 'notAllDataShown' => false }
render_res = FakeRenderResponse.new(JSON.generate(envelope))
eq(Domo.decode_render(render_res), 'PNGDATA',
   'image.data extracted correctly even though json["image"] is a Hash, not a bare base64 string')

puts
if $failures.zero?
  puts "ALL PASS"
  exit 0
else
  puts "#{$failures} FAILURE(S)"
  exit 1
end
