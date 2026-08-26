#!/usr/bin/env ruby
# Offline: PDP detection (C9) — flag row-level policies, never silently drop.
#   ruby test/test-pdp-detect.rb
require 'json'
require 'tmpdir'
require_relative '../scripts/lib/domo_sigma_util'
include DomoSigma
$failures = 0
def eq(a, b, m) if a == b then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}\n    exp #{b.inspect}\n    got #{a.inspect}" end end
def ok(c, m) eq(!!c, true, m) end

puts '== detect_pdp: reads permission/pdp block =='
ds = { 'id' => 'ds1', 'name' => 'Orders',
       'permission' => { 'policies' => [
         { 'id' => 'p1', 'name' => 'West only', 'predicates' => ['region = "West"'] } ] } }
pols = detect_pdp(ds)
eq(pols.length, 1, 'one policy detected')
eq(pols.first['id'], 'p1', 'policy id')
eq(pols.first['predicates'], ['region = "West"'], 'predicates preserved')

puts '== detect_pdp: no PDP → empty (not nil) =='
eq(detect_pdp({ 'id' => 'ds2', 'name' => 'Plain' }), [], 'empty array when no policies')

puts '== build-dm: PDP dataset → rls-todo.json + no silent drop =='
Dir.mktmpdir('domo-pdp') do |dir|
  w = ->(n, o) { File.write(File.join(dir, n), JSON.generate(o)) }
  w.('datasets.json', [{ 'id' => 'ds1', 'name' => 'Orders', 'columns' => [{ 'name' => 'region', 'type' => 'STRING' }],
                         'permission' => { 'policies' => [{ 'id' => 'p1', 'name' => 'West', 'predicates' => ['region = "West"'] }] } }])
  w.('cards.json', [{ 'id' => 'c1', 'datasetId' => 'ds1' }])
  w.('formulas.json', [])
  # dataset-map.json entry shape mirrors build-dm.rb's own template
  # (connectionId/database/schema/table/name), NOT a nested path array.
  w.('dataset-map.json', { 'ds1' => { 'connectionId' => 'inode-CONN', 'database' => 'DB',
                                       'schema' => 'SCH', 'table' => 'ORDERS', 'name' => 'Orders' } })
  env = { 'DOMO_DISCOVERY_DIR' => dir, 'SIGMA_SKIP_DOCTOR_GATE' => 'test',
          'SIGMA_SKIP_COLUMN_PREFLIGHT' => 'test: pdp detection under test, not column pre-flight' }
  system(env, 'ruby', File.expand_path('../scripts/build-dm.rb', __dir__), out: File::NULL, err: File::NULL)
  ok(File.exist?(File.join(dir, 'rls-todo.json')), 'rls-todo.json written for PDP dataset')
  todo = JSON.parse(File.read(File.join(dir, 'rls-todo.json')))
  eq(todo['policies'].length, 1, 'rls-todo.json carries the one detected policy')
  eq(todo['policies'].first['id'], 'p1', 'rls-todo.json policy id round-trips')
end

if $failures.zero? then puts 'ALL PASS'; exit 0 else puts "#{$failures} FAILURE(S)"; exit 1 end
