#!/usr/bin/env python3
"""POST a Sigma data-model spec to /v2/dataModels/spec.

- Swaps any placeholder connectionId in the spec for the full connection UUID
  ($SIGMA_CONNECTION_ID). convert_dm.mjs writes a placeholder; use the FULL UUID
  here (a short prefix → "Source not found: warehouse table ...").
- Auto-picks a writable folder (folderId is required), preferring one whose name
  mentions LOOKER / MIGRATION / TEST; override with --folder-id.
- The spec endpoints return YAML, not JSON — don't json.load the response.

Usage:
  eval "$(scripts/get-token.sh)"
  SIGMA_CONNECTION_ID=<full-uuid> python3 post_dm.py <spec.json> [--folder-id <id>]
"""
import argparse, json, os, re, sys, urllib.request, urllib.error

BASE = os.environ["SIGMA_BASE_URL"]
TOK = os.environ["SIGMA_API_TOKEN"]
FULL_CONN = os.environ.get("SIGMA_CONNECTION_ID")


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
        headers={"Authorization": "Bearer " + TOK, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read().decode()
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, method, path, "->", e.read().decode()[:1000], file=sys.stderr); raise
    try:
        return json.loads(raw)
    except Exception:
        return raw  # YAML/text


def drop_join_key_passthroughs(spec):
    """Guard: drop derived-view columns that pass a relationship's OWN join key across
    the join (formula [Base/REL_NAME/<target key col>]). A cross-element passthrough of
    a join key compiles to type "error" in Sigma (the base element already carries that
    value; Sigma degrades the ref on readback). The MCP lookml converter's denormalized
    element can still emit one — strip it here with a WARN before POSTing."""
    rel_keys = {}   # relationship name -> set of target-key DISPLAY names
    elements = [e for p in spec.get("pages", []) for e in (p.get("elements") or [])]
    by_id = {e.get("id"): e for e in elements}
    for el in elements:
        for rel in (el.get("relationships") or []):
            tgt = by_id.get(rel.get("targetElementId")) or {}
            tcols = {c.get("id"): c for c in (tgt.get("columns") or [])}
            names = rel_keys.setdefault(rel.get("name") or "", set())
            for k in (rel.get("keys") or []):
                c = tcols.get(k.get("targetColumnId"))
                if not c:
                    continue
                d = c.get("name")
                if not d:
                    m = re.match(r"\[([^\]]+)\]$", c.get("formula") or "")
                    if m:
                        d = m.group(1).split("/")[-1]
                if d:
                    names.add(d)
    for el in elements:
        cols = el.get("columns") or []
        kept = []
        for c in cols:
            m = re.match(r"\[([^/\]]+)/([^/\]]+)/([^\]]+)\]$", c.get("formula") or "")
            if m and m.group(3) in rel_keys.get(m.group(2), set()):
                print(f"WARN: dropping join-key passthrough column {c.get('id')} "
                      f"({c.get('formula')}) on element {el.get('name') or el.get('id')} — "
                      f"cross-element passthrough of a join key compiles to type=error in Sigma",
                      file=sys.stderr)
                if el.get("order"):
                    el["order"] = [o for o in el["order"] if o != c.get("id")]
                continue
            kept.append(c)
        if len(kept) != len(cols):
            el["columns"] = kept
    return spec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--folder-id")
    a = ap.parse_args()

    spec = json.load(open(a.spec))
    spec = drop_join_key_passthroughs(spec)

    # rewrite every connectionId (placeholder or short prefix) to the full UUID
    if FULL_CONN:
        s = re.sub(r'("connectionId"\s*:\s*)"[^"]*"', rf'\1"{FULL_CONN}"', json.dumps(spec))
        spec = json.loads(s)
    else:
        print("WARN: SIGMA_CONNECTION_ID unset — posting spec connectionId as-is", file=sys.stderr)

    folder = a.folder_id
    if not folder:
        files = api("GET", "/v2/files?typeFilters=folder&limit=200")
        entries = files.get("entries", files.get("data", [])) if isinstance(files, dict) else []
        for f in entries:
            if any(k in (f.get("name", "") or "").upper() for k in ("LOOKER", "MIGRATION", "TEST")):
                folder = f["id"]; break
        if not folder and entries:
            folder = entries[0]["id"]
    print("folderId:", folder, file=sys.stderr)
    if folder:
        spec["folderId"] = folder

    res = api("POST", "/v2/dataModels/spec", spec)
    print(json.dumps(res, indent=2)[:600] if isinstance(res, dict) else str(res)[:600])


if __name__ == "__main__":
    main()
