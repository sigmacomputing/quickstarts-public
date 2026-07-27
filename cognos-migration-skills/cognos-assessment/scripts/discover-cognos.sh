#!/usr/bin/env bash
# Cognos Analytics estate discovery — read-only inventory walk for the
# cognos-assessment skill.
#
# Reuses the same auth shape as the converter's cognos-discover.sh:
#   export COGNOS_BASE="https://<host>/bi/v1"     # NOTE: /bi/v1, not /api/v1
#   export COGNOS_COOKIE="<full Cookie header from a logged-in session>"
#   export COGNOS_XSRF="<X-XSRF-Token header value>"
#
# Usage:
#   discover-cognos.sh --probe
#       Cheap auth check — lists the content root and exits.
#   discover-cognos.sh --root <folderId> --out <dir>
#       Walk the tree under <folderId> (e.g. .public_folders), fetch every
#       module/report spec into <dir>/specs/, emit <dir>/inventory.json.
#
# READ-ONLY: only ever issues GETs. Never POSTs / modifies / runs anything.
# Paginated, resumable (already-downloaded specs are skipped), token-expiry aware.
set -euo pipefail

ROOT=".public_folders"
OUT=""
PROBE=0
PAGE=100
MAXDEPTH=12
while [ $# -gt 0 ]; do
  case "$1" in
    --probe) PROBE=1; shift ;;
    --root)  ROOT="$2"; shift 2 ;;
    --out)   OUT="$2"; shift 2 ;;
    --page)  PAGE="$2"; shift 2 ;;
    --max-depth) MAXDEPTH="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

: "${COGNOS_BASE:?set COGNOS_BASE (e.g. https://host/bi/v1)}"
: "${COGNOS_COOKIE:?set COGNOS_COOKIE}"
: "${COGNOS_XSRF:?set COGNOS_XSRF}"

# req <path-with-leading-slash>  → prints body; sets global HTTP_CODE
req() {
  local body
  body=$(curl -s -w '\n%{http_code}' "$COGNOS_BASE$1" \
    -H 'Accept: application/json' \
    -H "X-XSRF-TOKEN: $COGNOS_XSRF" \
    -H 'X-Requested-With: XMLHttpRequest' \
    -b "$COGNOS_COOKIE")
  HTTP_CODE="${body##*$'\n'}"
  printf '%s' "${body%$'\n'*}"
}

if [ "$PROBE" = "1" ]; then
  out=$(req "/objects/$ROOT/items?fields=defaultName,type,id&top=10")
  if [ "$HTTP_CODE" -ge 400 ] 2>/dev/null || [ -z "$HTTP_CODE" ]; then
    echo "PROBE FAILED (HTTP ${HTTP_CODE:-?}) — session likely expired; re-grab COGNOS_COOKIE + COGNOS_XSRF." >&2
    exit 1
  fi
  echo "PROBE OK (HTTP $HTTP_CODE). Sample items under '$ROOT':"
  printf '%s' "$out" | python3 -c '
import sys,json
try: d=json.load(sys.stdin)
except Exception: print("  (non-JSON body)"); sys.exit(0)
items=d.get("data") or d.get("content") or d.get("items") or []
for i in items[:10]:
    print(f"  {i.get(\"type\",\"?\"):14} {i.get(\"id\")}  {i.get(\"defaultName\") or i.get(\"name\")}")
'
  exit 0
fi

[ -n "$OUT" ] || { echo "--out <dir> required (unless --probe)" >&2; exit 2; }
mkdir -p "$OUT/specs"

# The recursive walk + spec fetch is driven by a small Python helper that shells
# back out to curl through this script's req() for each request. Keeping the
# logic in Python (a Node/bash built-in everywhere) avoids a jq dependency.
export COGNOS_BASE COGNOS_COOKIE COGNOS_XSRF OUT ROOT PAGE MAXDEPTH
python3 <<'PY'
import os, sys, json, subprocess, urllib.parse, datetime

BASE   = os.environ["COGNOS_BASE"]
COOKIE = os.environ["COGNOS_COOKIE"]
XSRF   = os.environ["COGNOS_XSRF"]
OUT    = os.environ["OUT"]
ROOT   = os.environ["ROOT"]
PAGE   = int(os.environ["PAGE"])
MAXDEPTH = int(os.environ["MAXDEPTH"])

LEAF   = {"module", "report", "reportview", "exploration", "dashboard", "dataset2"}
FOLDER = {"folder", "package", "myFolders".lower(), "namespacefolder"}

token_expired = [False]

def get(path):
    """GET path (leading slash). Returns (status, text)."""
    p = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", BASE + path,
         "-H", "Accept: application/json",
         "-H", "X-XSRF-TOKEN: " + XSRF,
         "-H", "X-Requested-With: XMLHttpRequest",
         "-b", COOKIE],
        capture_output=True, text=True)
    body = p.stdout
    nl = body.rfind("\n")
    code = body[nl+1:].strip() if nl >= 0 else ""
    text = body[:nl] if nl >= 0 else body
    try:
        status = int(code)
    except ValueError:
        status = 0
    if status in (401, 403):
        token_expired[0] = True
    return status, text

def items_of(folder_id):
    """Yield child items of a folder, following pagination."""
    skip = 0
    while True:
        if token_expired[0]:
            return
        q = f"/objects/{urllib.parse.quote(str(folder_id))}/items?fields=defaultName,type,id,owner,modificationTime&top={PAGE}&skip={skip}"
        status, text = get(q)
        if status >= 400 or status == 0:
            return
        try:
            d = json.loads(text)
        except Exception:
            return
        batch = d.get("data") or d.get("content") or d.get("items") or []
        if not batch:
            return
        for it in batch:
            yield it
        if len(batch) < PAGE:
            return
        skip += PAGE

def fetch_spec(art):
    """Fetch + persist the spec for a leaf artifact. Returns the spec filename or None."""
    aid, atype = art["id"], art["type"]
    if atype == "module":
        fname = f"{aid}.module.json"
        path = os.path.join(OUT, "specs", fname)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return fname
        status, text = get(f"/metadata/modules/{urllib.parse.quote(str(aid))}")
        if status >= 400 or status == 0 or not text.strip():
            return None
        with open(path, "w") as f:
            f.write(text)
        return fname
    if atype in ("report", "reportview"):
        fname = f"{aid}.report.xml"
        path = os.path.join(OUT, "specs", fname)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return fname
        status, text = get(f"/objects/{urllib.parse.quote(str(aid))}?fields=specification")
        if status >= 400 or status == 0:
            return None
        try:
            o = (json.loads(text).get("data") or [{}])[0]
            spec = o.get("specification") or ""
        except Exception:
            spec = ""
        if not spec.strip():
            return None
        with open(path, "w") as f:
            f.write(spec)
        return fname
    # dashboards / explorations: spec format differs; record but don't deep-score yet
    return None

artifacts = []
counts = {}
seen = set()

def walk(folder_id, path, depth):
    if depth > MAXDEPTH or token_expired[0]:
        return
    for it in items_of(folder_id):
        aid = it.get("id")
        if not aid or aid in seen:
            continue
        seen.add(aid)
        atype = (it.get("type") or "").lower()
        name = it.get("defaultName") or it.get("name") or aid
        owner = it.get("owner")
        if isinstance(owner, list):
            owner = owner[0] if owner else None
        last_run = it.get("modificationTime")  # CA does not expose run/view counts here
        child_path = f"{path}/{name}"
        counts[atype] = counts.get(atype, 0) + 1
        if atype in FOLDER:
            walk(aid, child_path, depth + 1)
        elif atype in LEAF:
            spec_file = fetch_spec({"id": aid, "type": atype})
            artifacts.append({
                "id": aid, "type": atype, "name": name, "path": child_path,
                "owner": owner, "lastRun": last_run, "specFile": spec_file,
            })
        else:
            artifacts.append({
                "id": aid, "type": atype, "name": name, "path": child_path,
                "owner": owner, "lastRun": last_run, "specFile": None,
            })

walk(ROOT, "", 0)

env = {
    "generated_at": datetime.date.today().isoformat(),
    "base": BASE,
    "root": ROOT,
    "by_type": counts,
    "n_artifacts": len(artifacts),
    "n_modules": sum(1 for a in artifacts if a["type"] == "module"),
    "n_reports": sum(1 for a in artifacts if a["type"] in ("report", "reportview")),
}
inv = {"environment": env, "artifacts": artifacts}
if token_expired[0]:
    inv["token_expired"] = True

with open(os.path.join(OUT, "inventory.json"), "w") as f:
    json.dump(inv, f, indent=2)

msg = f"discovered {len(artifacts)} artifacts ({env['n_modules']} modules, {env['n_reports']} reports) -> {OUT}/inventory.json"
if token_expired[0]:
    msg += "  [WARNING: token expired mid-walk — re-auth and re-run to complete; on-disk specs are kept]"
print(msg)
PY
