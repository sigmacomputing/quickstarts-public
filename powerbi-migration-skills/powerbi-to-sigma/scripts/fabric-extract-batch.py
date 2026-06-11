#!/usr/bin/env python3
"""fabric-extract-batch.py — pooled estate extraction (the assessment-fleet /
batch-migration path).

For a 20-40 dashboard estate the old loop fetched every model TMSL and report
definition SERIALLY (12-20s per report -> 5-13 min wall). This pools the
INDEPENDENT getDefinition LROs 4-wide (the Fabric per-principal throttling cap),
flattening each report into two artifact tasks (model TMSL + report definition),
so a 20-report estate extracts in roughly 1/4 the serial wall time. Estate
enumeration itself is the shared fast path (8-wide, session-cached — see
pbi_fabric.py).

Each report lands under <out-root>/<slug>/:
    model/        flattened TMSL parts (model.bim / definition__database.tmsl)
    report/       exploded report definition (PBIR tree or classic report.json)
    report-bundle.json   the flat {part: text} bundle migrate-powerbi.rb --pbir eats
A manifest.json + timings.json (per-task wall clock — ALWAYS written) land at
<out-root>/.

Usage:
    python3 fabric-extract-batch.py --reports "Superstore Overview,Retail Sales Star" \
        [--workspace <id|name>] [--out-root /tmp/pbi-batch] [--pool 4] [--no-cache]
    python3 fabric-extract-batch.py --all --workspace Test   # every report in ws

Model binding: each report's semantic model is resolved via the Power BI REST
API (GET reports/{id} -> datasetId); when that scope/endpoint is unavailable it
falls back to a display-name match within the workspace.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbi_fabric as fab  # noqa: E402  (injects truststore)

ap = argparse.ArgumentParser(description="Pooled Fabric extraction for a report estate")
ap.add_argument("--reports", default=None,
                help="comma-separated report names/ids (case-insensitive substrings)")
ap.add_argument("--all", action="store_true", help="every report (optionally within --workspace)")
ap.add_argument("--workspace", default=None, help="workspace id or name to scope the search")
ap.add_argument("--out-root", default="/tmp/pbi-batch")
ap.add_argument("--pool", type=int, default=4,
                help="concurrent definition fetches (hard cap 4 — Fabric per-principal throttling)")
ap.add_argument("--no-cache", action="store_true", help="bypass the estate-map session cache")
ARGS = ap.parse_args()
if not ARGS.reports and not ARGS.all:
    ap.error("need --reports or --all")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "report"


def main():
    tm = fab.Timings()
    tok = tm.timed("auth", lambda: fab.get_token())
    if not tok:
        print("NO_TOKEN — device code blocked or no client worked.", flush=True)
        sys.exit(2)

    # ---- estate map (session cache -> live parallel enumeration) -------------
    estate = None if ARGS.no_cache else fab.load_estate_cache()
    if estate:
        print(f"[estate-cache] using {fab.ESTATE_CACHE}", flush=True)
    else:
        estate = fab.enumerate_estate(tok, timings=tm)
        fab.save_estate_cache(estate)
    wss = estate["workspaces"]
    if ARGS.workspace:
        w = fab._match(wss, ARGS.workspace)
        if not w:  # cache may be stale — re-enumerate once
            estate = fab.enumerate_estate(tok, timings=tm)
            fab.save_estate_cache(estate)
            wss = estate["workspaces"]
            w = fab._match(wss, ARGS.workspace)
        if not w:
            print(f"NO workspace matching '{ARGS.workspace}'", flush=True)
            sys.exit(4)
        wss = [w]

    # ---- pick the reports -----------------------------------------------------
    wanted = [s.strip() for s in (ARGS.reports or "").split(",") if s.strip()]
    picked = []  # (ws, report)
    for w in wss:
        for r in w["reports"]:
            if ARGS.all or any(n == r["id"] or n.lower() in (r["name"] or "").lower() for n in wanted):
                picked.append((w, r))
    if wanted:
        missing = [n for n in wanted
                   if not any(n == r["id"] or n.lower() in (r["name"] or "").lower() for _, r in picked)]
        if missing:
            print(f"WARN: no report matched: {', '.join(missing)}", flush=True)
    if not picked:
        print("NO reports matched.", flush=True)
        sys.exit(4)
    print(f"[batch] {len(picked)} report(s), pool={min(max(ARGS.pool,1),4)}", flush=True)

    # ---- bind each report to its semantic model -------------------------------
    jobs, meta = [], {}
    for w, r in picked:
        sl = slug(r["name"])
        meta[sl] = {"workspace": {"id": w["id"], "name": w["name"]},
                    "report": {"id": r["id"], "name": r["name"]}, "model": None}
        ds = tm.timed(f"bind:{sl}", lambda w=w, r=r: fab.report_dataset_id(w["id"], r["id"]))
        model = None
        if ds:
            model = next((m for m in w["models"] if m["id"] == ds), None)
        if not model:  # fallback: display-name match within the workspace
            model = fab._match(w["models"], r["name"])
        if model:
            meta[sl]["model"] = model
            jobs.append({"name": f"model:{sl}", "ws": w["id"], "kind": "semanticModels",
                         "id": model["id"], "fmt": "TMSL"})
        else:
            print(f"  WARN [{r['name']}] no bound semantic model resolved — report-only", flush=True)
        jobs.append({"name": f"report:{sl}", "ws": w["id"], "kind": "reports",
                     "id": r["id"], "report_fallback": True})

    # ---- ONE shared pool over every artifact (model TMSL + report def) --------
    results = fab.fetch_definitions(tok, jobs, pool=ARGS.pool, timings=tm)

    manifest = {}
    for sl, info in meta.items():
        root = os.path.join(ARGS.out_root, sl)
        entry = dict(info)
        mdef = results.get(f"model:{sl}")
        if mdef:
            entry["model_dir"] = os.path.join(root, "model")
            entry["model_parts"] = fab.write_parts(mdef, entry["model_dir"], flatten=True)
        rdef = results.get(f"report:{sl}")
        if rdef:
            entry["report_dir"] = os.path.join(root, "report")
            entry["report_parts"] = fab.write_parts(rdef, entry["report_dir"], flatten=False)
            bundle_path = os.path.join(root, "report-bundle.json")
            json.dump(fab.parts_bundle(rdef), open_w(bundle_path))
            entry["report_bundle"] = bundle_path
        manifest[sl] = entry
        print(f"  {sl}: model={'ok' if mdef else '—'} report={'ok' if rdef else '—'} -> {root}", flush=True)

    os.makedirs(ARGS.out_root, exist_ok=True)
    json.dump(manifest, open(os.path.join(ARGS.out_root, "manifest.json"), "w"), indent=2)
    t = tm.write(os.path.join(ARGS.out_root, "timings.json"),
                 status="ok", reports=len(picked), pool=min(max(ARGS.pool, 1), 4))
    print(f"TIMINGS total={t['totalSeconds']}s", flush=True)
    for x in t["tasks"]:
        print(f"  {x['task']}: {x['seconds']}s", flush=True)
    print(f"WROTE {os.path.join(ARGS.out_root, 'manifest.json')}. DONE.", flush=True)


def open_w(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return open(path, "w")


main()
