#!/usr/bin/env ruby
# Offline: build-domo-layout.rb's zone chart_kind must be the LOGICAL 'kpi'
# tag that lib/layout.rb's kpi_like_zone? (vendored VERBATIM from
# tableau-to-sigma — do not diverge that copy) expects, not the Sigma
# ELEMENT kind 'kpi-chart' that domo-discover.rb's separate sigma_kind_hint
# emits for build-workbook.rb's build_kpi. build-domo-layout.rb's kind_hint
# (scripts/build-domo-layout.rb:33) used to stamp 'kpi-chart' onto the zone,
# so a Domo KPI tile that failed the plain size heuristic silently missed
# KPI-row detection instead of grouping into one GridContainer.
#   ruby test/test-layout-tag.rb
require 'stringio'
require 'tmpdir'
require_relative '../scripts/lib/layout'
require_relative '../scripts/build-domo-layout'

$failures = 0
def eq(actual, expected, msg)
  if actual == expected
    puts "  ok: #{msg}"
  else
    $failures += 1
    puts "  FAIL: #{msg}\n        expected #{expected.inspect}\n        got      #{actual.inspect}"
  end
end
def ok(cond, msg) eq(!!cond, true, msg) end

# Kernel#warn writes to $stderr — swap it for a StringIO so the "warn loudly,
# never silently" behaviour below is an ASSERTION, not an eyeballed log line.
def capture_stderr
  old = $stderr
  $stderr = StringIO.new
  yield
  $stderr.string
ensure
  $stderr = old
end

puts "== kind_hint: Domo singlevalue/summary/badge cards -> logical 'kpi' (not 'kpi-chart') =="
eq(kind_hint('badge'), 'kpi', "chartType 'badge' -> 'kpi'")
eq(kind_hint('singlevalue'), 'kpi', "chartType containing 'singlevalue' -> 'kpi'")
eq(kind_hint('summary_number'), 'kpi', "chartType containing 'summary' -> 'kpi'")
eq(kind_hint('filter'), 'filter', "chartType 'filter' unaffected")

puts "== build_dashboard: a KPI card's zone carries chart_kind=='kpi' =="
# Two cards so max_x/max_y come from their combined extent — the KPI card's
# own w_pct/h_pct end up WAY over the plain size heuristic thresholds
# (KPI_MAX_W_PCT 40 / KPI_MAX_H_PCT 12), isolating detection via the
# chart_kind tag rather than a heuristic size coincidence. Cards use cards.json's
# own 'id' field (domo-discover.rb's normalize_card), not the old capture-visuals
# 'cardId' shape — build-domo-layout.rb now sources geometry from cards.json.
cards = [
  { 'id' => 'kpi1', 'title' => 'Total Revenue', 'chartType' => 'badge',
    'x' => 0, 'y' => 0, 'w' => 80, 'h' => 50 },
  { 'id' => 't1', 'title' => 'Detail', 'chartType' => 'table',
    'x' => 80, 'y' => 0, 'w' => 20, 'h' => 10 },
]
dashboard = build_dashboard('Overview', cards)
kpi_zone = dashboard['zones'].find { |z| z['id'] == 'kpi1' }
ok(kpi_zone, 'KPI card produced a zone')
eq(kpi_zone['chart_kind'], 'kpi', "zone chart_kind is the logical 'kpi', not the element kind 'kpi-chart'")
ok(kpi_zone['w_pct'] > SigmaLayout::KPI_MAX_W_PCT || kpi_zone['h_pct'] > SigmaLayout::KPI_MAX_H_PCT,
   'sanity: this zone geometry exceeds the size heuristic, so detection below can only come from the tag')

puts "== lib/layout.rb's UNCHANGED kpi_like_zone? detects the corrected tag =="
ok(SigmaLayout.kpi_like_zone?(kpi_zone), "build-domo-layout's 'kpi'-tagged zone is detected as KPI-like")

puts "== no regression: a plain chart zone (non-KPI) is not swept in =="
tbl_zone = dashboard['zones'].find { |z| z['id'] == 't1' }
eq(tbl_zone['chart_kind'], 'table', "non-KPI card keeps its own chart_kind")

# ===========================================================================
# Live-validation fix (refs/live-validation-2026-07-30.md): classic Domo pages
# expose NO x/y/w/h at all — only a per-card `size` T-shirt token and titled
# `collections[]` that group cards by index. The tests below exercise the new
# rung-2/rung-3 fallback (build-domo-layout.rb) directly, function-level, so
# a regression here fails fast without needing the full CLI subprocess (see
# test-build-domo-layout.rb for the CLI/subprocess-level coverage of the same
# fix, including the run's stderr output).
# ===========================================================================

puts "== normalize_size_token: known family passes through; unknown WARNS -> 'medium' =="
eq(normalize_size_token('medium'), 'medium', "'medium' passes through unchanged")
eq(normalize_size_token('SMALL'), 'small', "case-insensitive: 'SMALL' -> 'small'")
eq(normalize_size_token(nil), 'medium', 'a genuinely MISSING token defaults to medium silently')
ok(capture_stderr { normalize_size_token(nil) }.strip.empty?, 'a missing token does not warn')
ok(capture_stderr { normalize_size_token('medium') }.strip.empty?, 'a KNOWN token does not warn')
warned = capture_stderr { eq(normalize_size_token('huge'), 'medium', "unrecognized token 'huge' falls back to 'medium'") }
ok(warned.include?('huge') && warned.include?('medium'),
   'an UNRECOGNIZED size token WARNS (never a silent guess) and names the bad token')

# ===========================================================================
# Bug B (refs/live-validation-2026-07-30.md), part 2: for cards created via
# Domo's public write API, live sizes[] carries the EMPTY STRING as the token
# (e.g. {"id":"189217601","size":""}) — NOT "medium". "" is the NORMAL,
# expected "unspecified" value, not a genuine anomaly, so it must degrade to
# the documented default WITHOUT spamming a warning per card — unlike a truly
# unrecognized non-empty token (asserted above), which still deserves one.
# ===========================================================================
puts "== normalize_size_token: the EMPTY STRING (API-created cards) degrades to 'medium' SILENTLY, like nil =="
eq(normalize_size_token(''), 'medium', 'an empty-string token (the live API-created-card shape) defaults to medium')
ok(capture_stderr { normalize_size_token('') }.strip.empty?,
   '"" does NOT warn — it is the normal, expected value for an API-created card, not an unrecognized token')
eq(normalize_size_token('   '), 'medium', 'a blank (whitespace-only) token also defaults to medium')
ok(capture_stderr { normalize_size_token('   ') }.strip.empty?, 'a blank (whitespace-only) token does not warn either')

puts "== card_width_units: an empty-string '_size' (API-created card) still resolves a usable width, no crash =="
eq(card_width_units({ '_size' => '' }), 3.0,
   "an empty '_size' token resolves via normalize_size_token's default ('medium' -> 3 of 6), not a KeyError")
eq(card_width_units({ '_size' => '', 'preferredFullWidth' => 4 }), 4.0,
   'preferredFullWidth STILL wins over an empty _size token, exactly as it does over a real token')

puts "== card_width_units: preferredFullWidth overrides the size-token lookup =="
# '_size' is DomoSigma.merge_geometry's field name (Bug 5) for the raw
# stacks['sizes'] token.
eq(card_width_units({ '_size' => 'small' }), 2.0, "size token 'small' -> 2 of Domo's 6 native grid columns")
eq(card_width_units({ '_size' => 'medium' }), 3.0, "size token 'medium' -> 3 of 6")
eq(card_width_units({ '_size' => 'large' }), 6.0, "size token 'large' -> 6 of 6 (a full row)")
eq(card_width_units({ '_size' => 'small', 'preferredFullWidth' => 5 }), 5.0,
   'an explicit preferredFullWidth WINS over the size token (5, not small\'s 2)')
eq(card_width_units({ '_size' => 'small', 'preferredFullWidth' => 9 }), 6.0,
   'preferredFullWidth is clamped to the Domo grid ceiling of 6 (Domo itself rejects >6 live)')
eq(card_height_units({}), 4.0, 'no preferredFullHeight -> the flat ROW_HEIGHT_UNITS default')
eq(card_height_units({ 'preferredFullHeight' => 2 }), 2.0, 'an explicit preferredFullHeight overrides the default')

puts "== group_into_sections: sections ordered by min _pageOrder; cards by _pageOrder; ungrouped trails =="
# '_collection' ({'id','title','index'}) and '_pageOrder' are
# DomoSigma.merge_geometry's field names (Bug 5) — 'index' inside
# '_collection' is the CARD's own stacks-array position (same number as
# '_pageOrder'), not a collection sequence number, so section order is
# derived from the MIN '_pageOrder' across each collection's cards.
mixed = [
  { 'id' => 'x1', '_collection' => { 'id' => 2, 'title' => 'Second', 'index' => 3 }, '_pageOrder' => 3 },
  { 'id' => 'x2', '_collection' => { 'id' => 1, 'title' => 'First',  'index' => 1 }, '_pageOrder' => 1 },
  { 'id' => 'x3', '_collection' => { 'id' => 1, 'title' => 'First',  'index' => 0 }, '_pageOrder' => 0 },
  { 'id' => 'x4', '_pageOrder' => 5 }, # ungrouped: no '_collection' at all
  { 'id' => 'x5', '_collection' => { 'id' => 2, 'title' => 'Second', 'index' => 2 }, '_pageOrder' => 2 },
]
sections = group_into_sections(mixed)
eq(sections.map { |s| s['title'] }, ['First', 'Second', nil],
   'sections ordered by their cards\' minimum _pageOrder (First before Second); ungrouped section trails, untitled')
eq(sections[0]['cards'].map { |c| c['id'] }, %w[x3 x2], "'First' section's cards ordered by _pageOrder")
eq(sections[1]['cards'].map { |c| c['id'] }, %w[x5 x1], "'Second' section's cards ordered by _pageOrder")
eq(sections[2]['cards'].map { |c| c['id'] }, %w[x4], 'the lone ungrouped card lands in the trailing section, never dropped')

puts "== build_dashboard_from_collections: a real 2D grid from collections[] + size tokens — NO x/y/w/h anywhere =="
cards2 = [
  # Section 0 "Group A": two 'medium' (3-of-6) cards -> exactly fill one row, side by side
  { 'id' => 'a1', 'title' => 'Card A1', 'chartType' => 'badge_vert_bar', '_size' => 'medium',
    '_collection' => { 'id' => 10, 'title' => 'Group A', 'index' => 0 }, '_pageOrder' => 0 },
  { 'id' => 'a2', 'title' => 'Card A2', 'chartType' => 'badge_vert_bar', '_size' => 'medium',
    '_collection' => { 'id' => 10, 'title' => 'Group A', 'index' => 1 }, '_pageOrder' => 1 },
  # Section 1 "Group B": one 'large' (6-of-6, full row) card -> its own row
  { 'id' => 'b1', 'title' => 'Card B1', 'chartType' => 'badge', '_size' => 'large',
    '_collection' => { 'id' => 11, 'title' => 'Group B', 'index' => 2 }, '_pageOrder' => 2 },
]
dash2 = build_dashboard_from_collections('Classic Page', cards2)
ok(dash2, 'build_dashboard_from_collections returns a dashboard for cards with NO x/y/w/h at all')
zones2 = dash2['zones']

hdr_a = zones2.find { |z| z['kind'] == 'text' && z['caption'] == 'Group A' }
hdr_b = zones2.find { |z| z['kind'] == 'text' && z['caption'] == 'Group B' }
ok(hdr_a && hdr_b, 'each collection got its own heading zone, titled with the collection title')
ok(hdr_a['y_pct'] < hdr_b['y_pct'], "section headings are ordered top-to-bottom by their cards' _pageOrder")

za1 = zones2.find { |z| z['id'] == 'a1' }
za2 = zones2.find { |z| z['id'] == 'a2' }
zb1 = zones2.find { |z| z['id'] == 'b1' }
eq(za1['y_pct'], za2['y_pct'], 'a1 and a2 (both medium, same collection) share a row (identical y_pct)')
ok(za1['x_pct'] != za2['x_pct'], 'a1 and a2 sit at DISTINCT x_pct on that shared row — a real 2D grid, not a stack')
eq(za1['w_pct'], 50.0, "a 'medium' card is 3 of Domo's 6 native grid columns -> 50% width")
eq(zb1['w_pct'], 100.0, "a 'large' card is 6 of 6 native grid columns -> 100% (full row) width")
eq(zb1['x_pct'], 0.0, "a full-width 'large' card starts at x_pct 0")
ok(zb1['y_pct'] > za1['y_pct'], "Group B's row sits below Group A's row")
ok(zones2.all? { |z| z['kind'] == 'chart' ? Array(z['measures']) == ['value'] : true },
   'every real chart zone still carries a non-empty measures array (ZoneCensus.plots? must count it)')

content = ZoneCensus.content_zones(zones2)
by_row = content.group_by { |z| z['y_pct'].to_f.round(1) }
grid = by_row.values.any? { |zs| zs.map { |z| z['x_pct'].to_f.round(1) }.uniq.size >= 2 }
ok(grid, "the collections+size-token zones read as a 'grid' under migrate-domo.rb's OWN 2D-flag rule " \
         "(content_zones grouped by rounded y_pct, >= 2 distinct x_pct sharing a row) — the fix this whole " \
         'chain exists for: a classic page must NOT degrade to a single-column stack')

puts "== build_stack_fallback: absolute last resort — single column, but WARNS LOUDLY (never silent) =="
cards3 = [
  { 'id' => 's1', 'title' => 'No Geometry At All', 'chartType' => 'badge_vert_bar' },
  { 'id' => 's2', 'title' => 'Still No Geometry',  'chartType' => 'table' },
]
stack_dash = nil
warned3 = capture_stderr { stack_dash = build_stack_fallback('Degraded Page', cards3) }
ok(warned3.include?('WARNING') && warned3.include?('Degraded Page'),
   'the stack fallback prints a loud, page-named WARNING every time it fires — never the silent stack the ' \
   'pre-live-validation bug shipped')
zones3 = stack_dash['zones']
eq(zones3.map { |z| z['x_pct'] }.uniq, [0.0], 'every stacked zone starts at x_pct 0 (single column)')
eq(zones3.map { |z| z['w_pct'] }.uniq, [100.0], 'every stacked zone is full width (100%)')
ok(zones3[0]['y_pct'] < zones3[1]['y_pct'], 'stacked zones are still ordered top-to-bottom, not overlapping')

puts "== build_dashboard_for_page: the orchestrator picks the highest-fidelity rung that has data =="
eq(build_dashboard_for_page('Empty', []), nil, 'an empty card list returns nil (no dashboard) — no abort-worthy page')
pixel_cards = [{ 'id' => 'p1', 'title' => 'Pix', 'chartType' => 'table', 'x' => 0, 'y' => 0, 'w' => 10, 'h' => 10 }]
pixel_dash = build_dashboard_for_page('Pixel Page', pixel_cards)
eq(pixel_dash['zones'].first['id'], 'p1', 'a page WITH real x/y/w/h still uses rung 1 (build_dashboard) unchanged')

# ===========================================================================
# Phase 5e visual-QA fix (refs/layout-visual-qa.md, refs/
# live-validation-2026-07-30.md): "2a" kind-aware default composition.
# Real live discovery (a 15-card / 3-page no-geometry run) showed EVERY card
# with '_size' => "" and no collections at all — the exact rung-2 shape
# below — yet the OLD build_dashboard_from_collections gave every card the
# same flat 'medium' width/height regardless of kind, so 4 KPIs each got a
# full chart-sized band instead of sharing one compact row. These tests
# exercise the fix at the function level; test-build-domo-layout.rb covers
# the same fix through the real CLI subprocess with a fixtures/ dataset.
# ===========================================================================

puts "== composition_class: buckets both the Sigma element-kind vocabulary AND kind_hint's logical vocabulary =="
eq(composition_class('kpi-chart'), :kpi, "Sigma element kind 'kpi-chart' -> :kpi")
eq(composition_class('kpi'), :kpi, "kind_hint's logical 'kpi' -> :kpi (same bucket, different vocabulary)")
eq(composition_class('table'), :table, "'table' -> :table")
eq(composition_class('pivot-table'), :table, "'pivot-table' -> :table (chart-specs/Sigma-only kind, never emitted by kind_hint)")
eq(composition_class('bar-chart'), :chart, "'bar-chart' -> :chart")
eq(composition_class('combo-chart'), :chart, "'combo-chart' -> :chart (a chart-specs-only resolved kind kind_hint never emits)")
eq(composition_class('donut-chart'), :chart, "'donut-chart' -> :chart")
eq(composition_class('control'), :control, "'control' (a Sigma filter element) -> :control (its own house-style band)")
eq(composition_class('filter'), :control, "kind_hint's logical 'filter' -> :control (same bucket, different vocabulary)")
eq(composition_class('text'), :other, "'text' -> :other (not a named house-style band)")
eq(composition_class(nil), :other, 'nil -> :other, never raises')

puts "== element_kind_for: chart-specs.json beats sigmaKindHint beats kind_hint(chartType) =="
kind_map = { 'el-42' => 'combo-chart' }
card_all_three = { 'id' => 42, 'chartType' => 'badge_horiz_bar', 'sigmaKindHint' => 'bar-chart' }
eq(element_kind_for(card_all_three, kind_map), 'combo-chart',
   "chart-specs.json's resolved kind wins even though sigmaKindHint/chartType both say a plain bar — mirrors the " \
   "real live divergence (a badge_line_bar card whose EARLIER sigmaKindHint guess said 'bar-chart' but " \
   "build-workbook.rb's own final resolution promoted it to 'combo-chart')")
card_hint_only = { 'id' => 99, 'chartType' => 'badge_horiz_bar', 'sigmaKindHint' => 'bar-chart' }
eq(element_kind_for(card_hint_only, {}), 'bar-chart', 'no chart-specs entry -> falls back to sigmaKindHint')
card_chart_type_only = { 'id' => 100, 'chartType' => 'badge_vert_bar' }
eq(element_kind_for(card_chart_type_only, {}), 'bar-chart',
   'no chart-specs entry, no sigmaKindHint -> falls back to kind_hint(chartType)')

puts "== zone_chart_kind_for: normalizes to the ZONE vocabulary (literal 'kpi'/'filter'), passes through the rest =="
eq(zone_chart_kind_for({ 'id' => 1, 'sigmaKindHint' => 'kpi-chart' }, {}), 'kpi',
   "resolved 'kpi-chart' -> zone tag 'kpi' (kpi_like_zone? contract, same as build_dashboard's own kind_hint)")
eq(zone_chart_kind_for({ 'id' => 2, 'sigmaKindHint' => 'control' }, {}), 'filter', "resolved 'control' -> zone tag 'filter'")
eq(zone_chart_kind_for({ 'id' => 3, 'sigmaKindHint' => 'combo-chart' }, {}), 'combo-chart',
   'any other resolved kind passes through UNCHANGED (min_rows_for_zone only special-cases kpi/table/pivot-table)')

puts "== has_width_signal?: a REAL signal (non-empty token or numeric preferred*) vs genuinely none =="
ok(has_width_signal?({ '_size' => 'medium' }), "a known non-empty token IS a real signal")
ok(has_width_signal?({ '_size' => 'huge-token' }), "an UNRECOGNIZED non-empty token still counts as a real signal " \
                                                    '(Domo told us something, even if we don\'t know its span)')
ok(has_width_signal?({ 'preferredFullWidth' => 4 }), 'a numeric preferredFullWidth is a real signal')
ok(has_width_signal?({ 'preferredFullHeight' => 2 }), 'a numeric preferredFullHeight is a real signal')
ok(!has_width_signal?({ '_size' => '' }), "the live API-created-card shape ('_size' => \"\") is NOT a real signal")
ok(!has_width_signal?({ '_size' => '   ' }), 'a blank/whitespace-only token is NOT a real signal')
ok(!has_width_signal?({}), 'no _size key and no preferred* fields at all is NOT a real signal')

puts "== balanced_chunk_sizes: n items into groups of <= max, sizes differ by <= 1, remainder to the LAST groups =="
eq(balanced_chunk_sizes(4, 6), [4], 'n=4 <= max -> one row of 4 (the common 4-KPI case)')
eq(balanced_chunk_sizes(6, 6), [6], 'n=6 == max -> one row of 6')
eq(balanced_chunk_sizes(7, 6), [3, 4], 'n=7 > max -> [3,4], NOT the greedy [6,1] straggler')
eq(balanced_chunk_sizes(1, 6), [1], 'n=1 -> a single row of 1 (still handled, see kpi_row_widths for its width)')
eq(balanced_chunk_sizes(0, 6), [], 'n=0 -> no rows')

puts "== kpi_row_widths: even split of Domo's native 6-col row; a LONE kpi is capped at half, not full width =="
eq(kpi_row_widths(4), [1.5, 1.5, 1.5, 1.5], "4 KPIs -> 1.5 native units each (25% of 6, i.e. 6-of-24 Sigma cols each)")
eq(kpi_row_widths(3), [2.0, 2.0, 2.0], '3 KPIs -> 2.0 each (33.3%, i.e. 8-of-24 Sigma cols each)')
eq(kpi_row_widths(2), [3.0, 3.0], '2 KPIs -> 3.0 each (50%, i.e. 12-of-24 Sigma cols each)')
eq(kpi_row_widths(6), [1.0] * 6, '6 KPIs -> 1.0 each (16.7%, i.e. 4-of-24 Sigma cols each)')
eq(kpi_row_widths(1), [3.0], 'a LONE kpi (no peers) is still capped at HALF width (divisor clamped to 2), never full-row')

# ===========================================================================
# compose_kind_aware_rows / build_dashboard_from_collections, end to end —
# fixture SHAPE derived from a real 15-card/3-page no-geometry live discovery
# run (anonymized; see also test/fixtures/domo-nogeom for the CLI-level
# equivalent). Page A mirrors that run's 6-card page: 4 KPIs interleaved with
# 2 charts in _pageOrder (KPI, chart, KPI, KPI, chart, KPI) — DELIBERATELY
# interleaved, not pre-grouped, because that interleaving is exactly what a
# naive "consecutive runs only" grouping would fail to fix (see this
# function's own header comment on the file). All cards share the live
# API-created-card shape: '_size' => "", no '_collection', '_pageOrder' only.
# ===========================================================================
puts "== compose_kind_aware_rows / build_dashboard_from_collections: interleaved KPI/chart page -> " \
     "ONE compact KPI row + ONE paired chart row =="
page_a = [
  { 'id' => 'u1', 'title' => 'Metric Units',   'chartType' => 'badge_singlevalue', 'sigmaKindHint' => 'kpi-chart',
    '_size' => '', '_pageOrder' => 0 },
  { 'id' => 'c1', 'title' => 'Trend Line',     'chartType' => 'badge_symbolline',  'sigmaKindHint' => 'line-chart',
    '_size' => '', '_pageOrder' => 1 },
  { 'id' => 'u2', 'title' => 'Metric Revenue', 'chartType' => 'badge_singlevalue', 'sigmaKindHint' => 'kpi-chart',
    '_size' => '', '_pageOrder' => 2 },
  { 'id' => 'u3', 'title' => 'Metric Margin',  'chartType' => 'badge_singlevalue', 'sigmaKindHint' => 'kpi-chart',
    '_size' => '', '_pageOrder' => 3 },
  { 'id' => 'c2', 'title' => 'Category Bar',   'chartType' => 'badge_horiz_bar',   'sigmaKindHint' => 'bar-chart',
    '_size' => '', '_pageOrder' => 4 },
  { 'id' => 'u4', 'title' => 'Metric Orders',  'chartType' => 'badge_singlevalue', 'sigmaKindHint' => 'kpi-chart',
    '_size' => '', '_pageOrder' => 5 },
]
dash_a = build_dashboard_from_collections('Page A', page_a)
ok(dash_a, 'a page with NO width signal on any card still produces a dashboard')
zones_a = dash_a['zones']

kpi_zones = %w[u1 u2 u3 u4].map { |id| zones_a.find { |z| z['id'] == id } }
chart_zones = %w[c1 c2].map { |id| zones_a.find { |z| z['id'] == id } }
ok(kpi_zones.all?, 'all 4 KPI zones were placed')
ok(chart_zones.all?, 'both chart zones were placed')

eq(kpi_zones.map { |z| z['y_pct'] }.uniq.length, 1,
   'all 4 KPIs share ONE y-band — a single ROW, not one-per-band (the bug this task fixes) — ' \
   'even though u1/u2/u3/u4 were interleaved with c1/c2 in the source _pageOrder')
eq(kpi_zones.map { |z| z['chart_kind'] }.uniq, ['kpi'], "every KPI zone is tagged chart_kind 'kpi' (kpi_like_zone? contract)")
eq(kpi_zones.map { |z| z['w_pct'] }, [25.0, 25.0, 25.0, 25.0],
   '4 KPIs sharing a row -> exactly 25% each (6-of-24 Sigma cols), per WHAT TO BUILD #1')
eq(kpi_zones.map { |z| z['x_pct'] }, [0.0, 25.0, 50.0, 75.0],
   'the 4 KPI zones sit at DISTINCT, sequential x_pct — a real row, not stacked at x=0 — ' \
   'IN THEIR OWN _pageOrder (u1 < u2 < u3 < u4), i.e. source order preserved WITHIN the KPI grouping (WHAT TO BUILD #4)')

eq(chart_zones.map { |z| z['y_pct'] }.uniq.length, 1, 'both chart zones share ONE y-band — paired on one row')
ok(chart_zones.first['y_pct'] > kpi_zones.first['y_pct'], 'the chart row sits BELOW the KPI row (house-style band order)')
eq(chart_zones.map { |z| z['w_pct'] }, [50.0, 50.0], '2 charts pairing -> exactly 50% each (12-of-24 Sigma cols), per WHAT TO BUILD #2')
eq(chart_zones.map { |z| z['x_pct'] }, [0.0, 50.0],
   'the 2 chart zones sit side by side in their OWN _pageOrder (c1 before c2), not stacked')
eq(chart_zones.map { |z| z['chart_kind'] }, %w[line-chart bar-chart],
   "each chart zone keeps its OWN resolved kind (from sigmaKindHint here) — not flattened to a generic 'chart'")

ok(chart_zones.first['h_pct'] > kpi_zones.first['h_pct'],
   'the chart row is noticeably TALLER than the KPI row (CHART_ROW_HEIGHT_UNITS > KPI_ROW_HEIGHT_UNITS) — ' \
   'a KPI must never occupy the same footprint as a full chart (WHAT TO BUILD #1)')

content_a = ZoneCensus.content_zones(zones_a)
by_row_a = content_a.group_by { |z| z['y_pct'].to_f.round(1) }
grid_a = by_row_a.values.any? { |zs| zs.map { |z| z['x_pct'].to_f.round(1) }.uniq.size >= 2 }
ok(grid_a, "the kind-aware composition still classifies as a 'grid' under migrate-domo.rb's own layout-2d.flag rule")

# ---- Page B: chart/chart/table/chart (a run of 3 charts, one lone trailing) --
puts "== compose_kind_aware_rows: an ODD number of charts pairs 2-up, the trailing lone chart gets FULL width; " \
     "a table always gets its own full-width row =="
page_b = [
  { 'id' => 'd1', 'title' => 'Share Donut',  'chartType' => 'badge_donut',          'sigmaKindHint' => 'donut-chart',
    '_size' => '', '_pageOrder' => 0 },
  { 'id' => 'b1', 'title' => 'Compare Bar',  'chartType' => 'badge_vert_stackedbar', 'sigmaKindHint' => 'bar-chart',
    '_size' => '', '_pageOrder' => 1 },
  { 'id' => 't1', 'title' => 'Detail Table', 'chartType' => 'badge_table',          'sigmaKindHint' => 'table',
    '_size' => '', '_pageOrder' => 2 },
  { 'id' => 'b2', 'title' => 'Margin Bar',   'chartType' => 'badge_vert_bar',       'sigmaKindHint' => 'bar-chart',
    '_size' => '', '_pageOrder' => 3 },
]
dash_b = build_dashboard_from_collections('Page B', page_b)
zones_b = dash_b['zones']
zd1 = zones_b.find { |z| z['id'] == 'd1' }
zb1 = zones_b.find { |z| z['id'] == 'b1' }
zt1 = zones_b.find { |z| z['id'] == 't1' }
zb2 = zones_b.find { |z| z['id'] == 'b2' }

eq(zd1['y_pct'], zb1['y_pct'], 'd1 and b1 (first pair, in _pageOrder) share a row')
eq([zd1['w_pct'], zb1['w_pct']], [50.0, 50.0], 'the first pair is 50%/50% (paired 2-up)')
eq([zd1['x_pct'], zb1['x_pct']], [0.0, 50.0], 'd1 (pageOrder 0) sits left of b1 (pageOrder 1) — source order preserved')

ok(zb2['y_pct'] != zd1['y_pct'], 'b2 (the odd one out — 3rd chart, no partner) is on its OWN row, not crammed into the first pair')
eq(zb2['w_pct'], 100.0, 'the trailing UNPAIRED chart gets FULL width, per WHAT TO BUILD #2\'s explicit exception')
eq(zb2['x_pct'], 0.0, 'the full-width trailing chart starts at x_pct 0')

eq(zt1['w_pct'], 100.0, 'the table gets FULL width, per WHAT TO BUILD #3')
ok(zt1['h_pct'] > zd1['h_pct'], "the table's row is TALLER than a chart row (TABLE_ROW_HEIGHT_UNITS > CHART_ROW_HEIGHT_UNITS) " \
                                '— tables need more vertical room, per WHAT TO BUILD #3')
eq(zt1['chart_kind'], 'table', "the table zone is tagged chart_kind 'table'")

# ===========================================================================
# Spec refinement (post-brief coordinator note): the default composition
# order is CONTROLS -> KPIs -> charts -> tables — a full-width control band
# FIRST, never left loose/interleaved among charts (refs/layout-visual-qa.md's
# "Building clean in the first place" table: Header -> Control row -> KPI row
# -> Chart row -> Detail table; also millersigma:branded-dashboard-format's
# header -> filter-bar -> KPI row -> trend -> detail shape). This confirms
# control_rows_for is wired FIRST in compose_kind_aware_rows, ahead of every
# other band, and that a lone control still spans the FULL band width (no
# half-width floor the way a lone KPI has).
# ===========================================================================
puts "== control_rows_for: a full-width band, side by side, ahead of everything else =="
eq(control_rows_for([]), [], 'no controls -> no band at all (never an empty row)')
one_ctl = [{ 'id' => 'ctl1' }]
r1 = control_rows_for(one_ctl)
eq(r1.length, 1, 'one control -> one row')
eq(r1.first['row'], [[one_ctl.first, 0.0, 6.0, 'filter', true]],
   'a SOLE control spans the FULL row width (6-of-6 native units, unlike a lone KPI\'s half-width cap) ' \
   'and is tagged kind filter/is_filter=true')
eq(r1.first['height'], CONTROL_ROW_HEIGHT_UNITS, 'the control band uses CONTROL_ROW_HEIGHT_UNITS (short, like a KPI row)')
two_ctls = [{ 'id' => 'ctlA' }, { 'id' => 'ctlB' }]
r2 = control_rows_for(two_ctls)
eq(r2.length, 1, 'two controls still share ONE row (a single control band), not two separate bands')
eq(r2.first['row'].map { |c, x, w, _k, _f| [c['id'], x, w] }, [['ctlA', 0.0, 3.0], ['ctlB', 3.0, 3.0]],
   'two controls split the band 50/50, side by side, in order')

puts "== compose_kind_aware_rows / build_dashboard_from_collections: CONTROLS -> KPIs -> charts -> tables, in that order =="
page_c = [
  { 'id' => 'ctl1', 'title' => 'Region Filter', 'chartType' => 'filter', 'sigmaKindHint' => 'control',
    '_size' => '', '_pageOrder' => 0 },
  { 'id' => 'k1', 'title' => 'Metric One', 'chartType' => 'badge_singlevalue', 'sigmaKindHint' => 'kpi-chart',
    '_size' => '', '_pageOrder' => 1 },
  { 'id' => 'ch1', 'title' => 'Trend One', 'chartType' => 'badge_symbolline', 'sigmaKindHint' => 'line-chart',
    '_size' => '', '_pageOrder' => 2 },
  { 'id' => 'k2', 'title' => 'Metric Two', 'chartType' => 'badge_singlevalue', 'sigmaKindHint' => 'kpi-chart',
    '_size' => '', '_pageOrder' => 3 },
  { 'id' => 'tb1', 'title' => 'Detail', 'chartType' => 'badge_table', 'sigmaKindHint' => 'table',
    '_size' => '', '_pageOrder' => 4 },
  { 'id' => 'ch2', 'title' => 'Trend Two', 'chartType' => 'badge_vert_bar', 'sigmaKindHint' => 'bar-chart',
    '_size' => '', '_pageOrder' => 5 },
]
dash_c = build_dashboard_from_collections('Page C', page_c)
zones_c = dash_c['zones']
z_ctl = zones_c.find { |z| z['id'] == 'ctl1' }
z_k1  = zones_c.find { |z| z['id'] == 'k1' }
z_k2  = zones_c.find { |z| z['id'] == 'k2' }
z_ch1 = zones_c.find { |z| z['id'] == 'ch1' }
z_ch2 = zones_c.find { |z| z['id'] == 'ch2' }
z_tb1 = zones_c.find { |z| z['id'] == 'tb1' }

eq(z_ctl['kind'], 'filter', "the control card becomes a zone of kind 'filter'")
eq(z_ctl['w_pct'], 100.0, 'a SOLE control on the page spans the full band width')
eq(z_ctl['x_pct'], 0.0, 'the control band starts at x_pct 0')
eq(z_ctl['y_pct'], 0.0, 'the control band is the FIRST thing on the page (y_pct 0) — ' \
                        'even though it was interleaved among KPIs/charts/table in the source _pageOrder')

ok(z_ctl['y_pct'] < z_k1['y_pct'], 'the control band sits ABOVE the KPI row')
eq(z_k1['y_pct'], z_k2['y_pct'], 'the 2 KPIs still share their own single row (k1/k2 group despite ' \
                                 'ch1/tb1/ch2 interleaved between them in _pageOrder)')
ok(z_k1['y_pct'] < z_ch1['y_pct'], 'the KPI row sits ABOVE the chart row')
eq(z_ch1['y_pct'], z_ch2['y_pct'], 'the 2 charts still pair onto their own single row')
ok(z_ch1['y_pct'] < z_tb1['y_pct'], 'the chart row sits ABOVE the table row (house-style band order: ' \
                                    'control -> KPI -> chart -> table, confirmed end to end)')

# ===========================================================================
# Spec refinement #2 (post-brief coordinator note): a NEW, higher-priority
# geometry source — discovery/layout-observed.json, an OPERATOR-authored
# sidecar (a human/agent reading a real page screenshot; this file NEVER
# writes it, only reads it — same as dataset-map.json). Schema: flat, keyed
# by card id (string), { x, y, w, h } as FRACTIONS of the page (0.0..1.0),
# optional 'section'. See build_dashboard_with_observed's own header comment
# for the full rationale.
# ===========================================================================
puts "== load_observed_layout: reads the sidecar; malformed/partial entries are skipped, never raise =="
Dir.mktmpdir('domo-observed-load') do |dir|
  File.write(File.join(dir, 'layout-observed.json'), JSON.generate(
    '111' => { 'x' => 0.0, 'y' => 0.0, 'w' => 0.5, 'h' => 0.2 },
    '222' => { 'x' => 0.5, 'y' => 0.0 }, # missing w/h -> skipped, not a crash
    '333' => 'not a hash', # wrong shape -> skipped
  ))
  loaded = load_observed_layout(dir)
  eq(loaded.keys.sort, %w[111], "only the well-formed entry ('111') survives; '222' (missing w/h) and " \
                                "'333' (wrong shape) are silently dropped, never raise")
  eq(loaded['111'], { 'x' => 0.0, 'y' => 0.0, 'w' => 0.5, 'h' => 0.2 }, 'the surviving entry round-trips exactly')
end
eq(load_observed_layout(Dir.mktmpdir), {}, 'no layout-observed.json at all -> {} (rung 1.5 never fires), no crash')

puts "== build_dashboard_with_observed: observed geometry wins for its cards; unobserved cards fall back " \
     "to the kind-aware default composition, placed BELOW, never overlapping =="
obs_cards = [
  { 'id' => 'o1', 'title' => 'Observed KPI', 'chartType' => 'badge_singlevalue', '_size' => '', '_pageOrder' => 0 },
  { 'id' => 'o2', 'title' => 'Observed Chart', 'chartType' => 'badge_vert_bar', '_size' => '', '_pageOrder' => 1 },
  { 'id' => 'o3', 'title' => 'Unobserved Table', 'chartType' => 'badge_table', 'sigmaKindHint' => 'table',
    '_size' => '', '_pageOrder' => 2 },
]
observed_map = {
  'o1' => { 'x' => 0.0, 'y' => 0.0, 'w' => 0.3, 'h' => 0.1 },
  'o2' => { 'x' => 0.3, 'y' => 0.0, 'w' => 0.7, 'h' => 0.15 },
}
obs_dash = nil
warned = capture_stderr { obs_dash = build_dashboard_with_observed('Observed Page', obs_cards, observed_map, {}) }
ok(obs_dash, 'a page with at least one observed card returns a dashboard (never nil)')
ok(warned.include?('Unobserved Table') && warned.include?('Observed Page'),
   'the partial-coverage warning NAMES the unobserved card and the page, never silent')

ozones = obs_dash['zones']
zo1 = ozones.find { |z| z['id'] == 'o1' }
zo2 = ozones.find { |z| z['id'] == 'o2' }
zo3 = ozones.find { |z| z['id'] == 'o3' }
eq([zo1['x_pct'], zo1['y_pct'], zo1['w_pct'], zo1['h_pct']], [0.0, 0.0, 30.0, 10.0],
   "o1's zone is EXACTLY its observed fraction * 100 (x=0, y=0, w=0.3->30%, h=0.1->10%)")
eq([zo2['x_pct'], zo2['w_pct']], [30.0, 70.0], "o2's zone is exactly its own observed x/w * 100")
eq(zo1['_source'], 'observed-from-screenshot', "an observed zone is tagged _source 'observed-from-screenshot'")
eq(zo2['_source'], 'observed-from-screenshot', 'so is the second observed zone')
ok(zo3['_source'].nil?, 'the UNOBSERVED card\'s zone (kind-aware composed) carries NO _source tag — ' \
                        'only genuinely-observed zones are marked as such')
ok(zo3['y_pct'] > zo1['y_pct'] + zo1['h_pct'] - 0.01 && zo3['y_pct'] > zo2['y_pct'] + zo2['h_pct'] - 0.01,
   "o3 (unobserved, composed) sits BELOW the entire observed region's bottom edge — never overlapping it")
eq(zo3['w_pct'], 100.0, 'o3 (a table, no signal) still gets the kind-aware FULL-WIDTH table treatment ' \
                        'for the composed remainder — build_dashboard_from_collections is reused, not duplicated')

puts "== build_dashboard_with_observed: optional 'section' grouping -> one heading zone per named group =="
sec_cards = [
  { 'id' => 's1', 'title' => 'A' }, { 'id' => 's2', 'title' => 'B' }, { 'id' => 's3', 'title' => 'C' },
]
sec_map = {
  's1' => { 'x' => 0.0, 'y' => 0.1, 'w' => 0.5, 'h' => 0.1, 'section' => 'Team Alpha' },
  's2' => { 'x' => 0.5, 'y' => 0.1, 'w' => 0.5, 'h' => 0.1, 'section' => 'Team Alpha' },
  's3' => { 'x' => 0.0, 'y' => 0.3, 'w' => 1.0, 'h' => 0.1, 'section' => 'Team Beta' },
}
sec_dash = build_dashboard_with_observed('Sectioned Page', sec_cards, sec_map, {})
hdrs = sec_dash['zones'].select { |z| z['kind'] == 'text' }
eq(hdrs.map { |h| h['caption'] }, ['Team Alpha', 'Team Beta'], "one heading zone per named 'section', in first-seen order")
ok(hdrs.all? { |h| h['_source'] == 'observed-from-screenshot' }, 'section heading zones are ALSO tagged _source')

puts "== build_dashboard_with_observed: no observed cards on this page at all -> nil (caller falls through) =="
eq(build_dashboard_with_observed('No Match', [{ 'id' => 'zzz' }], { 'not-on-this-page' => { 'x' => 0, 'y' => 0, 'w' => 1, 'h' => 1 } }, {}),
   nil, "an observed map with entries for OTHER pages' cards only -> nil, not a false-positive rung-1.5 hit")

puts "== build_dashboard_for_page: rung 1.5 (observed) wins over rung 2 (collections/kind-aware) when present =="
mixed_cards = [
  { 'id' => 'm1', 'title' => 'M1', 'chartType' => 'badge_singlevalue', '_size' => '', '_pageOrder' => 0 },
]
plain = build_dashboard_for_page('Plain', mixed_cards)
obs   = build_dashboard_for_page('Plain', mixed_cards, {}, { 'm1' => { 'x' => 0.1, 'y' => 0.2, 'w' => 0.3, 'h' => 0.4 } })
ok(plain['zones'].first['_source'].nil?, 'WITHOUT an observed entry, the ordinary (unsourced) composition runs')
eq(obs['zones'].first['_source'], 'observed-from-screenshot', 'WITH an observed entry, rung 1.5 wins and tags the zone')
eq([obs['zones'].first['x_pct'], obs['zones'].first['y_pct']], [10.0, 20.0], "rung 1.5's geometry is used verbatim")

puts
if $failures.zero? then puts "ALL PASS"; exit 0 else puts "#{$failures} FAILURE(S)"; exit 1 end
