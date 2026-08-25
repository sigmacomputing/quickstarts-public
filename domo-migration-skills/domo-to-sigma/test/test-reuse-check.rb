#!/usr/bin/env ruby
# Offline: build-dm honors find-or-pick-dm.rb's REAL decision file (C3) instead of
# always creating a DM. find-or-pick-dm.rb writes discovery/dm-match.json shaped
# {recommended_dm_id, auto_picked, ...} (verified against its --out writer and the
# sibling cognos/looker converters, which reuse recommended_dm_id ONLY when
# auto_picked is true).
require 'json'
require 'tmpdir'
$failures = 0
def ok(c, m) if c then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}" end end
def eq(a, b, m) if a == b then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}\n    exp #{b.inspect}\n    got #{a.inspect}" end end
SCRIPTS = File.expand_path('../scripts', __dir__)

def run_build(dir)
  env = { 'DOMO_DISCOVERY_DIR' => dir, 'SIGMA_SKIP_DOCTOR_GATE' => 'test: env not under test' }
  system(env, 'ruby', File.join(SCRIPTS, 'build-dm.rb'), out: File::NULL, err: File::NULL)
end

puts '== C3 reuse-check: auto_picked dm-match.json short-circuits DM creation =='
Dir.mktmpdir('domo-reuse') do |dir|
  File.write(File.join(dir, 'dm-match.json'), JSON.generate({ 'recommended_dm_id' => 'inode-REUSE01', 'auto_picked' => true }))
  run_build(dir)
  ok(File.exist?(File.join(dir, 'dm-reuse.json')), 'writes dm-reuse.json when auto_picked')
  ok(!File.exist?(File.join(dir, 'dm-spec.json')), 'does NOT emit a fresh dm-spec.json when auto_picked')
  marker = JSON.parse(File.read(File.join(dir, 'dm-reuse.json')))
  eq(marker['reused'], 'inode-REUSE01', 'marker records the reused id')
end

puts '== C3 reuse-check: NOT auto_picked -> build-dm does NOT short-circuit =='
Dir.mktmpdir('domo-reuse-noauto') do |dir|
  File.write(File.join(dir, 'dm-match.json'), JSON.generate({ 'recommended_dm_id' => 'inode-X', 'auto_picked' => false }))
  run_build(dir) # may exit non-zero once it proceeds to load (missing) datasets.json/etc — that's fine
  ok(!File.exist?(File.join(dir, 'dm-reuse.json')), 'does NOT write dm-reuse.json when auto_picked is false')
end

if $failures.zero? then puts 'ALL PASS'; exit 0 else puts "#{$failures} FAILURE(S)"; exit 1 end
