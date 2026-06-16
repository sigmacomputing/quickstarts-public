#!/usr/bin/env python3
"""ThoughtSpot REST v2 helpers for the thoughtspot-to-sigma skill.

Auth: export TS_HOST + TS_TOKEN (a bearer token). On an SSO trial with no local
password, get a token by visiting `${TS_HOST}/api/rest/2.0/auth/session/token`
in the browser tab where you're logged in, or via Develop > REST Playground.
For a service identity, enable Trusted Auth (Develop > Customizations >
Security Settings) and POST username+secret_key to auth/token/full.

SCALE NOTES (2026-06-11, for 20-40+ liveboard estates):
  - One persistent keep-alive HTTPS connection PER THREAD (http.client) instead
    of a fresh TLS handshake per request — TS Cloud handshakes cost ~0.3-0.5s
    each, which dominates header-only calls.
  - dependents(model_id): server-side dependency lookup (metadata/search with
    include_dependent_objects) — returns ONLY the liveboards/answers that read
    the model, so callers export N candidate TMLs instead of every liveboard
    in the org. VERIFIED LIVE against team2.thoughtspot.cloud (13 candidates
    of 33 org liveboards for the Retail Analytics worksheet).
  - export_tml_many(): ThreadPool(4) parallel TML export with a DISK CACHE
    keyed (metadata_id, modified-epoch-ms) — re-runs and multi-liveboard
    migrations skip unchanged exports entirely (hit/miss logged).
"""
import http.client, json, os, ssl, threading, urllib.parse

HOST = os.environ.get("TS_HOST", "").rstrip("/")
TOKEN = os.environ.get("TS_TOKEN", "")
# Trials often sit behind corp TLS interception whose CA Python won't verify
# (curl uses the system store and works). Use an unverified context.
_SSL = ssl._create_unverified_context()
_TL = threading.local()      # one persistent keep-alive connection per thread


def _conn():
    c = getattr(_TL, "conn", None)
    if c is None:
        netloc = urllib.parse.urlparse(HOST).netloc
        c = http.client.HTTPSConnection(netloc, context=_SSL, timeout=120)
        _TL.conn = c
    return c


def _req(path, body=None, method="POST"):
    payload = json.dumps(body) if body is not None else None
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
               "Accept": "application/json",
               # http.client sends NO default User-Agent and the TS Cloud edge
               # (WAF) answers UA-less requests with an HTML 403 — keep one.
               "User-Agent": "thoughtspot-to-sigma/1.0"}
    last = None
    for attempt in (0, 1):                  # one transparent retry on a dropped keep-alive
        c = _conn()
        try:
            c.request(method, f"/api/rest/2.0/{path}", body=payload, headers=headers)
            r = c.getresponse()
            raw = r.read().decode()
        except (http.client.HTTPException, OSError) as e:
            try:
                c.close()
            finally:
                _TL.conn = None
            last = e
            continue
        if r.status >= 400:
            raise RuntimeError(f"TS {method} {path} -> {r.status}: {raw[:400]}")
        # TML export embeds raw control chars in the JSON string values
        return json.loads(raw, strict=False) if raw.strip() else None
    raise RuntimeError(f"TS {method} {path} -> connection failed twice: {last}")


def whoami():
    return _req("auth/session/user", method="GET")


def search(mtype, record_size=200):
    """List metadata of a type: LOGICAL_TABLE | LIVEBOARD | ANSWER | CONNECTION."""
    return _req("metadata/search", {"metadata": [{"type": mtype}], "record_size": record_size})


def search_headers(mtype, record_size=200):
    """HEADERS-ONLY listing — id/name/modified per object, NO TML export.
    The O(1)-per-object call estate-scale code paths list with; only confirmed
    candidates get the expensive tml/export."""
    out = []
    for x in search(mtype, record_size):
        h = x.get("metadata_header") or {}
        out.append({"id": x.get("metadata_id"), "name": x.get("metadata_name"),
                    "modified": h.get("modified")})  # epoch-ms; cache key component
    return out


def dependents(model_id, types=("PINBOARD_ANSWER_BOOK",), record_size=200):
    """Server-side dependency lookup: the liveboards (PINBOARD_ANSWER_BOOK) /
    answers (QUESTION_ANSWER_BOOK) that READ a model — so callers never export
    the whole org's TML to find them. Returns [{id, name, modified}] (deduped)
    or None when the API yields nothing usable (caller falls back to the
    export-all-then-grep path and says so).
    VERIFIED LIVE 2026-06-11 (team2.thoughtspot.cloud, REST v2 metadata/search
    + include_dependent_objects on the LOGICAL_TABLE identifier)."""
    try:
        d = _req("metadata/search",
                 {"metadata": [{"identifier": model_id, "type": "LOGICAL_TABLE"}],
                  "include_dependent_objects": True,
                  "dependent_objects_record_size": record_size})
    except Exception:
        return None
    if not d:
        return None
    dep = d[0].get("dependent_objects")
    if dep is None:                      # older TS builds: field absent/null
        return None
    seen, out = set(), []
    for _table_guid, by_type in dep.items():
        for t, items in (by_type or {}).items():
            if t not in types:
                continue
            for it in items or []:
                if it.get("id") and it["id"] not in seen:
                    seen.add(it["id"])
                    out.append({"id": it["id"], "name": it.get("name"),
                                "modified": it.get("modified")})
    return out


def export_tml(identifier, mtype="LIVEBOARD"):
    """Export one object's TML (YAML string). Returns (edoc, error_or_None)."""
    d = _req("metadata/tml/export", {"metadata": [{"identifier": identifier, "type": mtype}],
                                     "export_fqn": True, "edoc_format": "YAML"})
    it = d[0]
    st = it.get("info", {}).get("status", {})
    if st.get("status_code") == "ERROR":
        return None, st.get("error_message", "")[:120]
    return it.get("edoc"), None


def _cache_dir():
    d = os.environ.get("TS_TML_CACHE") or os.path.expanduser("~/.sigma-migration/ts-tml-cache")
    os.makedirs(d, exist_ok=True)
    return d


def export_tml_many(items, mtype="LIVEBOARD", pool=4, use_cache=True, log=print):
    """Parallel TML export with a disk cache.

    items: [{id, name, modified}] (search_headers()/dependents() shape).
    Cache key = (metadata_id, modified epoch-ms) — a re-export can only differ
    if the object was modified, so an id+modified hit is exact, and a stale
    entry is unreachable (its key includes the old stamp). Returns
    [(item, edoc_or_None, err_or_None)] in input order; logs hits/misses."""
    from concurrent.futures import ThreadPoolExecutor
    cdir = _cache_dir() if use_cache else None
    hit_ids = []                                  # list.append is thread-safe

    def one(it):
        cpath = None
        if cdir and it.get("id") and it.get("modified"):
            cpath = os.path.join(cdir, f"{it['id']}.{it['modified']}.tml")
            if os.path.exists(cpath):
                hit_ids.append(it["id"])
                return it, open(cpath).read(), None
        edoc, err = export_tml(it["id"], mtype)
        if edoc and cpath:
            tmp = f"{cpath}.tmp.{os.getpid()}.{threading.get_ident()}"
            with open(tmp, "w") as f:
                f.write(edoc)
            os.replace(tmp, cpath)
        return it, edoc, err

    if not items:
        return []
    with ThreadPoolExecutor(max_workers=max(1, pool)) as ex:
        res = list(ex.map(one, items))
    if cdir:
        log(f"  TML cache: {len(hit_ids)} hit(s), {len(items) - len(hit_ids)} miss(es) ({cdir})")
    return res


def import_tml(tml_str, policy="ALL_OR_NONE", create_new=True):
    """Import a TML string. Returns the response dict (status + header)."""
    d = _req("metadata/tml/import", {"metadata_tmls": [tml_str],
                                     "import_policy": policy, "create_new": create_new})
    return d[0]["response"]


def searchdata(query_string, model_id, record_size=200):
    """Run a TML search against a model. Returns {column_names, data_rows}."""
    d = _req("searchdata", {"query_string": query_string, "logical_table_identifier": model_id,
                            "data_format": "COMPACT", "record_size": record_size})
    return d["contents"][0]


if __name__ == "__main__":
    u = whoami()
    print("Connected as", u.get("name"), "| org", u.get("current_org", {}).get("name"))
    for t in ("LOGICAL_TABLE", "LIVEBOARD", "ANSWER", "CONNECTION"):
        try:
            print(f"  {t}: {len(search(t))}")
        except Exception as e:
            print(f"  {t}: err {e}")
