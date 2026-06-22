# Strategy One "Data Models" (Mosaic) — extraction + authoring, live-validated

Strategy One has a newer semantic-layer object alongside the classic project
schema: the **Data Model** (subType `report_emma_cube`, "Mosaic model").
Customers on current versions may model in these instead of classic
attributes/facts. Both paths are handled; this doc covers the Data Model side.
Everything below was validated live (build + query, exact parity vs the
classic-schema fixture: same 19/19 Region×Category cells).

## Why it matters for migration
- Maps almost 1:1 to a Sigma data model: tables + key-joined star +
  metrics, with `dataServeMode: connect_live` (live warehouse SQL — same
  execution model as Sigma) or `in_memory` (cube — migrate as the underlying
  tables, not the cache).
- Has `securityFilters` (RLS) with member assignment — extractable via
  `GET /api/dataModels/{id}/securityFilters` (+ `/members`).

## Extraction (converter input)
`extract_datamodel.py <dataModelId>` → `datamodel_definition.json`:
dataModel info + tables (with token expressions) + attributes + factMetrics +
metrics + hierarchy + per-attribute relationships + links. See
`fixtures/datamodel_definition.json` for the shape.
- Joins are NOT in `/links` — in-model star joins are classic-style
  **shared multi-table key attributes** (e.g. Store ID = `STORE_KEY`@dim +
  `ORDER_STORE_KEY`@fact). Derive Sigma joins exactly like the classic path.
- `/links` is **cross-data-model linking only** ("target objects must come
  from different Mosaic models"); also the only GET that requires an
  `X-MSTR-MS-Changeset` header.
- Query for parity: `POST /api/v2/cubes/{dmId}/instances` — synchronous,
  data inline in the response. Do NOT poll `.../instances/{iid}/status`
  (500s for connect_live instances).

## Authoring (fixture building) — flow that works
`build_datamodel.py` (phased: core|metrics|query|all; state in
`datamodel_ids.json`):
1. dataServer pipeline first, NO changeset: `POST /api/dataServer/workspaces`
   → `.../pipelines` → `.../pipelines/{pid}/tables` with
   `importSource:{type:"single_table", dataSourceId, namespace, tableName}`
   (the data server introspects warehouse columns itself). Workspaces are
   session-bound — never reuse across logins (401 "trusted communication").
2. ONE `schemaEdit=false` changeset: create DM (+ `destinationFolderId` —
   enforced at COMMIT, not POST) → add tables with
   `physicalTable:{pipeline:"<stringified pipeline JSON>"}` (classic logical
   tables are rejected: "not from pipeline") → attributes → relationships →
   factMetrics → commit. An EMPTY DM cannot commit; DM + tables share the
   changeset. Inline `attributes`/`factMetrics` in the table POST are
   silently ignored — use the dedicated endpoints. `isKeyForm` on a form is
   rejected; key is the attribute-level `keyForm:{name:'ID'}`.
3. Second changeset for metrics (one-token formula text, e.g.
   `Sum([NET_REVENUE]) {~}`; distinct count via `function:"count"` +
   `functionProperties:[{name:"Distinct", value:{type:"boolean", value:"true"}}]`).
4. No `/model/schema/reload` needed; connect_live DMs have NO publish
   workflow (`POST /api/dataModels/{id}/publish` → 400 — skip it).
