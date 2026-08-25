# frozen_string_literal: true
#
# offramp.rb — record every point where a run LEAVES the golden path.
#
# The hard part of debugging inconsistent agent runs is not "did it fail" but
# "WHERE did it leave the rails" — which gate was waived, which stop was hit,
# which degraded mode was taken. Those off-ramps were previously scattered across
# prose warnings and a couple of ad-hoc files. This appends a structured line to
# <WORK>/offramps.jsonl at each one, so a single file answers "where did this run
# defect?" post-hoc (and verify-complete.rb surfaces the trail).
#
# Kinds (stable strings — group on these in telemetry):
#   cred-gate-waived     SIGMA_SKIP_CRED_GATE used — creds unresolved, run may die at first API call
#   doctor-gate-waived   --skip-doctor-gate / SIGMA_SKIP_DOCTOR_GATE used
#   pass1-stop           PASS 1 ended at exit 12 (parity + gates NOT run yet)
#   converter-stop       converter unavailable / refused — routed to a fallback
#   workbook-handoff     workbook build raised (exit 4) — untranslatable fields handed off
#   degraded-fastpath    --yes fast path proceeded with missing discovery artifacts
#   gate-waived          an assert-phase6-ran gate waived (mirrored from waivers.json)
#   stale-skill-waived   SIGMA_ALLOW_STALE used — run proceeded on a stale checkout
#   loop-stop            the loop breaker tripped (verbatim signature repeat, same
#                        failure MODE with no measured progress, or the attempt
#                        cap) — hard STOP
#
# Never fatal: bookkeeping must not break a run.

require 'json'
require 'digest' # failure_signature hashes the normalized error line

module Offramp
  module_function

  def log(work, kind:, reason: nil, detail: nil)
    return unless work && Dir.exist?(work.to_s)
    rec = { 'kind' => kind, 'reason' => reason, 'detail' => detail,
            'at' => Time.now.utc.strftime('%Y-%m-%dT%H:%M:%SZ') }.reject { |_, v| v.nil? }
    File.open(File.join(work, 'offramps.jsonl'), 'a') { |f| f.puts(JSON.generate(rec)) }
    warn "   ↪ off-ramp recorded: #{kind}#{reason ? " (#{reason})" : ''} → #{File.join(work, 'offramps.jsonl')}"
  rescue StandardError
    # bookkeeping only — never fail the run
  end

  # Read the trail back (array of records, oldest first). Empty on any error.
  def trail(work)
    path = File.join(work.to_s, 'offramps.jsonl')
    return [] unless File.exist?(path)
    # map + compact (not filter_map — that is Ruby 2.7+; the skills target 2.6).
    File.readlines(path).map { |l| JSON.parse(l) rescue nil }.compact
  rescue StandardError
    []
  end

  # ── Same-failure loop breaker ──────────────────────────────────────────────
  # Append SIGNATURE (caller-supplied; build it with failure_signature below)
  # to <WORK>/loop-log.jsonl and return a verdict for THIS attempt, counted
  # SINCE THE LAST GREEN RESET. Three stop rules, each covering the others'
  # blind spot (PR-507 finding 1A redesign):
  #
  #   :stop  S1 verbatim repeat — this exact signature already occurred.
  #          Identical failures and pure reorders (error_digest sorts the
  #          detail tail) stop at attempt 2, as before.
  #   :stop  S2 no progress — `mode:` (the failure-MODE key: same failure KIND
  #          with counts masked; build with failure_mode) already occurred and
  #          `measure:` (the surviving failure count; region_measure) is NOT a
  #          strict improvement on the BEST (lowest) measure yet seen for that
  #          mode. A converging repair loop (5→3→2→1 unresolved refs) improves
  #          every attempt and never stops; growing, oscillating, churning, and
  #          unmeasurable same-mode failures stop at attempt 2. Comparing to
  #          the best-yet (not the previous) measure keeps an oscillator from
  #          "improving" on alternate attempts forever.
  #   :cap   S3 attempt cap — `scope:` (a per-(script,context) bucket) has now
  #          burned ATTEMPT_CAP attempts without a green reset, regardless of
  #          signatures. No signature scheme can bound a loop that mints fresh
  #          failure text every attempt; the cap is the unconditional
  #          termination guarantee (it also bounds glacial-but-real 550→549→…
  #          convergence — deliberate: the handoff prescribes incremental
  #          repair, and ATTEMPT_CAP unattended attempts is already generous).
  #
  # The record a stop lands on is stamped {'stop': true, 'stop_rule': ...}:
  # S2/S3 can trip WITHOUT any signature reaching a 2-count, so
  # verify-complete.rb refuses completion (exit 5) over a stop-stamped trail
  # as well as over any 2-count signature — same post-reset window.
  #
  # Callers that pass only `signature:` get S1 + S3 (cap scope defaults to the
  # signature's script:context prefix) — byte-compatible with the old
  # stop-at-2 contract. Pre-upgrade records (no mode/scope keys) never pair
  # with new ones and are NOT counted toward the cap, so an upgrade restarts
  # counting instead of springing an instant stop on a long-lived workdir
  # (same accepted trade as the finalize cleanup-key addition).
  #
  # Counts are NOT cumulative over the workdir's whole lifetime: a GREEN
  # finalize appends a {'reset': true} record (loop_reset below) and counting
  # restarts after it — a green run has just DISPROVEN that the earlier
  # failures were a grind loop, so a stale 1-count from days ago must not
  # convert the next unrelated same-signature failure into a false hard-STOP.
  # The reset is append-only (never truncates the log), so the full history
  # stays auditable and the planned E5.19 reset defense can tell this
  # sanctioned post-green record from an operator clearing the file to dodge
  # the breaker (which remains operator-only). Never fatal.
  ATTEMPT_CAP = (ENV['SIGMA_LOOP_ATTEMPT_CAP'] || '6').to_i

  def loop_check(work, signature:, mode: nil, measure: nil, scope: nil, cap: ATTEMPT_CAP)
    return :first unless work && Dir.exist?(work.to_s)
    scope = scope.to_s.empty? ? signature.to_s.split(':').first(2).join(':') : scope.to_s
    prior = loop_active_trail(work)
    rule = nil
    if prior.any? { |r| r['signature'] == signature.to_s }
      rule = 'repeat'
    elsif mode
      same_mode = prior.select { |r| r['mode'] == mode.to_s }
      if same_mode.any?
        best = same_mode.map { |r| r['measure'] }.compact.min
        rule = 'no-progress' unless measure && best && measure.to_i < best.to_i
      end
    end
    rule ||= 'attempt-cap' if cap.to_i.positive? && prior.count { |r| r['scope'] == scope } + 1 >= cap.to_i
    rec = { 'signature' => signature.to_s,
            'at' => Time.now.utc.strftime('%Y-%m-%dT%H:%M:%SZ') }
    rec['mode']    = mode.to_s if mode
    rec['measure'] = measure.to_i if measure
    rec['scope']   = scope
    if rule
      rec['stop']      = true
      rec['stop_rule'] = rule
    end
    File.open(File.join(work, 'loop-log.jsonl'), 'a') { |f| f.puts(JSON.generate(rec)) }
    return :cap if rule == 'attempt-cap'
    rule ? :stop : :first
  rescue StandardError
    :first # bookkeeping must never break a run
  end

  # Attempts recorded for a cap scope since the last green reset (banner math).
  def scope_attempts(work, scope)
    loop_active_trail(work).count { |r| r['scope'] == scope.to_s }
  end

  # Stop-stamped records since the last green reset. verify-complete.rb ORs
  # this into its refusal: an S2/S3 stop leaves every signature at a 1-count,
  # so the 2-count rule alone would let a hard-STOPPED run claim DONE.
  def loop_stops(work)
    loop_active_trail(work).select { |r| r['stop'] }
  end

  # Re-arm the breaker after a GREEN gate pass: append a structured reset
  # record. loop_check / loop_counts only count entries AFTER the last reset;
  # loop_trail still returns everything (auditability).
  def loop_reset(work, run_id: nil)
    return unless work && Dir.exist?(work.to_s)
    return if loop_active_trail(work).empty? # nothing to re-arm — keep the log stable
    rec = { 'reset' => true,
            'at' => Time.now.utc.strftime('%Y-%m-%dT%H:%M:%SZ') }
    rec['run_id'] = run_id if run_id
    File.open(File.join(work, 'loop-log.jsonl'), 'a') { |f| f.puts(JSON.generate(rec)) }
  rescue StandardError
    # bookkeeping only — never fail the run
  end

  # Normalize a raw error line to its STABLE shape: identifiers become
  # placeholders, BARE INTEGERS SURVIVE. Rationale: the exit-4 signature used
  # to be SHA1(raw first error line), so a repair loop whose each patch merely
  # shuffled WHICH element fails first (new id, new quoted name, new path)
  # minted a fresh "distinct" signature every attempt and the breaker never
  # tripped. Two attempts failing the same WAY must hash identically. The old
  # final rule (\S*\d\S* → <id>) over-rotated: it also ate every COUNT, so
  # "5 of 340 unresolved" and "1 of 340 unresolved" collapsed into one
  # signature and a CONVERGING repair loop was hard-stopped as a grind (PR-507
  # finding 1A). Inverted default: identifiers are consumed by the explicit
  # rules below — in this codebase every real identifier is either DELIMITED
  # (path, quoted, bracketed, file:line) or MIXED alphanumeric (el-9, uuid,
  # k9Xy2Qw81) — and a bare integer (≤ 6 digits; longer is an epoch/surrogate
  # key) survives as the failure's progress measure (region_measure below).
  #
  # scrub first: the line arrives from captured child output tagged with the
  # default external encoding but UNVALIDATED (cp1252/Latin-1 bytes from
  # accented field names), and gsub raises on invalid bytes. A single-quote
  # span must OPEN at a token start, or an apostrophe contraction (can't)
  # pairs with a later quoted name and leaks it past the placeholder.
  # Rules apply IN ORDER; each consumes its span before a broader rule sees it.
  NORM_RULES = [
    [/\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z?/,      '<time>'], # ISO-8601
    [/\b\d\d:\d\d:\d\d\b/,                              '<time>'], # wall clock
    # bracketed refs BEFORE paths: [Master/Net Revenue] contains '/', so the
    # path rule would eat '/Net' and leave a half-token normalizing differently
    # from [Master/…]. The lookahead exempts house markers ([FAIL],[PASS],[OK],
    # [WARN]) — that shape is what tells two CHILDREN apart, so it must not
    # collapse to <ref>.
    [/\[(?![A-Z]{1,10}\])[^\[\]]*\]/,                   '<ref>'],
    [%r{(?:[A-Za-z]:)?[/\\][^\s"']+},                   '<path>'], # unix + windows paths
    [/\b[\w.+-]+\.[A-Za-z]{1,6}:\d+(?::\d+)?/,          '<src>'],  # foo.rb:41[:7] backtrace churn
    [/\b\d+(?:\.\d+)?(?:ms|us|ns|sec|secs|mins|hrs)\b/, '<time>'], # durations
    [/\b\d+\.\d+s\b/,                                   '<time>'],
    [/"[^"]*"/,                                         '<name>'],
    [/(^|[\s(:=,\[])'[^']*'/,                           '\1<name>'],
    [/\b\h{8}-\h{4}-\h{4}-\h{4}-\h{12}\b/,              '<id>'],   # uuid
    [/\b(?=[\w-]*\d)(?=[\w-]*[A-Za-z])[\w-]{2,}\b/,     '<id>'],   # MIXED alnum (el-9, k9Xy2Qw81)
    [/\b\d{7,}\b/,                                      '<id>']    # epoch-s/-ms, surrogate keys
    # SURVIVING class: a bare integer of ≤ 6 digits. No rule matches it.
  ].freeze

  def normalize_error_line(line)
    s = line.to_s.scrub('?')
    NORM_RULES.each { |re, rep| s = s.gsub(re, rep) }
    s.squeeze(' ').strip
  end

  # The multi-line ERROR REGION of a captured child output: from the first
  # error-shaped line (ERROR_LINE_RE — same selector first_error_line uses)
  # through the blank line that ends the measured detail block. The house
  # emission shape is `[FAIL] <summary with counts>` + one `✗ <detail>` line
  # per failure + `warn ''` + constant advice prose (assert-wb-refs-resolve.rb
  # prints exactly this), so the blank line is a natural terminator: everything
  # before it varies with the failure, everything after it is boilerplate that
  # would only dilute the digest. No error-shaped line at all (bare interpreter
  # backtrace) → the first MAX_LINES non-blank lines, so un-shaped failures
  # still discriminate (mirrors first_error_line's whole-output fallback).
  #
  # A block LONGER than the cap keeps its truth: the block is measured in FULL
  # before truncating, and the region's last slot becomes an overflow trailer
  # naming how many detail lines the cap hid. Without it, a converging >cap
  # list whose head carries no count false-stopped at attempt 2 — attempts
  # differing only past the cap minted IDENTICAL signatures (S1 'repeat') and
  # the detail-line measure plateaued at the cap (S2 'no-progress') — the
  # finding-1A pathology resurfacing past ERROR_REGION_MAX_LINES
  # (validate-spec's trailing `--- N errors` tally is the canonical victim: it
  # is the block's LAST line, i.e. beyond the window exactly when N > 15).
  # The trailer's wording is all-alpha + one bare integer so normalization
  # preserves it; error_digest pins it into the hashed window and
  # region_measure adds it back into the fallback count.
  ERROR_REGION_MAX_LINES      = 16
  ERROR_REGION_MAX_LINE_CHARS = 300
  ERROR_REGION_MAX_CHARS      = 2000
  ERROR_REGION_OVERFLOW_RE    = /\A\(\+(\d+) more detail lines beyond the region cap\)/

  def error_region(output, max_lines: ERROR_REGION_MAX_LINES)
    raw   = output.to_s.scrub('?').lines.map(&:strip)
    start = raw.index { |l| l =~ ERROR_LINE_RE }
    block = if start.nil? # bounded fallback: no error-shaped line anywhere
              raw.reject(&:empty?)
            else
              [raw[start]] + raw[(start + 1)..-1].to_a.take_while { |l| !l.empty? }
            end
    return block if block.size <= max_lines
    kept = block.first(max_lines - 1)
    kept << "(+#{block.size - kept.size} more detail lines beyond the region cap)"
  end

  # Digest input for a region: normalized head + SORTED normalized tail.
  # Sorted — a repair that merely reorders which failure is reported first is
  # neither a new failure nor progress; sorting makes the signature
  # order-independent. NOT dedup'd — multiplicity IS the count signal for
  # children that print one identical-shaped line per failure (validate-spec's
  # `ERROR: …` list); uniq'ing would re-collide 3-errors with 1-error.
  # The overflow trailer is pinned right AFTER the head instead of sorted with
  # the details: it carries the only evidence separating two long lists that
  # agree on every shown line, so it must land inside the MAX_CHARS window no
  # matter how the (up to 300-char) detail lines would sort around it.
  def error_digest(region)
    lines = Array(region).map { |l| normalize_error_line(l)[0, ERROR_REGION_MAX_LINE_CHARS] }
                         .reject { |l| l.nil? || l.empty? }
    return '' if lines.empty?
    tail = lines[1..-1].to_a
    trailer = tail.pop if tail.last.to_s =~ ERROR_REGION_OVERFLOW_RE
    ([lines.first, trailer].compact + tail.sort).join("\n")[0, ERROR_REGION_MAX_CHARS]
  end

  # The failure-MODE key: the structural identity (script + exit codes + error
  # class, same parts as failure_signature) + the region's HEAD line with its
  # surviving integers MASKED. Two attempts failing the same WAY — "N of M
  # refs unresolved" for any N/M — share one mode; loop_check's S2 rule then
  # decides grind-vs-converge from the UNmasked measure. The hash is prefixed
  # 'm' so a mode string can never equal a signature string in the loop-log.
  def failure_mode(script:, context: nil, exit_code: nil, error_class: nil, error_region: nil)
    parts = signature_parts(script: script, context: context, exit_code: exit_code,
                            error_class: error_class)
    masked = normalize_error_line(Array(error_region).first).gsub(/\b\d+\b/, '<n>')
    parts << "m#{Digest::SHA1.hexdigest(masked)[0, 12]}" unless masked.empty?
    parts.join(':')
  rescue StandardError
    # never-fatal contract (header): degrade to a byte-level digest of the head
    ((parts || [script.to_s]) << "m#{Digest::SHA1.hexdigest(Array(error_region).first.to_s.b)[0, 12]}").join(':')
  end

  # The progress MEASURE: the first surviving integer of the normalized head
  # line (the leading count in the house "[FAIL] … N of M …" summary shape).
  # Within one mode the masked head template is identical, so the measure is
  # read from the same position every attempt. A head with no integer falls
  # back to the region's detail-line count (a shrinking ERROR:-list is also
  # convergence) — the TRUE block count: an overflow trailer's hidden lines are
  # added back, so a >cap list measures 20→17→14, not a cap plateau that reads
  # convergence as 'no-progress'. nil when nothing is measurable — S2 then
  # stops on mode recurrence, the conservative direction (no measurable
  # progress ≠ progress).
  def region_measure(region)
    lines = Array(region)
    return nil if lines.empty?
    m = normalize_error_line(lines.first)[/\b\d{1,6}\b/]
    return m.to_i if m
    dropped = lines.last.to_s[ERROR_REGION_OVERFLOW_RE, 1]
    n = lines.size - 1 + (dropped ? dropped.to_i - 1 : 0) # the trailer holds a slot
    n.positive? ? n : nil
  end

  # The structural identity parts shared by failure_signature and failure_mode:
  # script + context + exit code(s) + error class. exit_code may be a Hash for
  # multi-gate failures ({ phase6: 2, gate: 7 } → "phase6=2:gate=7").
  def signature_parts(script:, context: nil, exit_code: nil, error_class: nil)
    parts = [script.to_s]
    parts << context.to_s unless context.to_s.empty?
    case exit_code
    when Hash then exit_code.each { |k, v| parts << "#{k}=#{v}" }
    when nil  then nil
    else           parts << "exit=#{exit_code}"
    end
    # bare class name — WorkbookBuildError, not Object::WorkbookBuildError
    parts << error_class.to_s.split('::').last unless error_class.to_s.empty?
    parts
  end

  # Build a loop-log signature from the STABLE identity of a failure: the
  # structural parts + SHA1 of the NORMALIZED error text. With `error_region:`
  # (preferred — pass error_region's output) the hash covers the whole
  # blank-line-terminated block via error_digest, so the signature carries the
  # failure's surviving counts and its (sorted) detail lines: converging
  # attempts mint DISTINCT signatures while identical/reordered attempts still
  # collide into one. `error_line:` alone keeps the old single-line behavior
  # for callers with no multi-line capture. Callers must never hash error text
  # themselves (that is exactly the signature churn normalize_error_line
  # exists to prevent).
  def failure_signature(script:, context: nil, exit_code: nil, error_class: nil,
                        error_line: nil, error_region: nil)
    parts = signature_parts(script: script, context: context, exit_code: exit_code,
                            error_class: error_class)
    region = Array(error_region)
    norm = region.empty? ? normalize_error_line(error_line) : error_digest(region)
    parts << Digest::SHA1.hexdigest(norm)[0, 12] unless norm.empty?
    parts.join(':')
  rescue StandardError
    # never-fatal contract (header): if normalization still chokes on a hostile
    # line, fall back to a stable byte-level digest so the breaker can count
    # recurrences instead of killing the rescue path that called us.
    ((parts || [script.to_s]) << Digest::SHA1.hexdigest("#{error_line}#{error_region}".b)[0, 12]).join(':')
  end

  # loop-log entries (oldest first), INCLUDING reset records. Empty on any error.
  def loop_trail(work)
    path = File.join(work.to_s, 'loop-log.jsonl')
    return [] unless File.exist?(path)
    File.readlines(path).map { |l| JSON.parse(l) rescue nil }.compact
  rescue StandardError
    []
  end

  # The entries that COUNT: everything after the last reset record (the whole
  # trail when no reset exists). Reset records themselves never appear here.
  def loop_active_trail(work)
    t = loop_trail(work)
    i = t.rindex { |r| r['reset'] }
    (i ? t[(i + 1)..-1] : t).reject { |r| r['reset'] }
  end

  # { signature => occurrence count } over the ACTIVE (post-reset) loop-log.
  def loop_counts(work)
    loop_active_trail(work).each_with_object(Hash.new(0)) { |r, h| h[r['signature']] += 1 }
  end

  # Pick the line worth SIGNATURING from captured child output: the first line
  # that looks like an ERROR (house shapes: "ERROR ...", "FATAL ...", "[FAIL]",
  # "✗", "error:"), NOT the first line of output. Children print NORMALIZE:/
  # WARN: report lines BEFORE their ERROR: lines (validate-spec.rb), so
  # first-line hashing would (a) collide two DIFFERENT root causes behind one
  # stable leading report line and (b) let a patch that merely removes a
  # leading warning mint a fresh signature for the SAME persisting error.
  # When NOTHING matches the error shape (e.g. a bare interpreter backtrace),
  # falls back to the WHOLE output collapsed to one line — a full-output hash
  # still separates different root causes, where hashing a stable first line
  # would recreate collision (a) for un-shaped failures. nil on empty output.
  ERROR_LINE_RE = /\A(?:ERROR\b|FATAL\b|\[FAIL\]|✗|error:|abort(?:ed)?\b)/i
  def first_error_line(output)
    lines = output.to_s.scrub('?').lines.map(&:strip).reject(&:empty?)
    lines.find { |l| l =~ ERROR_LINE_RE } || (lines.empty? ? nil : lines.join(' | '))
  end
end
