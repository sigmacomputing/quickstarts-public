#!/usr/bin/env python3
"""pbi-freshness.py — SOURCE-FRESHNESS PREFLIGHT for powerbi-to-sigma (bead fmte).

Mirrors qlik-to-sigma's Phase-1.5 freshness preflight. An IMPORT-mode Power BI
semantic model is a frozen snapshot: Sigma queries the LIVE warehouse, so any
parity delta caused by staleness must be called out BEFORE the side-by-side,
not discovered after the numbers look wrong.

Captures, via the cached Power BI token (/tmp/pbiauth/cache.bin — see
reference_powerbi_extraction_no_app):

  1. Refresh history    GET datasets/{id}/refreshes ($top=12) — the last
                        SUCCESSFUL refresh time (staleness clock) AND any
                        FAILED attempts (expired warehouse credentials are the
                        common cause: errorCode ModelRefresh_* + "credentials
                        ... are invalid"). A failing refresh means the snapshot
                        will only get staler — surface it loudly.
  2. Snapshot           a cheap executeQueries per TMSL table:
                        COUNTROWS + MAX(<date col>) (first 2 date columns) —
                        the numbers the Phase-6 warehouse compare classifies
                        against (MATCH / STALE-EXPLAINED / DIVERGENT).

Writes <out> (freshness.json) and prints the human banner. Exit 0 even when
the source is stale/failing (staleness is information, not an error); exit
non-zero only when the freshness data itself could not be fetched.

Usage:
  python3 scripts/pbi-freshness.py \
    --workspace <wsId|me> --dataset <datasetId> \
    [--tmsl /path/model.bim|.tmsl] [--top 12] \
    --out /tmp/pbir/freshness.json

`--workspace me` (or omitted) targets My workspace (no /groups/ segment).
Requires the msal/requests/truststore venv (run.sh bootstraps one; pass the
interpreter explicitly or rely on /tmp/pbiauth/bin/python).
"""
import argparse
import datetime
import json
import os
import sys

import truststore; truststore.inject_into_ssl()  # noqa: E702
import msal
import requests

CACHE = "/tmp/pbiauth/cache.bin"
CLIENT = "ea0616ba-638b-4df5-95b9-636659ae5121"  # well-known PBI public client
SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
CRED_HINTS = ("credential", "expired", "AADSTS", "authentication", "login")


def token():
    cache = msal.SerializableTokenCache()
    if os.path.exists(CACHE):
        cache.deserialize(open(CACHE).read())
    app = msal.PublicClientApplication(
        CLIENT, authority="https://login.microsoftonline.com/organizations",
        token_cache=cache)
    tok = None
    for a in app.get_accounts():
        r = app.acquire_token_silent(SCOPE, account=a)
        if r and "access_token" in r:
            tok = r["access_token"]
            break
    if not tok:
        flow = app.initiate_device_flow(scopes=SCOPE)
        print(">>> " + flow["verification_uri"] + " code " + flow["user_code"],
              file=sys.stderr)
        tok = app.acquire_token_by_device_flow(flow).get("access_token")
    if cache.has_state_changed:
        open(CACHE, "w").write(cache.serialize())
    assert tok, "no Power BI token (device-flow failed?)"
    return tok


def ds_base(ws, ds):
    if not ws or ws.lower() in ("me", "my workspace", "myworkspace"):
        return f"https://api.powerbi.com/v1.0/myorg/datasets/{ds}"
    return f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{ds}"


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def tmsl_tables(path):
    """[(table, [dateCol,...]), ...] from a TMSL model — real tables only."""
    m = json.load(open(path))
    m = m.get("model", m)
    out = []
    for t in m.get("tables", []):
        name = t.get("name", "")
        if name.startswith(("LocalDateTable_", "DateTableTemplate_")):
            continue
        dates = [c["name"] for c in t.get("columns", [])
                 if str(c.get("dataType", "")).lower() == "datetime"
                 and not c.get("isHidden")][:2]
        out.append((name, dates))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="me")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--tmsl", help="model.bim/TMSL — enables the table snapshot")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    tok = token()
    h = {"Authorization": f"Bearer {tok}"}
    base = ds_base(a.workspace, a.dataset)

    # ---- 1. refresh history -------------------------------------------------
    r = requests.get(f"{base}/refreshes?$top={a.top}", headers=h)
    if r.status_code != 200:
        sys.exit(f"refresh history fetch failed: {r.status_code} {r.text[:200]}")
    hist = r.json().get("value", [])
    last_ok = next((e for e in hist if e.get("status") == "Completed"), None)
    last_attempt = hist[0] if hist else None
    failures = [e for e in hist if e.get("status") == "Failed"]

    now = datetime.datetime.now(datetime.timezone.utc)
    stale_days = None
    ok_end = parse_ts(last_ok.get("endTime") or last_ok.get("startTime")) if last_ok else None
    if ok_end:
        stale_days = round((now - ok_end).total_seconds() / 86400, 1)

    def fail_info(e):
        raw = e.get("serviceExceptionJson") or ""
        code = desc = None
        try:
            j = json.loads(raw)
            code, desc = j.get("errorCode"), j.get("errorDescription")
        except (ValueError, TypeError):
            desc = raw[:300] or None
        creds = any(k.lower() in (desc or "").lower() or k.lower() in (code or "").lower()
                    for k in CRED_HINTS)
        return {"endTime": e.get("endTime") or e.get("startTime"),
                "refreshType": e.get("refreshType"),
                "errorCode": code, "errorDescription": desc,
                "credsSuspect": creds}

    fail_meta = [fail_info(e) for e in failures]
    creds_suspect = any(f["credsSuspect"] for f in fail_meta)

    # ---- 2. cheap executeQueries snapshot (rows + max dates per table) ------
    # Fast discovery: the per-table probes are independent — run them on a
    # small pool (4-wide) instead of serially; a 6-table model snapshots in
    # one round-trip's wall time instead of six.
    snapshot = {}
    snapshot_err = None
    if a.tmsl and os.path.exists(a.tmsl):
        from concurrent.futures import ThreadPoolExecutor

        def probe(item):
            table, dates = item
            cols = [f'"rows", COUNTROWS(\'{table}\')']
            cols += [f'"max:{d}", MAX(\'{table}\'[{d}])' for d in dates]
            dax = "EVALUATE ROW(" + ", ".join(cols) + ")"
            try:
                q = requests.post(f"{base}/executeQueries", headers=h, json={
                    "queries": [{"query": dax}],
                    "serializerSettings": {"includeNulls": True}})
                if q.status_code != 200:
                    return table, None, f"{table}: executeQueries {q.status_code} {q.text[:160]}"
                row = q.json()["results"][0]["tables"][0]["rows"][0]
                ent = {"rows": row.get("[rows]"), "maxDates": {}}
                for d in dates:
                    ent["maxDates"][d] = row.get(f"[max:{d}]")
                return table, ent, None
            except Exception as e:  # network/parse — snapshot is best-effort
                return table, None, f"{table}: {e}"

        items = tmsl_tables(a.tmsl)
        with ThreadPoolExecutor(max_workers=min(4, max(1, len(items)))) as ex:
            for table, ent, err in ex.map(probe, items):
                if ent is not None:
                    snapshot[table] = ent
                if err:
                    snapshot_err = err

    fresh = {
        "workspace": a.workspace, "dataset": a.dataset,
        "fetchedAt": now.isoformat(timespec="seconds"),
        "lastSuccessfulRefresh": last_ok and {
            "endTime": last_ok.get("endTime") or last_ok.get("startTime"),
            "refreshType": last_ok.get("refreshType")},
        "staleDays": stale_days,
        "lastAttemptStatus": last_attempt and last_attempt.get("status"),
        "failures": fail_meta,
        "credsSuspect": creds_suspect,
        "snapshot": snapshot,
        "snapshotError": snapshot_err,
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(fresh, open(a.out, "w"), indent=2)

    # ---- banner -------------------------------------------------------------
    print("⏱  SOURCE FRESHNESS (Power BI import model)")
    if last_ok:
        print(f"   dataset last refreshed {fresh['lastSuccessfulRefresh']['endTime']}"
              f" ({stale_days} days ago, {fresh['lastSuccessfulRefresh']['refreshType']})")
    else:
        print("   no successful refresh found in history — snapshot age unknown")
    for f in fail_meta[:2]:
        tag = " — dataset credentials look EXPIRED; the snapshot will only get staler" \
              if f["credsSuspect"] else ""
        print(f"   ⚠ refresh FAILED {f['endTime']} ({f['errorCode']}){tag}")
        if f["errorDescription"]:
            print(f"     {f['errorDescription'][:160]}")
    for t, ent in snapshot.items():
        md = "  ".join(f"max({k})={str(v)[:10]}" for k, v in ent["maxDates"].items() if v)
        print(f"   PBI snapshot: {t} rows={ent['rows']}{('  ' + md) if md else ''}")
    if snapshot_err:
        print(f"   (snapshot partial: {snapshot_err})")
    if stale_days is not None and stale_days >= 1:
        print(f"   → The import snapshot is ~{int(stale_days + 0.5)} day(s) old. Sigma queries the"
              " LIVE warehouse and")
        print("     will show newer data; deltas are classified MATCH / STALE-EXPLAINED /"
              " DIVERGENT at parity.")
    print(f"   freshness.json -> {a.out}")


if __name__ == "__main__":
    main()
