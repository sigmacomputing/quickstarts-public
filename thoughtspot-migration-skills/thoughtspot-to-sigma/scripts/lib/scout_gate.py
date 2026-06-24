"""Shared run-each-time gap-scout ledger (bead beads-sigma-5l5e) — Python side.

Mirrors scout_gate.rb's contract exactly: a per-conversion JSONL ledger at
<workdir>/scout-ledger.jsonl, one row per scouted gap:
    {"gap_id": ..., "feature": ..., "status": "validated"|"escalated", "at": ...}

Ruby orchestrators read it via scout_gate.rb#classify; Python scouts append to
it via record() below. The JSONL format is the language-neutral contract.
"""
import json
import os
import datetime

LEDGER = "scout-ledger.jsonl"


def record(workdir, gap_id, feature, status):
    """Append one scout result. Non-fatal on error (never crash a good scout)."""
    if not workdir or not os.path.isdir(workdir):
        return False
    row = {
        "gap_id": str(gap_id or feature),
        "feature": str(feature),
        "status": str(status),
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    try:
        with open(os.path.join(workdir, LEDGER), "a") as f:
            f.write(json.dumps(row) + "\n")
        return True
    except OSError as e:
        import sys
        print("scout-ledger write failed (non-fatal): %s" % e, file=sys.stderr)
        return False


def read_ledger(workdir):
    p = os.path.join(workdir or "", LEDGER)
    if not os.path.exists(p):
        return []
    out = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def classify(workdir, gap_ids):
    """Split unhandled gap-ids into unscouted / escalated / validated buckets.
    Mirrors scout_gate.rb#classify exactly (same JSONL ledger contract)."""
    by = {}
    for e in read_ledger(workdir):
        by.setdefault(str(e.get("gap_id")), []).append(e)
    unscouted = [g for g in gap_ids if str(g) not in by]
    rest = [g for g in gap_ids if str(g) in by]
    validated = [g for g in rest if any(x.get("status") == "validated" for x in by[str(g)])]
    escalated = [g for g in rest if g not in validated]
    return {"unscouted": unscouted, "escalated": escalated, "validated": validated}
