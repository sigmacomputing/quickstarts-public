#!/usr/bin/env python3
"""
batch-convert.py — fleet converter for a family of broker equity-research models
(the ~850-file case: same house template, "similar but not identical").

Per file: strip FactSet cruft (logged) -> fingerprint the template -> run canonical
inference (infer-canonical-formulas.py) -> map line items to the canonical
chart-of-accounts (coa.json) -> parity gate -> bucket into AUTO_PARITY / NEEDS_REVIEW
/ FAILED. Emits a triage manifest (JSON + CSV) with a rollup and the top unmapped
labels across the batch (which feed COA-alias growth). NO silent truncation.

Default = report-only (recommended calibration mode for the first tranche): inference
+ triage, nothing built. `--post --conn <id> --folder <id>` builds only gate-cleared
AUTO_PARITY files via build-research-model.py. Reviewed sources require source-bound,
complete `--review-dispositions`; `--post-review` alone grants no override. DMs are
READ-ONLY (inline VALUES), fully API, no UI step (see refs/research-recipes.md).

Usage:
  batch-convert.py <file-or-dir> [<more> ...] [--sheet "FY results"]
                   [--out manifest.json] [--review-dispositions <file-or-dir>]
                   [--post --conn <id> --folder <id>]
"""
import argparse
import sys, os, re, json, glob, hashlib, importlib.util
from collections import Counter

from lib.migration_gate import (
    MigrationGateError,
    dispositions_for_source,
    gate_source,
    plan_review_issues,
)

HERE = os.path.dirname(os.path.abspath(__file__))


def load_mod(fn, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


INF = load_mod("infer-canonical-formulas.py", "inf")
with open(os.path.join(HERE, "coa.json"), encoding="utf-8") as coa_file:
    COA = json.load(coa_file)


def norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).strip()


def alias_index(coa):
    idx = {}
    for acc in coa["accounts"]:
        for a in acc["aliases"]:
            idx[norm(a)] = acc["id"]
    return idx


ALIAS = alias_index(COA)
STABLE_NORM = {norm(s) for s in COA["template"]["sections_expected"]}


def in_stable(section):
    n = norm(section)
    return any(n == e or n in e or e in n for e in STABLE_NORM)


def strip_report(path):
    """Count (never silently drop) the FactSet cruft we ignore."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=False, read_only=True)
    named = len(wb.defined_names)
    fdscache = any(s.startswith("__") for s in wb.sheetnames)
    return {"named_ranges": named, "fdscache_sheet": fdscache, "sheets": list(wb.sheetnames)}


def is_detail(l):
    """Ratio / sub-item lines aren't canonical COA accounts (they're carried detail)."""
    n = norm(l["label"])
    return l["kind"] == "ratio" or n.startswith(("ow ", "% ")) or n in ("", ".") or "%" in l["label"][:3]


def fingerprint(plan, sheets, n_mapped):
    """Similarity (not equality) to the house template -> SAME / VARIANT / UNKNOWN."""
    T = COA["template"]; w = T["fingerprint_weights"]
    file_secs = {norm(l["section"]) for l in plan["lines"] if l["section"] != "(none)"}
    exp_secs = {norm(s) for s in T["sections_expected"]}
    matched = sum(1 for e in exp_secs if any(e in fs or fs in e for fs in file_secs))
    sec_score = min(matched / 3.0, 1.0)                 # recognizing >=3 known sections = full
    sheet_score = len({norm(s) for s in sheets} & {norm(s) for s in T["sheets_expected"]}) / \
                  max(len(T["sheets_expected"]), 1)
    accountish = [l for l in plan["lines"] if not is_detail(l)]      # headline lines only
    lab_score = n_mapped / max(len(accountish), 1)
    # formula-shape signal: how many derived canonicals look like a COA shape (rough: has refs)
    shp = sum(1 for l in plan["lines"] if l["kind"] in ("derived", "ratio") and l.get("canonical"))
    shp_score = min(shp / 20.0, 1.0)
    # anchor coverage — the most template-agnostic "this is a financial statement" signal
    acat = {"Revenue": "rev", "EBIT": "profit", "EBITDA": "profit", "Net income": "bottom",
            "Net attributable": "bottom", "EPS reported": "eps", "EPS adjusted": "eps"}
    anchor_score = len({acat[a] for a in plan["anchors"] if a in acat}) / 4.0
    score = (w["sections"] * sec_score + w["sheets"] * sheet_score +
             w["label_jaccard"] * lab_score + w["formula_shapes"] * shp_score +
             w.get("anchors", 0) * anchor_score)
    cls = "SAME" if score >= T["thresholds"]["same"] else \
          ("VARIANT" if score >= T["thresholds"]["variant"] else "UNKNOWN")
    return round(score, 3), cls, {"sections": round(sec_score, 2), "sheets": round(sheet_score, 2),
                                  "labels": round(lab_score, 2), "anchors": round(anchor_score, 2)}


def coa_map(plan):
    """Map each line to a canonical account (exact alias, then fuzzy token overlap).
    Unmapped lines are CARRIED (company-specific), never dropped."""
    mapped = {}; unmapped = []
    for l in plan["lines"]:
        n = norm(l["label"])
        acc = ALIAS.get(n)
        if not acc:                                   # fuzzy: alias fully contained / token overlap
            toks = set(n.split())
            best, bestj = None, 0.0
            for a, aid in ALIAS.items():
                at = set(a.split())
                if not at:
                    continue
                j = len(toks & at) / len(toks | at)
                if j > bestj:
                    bestj, best = j, aid
            acc = best if bestj >= 0.6 else None
        if acc:
            mapped[l["row"]] = acc
        else:
            unmapped.append(l["label"])
    return mapped, unmapped


def pick_annual_sheet(sheets, explicit):
    """Prefer the contract's known annual-sheet names (case-insensitive substring) before
    falling back to infer's content auto-detection (None)."""
    if explicit:
        return explicit
    names = COA["template"].get("annual_sheet_names", [])
    lc = {norm(s): s for s in sheets}
    for want in names:                                   # exact-ish first
        for ns, orig in lc.items():
            if norm(want) == ns:
                return orig
    for want in names:                                   # then substring
        for ns, orig in lc.items():
            if norm(want) in ns or ns in norm(want):
                return orig
    return None                                          # auto-detect


def triage(path, sheet, dispositions_path=None):
    with open(path, "rb") as source_file:
        short_hash = hashlib.sha1(source_file.read()).hexdigest()[:12]
    entry = {"file": os.path.basename(path),
             "hash": short_hash}
    review_path = dispositions_for_source(dispositions_path, path)
    try:
        audit = gate_source(path, review_path)
    except MigrationGateError as error:
        audit = error.report
        entry.update(
            bucket="BLOCKED" if error.exit_code == 2 else "NEEDS_REVIEW",
            fingerprint_class="UNKNOWN",
            reasons=[str(error)],
            auditStatus=audit.get("status", "ERROR"),
            auditIssues=audit.get("issues", []),
            reviewStatus=audit.get("reviewStatus", "UNRESOLVED"),
            sourceSha256=audit.get("sourceSha256"),
        )
        return entry, None
    entry.update(
        auditStatus=audit["status"],
        auditIssues=audit["issues"],
        reviewStatus=audit["reviewStatus"],
        sourceSha256=audit["sourceSha256"],
    )
    try:
        strip = strip_report(path)
        entry["stripped"] = strip
        chosen = pick_annual_sheet(strip["sheets"], sheet)
        entry["chosen_sheet"] = chosen
        plan = INF.infer(path, sheet=chosen)
    except BaseException as ex:                          # incl. ValueError from axis detection
        entry.update(bucket="FAILED", fingerprint_class="UNKNOWN",
                     reasons=[f"inference error: {ex}"])
        return entry, None
    plan["sourcePath"] = os.path.realpath(os.path.abspath(path))
    plan["sourceSha256"] = entry["sourceSha256"]
    initial_summary = plan["summary"]
    initial_parity = plan["parity"]
    entry.update(
        sheet=plan["sheet"],
        n_periods=len(plan["periods"]),
        periods=[period["year"] for period in plan["periods"]],
        n_lines=len(plan["lines"]),
        input=initial_summary.get("input", 0),
        derived=initial_summary.get("derived", 0),
        ratio=initial_summary.get("ratio", 0),
        carried=initial_summary.get("carried_plug", 0),
        needs_review=initial_summary.get("needs_review", 0),
        live=initial_parity.get("live", 0),
        frozen=initial_parity.get("frozen", 0),
        anchors=list(plan["anchors"]),
    )
    try:
        completed_audit = gate_source(path, review_path, plan_review_issues(plan))
    except MigrationGateError as error:
        completed_audit = error.report
        entry.update(
            bucket="NEEDS_REVIEW",
            reasons=[str(error)],
            auditStatus=completed_audit.get("status", "REVIEW_REQUIRED"),
            auditIssues=completed_audit.get("issues", []),
            reviewStatus=completed_audit.get("reviewStatus", "UNRESOLVED"),
        )
        return entry, None
    entry.update(
        auditStatus=completed_audit["status"],
        auditIssues=completed_audit["issues"],
        reviewStatus=completed_audit["reviewStatus"],
    )
    mapped, unmapped = coa_map(plan)
    sc, cls, det = fingerprint(plan, entry["stripped"]["sheets"], len(mapped))
    s = plan["summary"]; par = plan["parity"]
    n_periods = len(plan["periods"])
    anchors = list(plan["anchors"])
    # a real gap = a HEADLINE line (not a ratio/sub-item) in a stable section that didn't map
    unmapped_stable = [l["label"] for l in plan["lines"]
                       if l["row"] not in mapped and in_stable(l["section"])
                       and not is_detail(l)]
    reasons = []
    # no-silent-truncation invariants
    if n_periods == 0:
        reasons.append("INVARIANT: no year axis detected")
    acat = {"Revenue": "rev", "EBIT": "profit", "EBITDA": "profit", "Net income": "bottom",
            "Net attributable": "bottom", "EPS reported": "eps", "EPS adjusted": "eps"}
    ncat = len({acat[a] for a in anchors if a in acat})
    if ncat < 2:                                          # revenue + a profit/bottom line = a statement
        reasons.append(f"INVARIANT: only {ncat} anchor categor(ies) resolved")
    sections_found = {norm(l["section"]) for l in plan["lines"] if in_stable(l["section"])}
    if len(sections_found) < 2:                           # non-fatal: operating models lack section headers
        reasons.append(f"note: few recognised sections ({len(sections_found)}) — check section mapping")
    entry.update(sheet=plan["sheet"], fingerprint=sc, fingerprint_class=cls, fingerprint_detail=det,
                 n_periods=n_periods, periods=[p["year"] for p in plan["periods"]][:2] +
                 [plan["periods"][-1]["year"]] if plan["periods"] else [],
                 n_lines=len(plan["lines"]), input=s.get("input", 0), derived=s.get("derived", 0),
                 ratio=s.get("ratio", 0), carried=s.get("carried_plug", 0),
                 needs_review=s.get("needs_review", 0), live=par.get("live", 0),
                 frozen=par.get("frozen", 0), anchors=anchors,
                 n_mapped=len(mapped), n_unmapped=len(unmapped),
                 unmapped_stable=unmapped_stable[:8], reasons=reasons)
    # bucket
    if cls == "UNKNOWN" or any(r.startswith("INVARIANT") for r in reasons):
        entry["bucket"] = "FAILED"
    elif (cls == "SAME" and s.get("needs_review", 0) == 0 and not unmapped_stable):
        entry["bucket"] = "AUTO_PARITY"
    else:
        entry["bucket"] = "NEEDS_REVIEW"
        if cls == "VARIANT":
            reasons.append("VARIANT fingerprint")
        if s.get("needs_review", 0):
            reasons.append(f"{s['needs_review']} line(s) flagged in inference")
        if unmapped_stable:
            reasons.append(f"{len(unmapped_stable)} unmapped line(s) in stable sections (carried)")
    return entry, plan


def expand(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += sorted(glob.glob(os.path.join(p, "*.xlsx")))
        else:
            out += sorted(glob.glob(p)) if any(c in p for c in "*?[") else [p]
    return [p for p in out if p.lower().endswith(".xlsx") and "~$" not in p]


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="XLSX files, globs, or directories")
    parser.add_argument("--sheet")
    parser.add_argument("--out")
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--post-review", action="store_true",
                        help="legacy flag; reviewed files still require --review-dispositions")
    parser.add_argument("--review-dispositions",
                        help="source-bound JSON file, or directory of <sourceSha256>.json files")
    parser.add_argument("--conn")
    parser.add_argument("--folder")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    files = expand(args.paths)
    if not files:
        _parser().error("no .xlsx files found")
    sheet = args.sheet
    manifest = []; plans = []
    for f in files:
        entry, plan = triage(f, sheet, args.review_dispositions)
        manifest.append(entry); plans.append(plan)
        print(f"  [{entry['bucket']:12s}] {entry['file'][:48]:48s} "
              f"fp={entry.get('fingerprint','-')}/{entry.get('fingerprint_class','-')} "
              f"periods={entry.get('n_periods','-')} live={entry.get('live','-')} "
              f"frozen={entry.get('frozen','-')} unmapped={entry.get('n_unmapped','-')}")

    buckets = Counter(e["bucket"] for e in manifest)
    top_unmapped = Counter()
    for e in manifest:
        for lab in (e.get("unmapped_stable") or []):
            top_unmapped[lab] += 1
    print(f"\nROLLUP over {len(manifest)} file(s): " +
          "  ".join(f"{k}={v}" for k, v in buckets.most_common()))
    if top_unmapped:
        print("Top unmapped stable-section labels (grow coa.json aliases):")
        for lab, n in top_unmapped.most_common(10):
            print(f"   {n:3d}  {lab}")

    out = args.out
    if out:
        with open(out, "w", encoding="utf-8") as output_file:
            json.dump({"buckets": dict(buckets), "top_unmapped": top_unmapped.most_common(20),
                       "files": manifest}, output_file, indent=1)
        csvp = os.path.splitext(out)[0] + ".csv"
        import csv
        keys = ["file", "bucket", "fingerprint", "fingerprint_class", "n_periods", "n_lines",
                "input", "derived", "ratio", "carried", "needs_review", "live", "frozen",
                "n_mapped", "n_unmapped", "auditStatus", "reviewStatus", "sourceSha256",
                "auditIssues", "reasons"]
        with open(csvp, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore"); w.writeheader()
            for e in manifest:
                w.writerow(e)
        print(f"\nmanifest: {out}  +  {csvp}")

    # Optional live build. REVIEW_REQUIRED sources are eligible only after the gate
    # has validated their source-bound dispositions, at which point triage can mark
    # them AUTO_PARITY. --post-review alone never changes eligibility.
    if args.post and any(e["bucket"] == "AUTO_PARITY" for e in manifest):
        BUILD = load_mod("build-research-model.py", "brm")
        conn, folder = args.conn, args.folder
        if not (conn and folder):
            _parser().error("--post requires --conn and --folder")
        e = BUILD.env(); base = e["SIGMA_BASE_URL"]; tok = BUILD.token(e)
        for entry, plan in zip(manifest, plans):
            if entry["bucket"] != "AUTO_PARITY":
                continue
            name = os.path.splitext(entry["file"])[0][:56] + " (auto)"
            dl = [ln for ln in plan["lines"] if ln["typed"]]
            dm = BUILD.api(base, tok, "POST", "/v2/dataModels/spec",
                           BUILD.build_dm(plan, conn, folder, name)[0])
            full = BUILD.api(base, tok, "GET", f"/v2/dataModels/{dm['dataModelId']}/spec")
            # Current workbook API: wrap nested draft, validate, then create.
            wb_body = BUILD.workbook_wire.wire_workbook(
                BUILD.build_wb(plan, dm["dataModelId"], BUILD.map_dm(full), dl, folder, name))
            checked = BUILD.api(base, tok, "POST", "/v2/workbooks",
                                BUILD.workbook_wire.dry_run_request(wb_body))
            BUILD.workbook_wire.assert_dry_run_success(checked)
            wb = BUILD.api(base, tok, "POST", "/v2/workbooks", wb_body)
            print(f"   built {entry['file']}: wb {wb.get('workbookId')}")
    if any(entry["bucket"] == "BLOCKED" for entry in manifest):
        return 2
    if any(entry["bucket"] in {"NEEDS_REVIEW", "FAILED"} for entry in manifest):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
