#!/usr/bin/env ruby
# Probe whether the current Tableau MCP session can see the Admin Insights
# project. Output: a JSON map of datasource-name → LUID for the agent to use
# when calling mcp__tableau__query-datasource.
#
# This script is NOT directly callable from a script (the MCP tools live in the
# agent's context). Instead, the agent runs `mcp__tableau__search-content` with
# the parameters below, and this script is invoked to PARSE that result.
#
# Usage:
#   echo '<search-content JSON output>' | ruby scripts/probe-admin-insights.rb
#
# Or pass via stdin from the agent's MCP call output.
#
# Output to stdout: JSON of the form
#   { "TS Users":     "<luid>",
#     "TS Events":    "<luid>",
#     "Site Content": "<luid>",
#     ... }
# plus a `_meta` key with { mode: "MCP+AdminInsights" | "MCP-only", coverage: <int> }

require 'json'

EXPECTED = [
  'TS Users', 'TS Events', 'Site Content', 'Job Performance',
  'Subscriptions', 'Groups', 'Tokens', 'Viz Load Times',
  'Permissions'
]

raw = STDIN.read
abort('no input on stdin') if raw.strip.empty?

# Accept either an array of search results or a single object wrapping `results`.
parsed = JSON.parse(raw)
results = parsed.is_a?(Array) ? parsed : (parsed['results'] || parsed['entries'] || [])

map = {}
results.each do |r|
  next unless r['containerName'] == 'Admin Insights' || (r['project'] && r['project']['name'] == 'Admin Insights')
  name = r['title'] || r['name']
  luid = r['luid']  || r['id']
  next unless name && luid
  map[name] = luid
end

missing = EXPECTED - map.keys

out = map.dup
out['_meta'] = {
  'mode'     => map.empty? ? 'MCP-only' : 'MCP+AdminInsights',
  'coverage' => map.size,
  'expected' => EXPECTED.size,
  'missing'  => missing
}

puts JSON.pretty_generate(out)
exit(map.empty? ? 2 : 0)
