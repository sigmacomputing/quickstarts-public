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
#  2. RECORD RUN METADATA to <workdir>/intake.json: run_start (run-duration /
#     wall-clock audit), input_mode (live|file|both), and the source
#     tool/identifier. Prints an expectations banner for the mode.
#
#  3. FRONT-DOOR TRIAGE (speed-review #6a): when an assessment's
#     migration-plan.json is present (--plan PATH, or <workdir>/migration-plan.json),
#     look up this run's --source workbook in it:
#       - retire-tagged (zero usage)      -> REFUSE (exit 7). "The fastest
#         migration is the one you don't do." Override with
#         --triage-override "<who>: <why>" (or SIGMA_TRIAGE_OVERRIDE) — the
#         override is recorded to <workdir>/offramps.jsonl, never silent.
#       - ranked low (tier 'moderate' / score < 10 / path 'blocked')
#                                          -> WARN with the plan's value/cost
#         line and continue. No stop.
#       - marked consolidate-into-primary  -> WARN (the user chose to convert
#         the primary instead) and continue.
#     No plan anywhere -> ONE offer line, never a block (ratified assumption:
#     the plan is usually absent; the no-plan path stays friction-free).
#     A malformed plan / missing --source / ambiguous name match -> one note
#     line, triage skipped — the guard must not false-stop (≤5% budget).
#
# Usage:
#   ruby scripts/intake.rb --workdir <dir> --tool tableau-to-sigma --mode live \
#     [--connection <UUID>] [--name <connection-name-substring>] [--source "<wb name/app id>"] \
#     [--plan <migration-plan.json>] [--triage-override "<who>: <why>"]
#
# Exit codes:
#   0  connection resolved (connection.json written) + intake.json written
#   2  --connection given but not a full UUID
#   3  connection ambiguous — connection-candidates.json written; ask the user
#   4  no connections found / API error while listing
#   6  bootstrap sentinel missing/failed — run bootstrap first (PLAN-v3 PR-15)
#   7  workbook is retire-tagged in migration-plan.json — refused; override
#      with --triage-override "<who>: <why>" (recorded to offramps.jsonl)
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
  p.on('--plan PATH', 'assessment migration-plan.json (default: <workdir>/migration-plan.json when present)') { |v| opts[:plan] = v }
  p.on('--triage-override REASON', 'convert a retire-tagged workbook anyway — REQUIRED "<who>: <why>"; recorded to offramps.jsonl') { |v| opts[:triage_override] = v }
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
# offramp.rb lives at scripts/lib/ in a vendored plugin copy and at ../lib/
# from this file's shared/scripts/ canonical home — load from either, so the
# audit trail works in both layouts.
def require_offramp
  [File.expand_path('lib', __dir__), File.expand_path('../lib', __dir__)].each do |p|
    $LOAD_PATH.unshift(p) unless $LOAD_PATH.include?(p)
  end
  require 'offramp'
  true
rescue LoadError
  false
end

if _bs_skip && !_bs_skip.to_s.empty?
  warn "[SKIP] intake: bootstrap gate WAIVED (#{_bs_skip}) — name this in your report."
  if require_offramp
    Offramp.log(opts[:dir], kind: 'skip-flag-waived', reason: _bs_skip,
                detail: '--skip-bootstrap-gate')
  else
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

# ── FRONT-DOOR TRIAGE (speed-review #6a) ────────────────────────────────────
# Runs BEFORE connection resolution: a workbook the estate plan says to retire
# should refuse before this run burns a single API call. Guard discipline
# (ratified ≤5% false-stop budget): the ONLY stop is a matched retire tag with
# no override; every degraded state (no plan, malformed plan, no --source, no
# match, ambiguous name) is a one-line note and a normal proceed.

# The plan's value/cost evidence, printed on every triage verdict that cites it.
def triage_value_line(e)
  parts = []
  %w[score value cost accesses actors].each do |k|
    parts << "#{k}=#{e[k]}" unless e[k].nil?
  end
  line = parts.empty? ? 'no usage/cost metrics recorded in the plan' : parts.join(', ')
  blockers = e['blockers'].is_a?(Array) ? e['blockers'] : []
  line += " — blockers: #{blockers.join('; ')}" unless blockers.empty?
  line
end

triage = nil
plan_path = opts[:plan] || File.join(opts[:dir], 'migration-plan.json')
if opts[:plan] && !File.exist?(opts[:plan])
  warn "[WARN] intake: --plan #{opts[:plan]} not found — triage skipped."
elsif File.exist?(plan_path)
  plan = (JSON.parse(File.read(plan_path, encoding: 'bom|utf-8')) rescue nil)
  rows = if plan.is_a?(Hash) then (plan['workbooks'] || [])
         elsif plan.is_a?(Array) then plan # shortlist.json-shaped input tolerated
         else []
         end
  src = opts[:source].to_s.strip
  if !(plan.is_a?(Hash) || plan.is_a?(Array))
    warn "[WARN] intake: #{plan_path} is unreadable — triage skipped."
  elsif src.empty?
    warn "[NOTE] intake: migration plan present but no --source given — triage skipped (pass the workbook name or id)."
  else
    wb_id_of = lambda { |r| r['workbookId'] || r['luid'] || r['id'] }
    entry = rows.find { |r| wb_id_of.call(r).to_s == src }
    ambiguous = false
    if entry.nil?
      by_name = rows.select { |r| r['name'].to_s.downcase == src.downcase }
      if by_name.size > 1
        # Ambiguity is its own (accurate) note — the name WAS found, just not
        # uniquely, so the not-found note below must stay silent.
        ambiguous = true
        warn "[NOTE] intake: #{by_name.size} plan entries share the name #{src.inspect} — triage skipped (re-run with --source <workbook id>)."
      end
      entry = by_name.first if by_name.size == 1
    end
    if entry.nil?
      unless ambiguous
        warn "[NOTE] intake: #{src.inspect} not found in #{plan_path} — triage skipped." \
             ' (Converting outside the assessed set? Consider re-running the assessment.)'
      end
    else
      tier  = (entry['priority_tier'] || entry['tag']).to_s
      path_ = entry['recommended_path'].to_s
      triage = { 'plan_path' => plan_path, 'workbook' => wb_id_of.call(entry) || entry['name'],
                 'recommended_path' => path_, 'priority_tier' => tier }
      if path_ == 'retire' || tier == 'retire'
        override = opts[:triage_override] || ENV['SIGMA_TRIAGE_OVERRIDE']
        if override && !override.to_s.strip.empty?
          warn "[WARN] intake: #{src.inspect} is RETIRE-tagged in the migration plan — converting anyway (override: #{override})."
          warn "       plan evidence: #{triage_value_line(entry)}"
          triage['verdict'] = 'retire-overridden'
          triage['override_reason'] = override.to_s.strip
          if require_offramp
            Offramp.log(opts[:dir], kind: 'triage-retire-override', reason: override.to_s.strip,
                        detail: "#{src} (#{triage_value_line(entry)})")
          else
            warn '       WARN: lib/offramp.rb not vendored — the override could not be recorded to offramps.jsonl.'
          end
        else
          warn "[FAIL] intake: #{src.inspect} is RETIRE-tagged in #{File.basename(plan_path)} — refusing to convert it."
          warn "       plan evidence: #{triage_value_line(entry)}"
          warn '       The fastest migration is the one you don\'t do: retiring unused content is the'
          warn '       assessment\'s highest-value recommendation. If the customer still wants this'
          warn '       workbook converted, re-run with an explicit, attributable override:'
          warn '         --triage-override "<who>: <why>"   (or SIGMA_TRIAGE_OVERRIDE="<who>: <why>")'
          warn '       The override is recorded to offramps.jsonl — never a silent proceed.'
          exit 7
        end
      elsif tier == 'moderate' || path_ == 'blocked' ||
            (entry['score'].is_a?(Numeric) && entry['score'] < 10)
        warn "[WARN] intake: #{src.inspect} is ranked LOW in the migration plan (tier=#{tier.empty? ? '?' : tier}, path=#{path_.empty? ? '?' : path_})."
        warn "       value/cost: #{triage_value_line(entry)}"
        warn '       Higher-ranked workbooks convert first for a reason — proceeding, but consider the shortlist order.'
        triage['verdict'] = 'low-value-warn'
      elsif path_ == 'consolidate-into-primary'
        primary = entry['consolidate_into']
        warn "[WARN] intake: the plan folds #{src.inspect} into a consolidation primary#{primary ? " (#{primary})" : ''} — the recorded decision is to convert the PRIMARY plus a control, not this variant."
        triage['verdict'] = 'consolidation-member-warn'
      else
        puts "[OK] intake: triage — #{src.inspect} #{tier.empty? ? '' : "tier=#{tier} "}path=#{path_.empty? ? '?' : path_} (#{triage_value_line(entry)})"
        triage['verdict'] = 'proceed'
      end
    end
  end
else
  # Ratified assumption: the plan is usually absent — ONE line, never a block.
  puts '[TIP] intake: no migration-plan.json — converting without estate triage. To rank value/cost'
  puts '      and retire-tags first, run the assessment skill and pass --plan <dir>/migration-plan.json.'
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

# Run metadata for run-duration + audit.
mode = %w[live file both].include?(opts[:mode]) ? opts[:mode] : 'unknown'
intake_rec = {
  'run_start'  => Time.now.utc.iso8601,
  'input_mode' => mode,
  'tool'       => opts[:tool],
  'source'     => opts[:source],
}
intake_rec['triage'] = triage if triage # plan consulted → verdict on the audit record
write_json(intake_path, intake_rec)

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
  puts '     INPUT MODE = unknown. Pass --mode live|file|both so the raw-mode banner is accurate.'
end
exit 0
