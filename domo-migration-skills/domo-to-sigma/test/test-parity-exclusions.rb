#!/usr/bin/env ruby
# Contract tests for scripts/build-parity-exclusions.rb.
#
# WHY IT EXISTS: phase6-parity-domo.rb (bead 2tkm, PR #631) REFUSES to emit a
# gate-1 contract unless every chartable element is either verified by the parity
# plan or recorded in parity-plan-exclusions.json WITH A REASON — but nothing
# wrote that file. This generates it.
#
# THE DESIGN CONSTRAINT THAT MATTERS: an exclusions generator is itself a
# potential silent-inflation loophole — the failure mode the census exists to
# stop. If it can exclude a tile on a heuristic, it can quietly shrink the parity
# denominator and make a narrow run read as a full pass. So it derives exclusions
# ONLY from MACHINE FACTS the converter already recorded in warnings.json, carries
# the originating warning text through as evidence, and refuses to run away: if it
# would exclude more than MAX_EXCLUSION_RATE of the pool it ABORTS and tells the
# operator to fix the converter instead of excluding.
#
# Offline: no network, no creds.
#   ruby test/test-parity-exclusions.rb
require 'json'
require 'tmpdir'
require 'open3'

GEN = File.expand_path('../scripts/build-parity-exclusions.rb', __dir__)

$failures = 0
def eq(a, b, m)
  if a == b then puts "  ok: #{m}"
  else $failures += 1; puts "  FAIL: #{m}\n    exp #{b.inspect}\n    got #{a.inspect}" end
end
def truthy(v, m)
  if v then puts "  ok: #{m}"
  else $failures += 1; puts "  FAIL: #{m}\n    got #{v.inspect}" end
end
def at(doc, *path) path.reduce(doc) { |d, k| d.is_a?(Hash) || d.is_a?(Array) ? d[k] : nil } end

# A workbook spec whose tile ids follow the real convention el-<cardId>[-summary],
# plus the non-chartable furniture the census predicate excludes.
def spec_for(tiles)
  els = tiles.map do |t|
    { 'id' => t[:id], 'kind' => t[:kind] || 'kpi-chart', 'name' => t[:name],
      'columns' => [{ 'id' => 'c1', 'name' => 'v' }] }
  end
  els << { 'id' => 'ctl-1', 'kind' => 'control-list-values', 'name' => 'Region',
           'columns' => [{ 'id' => 'cc', 'name' => 'v' }] }
  els << { 'id' => 'master-1', 'kind' => 'table', 'name' => 'Master (DS)',
           'visibleAsSource' => false, 'columns' => [{ 'id' => 'mc', 'name' => 'v' }] }
  { 'name' => 'WB', 'kind' => 'workbook', 'pages' => [{ 'elements' => els }] }
end

def run_gen(dir, *extra)
  out, err, st = Open3.capture3('ruby', GEN, '--workdir', dir, *extra)
  p = File.join(dir, 'parity-plan-exclusions.json')
  { stdout: out, stderr: err, exit: st.exitstatus,
    doc: (File.exist?(p) ? JSON.parse(File.read(p)) : nil) }
end

def setup(dir, tiles, warnings)
  File.write(File.join(dir, 'workbook-spec.json'), JSON.pretty_generate(spec_for(tiles)))
  File.write(File.join(dir, 'warnings.json'), JSON.pretty_generate(warnings))
  dir
end

DATEWIN_WARN = 'date window NOT applied (type=INTERVAL_OFFSET interval=WEEK offset=1 count=0): ' \
               'only ROLLING_PERIOD has an established Sigma mapping here.'

# --- A. derive an exclusion from a recorded refusal -------------------------

puts '== A. a refused date window excludes that card\'s tiles, with the warning as evidence =='
Dir.mktmpdir do |dir|
  setup(dir,
        [{ id: 'el-983053598', name: 'Survey Completion Rate' },
         { id: 'el-983053598-summary', name: 'Survey Completion Rate (Summary)' },
         { id: 'el-111', name: 'Clean Tile' }],
        [{ 'card' => 'Survey Completion Rate', 'card_id' => '983053598', 'warning' => DATEWIN_WARN }])
  r = run_gen(dir)
  eq(r[:exit], 0, 'generator exits 0')
  excl = Array(at(r[:doc], 'exclusions'))
  eq(excl.size, 2, 'BOTH the base tile and its -summary companion are excluded')
  names = excl.map { |e| e['chart'] }.sort
  eq(names, ['Survey Completion Rate', 'Survey Completion Rate (Summary)'],
     'excluded by tile NAME (the key phase6-parity-domo.rb matches on)')
  truthy(excl.all? { |e| !e['reason'].to_s.strip.empty? },
         'every exclusion carries a non-empty reason (the finalizer rejects reasonless ones)')
  truthy(excl.any? { |e| e['reason'].include?('INTERVAL_OFFSET') },
         'the reason quotes the originating warning, not a generic string')
  truthy(excl.all? { |e| at(e, 'evidence', 'warning') },
         'the raw warning rides along as evidence so the exclusion is auditable')
  truthy(excl.none? { |e| e['chart'] == 'Clean Tile' },
         'a tile with no disqualifying warning is NOT excluded')
end

puts '== A2. the output is exactly the shape phase6-parity-domo.rb consumes =='
Dir.mktmpdir do |dir|
  setup(dir, [{ id: 'el-1', name: 'T1' }],
        [{ 'card' => 'T1', 'card_id' => '1', 'warning' => DATEWIN_WARN }])
  r = run_gen(dir)
  truthy(at(r[:doc], 'exclusions').is_a?(Array), "top level carries an 'exclusions' array")
  e = Array(at(r[:doc], 'exclusions')).first
  truthy(e.key?('chart') && e.key?('reason'), 'each entry has chart + reason')
end

puts '== A3. released flat workbook code finds document-global elements =='
Dir.mktmpdir do |dir|
  setup(dir,
        [{ id: 'el-983053598', name: 'Survey Completion Rate' },
         { id: 'el-983053598-summary', name: 'Survey Completion Rate (Summary)' }],
        [{ 'card' => 'Survey Completion Rate', 'card_id' => '983053598',
           'warning' => DATEWIN_WARN }])
  legacy = JSON.parse(File.read(File.join(dir, 'workbook-spec.json')))
  elements = legacy['pages'].flat_map { |p| Array(p['elements']) }
  released = {
    'name' => 'WB',
    'document' => {
      'schemaVersion' => 1, 'kind' => 'workbook',
      'pages' => [{ 'id' => 'page-1', 'name' => 'Overview' }],
      'elements' => elements,
    },
  }
  File.write(File.join(dir, 'workbook-spec.json'), JSON.pretty_generate(released))
  r = run_gen(dir)
  eq(r[:exit], 0, 'released flat spec exits 0')
  eq(Array(at(r[:doc], 'exclusions')).size, 2,
     'base and companion are found under document.elements')
end

# --- B. never exclude on anything but a recorded machine fact ---------------

puts '== B. an unrelated warning excludes nothing =='
Dir.mktmpdir do |dir|
  setup(dir, [{ id: 'el-1', name: 'T1' }],
        [{ 'card' => 'T1', 'card_id' => '1',
           'warning' => 'no grid geometry for page — layout will fall back to a single-column stack' }])
  r = run_gen(dir)
  eq(Array(at(r[:doc], 'exclusions')).size, 0,
     'a layout/cosmetic warning is NOT grounds for dropping a tile from parity')
end

puts '== B2. no warnings at all -> an EMPTY exclusions file, not a missing one =='
Dir.mktmpdir do |dir|
  setup(dir, [{ id: 'el-1', name: 'T1' }], [])
  r = run_gen(dir)
  eq(r[:exit], 0, 'still exits 0')
  truthy(!r[:doc].nil?, 'the file is written even when empty')
  eq(Array(at(r[:doc], 'exclusions')).size, 0, 'with zero exclusions')
end

# --- C. the runaway guard --------------------------------------------------
# An exclusions generator that can exclude the whole pool IS the silent-inflation
# bug wearing a different hat.

puts '== C. excluding most of the pool ABORTS rather than shrinking the denominator =='
Dir.mktmpdir do |dir|
  tiles = (1..10).map { |i| { id: "el-#{i}", name: "T#{i}" } }
  warns = (1..8).map { |i| { 'card' => "T#{i}", 'card_id' => i.to_s, 'warning' => DATEWIN_WARN } }
  setup(dir, tiles, warns)
  r = run_gen(dir)
  truthy(r[:exit] != 0, "8 of 10 tiles excludable -> non-zero exit (got #{r[:exit]})")
  combined = r[:stdout] + r[:stderr]
  truthy(combined.downcase.include?('fix the converter') || combined.downcase.include?('too many'),
         'the abort tells the operator to fix the converter, not to widen the exclusions')
  truthy(!(r[:doc] && Array(r[:doc]['exclusions']).size >= 8),
         'and no runaway exclusions file is left behind for the finalizer to consume')
end

puts '== C2. the guard can be overridden only by an explicit, named decision =='
Dir.mktmpdir do |dir|
  tiles = (1..10).map { |i| { id: "el-#{i}", name: "T#{i}" } }
  warns = (1..8).map { |i| { 'card' => "T#{i}", 'card_id' => i.to_s, 'warning' => DATEWIN_WARN } }
  setup(dir, tiles, warns)
  r = run_gen(dir, '--accept-exclusion-rate', 'converter fix deferred to the next pass; named in the report')
  eq(r[:exit], 0, 'an explicitly named override is accepted')
  eq(at(r[:doc], 'rate_waiver'), 'converter fix deferred to the next pass; named in the report',
     'and the reason is recorded in the artifact')
end

# --- D. census arithmetic is reported, so plan+exclusions can be checked ----

puts '== D. the generator reports the census arithmetic it is feeding =='
Dir.mktmpdir do |dir|
  setup(dir,
        [{ id: 'el-1', name: 'T1' }, { id: 'el-2', name: 'T2' }, { id: 'el-3', name: 'T3' }],
        [{ 'card' => 'T1', 'card_id' => '1', 'warning' => DATEWIN_WARN }])
  r = run_gen(dir)
  eq(at(r[:doc], 'chartable_total'), 3, 'records the true denominator')
  eq(at(r[:doc], 'excluded_total'), 1, 'records how many it excluded')
  truthy((r[:stdout] + r[:stderr]).include?('3'), 'and states the arithmetic on stdout/stderr')
end

# --- E. warnings without a joinable card_id must not silently no-op ---------

puts '== E. a warning with no card_id is reported, never silently ignored =='
Dir.mktmpdir do |dir|
  setup(dir, [{ id: 'el-1', name: 'T1' }],
        [{ 'card' => 'T1', 'warning' => DATEWIN_WARN }])  # no card_id
  r = run_gen(dir)
  combined = r[:stdout] + r[:stderr]
  truthy(combined.downcase.include?('card_id'),
         'the un-joinable disqualifying warning is surfaced, not dropped on the floor')
end


# --- F. INTEGRATION: the generator's output actually satisfies the census ----
# The whole point. Two independently-written scripts have to agree on the
# exclusions contract: build-parity-exclusions.rb writes {chart, reason} entries,
# and phase6-parity-domo.rb's census must accept them and balance
# plan + exclusions == chartable. A test on either script alone would not catch a
# key-name or matching mismatch between them.

puts '== F. generator output + a partial plan makes the FINALIZER census balance =='
FINALIZER = File.expand_path('../scripts/phase6-parity-domo.rb', __dir__)
Dir.mktmpdir do |dir|
  # 3 chartable tiles; the card behind T1 had its date window refused.
  setup(dir,
        [{ id: 'el-1', name: 'T1' }, { id: 'el-2', name: 'T2' }, { id: 'el-3', name: 'T3' }],
        [{ 'card' => 'T1', 'card_id' => '1', 'warning' => DATEWIN_WARN }])
  g = run_gen(dir)
  eq(g[:exit], 0, 'setup: generator wrote the exclusions')
  eq(at(g[:doc], 'excluded_total'), 1, 'setup: exactly T1 is excluded')

  # A plan covering ONLY the two scoreable tiles — the census must accept that,
  # because the third is accounted for by the generated exclusions file.
  plan = { 'charts' => %w[T2 T3].map { |n|
    { 'chart' => n, 'expected' => [['east', 100]], 'actual' => { 'rows' => [['east', 100]] } } } }
  File.write(File.join(dir, 'parity-plan.json'), JSON.pretty_generate(plan))

  out, err, st = Open3.capture3('ruby', FINALIZER, '--workdir', dir,
                                '--plan', File.join(dir, 'parity-plan.json'),
                                '--workbook-id', 'wb-test')
  combined = out + err
  eq(st.exitstatus, 0, "finalizer accepts the generated exclusions (got #{st.exitstatus}: #{combined[0, 200]})")
  final = JSON.parse(File.read(File.join(dir, 'parity-final.json'))) rescue nil
  eq(at(final, 'status'), 'PASS', 'and derives a PASS contract')
  eq(at(final, 'charts_total'), 2, 'charts_total is the VERIFIED pool, not the full 3')
  eq(at(final, 'parity_tile_census', 'chartable_total'), 3, 'census still records the true denominator')
  eq(at(final, 'parity_tile_census', 'excluded_total'), 1, 'census counts the generated exclusion')
  eq(Array(at(final, 'parity_tile_census', 'unaccounted')).size, 0,
     'census BALANCES: plan + generated exclusions == chartable')
  truthy(Array(at(final, 'excluded_with_reason')).any? { |e| e['chart'] == 'T1' },
         'the generated exclusion rides into the contract, so the report cannot omit it')
end

puts '== F2. dropping a tile the generator did NOT excuse still FAILS the census =='
# Proves F is not vacuous: the census is still strict about un-excused omissions.
Dir.mktmpdir do |dir|
  setup(dir,
        [{ id: 'el-1', name: 'T1' }, { id: 'el-2', name: 'T2' }, { id: 'el-3', name: 'T3' }],
        [{ 'card' => 'T1', 'card_id' => '1', 'warning' => DATEWIN_WARN }])
  run_gen(dir)
  # T3 is silently dropped from the plan and has NO exclusion entry.
  plan = { 'charts' => [{ 'chart' => 'T2', 'expected' => [['east', 100]],
                          'actual' => { 'rows' => [['east', 100]] } }] }
  File.write(File.join(dir, 'parity-plan.json'), JSON.pretty_generate(plan))
  out, err, st = Open3.capture3('ruby', FINALIZER, '--workdir', dir,
                                '--plan', File.join(dir, 'parity-plan.json'),
                                '--workbook-id', 'wb-test')
  truthy(st.exitstatus != 0, "an un-excused omission still fails (got #{st.exitstatus})")
  truthy((out + err).include?('T3'), 'and names the unaccounted tile')
end

puts
if $failures.zero? then puts 'ALL PASS'; exit 0
else puts "#{$failures} FAILURE(S)"; exit 1 end
