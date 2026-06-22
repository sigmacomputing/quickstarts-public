# MicroStrategy (Strategy One) REST API — verified behaviors & gotchas

Everything below was verified live on a Strategy One 2026 cloud trial during the
validated end-to-end migration. `scripts/mstr.py` bakes the session/changeset
mechanics in; this doc is the why.

## Auth & plumbing

- **Login**: `POST /api/auth/login` `{username, password, loginMode: 1}` →
  session token in the `X-MSTR-AuthToken` **response header** + cookies. Send
  both on every call, plus `X-MSTR-ProjectID` for project-scoped endpoints.
  There is **no API-key concept** — sessions only.
- **OpenAPI**: the full spec is served by the instance itself at
  `GET /api/openapi.json` (~6 MB). The hosted docs URL serves a stub — trust
  the instance.
- **Response headers matter**: several flows return required handles only as
  response headers (see report saving below). `mstr.py` exposes them as
  `session.last_headers`, **lowercased** (e.g. `x-mstr-ms-instance`).
- **Python 3.13+ TLS**: some MicroStrategy cloud CA certs lack the key-usage
  extension; Python 3.13+ rejects them under `VERIFY_X509_STRICT` (on by
  default — curl accepts the same cert). `mstr.py` clears only that flag and
  keeps verification on.

## Datasources

- `GET /api/dbmss` can be **404** on current builds — use `GET /api/gateways`;
  a gateway id **works as the dbms id** in `POST /api/datasources`
  (e.g. Snowflake gateway, `dbType: snow_flake`).
- Creating a warehouse datasource is a **trio**:
  1. `POST /api/datasources/logins` (username/password)
  2. `POST /api/datasources/connections` (connectionString + `database.type` +
     login id) — test first via `POST /api/datasources/connections/test`
     (accepts an inline login)
  3. `POST /api/datasources` (dbms + connection id)
  then attach to a project:
  `PATCH /api/projects/{id}/datasources`
  `{"operationList":[{"op":"add","path":"/id","value":"<dsId>"}]}`.
- On cloud trials, **JDBC connection strings work where ODBC driver names all
  fail** (`IM002`), e.g.
  `JDBC;DRIVER=net.snowflake.client.jdbc.SnowflakeDriver;URL={jdbc:snowflake://<account>.snowflakecomputing.com/?...};`

## Changesets (schema edits)

- Creating/editing **tables, attributes, facts, metrics** requires a changeset:
  `POST /api/model/changesets?schemaEdit=true` → use the returned id as the
  `X-MSTR-MS-Changeset` header on each modeling call → commit. `mstr.py`'s
  `schema_edit(fn)` wraps create/commit/abort.
- **A failed call inside a changeset dangles the schema lock** ("Schema
  editing is in use by another user") unless you `DELETE` the changeset.
  If a lock is already stuck: `DELETE /api/model/schema/lock`.
- Objects created in an **uncommitted** changeset are **not name-resolvable by
  later calls in the same changeset** — compound metrics that reference newly
  created base metrics need a **second changeset** after committing the first.
- Attribute/fact form-expression `tables` entries **require**
  `subType: "logical_table"`.
- Metric formulas accept **one token carrying the whole formula text**
  (`Sum([Net Revenue]) {~}`, `Count<Distinct=True>([Order Id Fact]) {~}`) —
  the server tokenizes it.
- After schema changes, reload with a **required body**:
  `POST /api/model/schema/reload`
  `{"updateTypes":["table_key","entry_level","logical_size","clear_element_cache"]}`.

## Hierarchy relationships

- `PUT /api/model/systemHierarchy/attributes/{id}/relationships` requires an
  explicit `child` ref **alongside** `parent`, else a 500 NPE
  (`getJointChild`).
- **The PUT REPLACES the attribute's entire parent list.** Writing one new
  relationship silently drops existing ones — GET the current relationships
  and merge before every write.

## Reports (the dossier datasets)

- **Reports do NOT use changesets** — the header is rejected.
- `POST /api/model/reports` only **stages in-memory** (the response's
  `versionId` is all zeros and the object is NOT in metadata yet). Persist via
  `POST /api/model/reports/{id}/instances/save` with the `X-MSTR-MS-Instance`
  header taken from the **creation response header** (lowercase
  `x-mstr-ms-instance` via `session.last_headers`).
- The save body needs `dataSource.dataTemplate.units` mirroring
  `grid.viewTemplate`.
- **Execution**: `POST /api/v2/reports/{id}/instances?limit=N` returns data
  directly; the `sqlView` endpoint on an instance exposes the generated
  warehouse SQL + the Analytical Engine steps (essential for parity debugging
  — see `ae-row-collapse.md`).

## Dossiers

- **Extraction**: `GET /api/v2/dossiers/{id}/definition` returns
  `{datasets, chapters[].pages[]}`. Walk each page's `visualizations` **and**
  `panelStacks[].panels[]` **recursively** — panels nest further `panelStacks`
  — plus free-form `fields` (images / text boxes), or you silently miss
  content. Non-dossier documents 404/error on this endpoint (useful as a
  dossier-vs-document probe).
- **Per-viz definition is shallow**: a visualization exposes ONLY
  `visualizationType` + `definition.grid` (`rows` / `columns` / `metrics` /
  `crossTab` / `metricsPosition`). There is no slot/encoding detail beyond the
  grid — the converter maps `visualizationType` → Sigma chart kind via lookup
  with a flagged-table fallback (see `viz-type-mapping.md`).
- **Authoring is REST-hostile**: `POST /api/dossiers/instances`
  `{objects:[{id, type:3}]}` wraps reports into an in-memory dossier (returns
  `mid`); save via `POST /api/documents/{id}/instances/{mid}/saveAs` — but the
  flow is **session-bound** (create + saveAs must share one auth session). The
  public manipulations API supports ONLY `setFilter` / `setCurrentPanel`; viz
  types can't be set via REST (UI only). Chart-rich fixtures must be authored
  in the Library UI (see `../fixtures/BUILD_SPEC.md`).

## Roadmap: the newer "Data Model" object

Strategy One also ships a **newer Data Model object**
(`/api/model/dataModels`) that is **fully REST-authorable** — including
`securityFilters`, publish, and `connect_live`. The validated converter targets
the classic schema path (attributes/facts/metrics + reports + dossiers); the
Data Model object is not yet exercised and is the natural next extraction
source (and the RLS port surface). Tracked as roadmap in `design-notes.md`.
