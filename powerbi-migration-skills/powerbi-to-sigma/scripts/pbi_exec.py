import truststore; truststore.inject_into_ssl()
import sys, os, json, msal, requests
CACHE="/tmp/pbiauth/cache.bin"
cache=msal.SerializableTokenCache()
if os.path.exists(CACHE): cache.deserialize(open(CACHE).read())
app=msal.PublicClientApplication("ea0616ba-638b-4df5-95b9-636659ae5121",
    authority="https://login.microsoftonline.com/organizations", token_cache=cache)
SCOPE=["https://analysis.windows.net/powerbi/api/.default"]
tok=None
for a in app.get_accounts():
    r=app.acquire_token_silent(SCOPE, account=a)
    if r and "access_token" in r: tok=r["access_token"]; break
if not tok:
    flow=app.initiate_device_flow(scopes=SCOPE)
    print(">>> "+flow["verification_uri"]+" code "+flow["user_code"], file=sys.stderr)
    tok=app.acquire_token_by_device_flow(flow).get("access_token")
if cache.has_state_changed: open(CACHE,"w").write(cache.serialize())
assert tok, "no powerbi token"
WS, DS = sys.argv[1], sys.argv[2]
spec=json.load(sys.stdin)   # {name:{dax,dim_col,val_col}}
# "me" / "My workspace" datasets live outside any group (no /groups/ segment).
if WS.lower() in ("me", "myorg", "my workspace", "myworkspace"):
    URL=f"https://api.powerbi.com/v1.0/myorg/datasets/{DS}/executeQueries"
else:
    URL=f"https://api.powerbi.com/v1.0/myorg/groups/{WS}/datasets/{DS}/executeQueries"
out={}
for name, q in spec.items():
    r=requests.post(URL, headers={"Authorization":f"Bearer {tok}"},
        json={"queries":[{"query":q["dax"]}],"serializerSettings":{"includeNulls":True}})
    if r.status_code!=200:
        out[name]={"error":r.text[:300]}; continue
    rows=r.json()["results"][0]["tables"][0]["rows"]
    dim, val = q.get("dim_col"), q.get("val_col")
    pairs=[]
    for row in rows:
        d = "" if not dim else row.get(dim)
        v = row.get(val) if val else None
        pairs.append([d, v])
    out[name]=pairs
json.dump(out, sys.stdout)
