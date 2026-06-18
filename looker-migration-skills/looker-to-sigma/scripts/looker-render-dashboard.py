#!/usr/bin/env python3
"""looker-render-dashboard.py — render a LIVE Looker dashboard to PNG via the
Looker render API, for Phase 4 SOURCE-vs-MIGRATED side-by-side visual QA.

Pairs with sigma-export-png.py: render the Looker SOURCE dashboard here and the
migrated Sigma workbook there, then eyeball them together to catch layout /
chart-kind / formatting drift a numeric parity check can't see.

Flow (Looker API 4.0):
  POST /render_tasks/dashboards/{id}/png?width=&height=  {body: {dashboard_style,...}}
       -> {id: <task_id>, status: "created"|"enqueued_for_query"...}
  GET  /render_tasks/{task_id}                            poll until status=="success"
       (status "failure" -> bail with the task's status_detail)
  GET  /render_tasks/{task_id}/results                    -> raw PNG bytes

Reuses looker_api.py's ~/.looker/looker.ini auth (fresh login per call). The
render endpoints return binary, so this fetches the bytes directly rather than
through looker_api.call() (which json-decodes).

Usage:
  python3 looker-render-dashboard.py <dashboard_id> [out.png] [--w 1200 --h 1600]
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# Reuse the looker.ini auth + login from the sibling client.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import looker_api  # noqa: E402


def _req(method, url, tok, verify, body=None, accept=None):
    """Raw request returning (status, bytes, content_type). No json decode."""
    data = None
    headers = {"Authorization": "Bearer " + tok}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=looker_api._ctx(verify), timeout=120) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "")


def render(dashboard_id, out_path, width, height, fmt="png", timeout_s=180):
    base, tok, verify = looker_api.login()

    # 1. kick off the render task
    create_url = (f"{base}/render_tasks/dashboards/{dashboard_id}/{fmt}"
                  f"?width={width}&height={height}")
    code, raw, _ = _req("POST", create_url, tok, verify,
                        body={"dashboard_style": "tiled"})
    if code not in (200, 201):
        sys.exit(f"render create POST {code}: {raw[:400].decode('utf-8', 'replace')}")
    task = json.loads(raw.decode())
    task_id = task.get("id")
    if not task_id:
        sys.exit(f"no render task id in response: {raw[:400].decode('utf-8','replace')}")
    print(f"[looker] render task {task_id} created (dashboard {dashboard_id})")

    # 2. poll the task until success (re-login each poll: looker_api logs in fresh,
    #    and a render can outlive a single short-lived bearer)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        base, tok, verify = looker_api.login()
        code, raw, _ = _req("GET", f"{base}/render_tasks/{task_id}", tok, verify)
        if code != 200:
            sys.exit(f"render poll GET {code}: {raw[:400].decode('utf-8','replace')}")
        st = json.loads(raw.decode())
        status = st.get("status")
        if status == "success":
            break
        if status == "failure":
            sys.exit(f"render failed: {st.get('status_detail') or st}")
        time.sleep(3)
    else:
        sys.exit(f"render task {task_id} did not finish within {timeout_s}s")

    # 3. download the rendered bytes
    base, tok, verify = looker_api.login()
    code, content, ct = _req("GET", f"{base}/render_tasks/{task_id}/results",
                             tok, verify, accept="image/png")
    if code != 200 or not content:
        sys.exit(f"render results GET {code} ({ct}): {content[:400].decode('utf-8','replace')}")
    with open(out_path, "wb") as f:
        f.write(content)
    print(f"[looker] {len(content)} bytes -> {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dashboard_id")
    ap.add_argument("out", nargs="?", default=None,
                    help="output PNG path (default: /tmp/looker-dashboard-<id>.png)")
    ap.add_argument("--w", type=int, default=1200, help="render width px")
    ap.add_argument("--h", type=int, default=1600, help="render height px")
    a = ap.parse_args()
    out = a.out or f"/tmp/looker-dashboard-{a.dashboard_id}.png"
    render(a.dashboard_id, out, a.w, a.h)


if __name__ == "__main__":
    main()
