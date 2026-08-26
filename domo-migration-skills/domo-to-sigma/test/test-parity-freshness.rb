#!/usr/bin/env ruby
# frozen_string_literal: true
# Regression: the WAREHOUSE FRESHNESS guard in build-parity-oracle.rb.
#
# THERE ARE THREE CLOCKS AND THE SAME-DAY GUARD ONLY WATCHED TWO. That guard
# refuses when the two collectors ran on different UTC days. But the Sigma side
# reads a warehouse COPY landed at some earlier moment — so both collectors can
# run in the same second and still compare different data.
#
# MEASURED on the 2026-08-07 live run this guard exists because of. The landed
# table carried Domo's own _BATCH_LAST_RUN_ = 2026-08-05T14:41:55Z with a newest
# fact date of 2026-08-04, while Domo rendered through 2026-08-06. Gate 1 then
# reported 24.6% (14/57), which read exactly like 43 broken tiles:
#   * trend tiles offset 2 days, measures aligning 1:1 by POSITION
#   * every %-change KPI SIGN-INVERTED (+0.198 -> -0.312) because a 7-day window
#     over data ending 2 days earlier reshuffles current vs prior period
#   * windowed counts off ~3%
#   * the 14 passes were exactly the non-windowed / static-dataset tiles, exact
# Re-running the guard over that real workdir finds 8 date-dimensioned tiles ALL
# reporting exactly -2 days. Nothing in the failure output points at the
# warehouse; the converter's formulas were correct.
#
#   ruby test/test-parity-freshness.rb
require 'json'
require 'open3'
require 'tmpdir'

SKILL   = File.expand_path('..', __dir__)
SCRIPTS = File.join(SKILL, 'scripts')
$failures = 0
def ok(c, m) if c then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}" end end
def eq(a, e, m)
  if a == e then puts "  ok: #{m}"
  else $failures += 1; puts "  FAIL: #{m}\n        expected #{e.inspect}\n        got      #{a.inspect}" end
end

# Two date-dimensioned tiles. `domo_max` is the newest Domo date; `sigma_lag`
# shifts the Sigma side back by that many days, i.e. a stale warehouse.
def stage(dir, sigma_lag:, tiles: 2)
  ids = (1..tiles).map { |i| "el-#{100 + i}" }
  File.write(File.join(dir, 'parity-plan.json'), JSON.generate(
    'charts' => ids.map do |i|
      { 'chart' => "Trend #{i}", 'sigma_element_id' => i,
        'sigma_kind' => 'line-chart', 'sigma_columns' => %w[d m] }
    end))
  # 5 daily points ending 2026-08-06 on the Domo side.
  domo = (0..4).map { |k| [(Date.new(2026, 8, 6) - (4 - k)).to_s, (k + 1) * 10] }
  sig  = domo.map { |d, v| [(Date.parse(d) - sigma_lag).to_s, v] }
  File.write(File.join(dir, 'parity-expected.json'), JSON.generate(
    'fetched_at' => '2026-08-07T12:00:00Z', 'unavailable' => [],
    'cards' => ids.each_with_index.to_h do |i, n|
      cid = (101 + n).to_s
      [cid, { 'card_id' => cid, 'title' => "Trend #{i}", 'rows' => domo }]
    end))
  File.write(File.join(dir, 'parity-actuals.json'), JSON.generate(
    'fetched_at' => '2026-08-07T12:05:00Z', 'unavailable' => [],
    'charts' => ids.to_h do |i|
      [i, { 'chart' => "Trend #{i}", 'element_id' => i,
            'columns' => %w[Date M], 'rows' => sig }]
    end))
end

require 'date'

def run(dir, *extra)
  out, st = Open3.capture2e('ruby', File.join(SCRIPTS, 'build-parity-oracle.rb'),
                            '--workdir', dir, *extra)
  [st.exitstatus, out]
end

# ---- stale warehouse, two tiles agreeing -> REFUSE ------------------------
Dir.mktmpdir('fresh-stale') do |dir|
  stage(dir, sigma_lag: 2)
  code, out = run(dir)
  eq(code, 9, 'a stale warehouse (2 tiles, -2 days) exits 9')
  ok(out.include?('WAREHOUSE COPY IS STALE'), 'and says so in as many words')
  ok(out.include?('-2 days'), 'reporting the measured lag per tile')
  ok(out.match?(/re-land/i), 'and names the remedy (re-land, then re-run parity)')
  ok(out.include?('The conversion is not what is wrong'),
     'and says plainly that the conversion is not the defect — the whole point, since ' \
     'the failure output otherwise reads as a broken migration')
  ok(!File.exist?(File.join(dir, 'parity-plan-verified.json')),
     'and writes NO plan — a stale plan scored later is exactly the misleading FAIL')
end

# ---- fresh warehouse -> proceed ------------------------------------------
Dir.mktmpdir('fresh-ok') do |dir|
  stage(dir, sigma_lag: 0)
  code, out = run(dir)
  eq(code, 0, 'a fresh warehouse proceeds')
  ok(!out.include?('STALE'), 'with no staleness complaint')
  ok(File.exist?(File.join(dir, 'parity-plan-verified.json')), 'and writes the plan')
end

# ---- ONE affected tile is a warning, not a refusal -----------------------
# A single tile could legitimately differ (a top-N, or a filter truncating the
# Sigma range). Two independent tiles showing the same direction cannot be
# explained that way. Under-reacting on one tile is deliberate.
Dir.mktmpdir('fresh-one') do |dir|
  stage(dir, sigma_lag: 2, tiles: 1)
  code, out = run(dir)
  eq(code, 0, 'a single affected tile does NOT refuse (could be a filter or top-N)')
  ok(out.match?(/WARNING/i) && out.match?(/newer than the warehouse/),
     'but it is still reported as a warning, never silent')
end

# ---- the override is honoured, and records the reason --------------------
Dir.mktmpdir('fresh-override') do |dir|
  stage(dir, sigma_lag: 2)
  code, out = run(dir, '--allow-stale-warehouse', 'no relative windows in this plan')
  eq(code, 0, '--allow-stale-warehouse proceeds')
  ok(out.include?('no relative windows in this plan'),
     'and echoes the operator reason rather than waiving silently')
  ok(File.exist?(File.join(dir, 'parity-plan-verified.json')), 'and writes the plan')
end

# ---- a NEWER warehouse than Domo must not trip it ------------------------
# Only Domo-newer-than-Sigma means the warehouse cannot match. The reverse
# (Sigma holding data Domo's card does not show) is a filter/window difference,
# not staleness, and firing on it would be a false alarm.
Dir.mktmpdir('fresh-reverse') do |dir|
  stage(dir, sigma_lag: -2)
  code, out = run(dir)
  eq(code, 0, 'Sigma holding NEWER data than Domo is not staleness — no refusal')
  ok(!out.include?('STALE'), 'and no staleness complaint')
end

puts $failures.zero? ? "\nALL PASS" : "\n#{$failures} FAILURE(S)"
exit($failures.zero? ? 0 : 1)
