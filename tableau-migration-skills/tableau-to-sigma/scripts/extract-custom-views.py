#!/usr/bin/env python3
"""extract-custom-views.py — Tableau Custom Views -> normalized states (bookmarks.json).

Tableau's analog of a Power BI bookmark is a **Custom View** (a saved per-user
filter/parameter/selection state of a published view). This enumerates them via
the REST API and emits the SAME normalized shape build-bookmark-workbooks.py
consumes, so the shared per-state workbook builder works for Tableau too.

  ⚠ KNOWN LIMITATION (verified 2026-06-02): the Tableau REST API exposes custom
  view METADATA only (name, owner, the view) — NOT the filter/parameter VALUES
  the view applies (they're an opaque workbook-state blob). So `filters` is left
  EMPTY here; to recover the actual filter values, render the custom view and
  diff its data vs the base view (the view-CSV-vs-warehouse diff technique the
  Tableau skill already uses), or capture them manually. Without that, each
  emitted state reproduces the base view (no subset/filter) — inventory only.

  Also: Tableau REST has no create-custom-view endpoint (they're created in the
  UI/embedding), so fixtures can't be authored via API.

Auth: eval "$(get-tableau-token.sh)" first (sets TABLEAU_AUTH_TOKEN + _SITE_ID).
Usage:
  python3 extract-custom-views.py --workbook <wbId> --out bookmarks.json
  python3 extract-custom-views.py --site-wide --out bookmarks.json
"""
try:
    import truststore; truststore.inject_into_ssl()  # corp TLS inspection — use macOS keychain CA
except Exception:
    pass
import argparse, json, os, sys, urllib.request

def _get(url, tok):
    req = urllib.request.Request(url, headers={"X-Tableau-Auth": tok, "Accept": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workbook"); ap.add_argument("--site-wide", action="store_true")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    srv = os.environ["TABLEAU_SERVER_URL"]; site = os.environ["TABLEAU_SITE_ID"]
    tok = os.environ["TABLEAU_AUTH_TOKEN"]; ver = os.environ.get("TABLEAU_API_VERSION", "3.22")
    base = f"{srv}/api/{ver}/sites/{site}/customviews"
    url = base + (f"?filter=workbookId:eq:{a.workbook}&pageSize=100" if a.workbook else "?pageSize=100")
    cvs = _get(url, tok).get("customViews", {}).get("customView", [])
    states = []
    for c in cvs:
        states.append({
            "name": (c.get("name") or c.get("id")).replace(" ", "_")[:40],
            "displayName": c.get("name") or "Custom View",
            "activeSection": c.get("view", {}).get("id"),
            "hidden": [], "spotlight": [],
            "filters": {},                       # NOT API-exposed — see module docstring
            "_tableau": {"id": c.get("id"), "view": c.get("view", {}),
                         "workbook": c.get("workbook", {}), "shared": c.get("shared")},
        })
    json.dump({"bookmarks": states, "source": "tableau-custom-views",
               "note": "filter values not API-exposed; recover via view-data diff or omit"},
              open(a.out, "w"), indent=2)
    print(f"[custom-views] {len(states)} -> {a.out}", file=sys.stderr)
    for s in states:
        print(f"  {s['displayName']:30} view={s['activeSection']}", file=sys.stderr)
    if not states:
        print("  (none found — Tableau custom views are user-created in the UI; "
              "REST can't author them)", file=sys.stderr)

if __name__ == "__main__":
    main()
