#!/usr/bin/env ruby
# Unit tests for domo-capture-visuals.rb — F1 (P0): the PUBLIC page() response's
# ['cardIds']/['cards'] is EMPTY even on a live 36-card page (confirmed
# discovery/pages.json), so the script used to enumerate zero cards, capture
# zero PNGs, and STILL exit 0 — migrate-domo.rb recorded capture-visuals as
# `done` with an empty png/cards/ directory. This file proves:
#   1. enumerate_page_cards degrades through its three routes correctly
#      (mirrors domo-discover.rb's already-fixed Bug 1), and
#   2. the script's own honesty gate now turns "zero cards enumerated" and
#      "cards enumerated but zero bytes written" into a loud, non-zero,
#      non-3 exit — never a silent success.
#
#   ruby test/test-capture-visuals.rb
#
# All network calls are stubbed at the Domo module boundary — no live Domo,
# no live Sigma, nothing on the wire.

require 'json'
require 'stringio'
require 'fileutils'
require 'tmpdir'

SCRIPT_DIR = File.expand_path('../scripts', __dir__)
SCRIPT     = File.join(SCRIPT_DIR, 'domo-capture-visuals.rb')

# Load the Domo module ourselves FIRST so we can stub its singleton methods
# before domo-capture-visuals.rb's top-level flow ever calls them — the
# script's own `require_relative 'lib/domo_rest'` then becomes a harmless
# no-op (same absolute path, already in $LOADED_FEATURES).
require_relative '../scripts/lib/domo_rest'

# Sandbox every write under a scratch dir — never touch the real discovery/.
SCRATCH = Dir.mktmpdir('domo-capture-visuals-test')
ENV['DOMO_DISCOVERY_DIR'] = SCRATCH
at_exit { FileUtils.remove_entry(SCRATCH) rescue nil }

# Same stub harness as test-discover.rb: swap a Domo singleton method for the
# duration of the block, ALWAYS restoring the original afterward.
def with_domo_stub(method_name, impl)
  orig = Domo.method(method_name)
  Domo.define_singleton_method(method_name, &impl)
  yield
ensure
  Domo.define_singleton_method(method_name, &orig)
end

def capture_stderr
  old = $stderr
  $stderr = StringIO.new
  yield
  $stderr.string
ensure
  $stderr = old
end

# domo-capture-visuals.rb is a straight-line script (top-level `if opts[:pages]`
# / exit calls), not a library — the only way to re-run its main flow per
# scenario is Kernel#load (re-executes every time, unlike require/require_relative
# which memoize). That re-runs `OUT = ...` / `CARD_PNG = ...` etc each call,
# which Ruby warns about ("already initialized constant") on $stderr — harmless
# noise mixed into `out` below; NOTE: silencing it via `$VERBOSE = nil` is
# tempting but wrong — Kernel#warn (the script's own loud-failure banner) is
# itself a no-op under $VERBOSE = nil, which would make this test pass for the
# wrong reason (exit code right, banner text silently missing). Left alone, at
# the default $VERBOSE = false. `exit 0/3/4` raises SystemExit, caught here and
# reported as a real number rather than letting it kill the test process.
def run_capture_script(argv)
  ARGV.replace(argv)
  code = 0
  out = capture_stderr do
    begin
      load(SCRIPT)
    rescue SystemExit => e
      code = e.status
    end
  end
  [code, out]
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

# ---------------------------------------------------------------------------
# Bootstrap one throwaway load so the script's method defs (enumerate_page_cards,
# write_bytes, table_card?, ...) exist for direct unit testing below. Empty
# ARGV + a stubbed dev_token means it defines everything then hits the
# "nothing to do" abort at the bottom — never the live network path.
# ---------------------------------------------------------------------------
with_domo_stub(:dev_token, ->() { 'stub-dev-token' }) do
  run_capture_script([])
end

puts '== enumerate_page_cards (F1 — three-route fallback, mirrors domo-discover.rb) =='

with_domo_stub(:dev_token, ->() { 'stub-dev-token' }) do
  with_domo_stub(:cards_for_page, ->(_pid) { { 'cards' => [{ 'id' => 111 }, { 'id' => 222 }] } }) do
    eq(enumerate_page_cards('p1'), [111, 222], 'route 1 (cards_for_page) used when it has cards')
  end
end

with_domo_stub(:dev_token, ->() { 'stub-dev-token' }) do
  with_domo_stub(:cards_for_page, ->(_pid) { { 'cards' => [] } }) do
    with_domo_stub(:cards_adminsummary, ->(_pid, skip:, limit:) {
      skip.zero? ? { 'cardAdminSummaries' => [{ 'id' => 333 }] } : { 'cardAdminSummaries' => [] }
    }) do
      eq(enumerate_page_cards('p1'), [333], 'route 1 empty -> falls back to route 2 (cards_adminsummary)')
    end
  end
end

with_domo_stub(:dev_token, ->() { nil }) do  # Tier B: route 2 must be skipped entirely
  with_domo_stub(:cards_for_page, ->(_pid) { { 'cards' => [] } }) do
    with_domo_stub(:list_cards, ->(limit:, offset:) {
      offset.zero? ? { 'cards' => [{ 'cardUrn' => 'urn:444', 'pages' => [{ 'id' => 'p1' }] },
                                     { 'cardUrn' => 'urn:555', 'pages' => [{ 'id' => 'OTHER' }] }] }
                    : { 'cards' => [] }
    }) do
      eq(enumerate_page_cards('p1'), ['urn:444'],
         'route 1+2 unavailable (Tier B) -> falls back to route 3 (list_cards), filtered to this page')
    end
  end
end

# THE regression this task exists to close: the exact live-confirmed shape
# (all three routes agree — public page() cardIds is empty, and so is every
# private/public card-enumeration route) must come back [], not raise, and
# must NOT be silently reinterpreted as success by the caller (see next section).
with_domo_stub(:dev_token, ->() { 'stub-dev-token' }) do
  with_domo_stub(:cards_for_page, ->(*_a, **_kw) { { 'cards' => [] } }) do
    with_domo_stub(:cards_adminsummary, ->(*_a, **_kw) { { 'cardAdminSummaries' => [] } }) do
      with_domo_stub(:list_cards, ->(*_a, **_kw) { { 'cards' => [] } }) do
        eq(enumerate_page_cards('p1'), [], 'all three routes empty -> [] (never raises, never fabricates cards)')
      end
    end
  end
end

puts "\n== write_bytes now signals real success/failure (was always nil before) =="
Dir.mktmpdir do |d|
  eq(write_bytes(File.join(d, 'a.png'), 'PNGBYTES'), true,  'non-empty bytes -> true (and file exists)')
  ok(File.exist?(File.join(d, 'a.png')), 'file actually written to disk')
  eq(write_bytes(File.join(d, 'b.png'), ''),  false, 'empty string -> false, no file written')
  eq(write_bytes(File.join(d, 'c.png'), nil), false, 'nil render -> false, no file written')
  ok(!File.exist?(File.join(d, 'b.png')), 'empty render never touches disk')
end

puts "\n== end-to-end honesty gate: empty cardIds must NOT be a silent zero-capture success =="

# Scenario A: the live F1 bug itself — public page's cardIds (and every other
# enumeration route) is empty. Before this fix the script had no way to reach
# this branch (page_card_ids trusted cardIds directly, saw [], and the script
# still exited 0 having "handled" 0 pages of 0 cards). Now it must exit 4.
with_domo_stub(:dev_token, ->() { 'stub-dev-token' }) do
  with_domo_stub(:cards_for_page,     ->(*_a, **_kw) { { 'cards' => [] } }) do
    with_domo_stub(:cards_adminsummary, ->(*_a, **_kw) { { 'cardAdminSummaries' => [] } }) do
      with_domo_stub(:list_cards,       ->(*_a, **_kw) { { 'cards' => [] } }) do
        code, out = run_capture_script(['--pages', '999', '--no-pdf'])
        eq(code, 4, 'zero cards enumerated across the requested page(s) -> exit 4 (not 0)')
        ok(out.include?('CAPTURE-VISUALS FAILED'), 'loud FAILED banner on stderr, not a quiet log line')
        ok(Dir.glob(File.join(SCRATCH, 'png', 'cards', '*')).empty?, 'no PNGs on disk to match the exit code')
      end
    end
  end
end

# Scenario B: cards enumerate fine, but every render comes back empty (the
# "captured nothing but still called it done" half of F1 — a rendering
# failure must be just as loud as an enumeration failure).
with_domo_stub(:dev_token, ->() { 'stub-dev-token' }) do
  with_domo_stub(:cards_for_page, ->(*_a, **_kw) { { 'cards' => [{ 'id' => 'c1' }, { 'id' => 'c2' }] } }) do
    with_domo_stub(:render_card_png, ->(*_a, **_kw) { nil }) do
      code, out = run_capture_script(['--pages', '999', '--no-pdf'])
      eq(code, 4, 'cards enumerated but zero bytes written -> exit 4 (not 0)')
      ok(out.include?('CAPTURE-VISUALS FAILED'), 'loud FAILED banner names the zero-writes case')
      ok(Dir.glob(File.join(SCRATCH, 'png', 'cards', '*')).empty?, 'no PNGs on disk to match the exit code')
    end
  end
end

# Scenario C: control — real cards, real bytes, must exit success (no
# SystemExit at all) with the visuals actually on disk. Without this, a
# broken honesty gate that always failed would look identical to a correct
# one for every assertion above.
with_domo_stub(:dev_token, ->() { 'stub-dev-token' }) do
  with_domo_stub(:cards_for_page, ->(*_a, **_kw) { { 'cards' => [{ 'id' => 'c1' }, { 'id' => 'c2' }] } }) do
    with_domo_stub(:render_card_png, ->(*_a, **_kw) { 'REALPNGBYTES' }) do
      code, out = run_capture_script(['--pages', '999', '--no-pdf'])
      eq(code, 0, 'cards enumerated AND bytes written -> exit 0, no false failure')
      ok(out.include?('Captured 2/2 card visual'), 'honest count reported on success too')
      eq(Dir.glob(File.join(SCRATCH, 'png', 'cards', '*')).map { |f| File.basename(f) }.sort,
         ['c1.png', 'c2.png'], 'both cards actually landed on disk')
    end
  end
end

puts "\n#{$failures.zero? ? 'ALL PASS' : "#{$failures} FAILURE(S)"}"
exit($failures.zero? ? 0 : 1)
