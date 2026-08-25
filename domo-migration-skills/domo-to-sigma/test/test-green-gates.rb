#!/usr/bin/env ruby
# Offline contract tests for the shared GREEN-gate linters.
require_relative '../scripts/lib/control_lint'
require_relative '../scripts/lib/layout_lint'
$failures = 0
def ok(c, m) if c then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}" end end

# --- layout_lint: raw-id display name is a violation -------------------------
puts '== layout_lint =='
bad_layout = { 'pages' => [ { 'id' => 'pg', 'name' => 'Overview',
  'elements' => [ { 'id' => 'el-abc123', 'kind' => 'kpi-chart', 'name' => 'el-abc123' } ] } ],
  'layout' => '<Page id="pg"><GridContainer gridRow="R0 / R1" gridTemplateColumns="1fr">' \
              '<LayoutElement elementId="el-abc123" gridColumn="C0 / C1" gridRow="R0 / R1"/></GridContainer></Page>' }
ok(LayoutLint.lint(bad_layout).any? { |v| v.include?('raw-id') }, 'raw-id display name flagged')

good_layout = Marshal.load(Marshal.dump(bad_layout))
good_layout['pages'][0]['elements'][0]['name'] = 'Total Revenue'
# raw-id check is what we assert on; a clean name must not itself trip the raw-id rule:
ok(LayoutLint.lint(good_layout).none? { |v| v.include?('raw-id') }, 'human name not flagged as raw-id')

# --- control_lint: dead control is a violation -------------------------------
puts '== control_lint =='
dead = { 'pages' => [ { 'id' => 'pg', 'name' => 'Overview', 'elements' => [
  { 'id' => 'tbl1', 'kind' => 'table', 'name' => 'Orders' },
  { 'id' => 'ctl1', 'kind' => 'control', 'controlId' => 'ctl-region', 'name' => 'Region' } ] } ] }
ok(ControlLint.lint(dead).any? { |v| v.include?('dead control') }, 'dead control (no target/formula ref) flagged')

wired = Marshal.load(Marshal.dump(dead))
wired['pages'][0]['elements'][1]['filters'] = [ { 'source' => { 'elementId' => 'tbl1' } } ]
ok(ControlLint.lint(wired).empty?, 'control filtering a table is clean')

if $failures.zero? then puts 'ALL PASS'; exit 0 else puts "#{$failures} FAILURE(S)"; exit 1 end
