#!/usr/bin/env ruby
# Delete orphan Sigma workbooks left behind by spec-iteration retries during
# a single conversion. Reads <workdir>/posted-workbooks.jsonl (written by
# post-and-readback.rb), keeps the most-recent entry as the "live" workbook,
# and deletes everything older via DELETE /v2/files/{id} (per
# feedback_sigma_workbook_delete_endpoint memory — NOT /v2/workbooks/{id}).
#
# See beads-sigma-38a for the regression motivating this script: a customer
# migration on 2026-05-28 created three workbooks (one final + two orphans
# from iterative POSTs) and the agent declared done without cleaning up.
#
# Usage:
#   ruby scripts/cleanup-orphan-workbooks.rb --workdir /tmp/<name>
#     [--dry-run]               # report what would be deleted; don't call DELETE
#     [--keep ID]               # explicit workbook ID to keep (default: most recent)
#     [--allow-empty-log]       # exit 0 when the log doesn't exist (default: exit 0
#                                 silently anyway; this flag is just for clarity)
#
# Writes <workdir>/cleanup-marker.json with the deleted IDs and timestamp so
# assert-phase6-ran.rb can confirm cleanup ran.
#
# Exit codes:
#   0  cleanup ran (or no cleanup needed — single workbook in log)
#   1  one or more DELETE calls failed; cleanup-marker.json reflects partial state
#   2  setup error (missing env, bad args)

require 'net/http'
require 'uri'
require 'json'
require 'time'
require 'optparse'

opts = { dry_run: false }
OptionParser.new do |p|
  p.on('--workdir DIR')    { |v| opts[:workdir] = v }
  p.on('--dry-run')        { opts[:dry_run] = true }
  p.on('--keep ID')        { |v| opts[:keep] = v }
  p.on('--allow-empty-log') { opts[:allow_empty] = true }
end.parse!
abort('--workdir required') unless opts[:workdir]

log = File.join(opts[:workdir], 'posted-workbooks.jsonl')
unless File.exist?(log)
  puts "[OK] no posted-workbooks.jsonl at #{log} — nothing to clean up"
  exit 0
end

ids = File.readlines(log).map { |l| JSON.parse(l) rescue nil }.compact
if ids.empty?
  puts "[OK] posted-workbooks.jsonl is empty — nothing to clean up"
  exit 0
end

# Keep target: --keep override, otherwise the most-recent (last appended) entry.
keep_id = opts[:keep] || ids.last['id']
to_delete = ids.map { |e| e['id'] }.reject { |id| id == keep_id }.uniq

if to_delete.empty?
  puts "[OK] only one POSTed workbook (#{keep_id}) — no orphans to clean up"
  marker = {
    'ran_at'  => Time.now.utc.iso8601,
    'kept'    => keep_id,
    'deleted' => [],
    'dry_run' => opts[:dry_run]
  }
  File.write(File.join(opts[:workdir], 'cleanup-marker.json'), JSON.pretty_generate(marker))
  exit 0
end

base = ENV['SIGMA_BASE_URL'] or (warn 'SIGMA_BASE_URL not set'; exit 2)
$LOAD_PATH.unshift File.expand_path('lib', __dir__)
require 'sigma_rest'

def http_delete(base, tok, path)
  attempts = 0
  loop do
    attempts += 1
    uri = URI("#{base}#{path}")
    req = Net::HTTP::Delete.new(uri)
    req['Authorization'] = "Bearer #{Sigma.auth_token}"
    req['Accept']        = 'application/json'
    res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, read_timeout: 30) { |h| h.request(req) }
    if res.code.to_i == 401 && attempts == 1 && ENV['SIGMA_CLIENT_ID']
      Sigma.refresh_token!
      next
    end
    return res
  end
end

puts "Keeping:  #{keep_id}"
puts "Orphans:  #{to_delete.length}"
to_delete.each { |id| puts "          - #{id}" }
puts ''

if opts[:dry_run]
  puts "[DRY-RUN] would DELETE /v2/files/<id> for each orphan above. No calls made."
  marker = {
    'ran_at'  => Time.now.utc.iso8601,
    'kept'    => keep_id,
    'deleted' => [],
    'would_delete' => to_delete,
    'dry_run' => true
  }
  File.write(File.join(opts[:workdir], 'cleanup-marker.json'), JSON.pretty_generate(marker))
  exit 0
end

deleted = []
failed  = []
to_delete.each do |id|
  r = http_delete(base, nil, "/v2/files/#{id}")
  code = r.code.to_i
  if code.between?(200, 299) || code == 404
    # 404 = already gone; treat as success for idempotency
    puts "  [deleted] #{id} (HTTP #{code})"
    deleted << { 'id' => id, 'status' => code }
  else
    body = r.body.to_s[0..200]
    puts "  [FAIL]    #{id} (HTTP #{code}) — #{body}"
    failed << { 'id' => id, 'status' => code, 'body' => body }
  end
end

marker = {
  'ran_at'  => Time.now.utc.iso8601,
  'kept'    => keep_id,
  'deleted' => deleted,
  'failed'  => failed,
  'dry_run' => false
}
File.write(File.join(opts[:workdir], 'cleanup-marker.json'), JSON.pretty_generate(marker))

if failed.any?
  warn "\n#{failed.length} of #{to_delete.length} delete(s) FAILED — cleanup-marker.json"
  warn "records the failure. Re-run with the failing IDs (--keep <good-id>) or"
  warn "delete them manually via the Sigma UI before declaring done."
  exit 1
end

puts "\n[OK] cleaned up #{deleted.length} orphan workbook(s); kept #{keep_id}"
exit 0
