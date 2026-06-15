# Qlik connection — qlik-cli

Discovery uses **qlik-cli** (official; reaches both the REST API and the Engine/qix
API — the Engine API is required for sheet/chart defs, the data model, and the load
script, which plain REST can't return).

## Install
GitHub release binary (brew tap was empty): download `qlik-Darwin-x86_64.tar.gz`
from `qlik-oss/qlik-cli` releases → `~/.local/bin/qlik` (runs via Rosetta on arm64).

## Auth — context
```bash
# API key (simplest, acts as you):
qlik context create <ctx> --server https://<tenant>.<region>.qlikcloud.com --api-key '<KEY>'
# OR OAuth M2M (service identity):
qlik context create <ctx> --server https://<tenant>… --oauth-client-id <ID> --oauth-client-secret <SECRET>
qlik context use <ctx>
qlik item ls --resourceType app --limit 20   # connectivity check
```
Create an API key under Profile settings → API keys; an M2M OAuth client under
Administration → OAuth (Web client, ✅ Machine-to-machine, consent → **Trusted**).
**Never put the secret in chat — create the context in your own terminal.**

---

## Gotchas — READ / DISCOVER (Phase 1)

1. **M2M visibility:** a plain M2M client is a service identity — it only sees content
   in **spaces it's a member of**, never personal-space apps. If `item ls` is empty,
   grant the client a space role (or move apps to a shared space).
2. **M2M reload:** a plain M2M client **cannot reload** an app that loads via a space
   data-connection — the reload fails `Connector <name> not found` even with a
   producer role (a real-user reload of the same app works). Connection injection
   needs a real-user context. Fix: reload as a real user (UI/API-key context) or use
   an **M2M-impersonation** client. *Discovery/extraction is unaffected — only reload.*

## Gotchas — REPOINT / WRITE-BACK (reload, connection edits, script PUT)

From a live repoint engagement (2026-06-10) — each of these cost real time:

3. **Impersonation tokens expire (~1h) — mint recipe.** An impersonated-user context
   that worked an hour ago starts returning 401s mid-engagement. Re-mint:
   ```bash
   curl -s -X POST "https://<tenant>.<region>.qlikcloud.com/oauth/token" \
     -H 'Content-Type: application/json' \
     -d '{"grant_type":"urn:qlik:oauth:user-impersonation",
          "client_id":"<M2M_IMPERSONATION_CLIENT_ID>","client_secret":"<SECRET>",
          "user_lookup":{"field":"email","value":"<user@company.com>"},
          "scope":"user_default"}'   # -> access_token (short-lived)
   ```
   The OAuth client must have **Allow user impersonation** enabled (admin consent).
4. **`qlik context update` can't rotate the token** — it has no `--api-key`/header
   flag, so a freshly-minted bearer can't be swapped into an existing context. Either
   recreate the context (`qlik context rm <ctx>` + `create`) or edit
   `~/.qlik/contexts.yml` directly (the `headers: Authorization: Bearer …` entry).
5. **`LIB CONNECT` needs the space-qualified name.** When the data connection lives in
   a shared space, `LIB CONNECT TO 'MyConn'` fails ("Connection not found") on reload —
   the load script must reference **`'SpaceName:MyConn'`**. Repointing a script means
   rewriting the LIB CONNECT line with the target space prefix, not just the name.
6. **Dead stored credentials.** A connection can exist, list fine, and still fail every
   reload: its stored credential dies when the owning user is deactivated or the
   warehouse secret rotates. Always smoke-test with a tiny reload after repointing;
   fix by PATCHing the connection with fresh credentials (as a user with access),
   not by debugging the script.
7. **Connection PUT body must echo `qID` + `qEngineObjectID`.** Updating a data
   connection (`PUT /v1/data-connections/{id}`) 400s if you send only the changed
   fields — GET the connection first, mutate, and PUT the **whole object back**
   including `qID` and `qEngineObjectID`.
8. **M2M-bot-owns-the-connection 403 — split the duties.** If the M2M bot owns the
   data connection, an impersonated real user gets **403** trying to update it; and
   (per gotcha 2) the M2M bot can't run the reload. The working split: **update the
   connection as the M2M owner; run the reload as the impersonated user.** Don't try
   to do both legs under one identity.

## Discovery commands
```bash
qlik app script get  -a <appId>              # load script (the data-model source of truth)
qlik app object ls   -a <appId>              # sheets + chart objects (NOT master items)
qlik app object get  <objId> -a <appId>      # full props: qHyperCubeDef / qMeasure / qDim
qlik app eval "Sum(NET_REVENUE)" -a <appId>  # engine eval (read-only) — freshness snapshot
```
Master measures/dimensions aren't listed by `object ls`; read by id with `object get`,
or enumerate via an Engine `MeasureList`/`DimensionList` session object
(`scripts/qlik-discover.py` does all of this, incl. per-sheet cell grids).
