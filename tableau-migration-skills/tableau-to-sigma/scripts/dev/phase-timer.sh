#!/usr/bin/env bash
# DEV / PROFILING ONLY. Do NOT source during real customer conversions —
# the start/end log lines and phase-timings.json artifact are internal
# instrumentation noise that's only useful when iterating on the skill
# itself. Use only when the user explicitly asks for timing data
# ("time it", "where did the minutes go", "profile this").
#
# Lightweight phase-timing helper. Source from a conversion driver and
# call phase_start / phase_end around each major phase. Call phase_report
# at the end to flush phase-timings.json.
#
# Usage:
#   source scripts/dev/phase-timer.sh
#   PHASE_TIMINGS_OUT=/tmp/foo/phase-timings.json
#   phase_start "Phase 1"
#   ruby scripts/tableau-discover.rb ...
#   phase_end
#   ...
#   phase_report
#
# Storage: tab-separated entries in $PHASE_TIMINGS_TMP, one per completed
# phase: "<name>\t<start_ts>\t<end_ts>\t<duration_s>".
# This avoids the bash array → python3 -c interpolation problems we hit
# when phase names contain shell-meaningful characters.

# State file. Two modes:
# - Caller exports PHASE_TIMINGS_TMP before sourcing → append-only (survives
#   across separate Bash tool-call blocks in an agent session). This is the
#   correct usage when phases span multiple shell invocations.
# - Caller doesn't export → fresh mktemp + truncate (single-shell usage).
# beads-sigma-hf4: previous version always truncated on source, losing
# accumulated rows across blocks. Now we only truncate when we created
# the file in this source.
if [ -z "${PHASE_TIMINGS_TMP:-}" ]; then
  PHASE_TIMINGS_TMP=$(mktemp -t phase-timings.XXXXXX)
  : > "$PHASE_TIMINGS_TMP"
  export PHASE_TIMINGS_TMP
fi
PHASE_CURRENT_NAME=""
PHASE_CURRENT_START=""

_now() { python3 -c 'import time; print(time.time())'; }

phase_start() {
  if [[ -n "$PHASE_CURRENT_NAME" ]]; then
    echo "phase-timer: WARN starting '$1' without ending '$PHASE_CURRENT_NAME'" >&2
    phase_end
  fi
  PHASE_CURRENT_NAME="$1"
  PHASE_CURRENT_START=$(_now)
  echo "▶  $PHASE_CURRENT_NAME (start)"
}

phase_end() {
  if [[ -z "$PHASE_CURRENT_NAME" ]]; then return; fi
  local end_ts duration
  end_ts=$(_now)
  duration=$(python3 -c "print(f'{${end_ts} - ${PHASE_CURRENT_START}:.2f}')")
  printf '%s\t%s\t%s\t%s\n' "$PHASE_CURRENT_NAME" "$PHASE_CURRENT_START" "$end_ts" "$duration" >> "$PHASE_TIMINGS_TMP"
  echo "■  $PHASE_CURRENT_NAME — ${duration}s"
  PHASE_CURRENT_NAME=""
  PHASE_CURRENT_START=""
}

phase_report() {
  phase_end
  local out="${PHASE_TIMINGS_OUT:-/tmp/phase-timings.json}"
  python3 - <<PY
import json
items = []
with open("$PHASE_TIMINGS_TMP") as fh:
    for line in fh:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 4: continue
        name, s, e, d = parts[0], float(parts[1]), float(parts[2]), float(parts[3])
        items.append({"phase": name, "start": s, "end": e, "duration_s": d})
total = sum(i["duration_s"] for i in items)
summary = [
    {"phase": i["phase"], "seconds": round(i["duration_s"], 1),
     "pct": round(100 * i["duration_s"] / total, 1) if total else 0}
    for i in sorted(items, key=lambda x: -x["duration_s"])
]
out = {"total_seconds": round(total, 2), "phases": items, "summary": summary}
with open("$out", "w") as fh: fh.write(json.dumps(out, indent=2))
print()
print("=== phase-timings ===")
print(f"Total: {out['total_seconds']}s")
for s in summary:
    print(f"  {s['seconds']:>6.1f}s  {s['pct']:>5.1f}%  {s['phase']}")
print(f"wrote $out")
PY
}
