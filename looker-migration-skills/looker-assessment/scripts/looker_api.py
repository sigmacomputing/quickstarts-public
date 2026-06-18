#!/usr/bin/env python3
"""Minimal Looker API 4.0 client driven by ~/.looker/looker.ini (no SDK dep).

Usage:
  python3 looker_api.py whoami
  python3 looker_api.py get  /connections
  python3 looker_api.py post /connections '<json>'
  python3 looker_api.py put  /connections/<name>/test
  python3 looker_api.py raw  GET /lookml_models
"""
import json
import os
import sys
import threading
import urllib.parse
import urllib.request
from configparser import ConfigParser

INI = os.path.expanduser("~/.looker/looker.ini")

# In-process token cache (same pattern as fetch_looker_dashboard.get._cache):
# login ONCE per process instead of once per call() — Looker bearers live ~1h,
# so for a multi-call run (parity fetches, estate walks) this removes a full
# network round-trip per call. call() retries once with a fresh login on 401.
# DEV-WORKSPACE CAVEAT: caching keeps ONE session across calls, which is what
# dev-workspace flows REQUIRE (`PATCH /session {workspace_id: dev}` only sticks
# within a session) — but a forced re-login (the 401 retry, or login(force=True))
# starts a NEW session that resets the workspace to production; re-PATCH after.
_token_lock = threading.Lock()
_token_cache = {}  # base_url -> access_token


def _cfg():
    c = ConfigParser()
    c.read(INI)
    s = c["Looker"]
    base = s["base_url"].rstrip("/")
    if not base.endswith("/api/4.0"):
        base = base + "/api/4.0"
    return base, s["client_id"], s["client_secret"], s.getboolean("verify_ssl", True)


def _ctx(verify):
    import ssl
    if verify:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def login(force=False):
    """Return (base, token, verify), reusing the per-process cached token.

    force=True mints a fresh token (NEW Looker session — see the dev-workspace
    caveat above). Thread-safe: parallel callers share one login.
    """
    base, cid, csec, verify = _cfg()
    with _token_lock:
        if not force and base in _token_cache:
            return base, _token_cache[base], verify
        data = urllib.parse.urlencode({"client_id": cid, "client_secret": csec}).encode()
        req = urllib.request.Request(base + "/login", data=data, method="POST")
        with urllib.request.urlopen(req, context=_ctx(verify), timeout=30) as r:
            tok = json.load(r)["access_token"]
        _token_cache[base] = tok
    return base, tok, verify


def call(method, path, body=None, _retry=True):
    base, tok, verify = login()
    if not path.startswith("/"):
        path = "/" + path
    url = base + path
    data = None
    headers = {"Authorization": "Bearer " + tok}
    if body is not None:
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=_ctx(verify), timeout=60) as r:
            raw = r.read().decode()
            code = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        code = e.code
    if code == 401 and _retry:
        # cached token expired (~1h TTL) — re-login once and retry.
        login(force=True)
        return call(method, path, body, _retry=False)
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = raw
    return code, parsed


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "whoami"
    if cmd == "whoami":
        code, me = call("GET", "/user")
        _, roles = call("GET", "/user/roles")
        _, perms = call("GET", "/user/roles")  # placeholder
        print("HTTP", code)
        print("user:", me.get("display_name"), "| id", me.get("id"), "|", me.get("email"))
        if isinstance(roles, list):
            print("roles:", ", ".join(r.get("name", "?") for r in roles))
        else:
            print("roles raw:", roles)
    elif cmd == "raw":
        code, out = call(sys.argv[2].upper(), sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
        print("HTTP", code)
        print(json.dumps(out, indent=2)[:6000])
    else:  # get/post/put/patch/delete
        code, out = call(cmd.upper(), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        print("HTTP", code)
        print(json.dumps(out, indent=2)[:8000] if not isinstance(out, str) else out[:8000])
