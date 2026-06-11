#!/usr/bin/env python3
"""fabric-extract.py — extract a semantic model's TMSL (and, optionally, its
report's definition CONCURRENTLY) from Fabric.

FAST DISCOVERY (customer scale: 30-50 workspaces, 20-40 report estates):
  * --workspace <id|name> skips the full-estate enumeration (a workspace ID is
    2 cheap GETs; at 30-50 workspaces the old serial walk was 15-30s).
  * without --workspace, enumeration fans out 8-wide (~2-3s for 30-50 ws) and
    is cached per session at /tmp/pbiauth/estate-map.json — invalidated
    automatically whenever a requested name isn't found in the cache.
  * --report <id|name> fetches the report definition IN PARALLEL with the model
    TMSL (independent artifacts; previously two serial scripts). LRO polling is
    0.5s-first + backoff instead of sleeping the full Retry-After. Concurrency
    is capped at 4 per principal (Fabric throttling).
  * timings.json (per-task wall clock) is ALWAYS written to --out-dir.

Usage:
    python3 fabric-extract.py [--model-name <substring>] [--out-dir DIR]
        [--workspace <id|name>] [--report <id|name>] [--report-out-dir DIR]
        [--report-bundle PATH] [--pool N] [--no-cache]

  --model-name: case-insensitive substring of the semantic model display name
                (default: first model found, with a note).
  --out-dir:    where the model definition parts land (default /tmp/pbix).
  --report:     also fetch this report's definition (PBIR, falling back to the
                classic format) — concurrently with the model.
  --report-out-dir: exploded report parts (default <out-dir>/report).
  --report-bundle:  ALSO write the flat {part-path: text} bundle JSON that
                migrate-powerbi.rb accepts as --pbir.
  --no-cache:   skip the estate-map session cache.
Token cache path is overridable via PBI_TOKEN_CACHE.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbi_fabric as fab  # noqa: E402  (injects truststore)

ap = argparse.ArgumentParser(description="Extract a semantic model's TMSL (+ report definition) from Fabric")
ap.add_argument("--model-name", default=None,
                help="case-insensitive substring of the target semantic model name (default: first found)")
ap.add_argument("--out-dir", default="/tmp/pbix", help="output directory for model definition parts (default /tmp/pbix)")
ap.add_argument("--workspace", default=None,
                help="workspace id or name — skips full-estate enumeration when given")
ap.add_argument("--report", default=None,
                help="report id or name — fetched CONCURRENTLY with the model")
ap.add_argument("--report-out-dir", default=None,
                help="exploded report definition parts (default <out-dir>/report)")
ap.add_argument("--report-bundle", default=None,
                help="also write the flat {part: text} bundle JSON (migrate-powerbi.rb --pbir)")
ap.add_argument("--pool", type=int, default=2,
                help="concurrent definition fetches (capped at 4 — Fabric per-principal throttling)")
ap.add_argument("--no-cache", action="store_true", help="bypass the estate-map session cache")
ARGS = ap.parse_args()


def main():
    tm = fab.Timings()
    tok = tm.timed("auth", lambda: fab.get_token())
    if not tok:
        print("NO_TOKEN — device code blocked or no client worked.", flush=True)
        sys.exit(2)

    # ---- resolve targets (estate cache -> live; --workspace = no enumeration)
    try:
        hit = fab.resolve_targets(
            tok, model_name=ARGS.model_name, workspace=ARGS.workspace,
            report=ARGS.report, use_cache=not ARGS.no_cache, timings=tm,
            log=lambda s: print(s, flush=True))
    except LookupError as e:
        print(f"NO MATCH: {e}", flush=True)
        tm.write(os.path.join(ARGS.out_dir, "timings.json"), status="no-match")
        sys.exit(4)
    ws, model, report = hit["workspace"], hit["model"], hit["report"]
    if not model and not report:
        print("NO_SEMANTIC_MODEL found in any accessible workspace.", flush=True)
        sys.exit(4)
    if model and not ARGS.model_name:
        print("[note] no --model-name given — defaulting to the first model found", flush=True)
    if model:
        print(f"[TARGET] ws='{ws.get('name')}' model='{model.get('name')}' id={model['id']}", flush=True)
    if report:
        rws = hit.get("report_workspace") or ws
        print(f"[TARGET] ws='{rws.get('name')}' report='{report.get('name')}' id={report['id']}", flush=True)

    # ---- fire the independent getDefinition LROs CONCURRENTLY ----------------
    jobs = []
    if model:
        jobs.append({"name": "model-tmsl", "ws": ws["id"], "kind": "semanticModels",
                     "id": model["id"], "fmt": "TMSL"})
    if report:
        rws = hit.get("report_workspace") or ws
        jobs.append({"name": "report-def", "ws": rws["id"], "kind": "reports",
                     "id": report["id"], "report_fallback": True})
    results = fab.fetch_definitions(tok, jobs, pool=ARGS.pool, timings=tm)

    if "model-tmsl" in results:
        body = results["model-tmsl"]
        parts = body.get("definition", {}).get("parts", [])
        print(f"[definition] {len(parts)} parts: " + ", ".join(p["path"] for p in parts), flush=True)
        fab.write_parts(body, ARGS.out_dir, flatten=True)  # legacy flat layout
        print(f"WROTE model definition parts to {ARGS.out_dir}/.", flush=True)

    if "report-def" in results:
        rdef = results["report-def"]
        rdir = ARGS.report_out_dir or os.path.join(ARGS.out_dir, "report")
        written = fab.write_parts(rdef, rdir, flatten=False)
        print(f"WROTE report definition ({len(written)} parts) to {rdir}/.", flush=True)
        if ARGS.report_bundle:
            bundle = fab.parts_bundle(rdef)
            os.makedirs(os.path.dirname(os.path.abspath(ARGS.report_bundle)), exist_ok=True)
            json.dump(bundle, open(ARGS.report_bundle, "w"))
            print(f"WROTE report bundle (migrate-powerbi.rb --pbir) to {ARGS.report_bundle}", flush=True)

    t = tm.write(os.path.join(ARGS.out_dir, "timings.json"),
                 status="ok", workspace=ws.get("name"),
                 model=model and model.get("name"), report=report and report.get("name"))
    line = "  ".join(f"{x['task']}={x['seconds']}s" for x in t["tasks"])
    print(f"TIMINGS total={t['totalSeconds']}s  {line}", flush=True)
    print("DONE.", flush=True)


main()
