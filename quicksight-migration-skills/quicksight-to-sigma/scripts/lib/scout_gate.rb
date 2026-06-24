# frozen_string_literal: true
#
# Shared "run-each-time gap-scout gate" (bead beads-sigma-5l5e).
#
# The guarantee: a migration may NOT proceed past its unhandled-feature gaps
# unless the gap-scout actually ran for EVERY one — either it validated a Sigma
# translation (`validated`) or it tried and could not (`escalated`). A blanket
# --force must NOT skip the scout; it may only accept gaps the scout escalated.
#
# This module is the reusable core, identical across every migration plugin:
#   - ScoutGate.record  — scout-validate-and-persist.rb appends one ledger row
#   - ScoutGate.classify — the orchestrator reads the ledger and splits the
#                          unhandled gaps into unscouted / escalated / validated
# Each plugin maps its own gap representation to a list of stable gap-id strings
# and calls classify; the gap-id naming is the plugin's business, the gate is not.
#
# Kept dependency-free (json/time only) so it can be vendored into any plugin's
# scripts/lib/ unchanged.
require 'json'
require 'time'

module ScoutGate
  LEDGER = 'scout-ledger.jsonl'

  def self.ledger_path(workdir)
    File.join(workdir.to_s, LEDGER)
  end

  # Append one scout result to the per-conversion ledger. Non-fatal on error —
  # a failed ledger write must never crash a scout that otherwise succeeded.
  def self.record(workdir, gap_id:, feature:, status:)
    return false unless workdir && Dir.exist?(workdir)
    row = { 'gap_id' => (gap_id || feature).to_s, 'feature' => feature.to_s,
            'status' => status.to_s, 'at' => Time.now.utc.iso8601 }
    File.open(ledger_path(workdir), 'a') { |f| f.puts(JSON.generate(row)) }
    true
  rescue StandardError => e
    warn "scout-ledger write failed (non-fatal): #{e.message}"
    false
  end

  def self.read_ledger(workdir)
    p = ledger_path(workdir)
    return [] unless File.exist?(p)
    File.readlines(p).map { |l| JSON.parse(l) rescue nil }.compact
  end

  # gap_ids: Array<String> — the unhandled gaps the scout was supposed to cover.
  # Returns a Hash with three disjoint buckets of gap-ids:
  #   :unscouted — no ledger row at all (the scout never ran) → hard STOP
  #   :escalated — scouted, every row is 'escalated' (tried, unsolved) → --force
  #   :validated — has at least one 'validated' row (solved locally)
  def self.classify(workdir, gap_ids)
    by = read_ledger(workdir).group_by { |e| e['gap_id'].to_s }
    unscouted = gap_ids.reject { |id| by[id.to_s] }
    rest      = gap_ids.select { |id| by[id.to_s] }
    validated = rest.select { |id| by[id.to_s].any? { |x| x['status'] == 'validated' } }
    escalated = rest - validated
    { unscouted: unscouted, escalated: escalated, validated: validated }
  end
end
