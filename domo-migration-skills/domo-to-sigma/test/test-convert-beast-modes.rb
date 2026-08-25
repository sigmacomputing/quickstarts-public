#!/usr/bin/env ruby
# Unit tests for convert-beast-modes.rb pure helpers (normalize_bm, lint_formula).
# Uses the verbatim internet-sourced Beast Mode examples as fixtures.
#
#   ruby test/test-convert-beast-modes.rb

require_relative '../scripts/convert-beast-modes'
require 'json'
require 'tmpdir'

SCRIPT = File.expand_path('../scripts/convert-beast-modes.rb', __dir__)

$failures = 0
def ok(cond, msg)
  if cond then puts "  ok: #{msg}" else $failures += 1; puts "  FAIL: #{msg}" end
end

puts "== normalize_bm: backtick identifiers → [Col] =="
n, _ = normalize_bm("CONCAT(`StringColumnCity`, ', ', `StringColumnState`)")
ok(n == "CONCAT([StringColumnCity], ', ', [StringColumnState])", 'backticks → brackets')

n, _ = normalize_bm("SUM(`Operating Budget`)")
ok(n == 'SUM([Operating Budget])', 'spaced identifier preserved in brackets')

puts "== normalize_bm: WEEKDAY → DAYOFWEEK =="
n, w = normalize_bm('WEEKDAY(`d`)')
ok(n == 'DAYOFWEEK([d])', 'WEEKDAY rewritten to DAYOFWEEK')
ok(w.any? { |x| x.include?('WEEKDAY') }, 'WEEKDAY warning emitted')

puts "== normalize_bm: unsupported functions flagged =="
_, w = normalize_bm('SQRT(`x`)')
ok(w.any? { |x| x.include?('SQRT') }, 'SQRT flagged unsupported')

puts "== normalize_bm: CEILING/FLOOR aggregate trap =="
_, w = normalize_bm('CEILING(`Budget`)')
ok(w.any? { |x| x.include?('AGGREGATE') && x.include?('Max') }, 'CEILING flagged as aggregate (Round(Max))')
_, w = normalize_bm('FLOOR(`Budget`)')
ok(w.any? { |x| x.include?('AGGREGATE') && x.include?('Min') }, 'FLOOR flagged as aggregate (Round(Min))')

puts "== normalize_bm: class-driven flags =="
_, w = normalize_bm('RANK() OVER(ORDER BY SUM(`Sales`) DESC)', 'window')
ok(w.any? { |x| x.include?('WINDOW') && x.include?('feedback_sigma_window_functions') }, 'window class flagged w/ workbook-master caveat')
_, w = normalize_bm('SUM(SUM(`Total Sales`) FIXED (BY `Region`))', 'lod')
ok(w.any? { |x| x.include?('FIXED/LOD') }, 'lod class flagged do-not-flatten')

puts "== lint_formula: leftover IN( is an ERROR =="
errs, _ = lint_formula('If([col] IN ("A","B"), 1, 0)')
ok(errs.any? { |e| e.include?('IsIn') }, 'raw IN(...) → error (no IsIn)')
errs, _ = lint_formula('If([col]="A" or [col]="B", 1, 0)')
ok(errs.empty?, 'expanded OR-chain passes clean')

puts "== lint_formula: And()/Or()/Not() function-call warnings =="
_, w = lint_formula('If(And([a]>1, [b]<2), 1, 0)')
ok(w.any? { |x| x.include?('infix') }, 'And() function-call warned (use infix)')

puts "== lint_formula: window function reminder =="
_, w = lint_formula('Rank(Sum([Sales]))')
ok(w.any? { |x| x.include?('feedback_sigma_window_functions') }, 'Rank() → window-limit reminder')

puts "== lint_formula: unbalanced parens/brackets =="
errs, _ = lint_formula('If([a]>1, 1, 0')
ok(errs.any? { |e| e.include?('parentheses') }, 'unbalanced parens caught (the "IF chokes" class)')
errs, _ = lint_formula('If([a>1, 1, 0)')
ok(errs.any? { |e| e.include?('brackets') }, 'unbalanced brackets caught')

puts "== lint_formula: valid multi-condition If passes =="
errs, w = lint_formula('If([Status]="Active","Active",[Status]="Pending","Pending","Other")')
ok(errs.empty?, 'native multi-condition If is clean (no nesting needed)')

puts '== normalize_bm: unsupported + WEEKDAY rewrite =='
n, w = normalize_bm('WEEKDAY(order_date)')
ok(n.include?('DAYOFWEEK'), 'WEEKDAY → DAYOFWEEK')
ok(!w.empty?, 'WEEKDAY rewrite warns')
_, w2 = normalize_bm('SQRT(x)')
ok(w2.join.match?(/SQRT/i), 'SQRT flagged unsupported')

puts '== lint_formula: raw IN + And()/Or() function-call =='
errs, _ = lint_formula('If([x] IN (1,2), "a", "b")')
ok(!errs.empty?, 'raw IN( is a lint error (Sigma has no IsIn)')
_, warns = lint_formula('And([a], [b])')
ok(!warns.empty?, 'And() as a function call warns')

puts '== lint_formula: balanced clean formula passes =='
errs2, _ = lint_formula('Sum([Sales Amount])')
ok(errs2.empty?, 'clean aggregate has no lint errors')

# ---------------------------------------------------------------------------
# discovery/formula-overrides.json escape hatch (resolve_entry / find_override
# / unmatched_override_keys) — the operator sidecar for whatever a Beast Mode
# the shared converter still can't translate. Historically that was CASE WHEN
# / COUNT(DISTINCT) / double-bracketed ALL-CAPS refs; all three are fixed now
# (sigma-data-model-mcp PR #115 then #116 — see
# refs/live-validation-2026-07-30.md). The mechanism itself is unaffected by
# that fix and is exercised below purely as a resolve_entry/find_override
# mechanism test, independent of which construct currently needs it.
# ---------------------------------------------------------------------------

puts '== resolve_entry: override fills a formula that is missing (id-keyed) =='
pending_missing = { 'id' => 'calculation_abc-123', 'name' => 'Gross Margin', 'class' => nil, 'sigmaFormula' => nil }
overrides_id = { 'calculation_abc-123' => { 'sigmaFormula' => 'If(Sum([Net Revenue]) = 0, 0, Sum([Gross Profit]) / Sum([Net Revenue]))',
                                            'note' => 'hand-authored: CASE WHEN unsupported (bead jva2)' } }
resolved, warns = resolve_entry(pending_missing, overrides_id)
ok(!resolved.nil?, 'override supplies a formula → entry is NOT dropped')
eq_val = resolved && resolved['sigmaFormula']
ok(eq_val == 'If(Sum([Net Revenue]) = 0, 0, Sum([Gross Profit]) / Sum([Net Revenue]))', 'sigmaFormula came from the override')
ok(warns.any? { |w| w.include?('Gross Margin') && w.include?('automated conversion') }, 'using an override warns, naming the Beast Mode + the automated-conversion failure')

puts '== resolve_entry: overridden entry survives lint clean + is attributed =='
ok(resolved['lintErrors'].empty?, 'the hand-authored formula passes lint_formula clean')
ok(resolved['_source'] == 'formula-override', 'attributed with _source: formula-override so it never looks machine-translated')
ok(resolved['note'] == 'hand-authored: CASE WHEN unsupported (bead jva2)', 'the override note is carried into the emitted entry')

puts '== resolve_entry: name-keyed lookup also works (ids are opaque) =='
pending_named = { 'id' => 'calculation_xyz-999', 'name' => 'Avg Order Value', 'class' => nil, 'sigmaFormula' => nil }
overrides_name = { 'Avg Order Value' => { 'sigmaFormula' => 'Sum([Net Revenue]) / CountDistinct([Order Id])' } }
resolved_named, = resolve_entry(pending_named, overrides_name)
ok(!resolved_named.nil?, 'name-keyed override matches when the id is not a key')
ok(resolved_named['sigmaFormula'] == 'Sum([Net Revenue]) / CountDistinct([Order Id])', 'formula supplied via the name key')
ok(resolved_named['_source'] == 'formula-override', 'name-keyed override is attributed too')

puts '== resolve_entry: a hand-authored override that FAILS lint is a hard error, not a silent pass =='
bad_override = { 'calculation_bad-1' => { 'sigmaFormula' => 'If([Region] IN ("EAST","WEST"), 1, 0)' } } # raw IN( — no IsIn
pending_bad = { 'id' => 'calculation_bad-1', 'name' => 'Bad Region Flag', 'class' => nil, 'sigmaFormula' => nil }
resolved_bad, warns_bad = resolve_entry(pending_bad, bad_override)
ok(!resolved_bad.nil?, 'entry still emitted (so the error is visible in formulas.json, not silently dropped)')
ok(!resolved_bad['lintErrors'].empty?, 'a typo/unsupported construct in a hand-authored override is a lintError')
ok(resolved_bad['lintErrors'].any? { |e| e.include?('IsIn') }, 'the specific IN(...) lint rule still applies to override-sourced formulas')
ok(resolved_bad['_source'] == 'formula-override', 'still attributed even though it fails lint — a reviewer must see who wrote it')

puts '== resolve_entry: override does NOT clobber a formula convert_sql_to_sigma_formula already filled =='
pending_filled = { 'id' => 'calculation_filled-1', 'name' => 'Already Done', 'class' => nil, 'sigmaFormula' => 'Sum([Net Revenue])' }
overrides_filled = { 'calculation_filled-1' => { 'sigmaFormula' => 'Avg([Net Revenue])' } }
resolved_filled, warns_filled = resolve_entry(pending_filled, overrides_filled)
ok(resolved_filled['sigmaFormula'] == 'Sum([Net Revenue])', 'auto-translated formula wins; override is not silently applied on top of a resolved entry')
ok(!resolved_filled.key?('_source'), 'no formula-override attribution when the override was not actually used')
ok(warns_filled.any? { |w| w.include?('NOT applied') }, 'still warns that the override existed but was ignored (not a silent no-op)')

puts '== resolve_entry: no override + no sigmaFormula → still dropped (unchanged honest-drop behaviour) =='
pending_none = { 'id' => 'calculation_none-1', 'name' => 'Untranslatable', 'class' => nil, 'sigmaFormula' => nil }
resolved_none, warns_none = resolve_entry(pending_none, {})
ok(resolved_none.nil?, 'no override available → entry is still dropped, exactly as before this feature existed')
ok(warns_none.empty?, 'no override present → no override-related warnings')

puts '== unmatched_override_keys: a typo\'d id/name warns instead of silently doing nothing =='
pending_list = [{ 'id' => 'calculation_real-1', 'name' => 'Real Metric', 'sigmaFormula' => nil }]
overrides_typo = { 'calculation_real-1' => { 'sigmaFormula' => 'Sum([x])' }, 'calculation_typo-does-not-exist' => { 'sigmaFormula' => 'Sum([y])' } }
unmatched = unmatched_override_keys(pending_list, overrides_typo)
ok(unmatched == ['calculation_typo-does-not-exist'], 'only the key matching no pending id/name is flagged unmatched')

puts '== unmatched_override_keys: a key matching by name is NOT reported as unmatched =='
pending_list2 = [{ 'id' => 'calculation_real-2', 'name' => 'Named Metric', 'sigmaFormula' => nil }]
unmatched2 = unmatched_override_keys(pending_list2, { 'Named Metric' => { 'sigmaFormula' => 'Sum([x])' } })
ok(unmatched2.empty?, 'name-keyed override key is recognized as matched, not flagged as a typo')

# ---------------------------------------------------------------------------
# End-to-end CLI: `ruby scripts/convert-beast-modes.rb --lint --overrides ...`
# — proves the --overrides flag, the JSON round-trip through formulas.json,
# and that the sidecar itself is never written by this script (re-running
# discovery/convert must not clobber operator-authored input).
# ---------------------------------------------------------------------------

puts '== CLI: --overrides fills a missing formula end-to-end and never touches the sidecar =='
Dir.mktmpdir('convert-beast-modes-overrides') do |dir|
  pending_path    = File.join(dir, 'formulas.pending.json')
  overrides_path  = File.join(dir, 'formula-overrides.json')
  out_path        = File.join(dir, 'formulas.json')

  File.write(pending_path, JSON.pretty_generate([
    { 'id' => 'calculation_cli-1', 'name' => 'Gross Margin Pct', 'class' => nil,
      'originalSql' => 'CASE WHEN SUM(`Net Revenue`) = 0 THEN 0 ELSE SUM(`Gross Profit`)/SUM(`Net Revenue`) END',
      'sigmaFormula' => nil },
  ]))
  overrides_json = { 'Gross Margin Pct' => { 'sigmaFormula' => 'If(Sum([Net Revenue]) = 0, 0, Sum([Gross Profit]) / Sum([Net Revenue]))',
                                              'note' => 'hand-authored: CASE WHEN unsupported (bead jva2)' } }
  File.write(overrides_path, JSON.pretty_generate(overrides_json))
  overrides_before = File.read(overrides_path)

  cmd = ['ruby', SCRIPT, '--lint', '--in', pending_path, '--out', out_path, '--overrides', overrides_path]
  output = IO.popen(cmd, err: [:child, :out], &:read)
  ok($?.success?, "CLI exits 0 on a clean override\n#{output unless $?.success?}")

  final = JSON.parse(File.read(out_path))
  ok(final.size == 1, 'the override-filled entry made it into formulas.json (not dropped)')
  ok(final.first['sigmaFormula'] == 'If(Sum([Net Revenue]) = 0, 0, Sum([Gross Profit]) / Sum([Net Revenue]))',
     'formulas.json carries the override-supplied formula')
  ok(final.first['_source'] == 'formula-override', 'formulas.json attributes the entry as formula-override')
  ok(final.first['lintErrors'].empty?, 'the CLI-lint pass is clean for a valid hand-authored formula')
  ok(output.include?('Gross Margin Pct') && output.downcase.include?('automated'),
     'stderr names the Beast Mode and flags that automated conversion failed')

  ok(File.read(overrides_path) == overrides_before, 'discovery/formula-overrides.json is byte-identical after --lint — never clobbered')
end

puts '== CLI: a completely absent formula-overrides.json is handled gracefully (no crash) =='
Dir.mktmpdir('convert-beast-modes-no-overrides') do |dir|
  pending_path = File.join(dir, 'formulas.pending.json')
  out_path     = File.join(dir, 'formulas.json')
  File.write(pending_path, JSON.pretty_generate([
    { 'id' => 'calculation_cli-2', 'name' => 'Untranslated Metric', 'class' => nil, 'sigmaFormula' => nil },
  ]))
  # Deliberately no --overrides flag and no formula-overrides.json on disk.
  cmd = ['ruby', SCRIPT, '--lint', '--in', pending_path, '--out', out_path, '--overrides', File.join(dir, 'nonexistent.json')]
  output = IO.popen(cmd, err: [:child, :out], &:read)
  # No sigmaFormula and no override → still the pre-existing unresolved-drop
  # path, so --lint exits 0 (no lintErrors) but flags 1 unresolved formula.
  ok($?.success?, "CLI still exits 0 when the sidecar file is absent (falls back to {})\n#{output unless $?.success?}")
  final = JSON.parse(File.read(out_path))
  ok(final.empty?, 'with no override and no sigmaFormula, the entry is still honestly dropped')
  ok(output.include?('Untranslated Metric'), 'the unresolved Beast Mode is still named in the drop warning')
end

puts
if $failures.zero? then puts "ALL PASS"; exit 0 else puts "#{$failures} FAILURE(S)"; exit 1 end
