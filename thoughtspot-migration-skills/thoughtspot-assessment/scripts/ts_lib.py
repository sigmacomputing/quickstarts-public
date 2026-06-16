#!/usr/bin/env python3
"""ThoughtSpot REST v2 helpers for the thoughtspot-to-sigma skill.

Auth: export TS_HOST + TS_TOKEN (a bearer token). On an SSO trial with no local
password, get a token by visiting `${TS_HOST}/api/rest/2.0/auth/session/token`
in the browser tab where you're logged in, or via Develop > REST Playground.
For a service identity, enable Trusted Auth (Develop > Customizations >
Security Settings) and POST username+secret_key to auth/token/full.
"""
import json, os, ssl, urllib.request, urllib.error

HOST = os.environ.get("TS_HOST", "").rstrip("/")
TOKEN = os.environ.get("TS_TOKEN", "")
# Trials often sit behind corp TLS interception whose CA Python won't verify
# (curl uses the system store and works). Use an unverified context.
_SSL = ssl._create_unverified_context()


def _req(path, body=None, method="POST"):
    url = f"{HOST}/api/rest/2.0/{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        raw = urllib.request.urlopen(r, context=_SSL).read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"TS {method} {path} -> {e.code}: {e.read().decode()[:400]}")
    # TML export embeds raw control chars in the JSON string values
    return json.loads(raw, strict=False) if raw.strip() else None


def whoami():
    return _req("auth/session/user", method="GET")


def search(mtype, record_size=200):
    """List metadata of a type: LOGICAL_TABLE | LIVEBOARD | ANSWER | CONNECTION."""
    return _req("metadata/search", {"metadata": [{"type": mtype}], "record_size": record_size})


def export_tml(identifier, mtype="LIVEBOARD"):
    """Export one object's TML (YAML string). Returns (edoc, error_or_None)."""
    d = _req("metadata/tml/export", {"metadata": [{"identifier": identifier, "type": mtype}],
                                     "export_fqn": True, "edoc_format": "YAML"})
    it = d[0]
    st = it.get("info", {}).get("status", {})
    if st.get("status_code") == "ERROR":
        return None, st.get("error_message", "")[:120]
    return it.get("edoc"), None


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
