#!/usr/bin/env python3
"""build-bookmark-workbooks.py — one Sigma workbook per saved view-state.

VENDOR-NEUTRAL. Power BI bookmarks (extract-bookmarks.py) and Tableau custom
views / story points (extract-custom-views.py) both normalize to the same
state shape; this builds one Sigma workbook per state:

  state = { name, displayName,
            hidden:[visualId], spotlight:[visualId],   # show/hide  -> visible subset
            filters: { "<column display name>": [values] } }  # filter state -> baked

Per state:
  - spotlight non-empty -> keep ONLY the spotlighted visuals (focus)
  - else                -> all base visuals MINUS `hidden`
  - filters             -> baked as a `list` filter on the Data-page MASTER
                           element(s) carrying that column, so every chart that
                           sources the master inherits it (page-filter semantics)

The signals->workbook build is delegated to a vendor builder via --build-script
(PBI: build-workbook-from-pbir.rb; Tableau: build-charts-from-signals.rb), so
this orchestration is shared. Lives in tableau-to-sigma/scripts (the shared
core); powerbi-to-sigma symlinks it.

Usage:
  python3 build-bookmark-workbooks.py --signals base/signals.json \
    --bookmarks states.json --master-map mm.json --data-model <dmId> \
    --folder-id <uuid> --name-prefix "<Report>" --out-dir /tmp/bm \
    [--build-script /path/to/build-workbook-from-pbir.rb]
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))

def _bake_filters(spec, filters):
    """Add `list` filters to the Data-page master element(s) holding each column."""
    if not filters:
        return 0
    n = 0
    masters = [el for pg in spec.get("pages", []) if pg.get("id") == "page-data"
               for el in pg.get("elements", [])]
    for col, vals in filters.items():
        vlist = vals if isinstance(vals, list) else [vals]
        for el in masters:
            hit = next((c for c in el.get("columns", [])
                        if (c.get("name") or "").lower() == str(col).lower()), None)
            if not hit:
                continue
            el.setdefault("filters", []).append({
                "id": f"bmf-{col}".replace(" ", "")[:20],
                "columnId": hit["id"], "kind": "list", "mode": "include", "values": vlist})
            n += 1
    return n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--signals", required=True); ap.add_argument("--bookmarks", required=True)
    ap.add_argument("--master-map", required=True); ap.add_argument("--data-model", required=True)
    ap.add_argument("--folder-id", required=True); ap.add_argument("--name-prefix", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--build-script", default=os.path.join(HERE, "build-workbook-from-pbir.rb"),
                    help="vendor signals->workbook builder (default: build-workbook-from-pbir.rb)")
    a = ap.parse_args()
    base = json.load(open(a.signals)); states = json.load(open(a.bookmarks))["bookmarks"]
    os.makedirs(a.out_dir, exist_ok=True)
    page = base["pages"][0]; all_vis = page["visuals"]; built = []
    for b in states:
        hidden, spot = set(b.get("hidden", [])), set(b.get("spotlight", []))
        vis = ([v for v in all_vis if v["visual_id"] in spot] if spot
               else [v for v in all_vis if v["visual_id"] not in hidden])
        if not vis:
            print(f"  [skip] {b['displayName']}: no visible visuals", file=sys.stderr); continue
        d = os.path.join(a.out_dir, b["name"]); os.makedirs(d, exist_ok=True)
        sigp = os.path.join(d, "signals.json")
        json.dump(dict(base, pages=[dict(page, visuals=vis)]), open(sigp, "w"), indent=2)
        spec = os.path.join(d, "workbook-spec.json"); lay = os.path.join(d, "layout.xml")
        name = f"{a.name_prefix} — {b['displayName']} (from Power BI)"
        r = subprocess.run(["ruby", a.build_script, "--signals", sigp, "--master-map", a.master_map,
            "--data-model", a.data_model, "--name", name, "--folder-id", a.folder_id,
            "--out", spec, "--layout-out", lay], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(spec):
            print(f"  ERR {b['displayName']}: {r.stderr[-200:]}", file=sys.stderr); continue
        nf = 0
        if b.get("filters"):                              # bake filter-state onto the master(s)
            s = json.load(open(spec)); nf = _bake_filters(s, b["filters"]); json.dump(s, open(spec, "w"), indent=2)
        print(f"  OK  {b['displayName']:22} {len(vis)} visual(s), {nf} filter(s) -> {spec}", file=sys.stderr)
        built.append({"bookmark": b["name"], "name": name, "spec": spec, "layout": lay,
                      "visuals": len(vis), "filters": nf})
    json.dump({"built": built}, open(os.path.join(a.out_dir, "manifest.json"), "w"), indent=2)
    print(f"[bookmark-workbooks] built {len(built)} -> {a.out_dir}/manifest.json", file=sys.stderr)

if __name__ == "__main__":
    main()
