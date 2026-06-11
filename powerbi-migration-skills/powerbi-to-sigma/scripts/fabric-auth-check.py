import truststore; truststore.inject_into_ssl()
import sys, json, base64, os, atexit, requests, msal

CACHE = "/tmp/pbiauth/cache.bin"
cache = msal.SerializableTokenCache()
if os.path.exists(CACHE): cache.deserialize(open(CACHE).read())
atexit.register(lambda: open(CACHE, "w").write(cache.serialize()) if cache.has_state_changed else None)

CID = "ea0616ba-638b-4df5-95b9-636659ae5121"
AUTH = "https://login.microsoftonline.com/organizations"
SCOPES = ["https://api.fabric.microsoft.com/.default"]

app = msal.PublicClientApplication(CID, authority=AUTH, token_cache=cache)
res = None
for a in app.get_accounts():
    res = app.acquire_token_silent(SCOPES, account=a)
    if res and "access_token" in res:
        print("[token from cache — no new login needed]", flush=True); break
    res = None
if not res:
    flow = app.initiate_device_flow(scopes=SCOPES)
    print("=" * 56, flush=True)
    print(">>> Go to: " + flow["verification_uri"], flush=True)
    print(">>> Enter code: " + flow["user_code"], flush=True)
    print("=" * 56, flush=True)
    res = app.acquire_token_by_device_flow(flow)
if "access_token" not in res:
    print("AUTH FAIL:", res.get("error"), res.get("error_description", "")[:200], flush=True); sys.exit(1)

tok = res["access_token"]
p = tok.split(".")[1]; p += "=" * (-len(p) % 4)
claims = json.loads(base64.urlsafe_b64decode(p))
scp = claims.get("scp", "") or ""
print("aud :", claims.get("aud"), flush=True)
print("scp :", scp, flush=True)
print("WRITE_SCOPE_PRESENT:", ("ReadWrite" in scp or "Item.ReadWrite" in scp), flush=True)

r = requests.get("https://api.fabric.microsoft.com/v1/workspaces", headers={"Authorization": f"Bearer {tok}"})
print("--- workspaces (capacityId set = on Fabric capacity, writable via API) ---", flush=True)
for w in r.json().get("value", []):
    print(f"  WS {w['id']} | {w.get('displayName')} | capacityId={w.get('capacityId')}", flush=True)
