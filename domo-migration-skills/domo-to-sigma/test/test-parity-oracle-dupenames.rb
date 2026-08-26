#!/usr/bin/env ruby
# frozen_string_literal: true
# Regression: DUPLICATE CHART NAMES must not cross-wire tiles.
#
# Found by adversarial review of the parity oracle, reproduced end to end, and
# the single worst class of defect this chain can have: it produced an UNEARNED
# PASS on a genuine migration bug.
#
# Domo hands the same generic summary label to many cards. On the real 65-tile
# page ELEVEN tiles share a name with at least one other:
#     "New Visits in Period"  x4    "Change over 7 Days"  x3
#     "Surveys in Period"     x2    "US Leads in Period"  x2
# phase6-parity-domo.rb:190-193 says so itself ("the same KPI title repeated on
# two pages is routine") and compares as a MULTISET for exactly this reason.
#
# Keying the Sigma actuals by display name broke two ways at once, both silent:
#   1. last writer wins in the thread pool, non-deterministically, and the losing
#      exports vanished with NO `unavailable` entry;
#   2. the join attached that ONE surviving export to EVERY tile sharing the name.
# Measured on the real element ids: a genuine match scored DIVERGE (false
# negative) and a genuine 42-vs-7 divergence scored PASS 100% (unearned pass).
#
# The same name-keying in prior_excl swept every same-named tile into one tile's
# exclusion — shrinking the denominator, which reads as a cleaner pass.
#
# Element ids are unique by construction. These tests pin that they are the key.
#
#   ruby test/test-parity-oracle-dupenames.rb
require 'json'
require 'time'
require 'open3'
require 'tmpdir'
require 'fileutils'

SKILL   = File.expand_path('..', __dir__)
# Stamped at RUN time, not hardcoded. The oracle's same-day guard compares the
# expected side's fetched_at against the actuals side, and the actuals collector
# stamps NOW — so a literal date here passes on the day it is written and aborts
# ('REFUSING to join ... different UTC days') every day after. Time-bomb, not a
# real cross-day case; the guard stays exercised by test-parity-freshness.rb.
TODAY_UTC = Time.now.utc.strftime('%Y-%m-%dT%H:%M:%SZ')
SCRIPTS = File.join(SKILL, 'scripts')
$failures = 0
def ok(c, m) if c then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}" end end
def eq(a, e, m)
  if a == e then puts "  ok: #{m}"
  else $failures += 1; puts "  FAIL: #{m}\n        expected #{e.inspect}\n        got      #{a.inspect}" end
end

# The three REAL element ids that collide on "Change over 7 Days" in
# ~/domo-coldrun-v4/workbook-spec.json, with deliberately DIFFERENT values so a
# cross-wire cannot hide behind coincidence.
IDS = %w[el-503650739-summary el-1136570741-summary el-53325952-summary].freeze
CARDS = { 'el-503650739-summary' => %w[503650739 999],
          'el-1136570741-summary' => %w[1136570741 7],
          'el-53325952-summary' => %w[53325952 7] }.freeze
ACTUAL = { 'el-503650739-summary' => '999',    # matches expected -> PASS
           'el-1136570741-summary' => '42',    # real divergence   -> DIVERGE
           'el-53325952-summary' => '7' }.freeze # matches         -> PASS

def stage(dir, exclusions: nil)
  File.write(File.join(dir, 'fixture.json'),
             JSON.generate(IDS.to_h { |i| [i, "value\n#{ACTUAL[i]}\n"] }))
  File.write(File.join(dir, 'parity-plan.json'), JSON.generate(
    'charts' => IDS.map do |i|
      { 'chart' => 'Change over 7 Days', 'sigma_element_id' => i,
        'sigma_kind' => 'kpi-chart', 'sigma_columns' => ['m'] }
    end))
  File.write(File.join(dir, 'parity-expected.json'), JSON.generate(
    'fetched_at' => TODAY_UTC, 'unavailable' => [],
    'cards' => IDS.to_h do |i|
      cid, sv = CARDS[i]
      [cid, { 'card_id' => cid, 'title' => "card #{cid}", 'rows' => [['x', 1]],
              'summary_value' => sv.to_i }]
    end))
  File.write(File.join(dir, 'parity-plan-exclusions.json'), JSON.generate(exclusions)) if exclusions
end

def run(*args)
  out, st = Open3.capture2e('ruby', *args)
  [st.success?, out]
end

Dir.mktmpdir('dupe') do |dir|
  stage(dir)

  # ---- the actuals collector keeps every element ---------------------------
  okc, out = run(File.join(SCRIPTS, 'collect-parity-actuals.rb'),
                 '--plan', File.join(dir, 'parity-plan.json'),
                 '--workbook-id', 'wb1', '--out', File.join(dir, 'parity-actuals.json'),
                 '--pool', '1', '--fixture', File.join(dir, 'fixture.json'))
  ok(okc, 'collect-parity-actuals.rb exits 0 on three same-named tiles')
  act = JSON.parse(File.read(File.join(dir, 'parity-actuals.json')))
  eq(act['charts_ok'], 3,
     'all THREE same-named exports survive (name-keyed, only 1 did — the other two vanished ' \
     'with no `unavailable` entry, contradicting the script\'s own guarantee)')
  eq(act['charts'].keys.sort, IDS.sort, 'actuals are keyed by ELEMENT ID, not display name')
  eq(act['unavailable'], [], 'and nothing was silently dropped')

  # ---- the join attaches each tile its OWN actual --------------------------
  okj, = run(File.join(SCRIPTS, 'build-parity-oracle.rb'), '--workdir', dir)
  ok(okj, 'build-parity-oracle.rb exits 0')
  plan = JSON.parse(File.read(File.join(dir, 'parity-plan-verified.json')))
  eq(plan['charts'].length, 3, 'all three tiles are verified')
  mapping = plan['charts'].to_h { |c| [c['sigma_element_id'], c['actual']['rows'].flatten.first.to_s] }
  eq(mapping, ACTUAL,
     'each tile carries ITS OWN Sigma export — a cross-wire here is an unearned PASS')
  exp = plan['charts'].to_h { |c| [c['sigma_element_id'], c['expected'].flatten.first.to_i] }
  eq(exp, IDS.to_h { |i| [i, CARDS[i][1].to_i] }, 'and its own Domo expected value')

  # ---- scoring comes out right --------------------------------------------
  _, vout = run(File.join(SCRIPTS, 'verify-parity.rb'), '--plan',
                File.join(dir, 'parity-plan-verified.json'))
  eq(vout.scan(/^PASS/).length, 2, 'exactly the two genuine matches PASS')
  eq(vout.scan(/^DIVERGE/).length, 1,
     'and the one genuine divergence (42 vs 7) DIVERGES — name-keyed it reported PASS 100%')
end

# ---- a prior exclusion must not sweep its same-named siblings -------------
Dir.mktmpdir('dupe-excl') do |dir|
  stage(dir, exclusions: { 'exclusions' => [
    { 'chart' => 'Change over 7 Days', 'reason' => 'refused date window (INTERVAL_OFFSET)',
      'evidence' => { 'card_id' => '1136570741', 'element_id' => 'el-1136570741-summary' } },
  ] })
  run(File.join(SCRIPTS, 'collect-parity-actuals.rb'),
      '--plan', File.join(dir, 'parity-plan.json'), '--workbook-id', 'wb1',
      '--out', File.join(dir, 'parity-actuals.json'), '--pool', '1',
      '--fixture', File.join(dir, 'fixture.json'))
  run(File.join(SCRIPTS, 'build-parity-oracle.rb'), '--workdir', dir)

  v = JSON.parse(File.read(File.join(dir, 'parity-plan-verified.json')))
  x = JSON.parse(File.read(File.join(dir, 'parity-plan-exclusions.json')))
  eq(v['charts'].map { |c| c['sigma_element_id'] }.sort,
     %w[el-503650739-summary el-53325952-summary],
     'the two NOT disqualified are still verified (name-keyed, all three were swept out)')
  eq(x['exclusions'].length, 1, 'exactly one exclusion survives')
  eq(x['exclusions'].first.dig('evidence', 'element_id'), 'el-1136570741-summary',
     'and it is the element that was actually disqualified')
  eq(v['charts'].length + x['exclusions'].length, 3, 'coverage invariant still exact')
end

# ---- a name-only prior exclusion is consumed ONCE, never broadcast --------
Dir.mktmpdir('dupe-nameonly') do |dir|
  stage(dir, exclusions: { 'exclusions' => [
    { 'chart' => 'Change over 7 Days', 'reason' => 'legacy hand-authored entry, no element_id' },
  ] })
  run(File.join(SCRIPTS, 'collect-parity-actuals.rb'),
      '--plan', File.join(dir, 'parity-plan.json'), '--workbook-id', 'wb1',
      '--out', File.join(dir, 'parity-actuals.json'), '--pool', '1',
      '--fixture', File.join(dir, 'fixture.json'))
  run(File.join(SCRIPTS, 'build-parity-oracle.rb'), '--workdir', dir)
  v = JSON.parse(File.read(File.join(dir, 'parity-plan-verified.json')))
  x = JSON.parse(File.read(File.join(dir, 'parity-plan-exclusions.json')))
  eq(x['exclusions'].length, 1,
     'an ambiguous name-only exclusion applies to ONE tile, not all three — ' \
     'it should under-apply, never over-apply')
  eq(v['charts'].length, 2, 'the other two are still scored')
end

# ---- round 2: re-running the join must be IDEMPOTENT ----------------------
# The round-1 fix added element_id to the two exclusion sites it happened to
# touch and missed three others. Those element_id-less entries were then
# indistinguishable from a legacy name-only exclusion on the NEXT standalone
# run, so .shift handed one to the FIRST same-named tile in plan order — which
# could be a tile carrying a real divergence. Measured: a caught 999-vs-100 bug
# became "2/2 pass = 100%" on the second invocation. A bare
# `build-parity-oracle.rb --workdir` re-run is documented, supported usage.
Dir.mktmpdir('dupe-rerun') do |dir|
  # The scenario must actually PRODUCE an exclusion of a self-written kind, or
  # the "every exclusion carries element_id" check is vacuously true on an empty
  # array. (First cut of this test was exactly that — it passed with the fix
  # deliberately reverted.) So: FOUR same-named tiles, one with NO Domo card
  # (fires the element_id-less "no Domo source value" path), and one carrying a
  # real divergence that must survive every re-run.
  ids = %w[el-1393001267-summary el-1037345428-summary el-579213727-summary el-1124999128-summary]
  actual = { ids[0] => '999', ids[1] => '5', ids[2] => '5', ids[3] => '5' }
  File.write(File.join(dir, 'fixture.json'),
             JSON.generate(ids.to_h { |i| [i, "value\n#{actual[i]}\n"] }))
  File.write(File.join(dir, 'parity-plan.json'), JSON.generate(
    'charts' => ids.map do |i|
      { 'chart' => 'New Visits in Period', 'sigma_element_id' => i,
        'sigma_kind' => 'kpi-chart', 'sigma_columns' => ['m'] }
    end))
  # el-1393001267-summary expects 100 but Sigma exports 999 -> a REAL divergence.
  # el-1124999128-summary has NO card entry at all -> "no Domo source value".
  File.write(File.join(dir, 'parity-expected.json'), JSON.generate(
    'fetched_at' => TODAY_UTC, 'unavailable' => [],
    'cards' => { '1393001267' => { 'card_id' => '1393001267', 'title' => 'a',
                                   'rows' => [['x', 1]], 'summary_value' => 100 },
                 '1037345428' => { 'card_id' => '1037345428', 'title' => 'b',
                                   'rows' => [['x', 1]], 'summary_value' => 5 },
                 '579213727'  => { 'card_id' => '579213727', 'title' => 'c',
                                   'rows' => [['x', 1]], 'summary_value' => 5 } }))
  run(File.join(SCRIPTS, 'collect-parity-actuals.rb'),
      '--plan', File.join(dir, 'parity-plan.json'), '--workbook-id', 'wb1',
      '--out', File.join(dir, 'parity-actuals.json'), '--pool', '1',
      '--fixture', File.join(dir, 'fixture.json'))

  scores = (1..3).map do
    run(File.join(SCRIPTS, 'build-parity-oracle.rb'), '--workdir', dir)
    _, vout = run(File.join(SCRIPTS, 'verify-parity.rb'), '--plan',
                  File.join(dir, 'parity-plan-verified.json'))
    [vout.scan(/^PASS/).length, vout.scan(/^DIVERGE/).length]
  end
  eq(scores, [[2, 1], [2, 1], [2, 1]],
     'three consecutive joins score identically — the real 999-vs-100 DIVERGE is never ' \
     'laundered into an unearned exclusion by a stale element_id-less entry')

  x = JSON.parse(File.read(File.join(dir, 'parity-plan-exclusions.json')))
  ok(!x['exclusions'].empty?,
     'the scenario really does produce an exclusion (guard below is not vacuous)')
  ok(x['exclusions'].all? { |e| !e['element_id'].to_s.empty? || !e.dig('evidence', 'element_id').to_s.empty? },
     'every exclusion this script writes carries an element_id, so its own output can never ' \
     'be mistaken for a legacy name-only entry on the next run')
  eq(x['exclusions'].map { |e| e['element_id'] }, [ids[3]],
     'and it is the tile that genuinely has no Domo card — not whichever came first by name')
end

# ---- round 2: the same ELEMENT ID listed twice in the plan -----------------
# A Domo card pinned to two dashboard pages is ordinary; discovery applies no
# cross-page dedup and the element id derives purely from the card id, so the
# plan can legitimately double-list one element. act_by_eid resolves for BOTH
# occurrences, so the second was scored a second time against the first one's
# single measurement — two plan rows, one measurement, both reported.
Dir.mktmpdir('dupe-eid') do |dir|
  File.write(File.join(dir, 'fixture.json'), JSON.generate('el-777-summary' => "value\n5\n"))
  File.write(File.join(dir, 'parity-plan.json'), JSON.generate('charts' => [
    { 'chart' => 'Pinned Card', 'sigma_element_id' => 'el-777-summary',
      'sigma_kind' => 'kpi-chart', 'sigma_columns' => ['m'] },
    { 'chart' => 'Pinned Card', 'sigma_element_id' => 'el-777-summary',
      'sigma_kind' => 'kpi-chart', 'sigma_columns' => ['m'] },
  ]))
  File.write(File.join(dir, 'parity-expected.json'), JSON.generate(
    'fetched_at' => TODAY_UTC, 'unavailable' => [],
    'cards' => { '777' => { 'card_id' => '777', 'title' => 'Pinned Card',
                            'rows' => [['x', 1]], 'summary_value' => 5 } }))
  run(File.join(SCRIPTS, 'collect-parity-actuals.rb'),
      '--plan', File.join(dir, 'parity-plan.json'), '--workbook-id', 'wb1',
      '--out', File.join(dir, 'parity-actuals.json'), '--pool', '1',
      '--fixture', File.join(dir, 'fixture.json'))
  run(File.join(SCRIPTS, 'build-parity-oracle.rb'), '--workdir', dir)

  v = JSON.parse(File.read(File.join(dir, 'parity-plan-verified.json')))
  x = JSON.parse(File.read(File.join(dir, 'parity-plan-exclusions.json')))
  eq(v['charts'].length, 1, 'a double-listed element is scored ONCE, not twice')
  eq(x['exclusions'].length, 1, 'and its duplicate is excluded, not silently dropped')
  ok(x['exclusions'].first['reason'].to_s.include?('more than once'),
     'with a reason naming the actual problem (the plan double-lists the element)')
  eq(v['charts'].length + x['exclusions'].length, 2, 'coverage invariant still exact')
end

puts $failures.zero? ? "\nALL PASS" : "\n#{$failures} FAILURE(S)"
exit($failures.zero? ? 0 : 1)
