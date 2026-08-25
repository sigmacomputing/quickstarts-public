#!/usr/bin/env ruby
# intake.rb — migration front-door. Run this ONCE, first, before discovery.
#
# It does the two things every converter otherwise improvises (badly):
#
#  1. RESOLVE THE SIGMA CONNECTION ONCE and cache it, so no downstream phase
#     free-searches /v2/connections (the token sink). Precedence (decision D2 —
#     config-first, prompt on miss):
#       a. --connection <UUID>                  explicit flag wins
#       b. cached <workdir>/connection.json     idempotent re-runs reuse it
#       c. ENV['SIGMA_CONNECTION_ID']           from ~/.sigma-migration/env (setup.rb)
#       d. list /v2/connections ONCE:
#            - exactly one connection            -> auto-pick
#            - --name SUBSTR uniquely matches     -> auto-pick
#            - otherwise -> write connection-candidates.json and exit 3 so the
#              agent ASKS THE USER, then re-runs with --connection <id>.
#              (We never guess among multiple, and never free-search per phase.)
#
#  2. RECORD RUN METADATA to <workdir>/intake.json: run_start (feeds telemetry
#     duration), input_mode (live|file|both — feeds telemetry --mode), and the
#     source tool/identifier. Prints an expectations banner for the mode.
#
# Usage:
#   ruby scripts/intake.rb --workdir <dir> --tool tableau-to-sigma --mode live \
#     [--connection <UUID>] [--name <connection-name-substring>] [--source "<wb name/app id>"]
#
# Exit codes:
#   0  connection resolved (connection.json written) + intake.json written
#   2  --connection given but not a full UUID
#   3  connection ambiguous — connection-candidates.json written; ask the user
#   4  no connections found / API error while listing
#   6  bootstrap sentinel missing/failed — run bootstrap first (PLAN-v3 PR-15)
#   1  usage error

require 'json'
require 'optparse'
require 'time'

opts = { mode: 'unknown' }
OptionParser.new do |p|
  p.on('--workdir DIR')      { |v| opts[:dir] = v }
  p.on('--tableau DIR', 'alias of --workdir') { |v| opts[:dir] = v }
  p.on('--tool NAME')        { |v| opts[:tool] = v }
  p.on('--mode MODE', 'live | file | both (input mode)') { |v| opts[:mode] = v }
  p.on('--connection ID')    { |v| opts[:conn] = v }
  p.on('--name SUBSTR', 'connection display-name substring to disambiguate') { |v| opts[:name] = v }
  p.on('--source STR', 'source identifier (workbook name / app id) for the audit record') { |v| opts[:source] = v }
  p.on('--rank-workbook-id LUID', 'when ambiguous, rank candidates by the Tableau workbook\'s warehouse (type+host) and auto-pick a unique match') { |v| opts[:rank_wb] = v }
  p.on('--rank-twb PATH', 'when ambiguous, rank candidates using a downloaded .twb (adds db-name tie-break)') { |v| opts[:rank_twb] = v }
  p.on('--connections-fixture FILE', 'TEST ONLY: read the connections list from FILE instead of the API') { |v| opts[:fixture] = v }
  p.on('--force', 'ignore a cached connection.json and re-resolve') { opts[:force] = true }
  p.on('--skip-bootstrap-gate REASON', 'waive the bootstrap-sentinel gate — REQUIRED reason; name it in your report') { |v| opts[:skip_bootstrap] = v }
end.parse!

abort('[FAIL] intake: --workdir required') unless opts[:dir]
require 'fileutils'
FileUtils.mkdir_p(opts[:dir])

# 🚧 BOOTSTRAP SENTINEL GATE (PLAN-v3 PR-15). Environment bootstrap burned
# ~25–30% of field tokens (hand-driven runtime installs, TTY/creds failures);
# the fix is ONE idempotent command — so the front door refuses to open until
# it has run to doctor-green. The sentinel (bootstrap.json) is written by
# scripts/bootstrap.sh / bootstrap.ps1 after they finish with a doctor run.
_bs_skip = opts[:skip_bootstrap] || ENV['SIGMA_SKIP_BOOTSTRAP_GATE']
if _bs_skip && !_bs_skip.to_s.empty?
  warn "[SKIP] intake: bootstrap gate WAIVED (#{_bs_skip}) — name this in your report."
  begin
    $LOAD_PATH.unshift File.expand_path('lib', __dir__)
    require 'offramp'
    Offramp.log(opts[:dir], kind: 'skip-flag-waived', reason: _bs_skip,
                detail: '--skip-bootstrap-gate')
  rescue LoadError
    warn '       WARN: lib/offramp.rb not vendored — the waiver could not be recorded to offramps.jsonl.'
  end
else
  _bs = [File.join(opts[:dir], 'bootstrap.json'),
         File.expand_path('~/.sigma-migration/bootstrap.json')]
        .map { |p| (JSON.parse(File.read(p, encoding: 'bom|utf-8')) rescue nil) }
        .find { |j| j.is_a?(Hash) }
  unless _bs && _bs['doctor_pass'] == true
    _bs_why = _bs ? 'bootstrap ran but the doctor did NOT pass' :
                    'no bootstrap sentinel found (bootstrap never ran on this machine/workdir)'
    warn "[FAIL] intake: #{_bs_why}."
    warn '       Run the ONE bootstrap command first (idempotent, non-interactive, no admin):'
    warn '         macOS/Linux/Git-Bash:  bash scripts/bootstrap.sh'
    warn '         Windows PowerShell:    powershell -ExecutionPolicy Bypass -File scripts\\bootstrap.ps1'
    warn '       …then re-run this exact intake command.'
    warn '       Escape hatch (name it in your report): --skip-bootstrap-gate "<reason>"'
    warn '       (or SIGMA_SKIP_BOOTSTRAP_GATE="<reason>").'
    exit 6
  end
end

UUID_RE = /\A\h{8}-\h{4}-\h{4}-\h{4}-\h{12}\z/
conn_path  = File.join(opts[:dir], 'connection.json')
cand_path  = File.join(opts[:dir], 'connection-candidates.json')
intake_path = File.join(opts[:dir], 'intake.json')

def write_json(path, obj)
  tmp = "#{path}.tmp"
  File.write(tmp, JSON.pretty_generate(obj))
  File.rename(tmp, path)   # atomic — no half-written sidecar reads
end

# Normalize a connection record from /v2/connections (entries[]) into our shape.
# host/account/warehouse are carried so the connection auto-ranker (rank-connections.rb)
# can match the workbook's warehouse without a second /v2/connections fetch.
def norm_conn(c)
  {
    'connection_id' => c['connectionId'] || c['id'],
    'name'          => c['name'] || c['label'],
    'type'          => c['type'] || c['connectionType'] || c.dig('warehouse', 'type'),
    'host'          => c['host'],
    'account'       => c['account'],
    'warehouse'     => c['warehouse'],
  }
end

# Fetch the connection list once (or from a fixture, for tests).
def list_connections(opts)
  if opts[:fixture]
    data = JSON.parse(File.read(opts[:fixture]))
  else
    require_relative 'lib/sigma_rest'
    data = Sigma.request(:get, '/v2/connections?limit=500')
  end
  rows = data.is_a?(Hash) ? (data['entries'] || data['connections'] || []) : (data || [])
  rows.map { |c| norm_conn(c) }.reject { |c| c['connection_id'].to_s.empty? }
end

resolved = nil
resolved_via = nil

# (a) explicit flag
if opts[:conn]
  unless opts[:conn] =~ UUID_RE
    warn "[FAIL] intake: --connection must be a FULL Sigma connection UUID (8-4-4-4-12 hex); got #{opts[:conn].inspect}."
    exit 2
  end
  resolved = { 'connection_id' => opts[:conn], 'name' => opts[:name], 'type' => nil }
  resolved_via = 'flag'
end

# (b) cached connection.json
if resolved.nil? && !opts[:force] && File.exist?(conn_path)
  cached = (JSON.parse(File.read(conn_path)) rescue nil)
  if cached.is_a?(Hash) && cached['connection_id'].to_s =~ UUID_RE
    resolved = cached.slice('connection_id', 'name', 'type')
    resolved_via = 'cache'
  end
end

# (c) ENV (loaded from ~/.sigma-migration/env by setup.rb / sigma_rest.rb)
if resolved.nil? && ENV['SIGMA_CONNECTION_ID'].to_s =~ UUID_RE
  resolved = { 'connection_id' => ENV['SIGMA_CONNECTION_ID'], 'name' => opts[:name], 'type' => nil }
  resolved_via = 'env'
end

# (d) list /v2/connections ONCE and pick deterministically
if resolved.nil?
  begin
    conns = list_connections(opts)
  rescue => e
    warn "[FAIL] intake: could not list connections — #{e.message}"
    exit 4
  end
  if conns.empty?
    warn '[FAIL] intake: no Sigma connections found for these credentials.'
    exit 4
  end
  pick = nil
  if opts[:name]
    matches = conns.select { |c| c['name'].to_s.downcase.include?(opts[:name].downcase) }
    pick = matches.first if matches.size == 1
  end
  pick ||= conns.first if conns.size == 1
  if pick
    resolved = pick
    resolved_via = (conns.size == 1 ? 'only-connection' : 'name-match')
  else
    # Auto-rank against the Tableau workbook's warehouse (type + host/account) when a
    # rank source is supplied. A UNIQUE type+host match auto-resolves (the whole point
    # of the front door — no manual .twb grep, no 26-way guess); otherwise we still ASK
    # but hand the agent a ranked list with a clear top pick.
    ranked = nil
    # rank-connections.rb ships only where a warehouse fingerprint is available
    # (tableau-to-sigma). In other plugins the ranker is absent, so the flags no-op
    # and we fall through to the plain ASK — the shared front door stays generic.
    if (opts[:rank_wb] || opts[:rank_twb]) && File.exist?(File.join(__dir__, 'rank-connections.rb'))
      begin
        require_relative 'rank-connections'
        fp = {}
        if opts[:rank_wb]
          require_relative 'lib/tableau_rest'
          begin; Tableau.site_id; rescue Tableau::Error; Tableau.refresh_token!; end
          fp = RankConnections.merge_fp(fp, RankConnections.fingerprint_from_workbook(Tableau, opts[:rank_wb]))
        end
        if opts[:rank_twb] && File.exist?(opts[:rank_twb])
          fp = RankConnections.merge_fp(fp, RankConnections.fingerprint_from_twb(File.read(opts[:rank_twb], encoding: 'UTF-8')))
        end
        ranked = RankConnections.rank(fp, conns) unless fp['type'].to_s.empty?
        ranked && (ranked['fingerprint'] = fp)
      rescue => e
        warn "      (auto-rank unavailable: #{e.message} — falling back to a plain ASK)"
      end
    end

    if ranked && ranked['confident']
      resolved = ranked['recommended'].slice('connection_id', 'name', 'type')
      resolved_via = 'auto-rank'
      warn "[OK] intake: auto-ranked #{conns.size} connections against the workbook's warehouse " \
           "(type=#{RankConnections.canon_type(ranked['fingerprint']['type'])} host=#{ranked['fingerprint']['host'] || '?'})."
      warn "     → picked #{resolved['name']} (#{resolved['connection_id']}) — #{ranked['recommended']['match_reasons'].join('; ')}"
      warn '     (override with --connection <id> --force if this is wrong.)'
    else
      out = ranked ? ranked['ranked'] : conns.map { |c| c.merge('match_score' => nil) }
      write_json(cand_path, { 'count' => conns.size, 'candidates' => out, 'ranked' => !ranked.nil?, 'fingerprint' => (ranked && ranked['fingerprint']) })
      warn "[ASK] intake: #{conns.size} connections available — cannot pick safely#{ranked ? ' (ranked, but no unique warehouse match)' : ''}."
      warn "      Candidates written to #{cand_path}. Ask the user which to use, then re-run:"
      warn "        ruby scripts/intake.rb --workdir #{opts[:dir]} --connection <id>"
      unless ranked
        warn '      TIP: pass --rank-workbook-id <LUID> (or --rank-twb <path>) to pre-rank by the'
        warn '           workbook\'s warehouse and auto-pick a unique match — or run scripts/rank-connections.rb.'
      end
      (out).first(10).each { |c| warn "        - #{c['connection_id']}  #{c['name']} (#{c['type']})#{c['match_score'] ? "  [score #{c['match_score']}]" : ''}" }
      exit 3
    end
  end
end

resolved['resolved_via'] = resolved_via
resolved['at'] = Time.now.utc.iso8601
write_json(conn_path, resolved)
File.delete(cand_path) if File.exist?(cand_path)   # resolved now; clear stale candidates

# Run metadata for telemetry + audit.
mode = %w[live file both].include?(opts[:mode]) ? opts[:mode] : 'unknown'
write_json(intake_path, {
  'run_start'  => Time.now.utc.iso8601,
  'input_mode' => mode,
  'tool'       => opts[:tool],
  'source'     => opts[:source],
})

puts "[OK] intake: connection #{resolved['connection_id']} (#{resolved['name'] || '?'}) via #{resolved_via} → #{conn_path}"
puts "[OK] intake: mode=#{mode}, tool=#{opts[:tool] || '?'} → #{intake_path}"
case mode
when 'file'
  puts '     INPUT MODE = file (raw export, no live source connection). The build runs from the'
  puts '     export; parity is verified against the live SIGMA WAREHOUSE, not the source tool.'
  dash_dir = File.join(opts[:dir], 'dashboards')
  puts ''
  puts '     [ASSIST] NO LIVE SOURCE TO AUTO-RENDER — ASK THE USER FOR DASHBOARD SCREENSHOTS.'
  puts '     Layout is inferred from export COORDINATES only; without a picture of the source the'
  puts '     visual gates (visual-compare, source-anchor values, visual-similarity) have nothing to'
  puts '     check against and SELF-SKIP — layout errors then ship unseen. Before building, ask the'
  puts '     user (AskUserQuestion) for a screenshot of EACH source dashboard page (one PNG per page)'
  puts "     and drop them here: #{dash_dir}/"
  puts '     Landing them there ARMS the visual gates. If the user has none, the gates are WAIVED'
  puts '     with a stated reason at Phase 6 — never a silent skip.'
when 'both', 'live'
  puts "     INPUT MODE = #{mode}. Live source available — full source-side parity verification applies."
else
  puts '     INPUT MODE = unknown. Pass --mode live|file|both so telemetry + the raw-mode banner are accurate.'
end
exit 0
