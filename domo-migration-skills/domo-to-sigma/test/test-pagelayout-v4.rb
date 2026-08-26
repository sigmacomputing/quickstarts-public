#!/usr/bin/env ruby
# Offline, end-to-end: Track C's whole point is that a v4-inline page reaches
# build_dashboard_for_page's rung 1 (build_dashboard: genuine x/y/w/h pixel
# geometry) automatically, once merge_geometry is fixed — with ZERO changes to
# build-domo-layout.rb itself. This proves that wiring, and proves a legacy
# (non-v4) page's existing rung-2 (collections[]/size-token) path is untouched.
#   ruby test/test-pagelayout-v4.rb
require 'json'
require_relative '../scripts/lib/domo_sigma_util'
require_relative '../scripts/build-domo-layout'
include DomoSigma

$failures = 0
def ok(c, m) if c then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}" end end
def eq(actual, expected, msg)
  if actual == expected
    puts "  ok: #{msg}"
  else
    $failures += 1
    puts "  FAIL: #{msg}\n        expected #{expected.inspect}\n        got      #{actual.inspect}"
  end
end

puts '== v4-inline page: merge_geometry + build_dashboard_for_page reaches rung 1 =='
stacks_v4_fixture = JSON.parse(File.read(File.join(__dir__, 'fixtures', 'domo-live-raw', 'stacks-page-v4.json')))
raw_cards = stacks_v4_fixture['cards'].map { |c| { 'id' => c['id'], 'title' => c['title'], 'chartType' => c.dig('metadata', 'chartType') } }
merged = merge_geometry(raw_cards, nil, stacks: stacks_v4_fixture)
dash = build_dashboard_for_page('V4 Page', merged)
ok(dash, 'build_dashboard_for_page returns a dashboard for the v4-merged cards')
eq(dash['zones'].length, 3, 'all 3 real cards became zones (the HEADER content entry never became a phantom zone)')
zone_by_id = dash['zones'].each_with_object({}) { |z, h| h[z['id']] = z }

layout_content = pagelayoutv4_content(stacks_v4_fixture, stacks_v4_fixture['id'])
eq(layout_content.map { |content| content['type'] }, %w[header page-break],
   'v4 authored HEADER and PAGE_BREAK are preserved as explicit layout content')
header = layout_content.find { |content| content['type'] == 'header' }
page_break = layout_content.find { |content| content['type'] == 'page-break' }
eq(header['text'], 'Sample Section', 'v4 header retains its authored text')
eq([header['x'], header['y'], header['w'], header['h']], [0.0, 0.0, 24.0, 1.2],
   'v4 header geometry scales from Domo 60-wide grid to Sigma 24-wide grid')
eq(page_break['h'], 0.4, 'v4 page-break source geometry is captured before fixed one-row layout placement')
ok(header['id'].length <= 64 && page_break['id'].length <= 64,
   'synthesized layout-content element ids satisfy Sigma length limits')

# Exact values, not a relative ordering check: rung 1's build_dashboard derives
# these from the v4 template's real x/y/w/h (scaled x0.4, then normalized to
# max_x=12.0/max_y=15.6 across the 3 cards). Rung 2 (build_dashboard_from_
# collections) would produce a DIFFERENT set of numbers from its own
# equal-width/size-token composition — e.g. an even 3-up row gives x_pct 0/50/
# 0 and w_pct 50/50/100, not the 0/36.67/0 and 36.67/26.67/100 below. Asserting
# the exact numbers (not just "card B is right of card A") is what gives this
# test the power to tell rung 1 and rung 2 apart; a relative ordering check
# alone cannot, because the fixture's cards[] happens to already be in
# left-to-right order, so rung 2's fallback would satisfy an ordering-only
# assertion too. Values confirmed by running the actual code (not hand math):
# see the fix-round-1 addendum in refs/task-3-report.md for both the real-run
# and monkey-patched-stub proof.
eq(zone_by_id[700000010]['x_pct'], 0.0,   'card 700000010: x_pct=0.0 (real x=0.0 / max_x=12.0)')
eq(zone_by_id[700000010]['y_pct'], 12.82, 'card 700000010: y_pct=12.82 (real y=2.0 / max_y=15.6) — rung 2 would give 0.0')
eq(zone_by_id[700000010]['w_pct'], 36.67, 'card 700000010: w_pct=36.67 (real w=4.4 / max_x=12.0) — rung 2 would give an even 50.0')
eq(zone_by_id[700000010]['h_pct'], 35.9,  'card 700000010: h_pct=35.9 (real h=5.6 / max_y=15.6) — rung 2 would give 38.46')
eq(zone_by_id[700000011]['x_pct'], 36.67, 'card 700000011: x_pct=36.67 (real x=4.4 / max_x=12.0) — rung 2 would give an even 50.0')
eq(zone_by_id[700000011]['y_pct'], 12.82, 'card 700000011: y_pct=12.82 (real y=2.0 / max_y=15.6) — rung 2 would give 0.0')
eq(zone_by_id[700000011]['w_pct'], 26.67, 'card 700000011: w_pct=26.67 (real w=3.2 / max_x=12.0) — rung 2 would give an even 50.0')
eq(zone_by_id[700000011]['h_pct'], 35.9,  'card 700000011: h_pct=35.9 (real h=5.6 / max_y=15.6) — rung 2 would give 38.46')
eq(zone_by_id[700000012]['y_pct'], 48.72, 'card 700000012: y_pct=48.72 (real y=7.6 / max_y=15.6) — rung 2 would give 38.46')
eq(zone_by_id[700000012]['h_pct'], 51.28, 'card 700000012: h_pct=51.28 (real h=8.0 / max_y=15.6) — rung 2 would give 61.54')

puts '== legacy (non-v4) page: unaffected, still falls through past rung 1 to rung 2 =='
legacy_fixture = JSON.parse(File.read(File.join(__dir__, 'fixtures', 'domo-live-raw', 'stacks-page.json')))
legacy_cards = legacy_fixture['cards'].map { |c| { 'id' => c['id'], 'title' => c['title'], 'chartType' => c.dig('metadata', 'chartType') } }
legacy_merged = merge_geometry(legacy_cards, nil, stacks: legacy_fixture)
ok(legacy_merged.none? { |c| c['x'] }, 'sanity: the legacy fixture has no pageLayoutV4, so no card gets x/y/w/h from this pass')
legacy_dash = build_dashboard_for_page('Legacy Page', legacy_merged)
ok(legacy_dash, 'legacy page still produces a dashboard (via rung 2, collections[]/size tokens)')

puts
if $failures.zero?
  puts 'ALL PASS'
  exit 0
else
  puts "#{$failures} FAILURE(S)"
  exit 1
end
