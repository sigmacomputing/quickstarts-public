#!/usr/bin/env ruby
# Contract tests for the vendored environment gate (assert-doctor-ran.rb) — the
# Windows / cross-user parity gate the build phases enforce. The gate must:
#   - FAIL when no doctor.json exists (the Step-0 doctor never ran),
#   - PASS on a pass:true doctor.json,
#   - FAIL on a pass:false doctor.json,
#   - tolerate a UTF-8 BOM (Windows PowerShell writes one — regression guard),
#   - honor the --skip-doctor-gate waiver,
#   - BLOCK on excessive version drift, overridable via SIGMA_MAX_BEHIND.
# Offline: no network, no creds. Runs the gate as a subprocess under an isolated
# HOME so the machine's real ~/.sigma-migration/doctor.json never leaks in.
#   ruby test/test-doctor-gate.rb
require 'json'
require 'tmpdir'
require 'fileutils'

GATE = File.expand_path('../scripts/assert-doctor-ran.rb', __dir__)
$failures = 0
def eq(a, b, m) if a == b then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}\n    exp #{b.inspect}\n    got #{a.inspect}" end end

# Run the gate with an isolated HOME + controlled args/env; return exit status.
def run_gate(home:, workdir: nil, skip: nil, max_behind: nil)
  cmd = ['ruby', GATE]
  cmd += ['--workdir', workdir] if workdir
  cmd += ['--skip-doctor-gate', skip] if skip
  env = { 'HOME' => home }
  env['SIGMA_MAX_BEHIND'] = max_behind.to_s if max_behind
  system(env, *cmd, out: File::NULL, err: File::NULL)
  $?.exitstatus
end

def write_doctor(dir, hash, bom: false)
  FileUtils.mkdir_p(dir)
  body = JSON.generate(hash)
  body = "\xEF\xBB\xBF".b + body.b if bom   # simulate PowerShell's UTF-8 BOM
  File.binwrite(File.join(dir, 'doctor.json'), body)
end

Dir.mktmpdir do |home|
  Dir.mktmpdir do |wd|
    puts "== missing doctor.json (doctor never ran) =="
    eq(run_gate(home: home, workdir: wd), 1, 'no doctor.json anywhere → exit 1')

    puts "== waiver bypasses a missing doctor.json =="
    eq(run_gate(home: home, workdir: wd, skip: 'CI sandbox, no runtime'), 0, '--skip-doctor-gate "<reason>" → exit 0')

    puts "== passing doctor.json =="
    write_doctor(wd, { 'os' => 'macos', 'shell' => 'bash',
                       'runtimes' => { 'ruby' => true, 'python' => true, 'node' => true, 'bash' => true },
                       'sandbox_hint' => 'none', 'behind_count' => 0, 'pass' => true, 'failures' => [] })
    eq(run_gate(home: home, workdir: wd), 0, 'pass:true → exit 0')

    puts "== passing doctor.json WITH utf-8 BOM (Windows PowerShell regression) =="
    write_doctor(wd, { 'os' => 'windows', 'shell' => 'powershell',
                       'runtimes' => { 'ruby' => true }, 'behind_count' => nil, 'pass' => true, 'failures' => [] }, bom: true)
    eq(run_gate(home: home, workdir: wd), 0, 'BOM-prefixed pass:true still parses → exit 0')

    puts "== failing doctor.json =="
    write_doctor(wd, { 'os' => 'macos', 'shell' => 'bash',
                       'runtimes' => { 'ruby' => false }, 'behind_count' => 0, 'pass' => false, 'failures' => ['ruby not found'] })
    eq(run_gate(home: home, workdir: wd), 1, 'pass:false → exit 1')

    puts "== version-drift hard gate =="
    write_doctor(wd, { 'os' => 'macos', 'shell' => 'bash', 'runtimes' => { 'ruby' => true },
                       'skill_sha' => 'abc1234', 'behind_count' => 999, 'pass' => true, 'failures' => [] })
    eq(run_gate(home: home, workdir: wd, max_behind: 50), 1, 'behind_count 999 > 50 → exit 1 even when pass:true')
    eq(run_gate(home: home, workdir: wd, max_behind: 100000), 0, 'raising SIGMA_MAX_BEHIND clears the drift block → exit 0')
  end
end

puts
if $failures.zero? then puts "ALL PASS"; exit 0 else puts "#{$failures} FAILURE(S)"; exit 1 end
