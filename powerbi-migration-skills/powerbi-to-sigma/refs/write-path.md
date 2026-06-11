# Authoring INTO Power BI — Fabric write-path recipe

Validated 2026-05-31: deployed `fixture_06_kitchen_sink` (20 complex-DAX measures + a calculated table) as a LIVE semantic model + bound report in the `Test` workspace, verified via round-trip, temp items cleaned up. This is the reverse of Phases 1–2; same device-code token (`user_impersonation` covers writes — see `connection.md`). Requires a Fabric-capacity workspace.

## Semantic model — create
- `POST https://api.fabric.microsoft.com/v1/workspaces/{ws}/semanticModels`
  body: `{ "displayName": "...", "definition": { "parts": [ {path, payload:<base64>, payloadType:"InlineBase64"}, ... ] } }`
- **Minimal part set that works:** `definition.pbism` + `model.bim`. (`.platform` is optional — Fabric generates it; including it is also accepted.)
- `definition.pbism` content:
  `{"$schema":"https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json","version":"4.2","settings":{}}`
- **LRO:** returns **202** + `Location` (`*.analysis.windows.net/v1/operations/{id}`) + `Retry-After`. Poll `Location` until `status:Succeeded`, then `GET {Location}/result` → `{id,...}`. **Bad content still returns 202** — failures only surface on poll as `status:Failed` with `error.errorCode`.

## ⚠️ Calculated-table columns gotcha (converter recipe note)
A TMSL **calculated table** (e.g. a DAX `DimDate`) fails create with `RequiredOptionsMissing`/`InferredName` errors if its columns are written as ordinary data columns. Each calculated-table column MUST be:
`{ "type": "calculatedTableColumn", "isNameInferred": true, "isDataTypeInferred": true }`
(NOT `sourceColumn` + `isDataTypeInferred`). Any converter/generator emitting calc tables to TMSL for Fabric write must mark columns this way.

## Verify
`POST .../semanticModels/{id}/getDefinition?format=TMSL` (also 202→poll→`/result`), base64-decode the `model.bim` part, diff measures/tables.

## Report — create (PBIR, live-bound to a separate model)
- `POST .../reports`, parts:
  - `definition.pbir` (version `4.0`) with
    `datasetReference.byConnection = {pbiModelVirtualServerName:"sobe_wowvirtualserver", pbiModelDatabaseName:"<semanticModel id>", name:"EntityDataSource", connectionType:"pbiServiceXmlaStyleLive"}` — this is how you bind a report to a separate model item.
  - `definition/version.json` (`version:"2.0.0"`) — **required**, else `Cannot find file 'version.json'`.
  - `definition/report.json` (1.0.0 schema) — **requires** `layoutOptimization` and `themeCollection`; `themeCollection.baseTheme` requires `name` + `reportVersionAtImport` + `type:"SharedResources"`. Do NOT put `reportVersionAtImport`/`type`/`layoutOptimization` at the report root (they belong on the theme).
  - `definition/pages/pages.json`, `definition/pages/{page}/page.json`, `definition/pages/{page}/visuals/{vid}/visual.json`.

## Adding/editing visuals (PBIR `updateDefinition`) — validated 9-visual build
- `POST .../reports/{id}/updateDefinition` with the FULL parts set (existing + new); 202 LRO. Re-fetch confirmed the service strips nothing — visualType + bindings round-trip.
- **Key fact:** `page.json`/`pages.json` do NOT track a visual list — visuals are discovered purely by the `pages/{page}/visuals/{id}/visual.json` folder layout, so **adding a visual = adding a folder**. Live-binding is held by `datasetReference.byConnection` in `definition.pbir`.
- Each `visual.json` (schema `…/visualContainer/1.0.0`): `{name, position:{x,y,z,width,height,tabOrder}, visual:{visualType, query.queryState}}`. Only the queryState *role* + Measure-vs-Column varies per type:
  - **Measure projection:** `{"field":{"Measure":{"Expression":{"SourceRef":{"Entity":"<table>"}},"Property":"<measure>"}},"queryRef":"<table>.<measure>","nativeQueryRef":"<measure>"}` — measures are referenced by their HOME table entity. **Column projection:** same with `"Column"`.
  - `card` → `Values`; `clusteredColumnChart`/`clusteredBarChart`/`lineChart` → `Category` (column) + `Y` (measures); `tableEx` → `Values` (cols+measures in order); `pivotTable` → `Rows` (column) + `Values` (measures).

## Load data — bind credentials + refresh (else all measures = "(Blank)")
An API-created import model has **no credentials and has never refreshed** → every measure is blank. Validated fix (Snowflake key-pair):
1. `GET https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{id}/datasources` (Power BI-audience token) → `datasourceId` + gateway cluster id; cloud source has `isOnPremGatewayRequired:false`, initial `credentialType:NotSpecified`.
2. **Bind via the legacy Update Datasource route** (NOT Fabric `/v1/connections` — that returned `InvalidCredentialDetails` for the PersonalCloud connection):
   `PATCH https://api.powerbi.com/v1.0/myorg/gateways/{gatewayCluster}/datasources/{datasourceId}` with `credentialType:"KeyPair"`, `encryptedConnection:"Encrypted"`, **`encryptionAlgorithm:"NONE"`** (no RSA-OAEP gateway-key wrapping needed for this cloud source), and `credentials` JSON `credentialData`: `username` (the Snowflake user, e.g. `TJ@SIGMACOMPUTING.COM`), `privateKey` (full PKCS#8 PEM), and **`passphrase:""`** — the `passphrase` property MUST be present even for an unencrypted key (omitting → `Property name: passphrase ... null value`).
3. `POST .../datasets/{id}/refreshes {"notifyOption":"NoNotification"}` → 202; poll `GET .../refreshes?$top=1` to `status:"Completed"` (~7s).
4. Verify: `executeQueries` `EVALUATE ROW("h",[Headcount])` → real number (got `363`).
Note: a successful refresh means the model's `rsa_key.pub` is already registered on the Snowflake user (`ALTER USER … SET RSA_PUBLIC_KEY=…`); if refresh fails auth, register it first.

## Validated artifacts (Test ws `269a33d0-98c4-476f-890d-612ea8072f9a`)
- Semantic model `049863fa-5500-4d45-a541-1478799a760c` — 20/20 measures, DimDate calc table, 5 relationships intact (RANKX/TOTALYTD/SAMEPERIODLASTYEAR confirmed).
- Report `0bebf272-45db-466e-ae93-522c6c9c9999` — bound to the model.
