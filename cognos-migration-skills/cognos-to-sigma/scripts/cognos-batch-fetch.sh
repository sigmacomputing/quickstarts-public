#!/usr/bin/env bash
# cognos-batch-fetch.sh — fetch the WHOLE Cognos estate in one hot-session
# window, and serve single-artifact runs from the same disk cache.
#
# WHY: CAoC sessions die in minutes (HTTP 441 — IBMid SSO re-auth + Akamai WAF).
# Walking an estate with one request per agent turn burns a human re-auth cycle
# every few objects. This script instead pulls ALL module + report specs as fast
# as the session allows (parallel curl, capped at 4 — modest bursts only, the
# Akamai WAF throttles aggressive clients), and every fetch lands in a disk
# cache keyed by object id + modificationTime. When the session dies mid-walk
# the run STOPS CLEANLY and a re-run RESUMES — nothing already fetched is
# re-fetched.
#
# Auth (same shape as cognos-discover.sh / get-cognos-session.sh):
#   export COGNOS_BASE="https://<host>/bi/v1"      # /bi/v1, NOT /api/v1
#   export COGNOS_COOKIE="<full Cookie header>"    # incl. Akamai _abck/bm_sz/…
#   export COGNOS_XSRF="<X-XSRF-Token value>"
#
# Usage:
#   cognos-batch-fetch.sh batch [--root <folderId>] [--out <dir>]
#                               [--parallel N] [--rewalk] [--max-depth N] [--page N]
#       Walk the folder tree under --root (default .public_folders), then fetch
#       every module's Data-Module JSON and every report's spec XML, N-wide
#       (default and HARD CAP = 4). Resumable: re-run the same command after a
#       441 and it continues from the manifest + cache.
#
#   cognos-batch-fetch.sh one {module|report} <objectId> [--out <dir>]
#       Single-artifact fetch through the SAME cache: one cheap metadata GET
#       checks modificationTime; unchanged → the cached spec is printed with NO
#       spec re-fetch (1 request instead of a full pull). Changed/missing →
#       fetch, cache, print.
#
# Cache layout (default --out: $COGNOS_CACHE_DIR or ~/.cognos/batch-cache):
#   <out>/manifest.json      the walked tree (artifacts + modificationTime)
#   <out>/cache-index.json   id → {modificationTime, file, fetchedAt}
#   <out>/specs/<id>.module.json | <id>.report.xml
#
# Exit codes: 0 = complete; 4 = SESSION DIED mid-run (resume by re-running);
#             2 = usage / env error.
set -euo pipefail

CMD="${1:-}"; shift || true
ROOT=".public_folders"
OUT="${COGNOS_CACHE_DIR:-$HOME/.cognos/batch-cache}"
PAR=4
PAGE=100
MAXDEPTH=12
REWALK=0
ONE_TYPE=""
ONE_ID=""

case "$CMD" in
  batch) ;;
  one)
    ONE_TYPE="${1:-}"; ONE_ID="${2:-}"; shift 2 || true
    case "$ONE_TYPE" in module|report|reportview) ;; *)
      echo "usage: cognos-batch-fetch.sh one {module|report} <objectId> [--out <dir>]" >&2; exit 2 ;;
    esac ;;
  *)
    echo "usage: cognos-batch-fetch.sh batch [--root <id>] [--out <dir>] [--parallel N] [--rewalk]" >&2
    echo "       cognos-batch-fetch.sh one {module|report} <objectId> [--out <dir>]" >&2
    exit 2 ;;
esac

while [ $# -gt 0 ]; do
  case "$1" in
    --root)      ROOT="$2"; shift 2 ;;
    --out)       OUT="$2"; shift 2 ;;
    --parallel)  PAR="$2"; shift 2 ;;
    --page)      PAGE="$2"; shift 2 ;;
    --max-depth) MAXDEPTH="$2"; shift 2 ;;
    --rewalk)    REWALK=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

: "${COGNOS_BASE:?set COGNOS_BASE (e.g. https://host/bi/v1)}"
: "${COGNOS_COOKIE:?set COGNOS_COOKIE}"
: "${COGNOS_XSRF:?set COGNOS_XSRF}"

if [ "$PAR" -gt 4 ]; then
  echo "WARN: --parallel $PAR clamped to 4 (Akamai WAF — modest bursts only)" >&2
  PAR=4
fi

mkdir -p "$OUT/specs"
export COGNOS_BASE COGNOS_COOKIE COGNOS_XSRF OUT ROOT PAGE MAXDEPTH PAR REWALK CMD ONE_TYPE ONE_ID

python3 - <<'PY'
import datetime
import json
import os
import subprocess
import sys
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

BASE     = os.environ["COGNOS_BASE"]
COOKIE   = os.environ["COGNOS_COOKIE"]
XSRF     = os.environ["COGNOS_XSRF"]
OUT      = os.environ["OUT"]
ROOT     = os.environ["ROOT"]
PAGE     = int(os.environ["PAGE"])
MAXDEPTH = int(os.environ["MAXDEPTH"])
PAR      = int(os.environ["PAR"])
REWALK   = os.environ["REWALK"] == "1"
CMD      = os.environ["CMD"]
ONE_TYPE = os.environ["ONE_TYPE"]
ONE_ID   = os.environ["ONE_ID"]

MANIFEST = os.path.join(OUT, "manifest.json")
INDEX    = os.path.join(OUT, "cache-index.json")
SPECS    = os.path.join(OUT, "specs")

LEAF   = {"module", "report", "reportview"}
FOLDER = {"folder", "package", "myfolders", "namespacefolder"}
DEAD   = {401, 403, 441}  # session death / WAF rejection — stop + resume later

session_dead = threading.Event()
index_lock = threading.Lock()


def get(path):
    """GET <path> (leading slash) via curl. Returns (status, text)."""
    p = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", BASE + path,
         "-H", "Accept: application/json",
         "-H", "X-XSRF-TOKEN: " + XSRF,
         "-H", "X-Requested-With: XMLHttpRequest",
         "-b", COOKIE],
        capture_output=True, text=True)
    body = p.stdout
    nl = body.rfind("\n")
    code, text = (body[nl + 1:].strip(), body[:nl]) if nl >= 0 else ("", body)
    try:
        status = int(code)
    except ValueError:
        status = 0
    if status in DEAD or status == 0:
        session_dead.set()
    return status, text


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def safe_name(aid):
    return urllib.parse.quote(str(aid), safe="")


def cache_fresh(index, art):
    """True when the cached spec for art is present AND modificationTime matches."""
    ent = index.get(art["id"])
    if not ent:
        return False
    if (art.get("modificationTime") or "") != (ent.get("modificationTime") or ""):
        return False
    f = os.path.join(SPECS, ent.get("file") or "")
    return bool(ent.get("file")) and os.path.exists(f) and os.path.getsize(f) > 0


def fetch_spec(art):
    """Fetch one module/report spec. Returns (id, filename|None, err|None)."""
    aid, atype = art["id"], art["type"]
    if session_dead.is_set():
        return aid, None, "skipped (session dead)"
    if atype == "module":
        status, text = get(f"/metadata/modules/{urllib.parse.quote(str(aid))}")
        if session_dead.is_set() or status >= 400 or not text.strip():
            return aid, None, f"HTTP {status}"
        fname = f"{safe_name(aid)}.module.json"
        payload = text
    else:  # report / reportview
        status, text = get(f"/objects/{urllib.parse.quote(str(aid))}?fields=specification")
        if session_dead.is_set() or status >= 400:
            return aid, None, f"HTTP {status}"
        try:
            o = (json.loads(text).get("data") or [{}])[0]
            payload = o.get("specification") or ""
        except Exception:
            payload = ""
        if not payload.strip():
            return aid, None, "empty specification"
        fname = f"{safe_name(aid)}.report.xml"
    with open(os.path.join(SPECS, fname), "w") as f:
        f.write(payload)
    return aid, fname, None


def record(index, art, fname):
    with index_lock:
        index[art["id"]] = {
            "type": art["type"],
            "name": art.get("name"),
            "modificationTime": art.get("modificationTime"),
            "file": fname,
            "fetchedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        save_json(INDEX, index)


# ── one — single artifact through the same cache ─────────────────────────────
if CMD == "one":
    index = load_json(INDEX, {})
    status, text = get(f"/objects/{urllib.parse.quote(ONE_ID)}"
                       "?fields=defaultName,type,modificationTime")
    if status >= 400 or status == 0:
        ent = index.get(ONE_ID) or {}
        cached = os.path.join(SPECS, ent.get("file") or "")
        hint = (f" A cached copy (modificationTime {ent.get('modificationTime')}) exists at"
                f" {cached} — use it only if staleness is acceptable.") if ent.get("file") else ""
        sys.exit(f"SESSION DIED (HTTP {status}) on the metadata check — re-auth "
                 f"(re-copy COGNOS_COOKIE/COGNOS_XSRF) and re-run.{hint}")
    try:
        meta = (json.loads(text).get("data") or [{}])[0]
    except Exception:
        meta = {}
    art = {"id": ONE_ID, "type": ONE_TYPE if ONE_TYPE != "reportview" else "report",
           "name": meta.get("defaultName"),
           "modificationTime": meta.get("modificationTime")}
    if cache_fresh(index, art):
        ent = index[ONE_ID]
        print(f"cache HIT: {ONE_ID} unchanged (modificationTime "
              f"{ent['modificationTime']}) — serving {ent['file']}, no re-fetch", file=sys.stderr)
        with open(os.path.join(SPECS, ent["file"])) as f:
            sys.stdout.write(f.read())
        sys.exit(0)
    aid, fname, err = fetch_spec(art)
    if err:
        if session_dead.is_set():
            sys.exit(f"SESSION DIED ({err}) fetching {ONE_ID} — re-auth and re-run.")
        sys.exit(f"fetch failed for {ONE_ID}: {err}")
    record(index, art, fname)
    print(f"cache MISS: fetched {ONE_ID} -> {fname}", file=sys.stderr)
    with open(os.path.join(SPECS, fname)) as f:
        sys.stdout.write(f.read())
    sys.exit(0)

# ── batch — walk (or reuse manifest), then fetch PAR-wide ────────────────────
manifest = None if REWALK else load_json(MANIFEST, None)
if manifest and manifest.get("root") == ROOT:
    arts = manifest["artifacts"]
    print(f"reusing manifest ({len(arts)} artifacts, walked {manifest.get('walkedAt')}) "
          f"— pass --rewalk to re-list the tree", file=sys.stderr)
else:
    print(f"walking tree under '{ROOT}' …", file=sys.stderr)
    arts, seen = [], set()

    def items_of(folder_id):
        skip = 0
        while not session_dead.is_set():
            q = (f"/objects/{urllib.parse.quote(str(folder_id))}/items"
                 f"?fields=defaultName,type,id,modificationTime&top={PAGE}&skip={skip}")
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
            yield from batch
            if len(batch) < PAGE:
                return
            skip += PAGE

    def walk(folder_id, path, depth):
        if depth > MAXDEPTH or session_dead.is_set():
            return
        for it in items_of(folder_id):
            aid = it.get("id")
            if not aid or aid in seen:
                continue
            seen.add(aid)
            atype = (it.get("type") or "").lower()
            name = it.get("defaultName") or it.get("name") or aid
            if atype in FOLDER:
                walk(aid, f"{path}/{name}", depth + 1)
            elif atype in LEAF:
                arts.append({"id": aid,
                             "type": "report" if atype == "reportview" else atype,
                             "name": name, "path": f"{path}/{name}",
                             "modificationTime": it.get("modificationTime")})

    walk(ROOT, "", 0)
    if session_dead.is_set():
        sys.exit("SESSION DIED during the tree walk — nothing cached yet from this walk. "
                 "Re-auth (re-copy COGNOS_COOKIE/COGNOS_XSRF from a hot browser session) "
                 "and re-run the SAME command.")
    save_json(MANIFEST, {"root": ROOT, "base": BASE,
                         "walkedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "artifacts": arts})
    print(f"manifest: {len(arts)} fetchable artifacts "
          f"({sum(1 for a in arts if a['type'] == 'module')} modules, "
          f"{sum(1 for a in arts if a['type'] == 'report')} reports) -> {MANIFEST}",
          file=sys.stderr)

index = load_json(INDEX, {})
todo = [a for a in arts if not cache_fresh(index, a)]
done_before = len(arts) - len(todo)
if done_before:
    print(f"cache: {done_before}/{len(arts)} already fetched (id+modificationTime match) "
          f"— skipping those", file=sys.stderr)
if not todo:
    print(f"COMPLETE: all {len(arts)} specs cached in {SPECS}", file=sys.stderr)
    sys.exit(0)

print(f"fetching {len(todo)} spec(s) {PAR}-wide …", file=sys.stderr)
fetched, errors = 0, []
with ThreadPoolExecutor(max_workers=PAR) as ex:
    for art, (aid, fname, err) in zip(todo, ex.map(fetch_spec, todo)):
        if fname:
            record(index, art, fname)
            fetched += 1
        elif not session_dead.is_set() and err:
            errors.append((aid, art.get("name"), err))

total_cached = done_before + fetched
if session_dead.is_set():
    print(f"\nSESSION DIED — {total_cached} of {len(arts)} specs fetched "
          f"({fetched} this run). Everything fetched so far is cached in {SPECS}.\n"
          f"Re-auth (re-copy COGNOS_COOKIE/COGNOS_XSRF from a hot browser session) and\n"
          f"re-run the SAME command to RESUME — cached specs are NOT re-fetched.",
          file=sys.stderr)
    sys.exit(4)
for aid, name, err in errors:
    print(f"WARN: {aid} ({name}): {err} — not cached", file=sys.stderr)
print(f"COMPLETE: {total_cached} of {len(arts)} specs cached in {SPECS}"
      + (f" ({len(errors)} non-fatal error(s) above)" if errors else ""), file=sys.stderr)
PY
