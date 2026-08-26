#!/usr/bin/env ruby
# Contract tests for the Domo-live-validated alias-case-collision fix in
# verify-parity.rb (2026-07-30): Domo's `query/execute` silently returns a
# requested alias in the COLLIDING COLUMN's casing (e.g. requested
# `gross_profit` comes back as "GROSS_PROFIT" when the table already has a
# GROSS_PROFIT column) — see refs/live-validation-2026-07-30.md "Parity —
# validated live". A comparison that keys on the requested alias
# case-sensitively silently drops that column from the check.
#
# verify-parity.rb is a vendored top-level script (no requireable guard, and
# it calls `exit` at the end) — like test-doctor-gate.rb, this runs it as a
# real subprocess against fixture plans and asserts on exit status + the
# --score-out JSON, rather than require_relative-ing it in-process.
#
# Offline: no network, no creds.
#   ruby test/test-verify-parity.rb
require 'json'
require 'tmpdir'
require 'open3'

SCRIPT = File.expand_path('../scripts/verify-parity.rb', __dir__)
$failures = 0
def eq(a, b, m) if a == b then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}\n    exp #{b.inspect}\n    got #{a.inspect}" end end

def run_parity(plan)
  Dir.mktmpdir do |dir|
    plan_path  = File.join(dir, 'plan.json')
    score_path = File.join(dir, 'score.json')
    File.write(plan_path, JSON.generate(plan))
    stdout, stderr, status = Open3.capture3('ruby', SCRIPT, '--plan', plan_path, '--score-out', score_path)
    score = File.exist?(score_path) ? JSON.parse(File.read(score_path)) : nil
    { stdout: stdout, stderr: stderr, exit: status.exitstatus, score: score }
  end
end

puts "== backward compatibility: original bare-array plan shape is untouched =="
old_shape_plan = [
  { 'chart' => 'Untouched Original Shape',
    'expected' => [['east', 100], ['west', 200]],
    'actual'   => { 'rows' => [['east', 100], ['west', 200]] } },
]
r = run_parity(old_shape_plan)
eq(r[:exit], 0, 'original plan shape still exits 0 (no regression)')
eq(r[:score]['tiles_pass'], 1, 'original plan shape still PASSes')

puts "== alias-case collision: requested 'gross_profit' comes back as 'GROSS_PROFIT' =="
# Mirrors the exact live-validated example: 4 requested aliases, the 4th
# collides case-insensitively with an existing column and Domo renames it to
# the column's own casing.
collision_plan = [
  { 'chart' => 'Revenue Summary',
    'expected' => { 'columns' => %w[lines orders net_rev GROSS_PROFIT],
                     'rows' => [[120, 45, 543.21, 987.65]],
                     'requested_columns' => %w[lines orders net_rev gross_profit] },
    'actual' => { 'rows' => [[120, 45, 543.21, 987.65]] } },
]
r = run_parity(collision_plan)
eq(r[:exit], 0, 'collision correctly resolved case-insensitively -> exit 0')
eq(r[:score]['tiles_pass'], 1, 'collision correctly resolved -> tile PASSes')
eq(r[:score]['tiles'][0]['score'], 1.0, 'collision correctly resolved -> exact score (no cell silently dropped)')

puts '== blank Domo dimension and null Sigma dimension are one missing-value bucket =='
blank_null_plan = [
  { 'chart' => 'Top Performing Subjects',
    'expected' => [['', 133_798, 95_912, 83_725]],
    'actual' => { 'rows' => [[nil, 133_798, 95_912, 83_725]] } },
]
r = run_parity(blank_null_plan)
eq(r[:exit], 0, 'blank vs null representation exits 0')
eq(r[:score]['tiles_pass'], 1, 'blank vs null representation PASSes')

puts "== silently-missing column is a LOUD failure, never a quiet skip/match =="
missing_plan = [
  { 'chart' => 'Broken Chart',
    'expected' => { 'columns' => %w[lines orders],
                     'rows' => [[1, 2]],
                     'requested_columns' => %w[lines totally_absent_measure] },
    'actual' => { 'rows' => [[1, 2]] } },
]
r = run_parity(missing_plan)
eq(r[:exit] != 0, true, 'a genuinely-missing requested column crashes the run (exit != 0), never a silent pass')
eq(r[:stderr].include?('totally_absent_measure'), true, 'the error names the specific missing column')

puts
if $failures.zero? then puts "ALL PASS"; exit 0 else puts "#{$failures} FAILURE(S)"; exit 1 end
