#!/usr/bin/env ruby
# Phase 2 — Beast Mode (MySQL SQL) → Sigma formula.
#
# Beast Mode is MySQL-dialect SQL, so the actual translation is delegated to the
# ONE source of truth: the `convert_sql_to_sigma_formula` MCP tool (which already
# handles CASE WHEN, IN lists, DATEDIFF, arithmetic, and SNAKE_CASE → [Title
# Case] column refs). This script does NOT reimplement translation. It adds the
# two layers the generic SQL converter can't know about:
#
#   PRE  — Domo-specific normalization (backtick identifiers → [Col], WEEKDAY →
#          DAYOFWEEK, flag unsupported fns, flag the CEILING/FLOOR-are-aggregates
#          trap, flag window/LOD Beast Modes) — see refs/beast-mode-to-sigma.md.
#   POST — Sigma-specific lint of the returned formula (leftover IN(, And()/Or()/
#          Not() function-call forms that silently null, window-fn workbook-master
#          limits) — see refs/beast-mode-to-sigma.md + feedback_sigma_window_functions.
#
# Two-step flow (the skill's Phase 2 orchestrates the middle step):
#   ruby scripts/convert-beast-modes.rb          # normalize → discovery/formulas.pending.json
#   # → skill calls convert_sql_to_sigma_formula(sql: normalizedSql) per entry,
#   #   writes the result into `sigmaFormula`, applies preWarning overrides.
#   ruby scripts/convert-beast-modes.rb --lint   # validate filled pending → discovery/formulas.json
#
# HAND-AUTHORED ESCAPE HATCH — discovery/formula-overrides.json
#
# UPDATE 2026-07-30: the shared `convert_sql_to_sigma_formula` DOES now
# translate `CASE WHEN` (→ `If(cond, then, else)`) and `COUNT(DISTINCT x)`
# (→ `CountDistinct(x)`) — fixed upstream in sigma-data-model-mcp PR #115
# (squashed as 2ba3ea8). Beads jva2 and sqp1 are closed.
#
# UPDATE 2026-07-30 (later same day): the double-bracketing collision this
# script's own step 1 used to trigger — handing the converter an
# ALREADY-bracketed, ALL-CAPS identifier (`SUM(\`NET_REVENUE\`)` → step 1 →
# `SUM([NET_REVENUE])`), which the converter's own bracket-wrapping pass used
# to wrap AGAIN into invalid `Sum([[Net Revenue]])` — is **also fixed**
# upstream, in sigma-data-model-mcp PR #116. Bead `qorq` is closed. Re-verified
# live against PR #116: all four Beast Modes that previously needed this
# sidecar (Margin Pct, Margin Pct 2, Avg Order Value, Return Rate) now convert
# to the hand-authored formula exactly (two of the four differ only by a
# semantically-inert wrapping paren — `(a / b)` vs `a / b`, the same formula in
# Sigma) and their override entries have been removed. See
# refs/live-validation-2026-07-30.md, "⛔ The formula layer is NOT 'nearly
# free'" — now annotated RESOLVED (all three bugs) with the corrected
# re-measurement.
#
# The sidecar mechanism STAYS: it is still the right escape hatch for whatever
# the shared converter cannot yet do next — e.g. the still-open gaps this
# script itself flags via `preWarnings` (CEILING/FLOOR-as-aggregate, unmapped
# functions, window/LOD Beast Modes) or a shape the corpus hasn't hit yet. It
# is simply no longer load-bearing for the CASE WHEN / COUNT(DISTINCT) /
# double-bracketing defect class.
#
# discovery/formula-overrides.json is an OPERATOR-authored sidecar (same
# convention as discovery/kpi-overrides.json / dataset-map.json — this script
# only ever READS it, so re-running normalize or --lint never clobbers it).
# Keyed by the Beast Mode's stable `id` (`calculation_<uuid>`, survives
# re-runs) or its human-friendly `name` (accepted alternate key, since ids are
# opaque). Worked example — Beast Mode's `CEILING()` is an AGGREGATE (rounded
# MAX), not math rounding, which the generic SQL converter has no way to know
# (see the CEILING/FLOOR warning below); this is the kind of shape the sidecar
# still earns its keep on:
#
#   {
#     "calculation_4cd7e7c8-...": {
#       "sigmaFormula": "Round(Max([Net Revenue]), 0)",
#       "note": "hand-authored: CEILING() is a Beast Mode AGGREGATE (rounded MAX), not math rounding — the generic converter cannot know this"
#     },
#     "Avg Order Value": {
#       "sigmaFormula": "Sum([Net Revenue]) / CountDistinct([Order Id])"
#     }
#   }
#
# `Round`, `Max`, `Sum`, `CountDistinct` verified against
# plugins/sigma-authoring/skills/sigma-workbooks/reference/specification/formulas.md.
#
# Rules (enforced in resolve_entry / unmatched_override_keys below):
#   - An override only SUPPLIES a MISSING sigmaFormula — it never silently
#     replaces one convert_sql_to_sigma_formula already filled in.
#   - Every use is still POST-linted by lint_formula (raw IN(, And()/Or()/
#     Not() as calls, unbalanced brackets) — a hand-authored typo is a hard
#     lintError in formulas.json, never a silent pass.
#   - Every use emits a loud stderr warning naming the Beast Mode and stating
#     that the AUTOMATED conversion failed — so the upstream bug stays
#     visible and an override can never look machine-translated. The emitted
#     entry also carries `"_source": "formula-override"` (+ `note` if given).
#   - A formula-overrides.json key matching no pending entry's id/name warns
#     (typo'd key must not silently no-op).

require 'json'
require 'optparse'

OUT = ENV['DOMO_DISCOVERY_DIR'] || File.expand_path('../discovery', __dir__)

# Removed from Beast Mode / unsupported in Sigma — warn if seen.
UNSUPPORTED = %w[SQRT CONVERT_TZ MICROSECOND WEEKDAY].freeze

# Convert a raw Beast Mode string toward what convert_sql_to_sigma_formula expects,
# applying only the Domo-specific deltas. Returns [normalizedSql, warnings].
def normalize_bm(sql, klass = nil)
  warnings = []
  s = sql.to_s.dup

  # 1. Backtick / bracket MySQL identifier quoting → Sigma [Column Name].
  s = s.gsub(/`([^`]+)`/) { "[#{$1}]" }

  # 2. WEEKDAY → DAYOFWEEK (Beast Mode does this itself; replicate for parity).
  #
  # ⚠️ MEASURED 2026-07-30 (bead, not fixed here — see progress ledger for
  # 2026-07-30-track-a-sql-formula-converter, "LIKELY REAL PRODUCTION BUG"):
  # this rewrite makes the formula WORSE, not better. `WEEKDAY(...)` passed to
  # the shared converter comes back clean (`Weekday(...)` — Sigma has it), but
  # this step rewrites it to `DAYOFWEEK(...)` FIRST, and `Dayofweek(...)` is
  # NOT a real Sigma function — the converter now warns on it
  # (lookUnknownFunctions) where the untouched WEEKDAY form would not have
  # warned at all. Do not "fix" this by just deleting the rewrite without
  # checking Sigma's WEEKDAY offset (1=Sunday) actually matches Beast Mode's —
  # that offset question is exactly why this was added "for parity" in the
  # first place, and is unverified either way. Tracked as its own bead; needs
  # its own investigation, not a silent revert.
  if s =~ /\bWEEKDAY\s*\(/i
    s = s.gsub(/\bWEEKDAY\s*\(/i, 'DAYOFWEEK(')
    warnings << 'WEEKDAY → DAYOFWEEK (1=Sunday base; verify offset).'
  end

  # 3. Unsupported functions.
  UNSUPPORTED.each do |fn|
    next if fn == 'WEEKDAY' # handled above
    warnings << "Unsupported function #{fn}() present — legacy formula; review (SQRT → Power([x],0.5))." if s =~ /\b#{fn}\s*\(/i
  end

  # 4. CEILING/FLOOR are AGGREGATES in Beast Mode (rounded MAX/MIN), NOT math
  #    rounding — the generic SQL converter gets this WRONG. Flag for override.
  if s =~ /\bCEILING\s*\(/i
    warnings << 'CEILING() is an AGGREGATE in Beast Mode (rounded MAX) — override to Round(Max([...])).'
  end
  if s =~ /\bFLOOR\s*\(/i
    warnings << 'FLOOR() is an AGGREGATE in Beast Mode (rounded MIN) — override to Round(Min([...])).'
  end

  # 5. Class-driven flags.
  case klass
  when 'window'
    warnings << 'WINDOW/analytic Beast Mode → Sigma Rank/SumOver/CountOver; these SILENTLY error in workbook-master/DM calc cols (feedback_sigma_window_functions). Place carefully + verify.'
  when 'lod'
    warnings << 'FIXED/LOD Beast Mode → Sigma level-of-detail; do NOT flatten to a plain aggregate. Needs review.'
  end

  [s.strip, warnings]
end

NEEDS_REVIEW = %w[window lod].freeze

# Lint a translated Sigma formula for the traps that ship silently-broken output.
# Returns [errors, warnings].
def lint_formula(sigma, klass = nil)
  errors = []
  warnings = []
  f = sigma.to_s

  # IN(...) survived translation → Sigma has no IsIn; it silently blanks the column.
  if f =~ /\bIN\s*\(/i && f !~ /\bContains\s*\(/i
    errors << 'Contains a raw IN(...) — Sigma has no IsIn; expand to an OR-chain ([c]=a or [c]=b) or it silently blanks the column (feedback_sigma_formula_isin).'
  end

  # And()/Or()/Not() as FUNCTION CALLS silently produce null rows — must be infix.
  if f =~ /\b(And|Or)\s*\(/i
    warnings << 'Uses And()/Or() as a function call — Sigma wants infix `and`/`or`; the function form can null rows (formulas.md).'
  end
  warnings << 'Uses Not() as a function call — verify; infix negation is safer.' if f =~ /\bNot\s*\(/i

  # Window functions present — remind of the workbook-master limitation.
  if f =~ /\b(Rank|SumOver|CountOver|CumulativeSum|CumulativeCount|MovingAvg)\s*\(/i
    warnings << 'Window function present — silently errors in workbook-master/DM calc cols (feedback_sigma_window_functions).'
  end

  # Balanced brackets/parens sanity (a common cause of "IF chokes").
  errors << 'Unbalanced parentheses.' if f.count('(') != f.count(')')
  errors << 'Unbalanced [ ] brackets.' if f.count('[') != f.count(']')

  [errors, warnings]
end

# Look up an operator-authored override for one pending entry. Keyed by the
# Beast Mode's stable `id` (calculation_<uuid>) first, falling back to the
# human-friendly `name` — ids are opaque, so name is an accepted alternate
# key. Returns the override Hash or nil.
def find_override(entry, overrides)
  ov = overrides[entry['id']] || overrides[entry['name']]
  ov.is_a?(Hash) ? ov : nil
end

# Resolve one discovery/formulas.pending.json entry against the operator
# sidecar, then apply the same POST-lint every entry gets. Returns
# [resolved_entry_or_nil, warnings]. resolved_entry is nil when there is still
# no sigmaFormula (no override applied) — the caller drops it, exactly
# today's honest-drop behaviour (refs/live-validation-2026-07-30.md).
#
# An override only SUPPLIES a sigmaFormula that is missing; it never silently
# clobbers one convert_sql_to_sigma_formula already filled in (if it matches
# an already-resolved entry, that's a no-op override — warned, not applied).
def resolve_entry(entry, overrides)
  warnings = []
  sigma = entry['sigmaFormula']
  already_resolved = !(sigma.nil? || sigma.to_s.strip.empty?)
  override = find_override(entry, overrides)
  used_override = false

  if override && !override['sigmaFormula'].to_s.strip.empty?
    if already_resolved
      warnings << "formula-overrides.json has an entry for " \
        "#{entry['name'] || entry['id']} but it already has a sigmaFormula — " \
        "override NOT applied (clear the pending entry's sigmaFormula to force it)."
    else
      sigma = override['sigmaFormula']
      used_override = true
    end
  end

  return [nil, warnings] if sigma.nil? || sigma.to_s.strip.empty?

  errs, lint_warns = lint_formula(sigma, entry['class'])
  resolved = entry.merge('sigmaFormula' => sigma, 'lintErrors' => errs, 'lintWarnings' => lint_warns)
  if used_override
    resolved['_source'] = 'formula-override'
    resolved['note'] = override['note'] if override['note']
    warnings << "#{entry['name'] || entry['id']}: sigmaFormula supplied by " \
      "discovery/formula-overrides.json (hand-authored) — automated conversion " \
      "(convert_sql_to_sigma_formula) did not produce a usable formula for this " \
      "Beast Mode; verify by hand. CASE WHEN / COUNT(DISTINCT) / double-bracketed " \
      "ALL-CAPS refs are fixed (sigma-data-model-mcp PR #115, #116) so this is NOT " \
      "that historical 74%-fail case — check refs/live-validation-2026-07-30.md " \
      "and this script's still-open gaps (WEEKDAY→DAYOFWEEK, CEILING/FLOOR " \
      "aggregates, untranslatable infix LIKE) for what actually still needs a " \
      "hand-authored formula."
  end
  [resolved, warnings]
end

# Override keys (id or name) that matched NO pending entry at all. A typo'd
# id/name in formula-overrides.json must not silently do nothing.
def unmatched_override_keys(pending, overrides)
  known = pending.flat_map { |e| [e['id'], e['name']] }.compact
  overrides.keys.reject { |k| known.include?(k) }
end

run_main = ($PROGRAM_NAME == __FILE__)
if run_main
opts = {}
OptionParser.new do |o|
  o.on('--lint') { opts[:lint] = true }
  o.on('--in PATH')  { |v| opts[:in] = v }
  o.on('--out PATH') { |v| opts[:out] = v }
  o.on('--overrides PATH') { |v| opts[:overrides] = v }
end.parse!(ARGV)

if opts[:lint]
  # ---- Validate a filled pending file → formulas.json --------------------
  path = opts[:in] || File.join(OUT, 'formulas.pending.json')
  pending = JSON.parse(File.read(path))
  # Operator sidecar (see header) — read-only, never written by this script.
  overrides_path = opts[:overrides] || File.join(OUT, 'formula-overrides.json')
  overrides = (JSON.parse(File.read(overrides_path)) rescue {}) || {}

  final = []
  unresolved = []
  pending.each do |e|
    resolved, warnings = resolve_entry(e, overrides)
    warnings.each { |w| warn "  ⚠ #{w}" }
    if resolved
      final << resolved
    else
      unresolved << (e['name'] || e['id'])
    end
  end

  unmatched_override_keys(pending, overrides).each do |k|
    warn "  ⚠ discovery/formula-overrides.json key '#{k}' matches no Beast Mode " \
      "id or name in #{path} — typo'd id/name? (ignored)"
  end

  out = opts[:out] || File.join(OUT, 'formulas.json')
  File.write(out, JSON.pretty_generate(final))
  warn "  wrote #{out} (#{final.size} formulas)"
  bad = final.select { |e| !e['lintErrors'].empty? }
  unless bad.empty?
    warn "\n  ⚠ #{bad.size} formula(s) have lint ERRORS — fix before building:"
    bad.each { |e| warn "    - #{e['name'] || e['id']}: #{e['lintErrors'].join('; ')}" }
  end
  unless unresolved.empty?
    warn "\n  ⚠ #{unresolved.size} Beast Mode(s) still lack a sigmaFormula: #{unresolved.join(', ')}"
  end
  exit(bad.empty? ? 0 : 1)
else
  # ---- Normalize discovery/beast-modes.json → formulas.pending.json ------
  path = opts[:in] || File.join(OUT, 'beast-modes.json')
  beast = JSON.parse(File.read(path))
  pending = beast.map do |b|
    sql = b['sql'] || b['formula'] || b['expression']
    norm, warns = normalize_bm(sql, b['class'])
    {
      'id'           => b['id'],
      'name'         => b['name'],
      'scope'        => b['scope'],
      'class'        => b['class'],
      'originalSql'  => sql,
      'normalizedSql'=> norm,
      'preWarnings'  => warns,
      'needsReview'  => NEEDS_REVIEW.include?(b['class']) || warns.any? { |w| w.include?('AGGREGATE') },
      'sigmaFormula' => nil,   # ← filled by convert_sql_to_sigma_formula in Phase 2
    }
  end
  out = opts[:out] || File.join(OUT, 'formulas.pending.json')
  require 'fileutils'; FileUtils.mkdir_p(OUT)
  File.write(out, JSON.pretty_generate(pending))
  warn "  wrote #{out} (#{pending.size} Beast Modes to translate)"
  warn "\n  Next (Phase 2): for each entry call convert_sql_to_sigma_formula(sql: normalizedSql),"
  warn "  write the result into `sigmaFormula`, apply preWarning overrides (CEILING/FLOOR/window/LOD),"
  warn "  then: ruby scripts/convert-beast-modes.rb --lint"
end
end
