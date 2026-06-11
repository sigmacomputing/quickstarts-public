#!/usr/bin/env python3
"""extract-bookmarks.py — normalize Power BI report bookmarks to bookmarks.json.

Handles both report formats:
  - PBIR:    definition/bookmarks/bookmarks.json (order) + <name>.bookmark.json
  - classic: report.json -> config (JSON string) -> bookmarks[]

Each bookmark's explorationState captures per-visual display state
(singleVisual.display.mode = hidden | spotlight | maximize | elevation) and,
optionally, filter state. We normalize to the part that maps to Sigma:
  { name, displayName, activeSection,
    hidden:   [visualName, ...],     # show/hide
    spotlight:[visualName, ...] }     # spotlight/maximize  (focus)

Consumed by build-bookmark-workbooks.py to emit one Sigma workbook per bookmark
(visible-visual subset). Filter-state is surfaced under `filters_raw` for the
agent but not auto-applied (the explorationState filter JSON is report-specific).

Usage:
  python3 extract-bookmarks.py --pbir-dir /tmp/pbir --out /tmp/pbir/bookmarks.json
  python3 extract-bookmarks.py --report-json /tmp/x/report.json --out bookmarks.json
"""
import argparse, json, os, sys, glob

def _vis_states(section):
    hidden, spot = [], []
    for vname, st in (section.get("visualContainers", {}) or {}).items():
        mode = (st.get("singleVisual", {}).get("display", {}) or {}).get("mode")
        if mode == "hidden": hidden.append(vname)
        elif mode in ("spotlight", "maximize"): spot.append(vname)
    return hidden, spot

def _norm(name, display, expl):
    secs = expl.get("sections", {}) or {}
    hidden, spot = [], []
    for _s, sec in secs.items():
        h, sp = _vis_states(sec); hidden += h; spot += sp
    return {"name": name, "displayName": display or name,
            "activeSection": expl.get("activeSection"),
            "hidden": hidden, "spotlight": spot,
            "filters_raw": bool(expl.get("filters"))}

def from_pbir(pbir_dir):
    bdir = os.path.join(pbir_dir, "definition", "bookmarks")
    if not os.path.isdir(bdir): return []
    order = []
    idx = os.path.join(bdir, "bookmarks.json")
    if os.path.exists(idx):
        order = [i.get("name") for i in json.load(open(idx)).get("items", []) if isinstance(i, dict)]
    out = {}
    for bf in glob.glob(os.path.join(bdir, "*.bookmark.json")):
        b = json.load(open(bf))
        out[b.get("name")] = _norm(b.get("name"), b.get("displayName"), b.get("explorationState", {}))
    return [out[n] for n in order if n in out] + [v for k, v in out.items() if k not in order]

def from_classic(report_json):
    rep = json.load(open(report_json))
    cfg = json.loads(rep.get("config", "{}"))
    return [_norm(b.get("name"), b.get("displayName"), b.get("explorationState", {}))
            for b in cfg.get("bookmarks", [])]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pbir-dir"); ap.add_argument("--report-json"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.pbir_dir: bms = from_pbir(a.pbir_dir)
    elif a.report_json: bms = from_classic(a.report_json)
    else: sys.exit("need --pbir-dir or --report-json")
    json.dump({"bookmarks": bms}, open(a.out, "w"), indent=2)
    print(f"[bookmarks] {len(bms)} -> {a.out}", file=sys.stderr)
    for b in bms:
        print(f"  {b['displayName']:24} hidden={len(b['hidden'])} spotlight={len(b['spotlight'])} "
              f"filters={'Y' if b['filters_raw'] else '-'}", file=sys.stderr)

if __name__ == "__main__":
    main()
