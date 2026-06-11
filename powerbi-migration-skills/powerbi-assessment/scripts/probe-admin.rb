#!/usr/bin/env ruby
# Parse the output of the Fabric-admin probe (probe-admin.py) and decide which
# usage/sprawl sections the assessment can run.
#
# Mirrors tableau-assessment/scripts/probe-admin-insights.rb: that script PARSES
# an MCP search result to decide whether Admin Insights is reachable. Here the
# admin surface is the Power BI **Activity Events API** (usage/adoption: views,
# user counts) and the **Scanner API** (tenant-wide sprawl) — both gated behind
# the **Fabric Administrator** role.
#
# probe-admin.py hits one cheap call against each and prints a JSON status line
# to stdout. This script reads that JSON (stdin or --file) and emits a normalized
# capability map + a clear degrade decision.
#
#   { "activity_events": "ok" | "forbidden" | "error",
#     "scanner":         "ok" | "forbidden" | "error",
#     "_meta": { "mode": "admin" | "complexity-only", "reason": "..." } }
#
# Usage:
#   /tmp/pbiauth/bin/python scripts/probe-admin.py | ruby scripts/probe-admin.rb
#   ruby scripts/probe-admin.rb --file <probe-output.json>

require 'json'
require 'optparse'

opts = {}
OptionParser.new { |p| p.on('--file PATH') { |v| opts[:file] = v } }.parse!

raw = opts[:file] ? File.read(opts[:file]) : STDIN.read
abort('no probe input') if raw.strip.empty?

# probe-admin.py prints one JSON object; tolerate leading log lines.
json_str = raw[/\{.*\}/m] || raw
probe = JSON.parse(json_str)

activity = probe['activity_events'] || 'error'
scanner  = probe['scanner'] || 'error'

admin_ok = activity == 'ok'   # usage/adoption hinges on Activity Events
mode = admin_ok ? 'admin' : 'complexity-only'
reason =
  if admin_ok
    'Fabric Administrator role detected — usage/adoption available'
  elsif activity == 'forbidden'
    'Activity Events API returned 401/403 — needs Fabric Administrator role; ' \
      'producing a complexity-only shortlist'
  else
    'Activity Events API error (not a permission issue) — falling back to ' \
      'complexity-only shortlist'
  end

out = {
  'activity_events' => activity,
  'scanner'         => scanner,
  '_meta'           => { 'mode' => mode, 'reason' => reason }
}
puts JSON.pretty_generate(out)
exit(admin_ok ? 0 : 3)
