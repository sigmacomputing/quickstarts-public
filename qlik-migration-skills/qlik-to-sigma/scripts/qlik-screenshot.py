#!/usr/bin/env python3
"""qlik-screenshot — export PNGs of Qlik viz objects via the Qlik Cloud reporting API.

    python3 qlik-screenshot.py --app <appId> --sheet <sheetId> --out shots/    # all charts on a sheet
    python3 qlik-screenshot.py --app <appId> --viz c-cat,c-mon --out shots/     # specific viz ids

Parallels tableau-to-sigma/scripts/export-chart-png.rb — capture before/after images for a
migration. Uses the active qlik-cli context (run `qlik context use <ctx>` first).

NOTE (verified 2026-06-03): the reporting API exports a **single visualization** as PNG
(`senseImageTemplate`); whole-sheet export is PDF/PPTX only. So this screenshots each viz
on the sheet individually. KPIs/auto-charts/tables render; bare concrete chart types built
via the API render blank (see refs/sigma-build-gotchas.md).
"""
import json, os, re, subprocess, sys, argparse, time

def qlik(*a, raw_out=False, parse=True):
    o = subprocess.run(["qlik", *a], capture_output=True, text=True)
    if raw_out: return o.stdout, o.stderr
    if not parse: return o.stdout
    try: return json.loads(o.stdout or "null")
    except json.JSONDecodeError: return None

def sheet_children(app, sheet):
    lay = qlik("app", "object", "layout", sheet, "-a", app)
    items = ((lay or {}).get("qChildList") or {}).get("qItems", [])
    out = []
    for it in items:
        info = it.get("qInfo", {})
        out.append((info.get("qId"), (it.get("qData") or {}).get("title") or info.get("qId")))
    return out

def export_png(app, viz, out_dir, w=900, h=600, zoom=2):
    body = {"type":"sense-image-1.0",
            "senseImageTemplate":{"appId":app,"visualization":{"id":viz,"type":"visualization","widthPx":w,"heightPx":h},"selectionsByState":{}},
            "output":{"outputId":viz,"type":"image","imageOutput":{"outZoom":zoom,"outDpi":96,"outFormat":"png"}}}
    bf = f"/tmp/_qshot_{viz}.json"; json.dump(body, open(bf,"w"))
    out, err = qlik("raw","post","v1/reports","--body-file",bf,"--verbose", raw_out=True)
    m = re.search(r'reports/([a-f0-9-]+)/status', err + out)
    if not m: return None, "no report id"
    rid = m.group(1)
    for _ in range(45):
        st = qlik("raw","get",f"v1/reports/{rid}/status")
        if st and st.get("status") == "done":
            loc = st["results"][0]["location"]
            path = loc.split("/api/")[-1]
            # binary-safe download (text mode corrupts PNG bytes)
            png = subprocess.run(["qlik","raw","get",path], capture_output=True).stdout
            p = os.path.join(out_dir, f"{viz}.png")
            with open(p,"wb") as f: f.write(png)
            return (p, None) if png[:4] == b"\x89PNG" else (None, "not a PNG (%d bytes)"%len(png))
        if st and "fail" in (st.get("status") or "").lower(): return None, "report failed"
        time.sleep(2)
    return None, "timeout"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--sheet"); ap.add_argument("--viz")
    ap.add_argument("--out", default="shots")
    ap.add_argument("--width", type=int, default=900); ap.add_argument("--height", type=int, default=600)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    targets = []
    if a.sheet: targets = sheet_children(a.app, a.sheet)
    elif a.viz: targets = [(v, v) for v in a.viz.split(",")]
    else: sys.exit("provide --sheet or --viz")
    manifest = {}
    for viz, title in targets:
        p, err = export_png(a.app, viz, a.out, a.width, a.height)
        print(f"  {viz} ({title}): {'OK '+p if p else 'FAIL '+str(err)}")
        manifest[viz] = {"title": title, "png": p, "error": err}
    json.dump(manifest, open(os.path.join(a.out,"_manifest.json"),"w"), indent=2)
    print(f"-> {a.out}/ ({sum(1 for v in manifest.values() if v['png'])}/{len(manifest)} ok)")

if __name__ == "__main__": main()
