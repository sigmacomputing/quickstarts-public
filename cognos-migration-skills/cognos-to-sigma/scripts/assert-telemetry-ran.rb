#!/usr/bin/env ruby
# Hard gate that proves the telemetry step was not silently skipped.
#
# The migration skills send an anonymous usage ping at the end of a run, but
# ONLY after asking the user for consent. That step lived as prose in each
# SKILL.md, so an agent could (and did — the powerbi case) wrap up a migration
# without ever prompting. This gate makes the decision mandatory: before a
# conversion may declare GREEN, the agent must have EITHER sent the ping OR
# recorded that the user declined. Either outcome writes a marker
# (telemetry-sent.json) via report-telemetry.py; this gate checks the marker.
#
# It never touches the network and never inspects payload contents — telemetry
# must never block or fail a migration. It only enforces that the consent
# decision happened once.
#
# Usage:
#   ruby scripts/assert-telemetry-ran.rb --workdir /tmp/<run>
#     [--skip-telemetry-gate REASON]   # waive — REQUIRED reason, name it in
#                                       # your migration report
#
# Exit codes:
#   0  marker present (sent or declined) — telemetry step was handled
#   1  --workdir missing / unreadable
#   12 no telemetry marker — the consent step was skipped

require 'json'
require 'optparse'

opts = {}
OptionParser.new do |p|
  p.on('--workdir DIR')               { |v| opts[:dir] = v }
  p.on('--tableau DIR', 'alias of --workdir') { |v| opts[:dir] = v }
  p.on('--skip-telemetry-gate REASON',
       'waive this gate — REQUIRED reason string. Name it in your migration report.') { |v| opts[:skip] = v }
end.parse!

unless opts[:dir]
  warn '[FAIL] telemetry gate: --workdir (or --tableau) required'
  exit 1
end

if opts[:skip]
  puts "[SKIP] telemetry gate: WAIVED via --skip-telemetry-gate (#{opts[:skip]})."
  puts '       This waiver MUST be named in the migration report — no usage ping decision was recorded.'
  exit 0
end

marker = File.join(opts[:dir], 'telemetry-sent.json')
unless File.exist?(marker)
  warn '[FAIL] telemetry gate: no telemetry-sent.json marker — the anonymous usage ping was never handled.'
  warn '       Before declaring GREEN you MUST ask the user for consent, then record the decision:'
  warn "         send:    python3 scripts/report-telemetry.py --tool <skill> --duration <sec> --workdir #{opts[:dir]} [--mode live|file|both] [--failed]"
  warn "         decline: python3 scripts/report-telemetry.py --tool <skill> --workdir #{opts[:dir]} --declined"
  warn '       Escape hatch (genuinely cannot prompt — e.g. unattended CI): --skip-telemetry-gate "<reason>".'
  exit 12
end

rec = (JSON.parse(File.read(marker)) rescue nil)
status = rec.is_a?(Hash) ? rec['status'] : nil
# "skipped" = consent given + send attempted but the endpoint was unreachable
# (handoff FIX 3). Telemetry must never block, so it still passes — the marker is
# honest about non-delivery instead of faking "sent".
unless %w[sent declined skipped].include?(status)
  warn "[FAIL] telemetry gate: #{marker} present but status is #{status.inspect} (expected \"sent\", \"declined\", or \"skipped\")."
  warn '       Re-run report-telemetry.py to write a valid marker.'
  exit 12
end

puts "[OK] telemetry gate: usage-ping decision recorded (status=#{status}" \
     "#{rec['tool'] ? ", tool=#{rec['tool']}" : ''}#{rec['mode'] ? ", mode=#{rec['mode']}" : ''})"
exit 0
