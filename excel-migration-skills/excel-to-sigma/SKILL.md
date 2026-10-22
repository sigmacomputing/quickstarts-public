---
name: excel-to-sigma
description: >-
  Convert an Excel (.xlsx) workbook — especially a planning / budget / forecast
  data-entry model — into a Sigma data model + workbook. Use when the user has
  an Excel file (formal Tables, pivots, charts, or a cell-formula budget model)
  and wants to recreate it in Sigma. Covers formal-Table discovery, Excel-formula
  translation, and the input-table → warehouse-view → data-model pattern that
  preserves data entry. Requires Sigma client credentials and (for the data-entry
  half) a write-enabled Sigma connection.
---

# Excel → Sigma Conversion

> **STATUS: input-table data-entry path VALIDATED end-to-end (2026-06-08).** The
> full chain — Excel formal Table → Sigma input table → warehouse view → data
> model reading `FROM` that view → section rollups — was proven with **exact
> parity** on a representative 540-row forecast model. The read/output half (DM +
> workbook from a landed seed) was validated earlier (2026-06-03). The discovery
> + formula-translation layer is designed and spiked, not yet a general one-shot
> converter; the cell-drawn actuals + driver-growth forecast archetype is the
> exception (router, plan drafter, builder with source-bound local parity; shapes
> outside it fail loudly). Complex-workbook support means **inventory + explicit
> routing + parity**, not a promise that arbitrary Excel programs convert automatically.

**Start here — do not read every ref.** Run the router first; it picks the archetype
and names the refs, decisions and commands for this workbook:

```bash
python scripts/migrate.py plan <file.xlsx|.xlsm> --out-dir <workdir>
```

It runs the audit, discovery and (for macro files) macro classification, writes
`migration-audit.json`, `discovery.json` and `review.template.json` to `<workdir>`,
and prints JSON: `auditStatus`, `archetype`, `readRefs`, `beforePost`, `askUser`,
`nextCommands`, `userHandoffs`, `routeReason`. Exit code 2 means `BLOCKED`. Read the refs
it lists, ask the user the `askUser` questions, then run the `nextCommands` in order.
`forecast` is named only when the plan drafter accepts the workbook's shape; a
SUMIFS/driver workbook it rejects routes to `cell-model` (source inventory, then a
source-specific Sigma MCP build) with the drafter's reason in `routeReason`.

| When | Read |
|---|---|
| Always | `refs/sigma-build-gotchas.md` — SQL element formula prefix, DM POST envelope, `contents` lifecycle, id reassignment, publish gate |
| Before `--post` or declaring completion | `refs/coverage-contract.md` — the fail-loud contract and hard completion gates |
| Formal Table to input table (the data-entry path) | `refs/input-tables.md` (the source-swap goes through a warehouse view, not a direct DM binding), `refs/excel-translation.md` |
| Cell-drawn planning / forecast model (no formal Table) | `refs/model-taxonomy.md`, `refs/forecast-recipes.md` |
| Broker / FactSet research model, or a fleet off one template | `refs/research-recipes.md`, `refs/research-template-coa.md` |
| `.xlsm` / macros | `refs/macro-handling.md` |
| Charts, validation, conditional formatting, formats to rebuild | `refs/presentation-migration.md`; `refs/generic-source-presentation.md` for the generic presentation inventory |
| Live Sigma API capability questions (Actions, Python, procedures) | `refs/code-rep-capabilities.md` |
| Source cell/formula inventory or formula-level native calculations | `refs/source-workbook-model.md`, `refs/workbook-expression-context.md`, `refs/source-inputs-and-reshape.md`, `refs/native-calculations.md` |

**Maintainer-only — skip for a customer migration.** These document fixture
acceptance machinery and reviewed canary packets, not the migration path:
`refs/acceptance-and-promotion.md`, `refs/forecast-scenario.md`,
`refs/forecast-snapshot.md`, `refs/custom-ports.md`, `refs/source-blank-validation.md`,
`refs/regional-grouped-canary.md`. Read one only when the user names that
workflow or you are changing it.

**Draft vs production.** Builds without `--post` are *draft mode*: local specs and
a local parity check, with audit review issues reported as pending
(`DRAFT MODE: review pending for ...`) instead of blocking. `--post` is
*production*: it keeps the full source-bound `--review-dispositions` contract
(Phase 0). `BLOCKED` stops both. Never fabricate `verified: true` to get past a
draft; draft mode exists so you do not need to.

**UI steps.** When the work reaches a step only the user can do in the Sigma UI
(CSV paste, Publish, Create warehouse view), collect every pending UI action into
one checklist, give it to the user, and stop. Do not interleave them.

The `sigma-workbooks` companion skill, if installed, plus the Sigma OpenAPI, is the
canonical workbook spec; find it through the agent's skill loader, and use
`refs/sigma-build-gotchas.md` when it is unavailable.

---

## The one big idea

Excel planning models are **data-entry tools**, not dashboards. Forecasters type
numbers into budget sheets; formulas roll them into an income statement. The
faithful Sigma translation keeps that data entry alive — which is exactly what
**input tables** are for.

The decisive structural insight (validated): in well-structured enterprise
workbooks, the value lives in **formal Excel Tables** at a tidy grain. Most of the
thousands of `INDEX/MATCH/SUMIFS` formulas are **wide→long reshaping**, not
business logic — they *evaporate* when the data lands at that grain in a Sigma DM.
What's left ("report" sheets drawn in cells) is rebuilt by hand, same as any
migration.

So the migration is two halves:

1. **Read / output half** — the formal Table(s) become DM elements; the income-
   statement SUMIFS become grouped DM metrics + workbook charts. (Build against a
   seed first; see `refs/excel-translation.md`.)
2. **Data-entry half** — the formal Table that forecasters edit becomes a Sigma
   **input table**; the DM re-points to read from it. (See `refs/input-tables.md`.)

---

## Preserve the inputs — never ship a read-only port

**A spreadsheet is an app people type into. If the conversion is read-only, you've
demoted it.** Don't default every table to a read-only DM element. Classify each
source table by *how it's used* and route accordingly:

| Source table is… | → Sigma | Editable? |
|---|---|---|
| **Entered** (users type values: budget inputs, a tracker, subscriptions) | **input table** (empty / CSV / linked) | ✅ like Excel/Sheets |
| **Derived** (formula rollups: the income statement, SUMIFS summaries) | read-only DM element + metrics | ❌ recomputes |
| **Reference dim** (lookup lists users maintain) | input table if maintained, else read-only | depends |
| **Mixed** (literal source columns beside formula columns, or literal overrides within formulas) | route literal cells and live calculations separately; review overrides and edit intent | depends |

Phase 0 records literal and formula provenance by column and cell. Route an
all-literal table as a candidate input source and an all-formula table as a
computed candidate. A mixed Table is not wholly derived or wholly editable:
retain its literal inputs and calculate its formula columns live. Ask how users
edit ambiguous cells before selecting the input surface.

### What's actually buildable via API today (validated 2026-06-10 by MCP query)

> **Hard-won correction.** Earlier drafts claimed linked input tables were the
> "powerful path, fully API, no seed." **That was wrong — validated only by
> structure (`/elements`), never by querying the data.** A linked input table
> authored through workbook code representation has **inherited columns that don't
> resolve** — every row shows **"multiple values"** (publish doesn't fix it;
> re-POSTing a known-good UI-built spec reproduces the break). The linked-column
> key-correlation is state the REST spec can't carry. Sigma MCP exposes a
> dedicated linked-input-table constructor, but validate that path separately. See
> `refs/input-tables.md`.

So, honestly, by usage pattern:

| Need | API today? | How |
|---|---|---|
| **Edit-in-place of the migrated rows** (the common spreadsheet case) | ✅ with Sigma MCP Code Mode | create the empty input-table **structure** with REST, then pre-query and seed it through MCP `InputTable.upsert_rows()`; `update_rows()` targets returned/system row IDs. UI CSV remains the fallback. |
| **Net-new entry at a grain** (blank forecast grid) | ⚠️ path-dependent | REST linked-off-spine creation leaves context columns as "multiple values"; UI works. MCP exposes `add_linked_input_table()`, but validate create/read/update end to end before shipping it. |
| **Augment / annotate existing rows** (notes/flags beside live data) | ⚠️ path-dependent | needs working linked columns; use UI or a separately verified MCP linked-table build |

REST can scaffold input-table *structure* and build read-only DMs. Sigma MCP
Code Mode can seed and update rows in an existing empty input table; it is a
separate connector capability and is not invoked by this skill's CLI. Working
linked context columns and warehouse-view creation still require UI/live review.

Design so the editable surfaces exist from day one, and seed them through MCP or
the UI. **Don't build a read-only model and call it a migration.**

---

## Prerequisites

### Sigma access
```bash
# neutral cred file written by the sigma-migration setup (see refs/input-tables.md)
bash -c 'source ~/.sigma-migration/env; TOKEN=$(curl -s -X POST "$SIGMA_BASE_URL/v2/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=$SIGMA_CLIENT_ID&client_secret=$SIGMA_CLIENT_SECRET" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)[\"access_token\"])"); <cmd>'
```
The **data-entry half requires a write-enabled connection** (input tables write
back to a `SIGDS_` schema). Confirm via `GET /v2/connections` → `writeAccess: true`.
Verified write connection on tj-wells-1989: `cb2f5180-…` (Snowflake ymb68310).

### Python
From this skill directory, install its pinned dependencies:
`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

### Optional: `snow` CLI
Used only to look up the **full path** of a Sigma-created warehouse view
(`SIGMA_WRITE_DB.<schema>.<view>`) when the UI truncates it. SSO browser-auth;
`snow sql -c default --format json -q "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME FROM <DB>.INFORMATION_SCHEMA.VIEWS WHERE TABLE_NAME ILIKE '<view>%'"`.

---

## Phase 0 — Audit, then discover

The capability audit is a hard gate before conversion:

```bash
python scripts/audit-xlsx.py <file.xlsx|file.xlsm> --out migration-audit.json
python scripts/audit-openapi.py --out sigma-code-rep-audit.json
```

`AUTO` can proceed. `REVIEW_REQUIRED` is reported, not fatal: `audit-xlsx.py` exits 0
for it (pass `--strict` to exit 1 in a production gate) and exits 2 for `BLOCKED`.
Local/draft builds proceed with the review issues pending; every issue must be
routed, implemented, and verified before `--post` or declaring the migration
complete. `BLOCKED` cannot proceed until its blocker is removed. Then run
`scripts/xlsx-discover.py` for the model/grain-specific report (`migrate.py plan`
runs both).

For a source-bound cell, table, and formula-dependency inventory, run
`python scripts/source-workbook.py SOURCE.xlsx --out source-model.json` and read
`refs/source-workbook-model.md`. This offline inventory preserves unresolved
formulas explicitly; it does not approve a migration or change the audit and
production-write gates.

The whole-workbook Excel migration entrypoints—standalone canonical inference,
batch conversion, the direct research-workbook builder, and the source-bound
forecast/research plan builders—re-run this audit against the source bytes.
Production (`--post`, and batch conversion) requires, for `REVIEW_REQUIRED`,
`--review-dispositions review.json`; the only accepted format is source-bound and
issue-specific (`migrate.py plan` writes a `review.template.json` to fill in).
Local forecast/research plan builds without `--post`, and `infer-canonical-formulas.py` /
`build-research-workbook.py` with the opt-in `--draft` flag, run in draft mode and
only report the pending codes:

```json
{
  "sourceSha256": "<64 lowercase hex characters>",
  "issues": [
    {
      "code": "CHARTS_PRESENT",
      "owner": "Named migration owner",
      "disposition": "Implemented as Sigma chart and render-checked",
      "verified": true
    }
  ]
}
```

Every reported issue code needs a nonempty owner and disposition plus
`verified: true`. The hash must match the workbook currently being converted;
copying a review record to a changed workbook fails. A disposition never
overrides `BLOCKED`.

Walk the `.xlsx` (OOXML = a ZIP of XML; `openpyxl` reads it). Produce an inventory:

- **Formal Tables** (`xl/tables/*.xml`) — name, sheet, range, columns. These are
  the migration's Rosetta Stone: each is a DM-element / input-table candidate.
- **Pivots, charts, slicers** — count + anchor; map to `pivot-table` / chart /
  control later.
- **Formula census** — tally functions; flag the untranslatable (`OFFSET`,
  `INDIRECT`, volatile locators) and the "report drawn in cells" sheets.
- **Degenerate-column warnings** — constant / decayed columns (broken fiscal
  defaults, stale lookup spines). **Derive these, don't port them.**

State the inventory back to the user and confirm the **canonical grain** of the
fact Table before building.

### Phase 0b — Macro inventory & disposition gate (if `.xlsm`/`.xlsb`/`.xls`)

If the file is macro-enabled, run the macro pass **before building** — a dropped
macro is a silent loss of behavior (see `refs/macro-handling.md`):

```bash
python scripts/macro-classify.py <file.xlsm>          # report
python scripts/macro-classify.py --json <file.xlsm>   # contract for build steps
```

Each procedure is classified (olevba-extracted VBA) and routed: **AUTO**,
**CONTROL**, **ACTION**, **STORED_PROC**, **PYTHON_REVIEW**, **DATA_REVIEW**, or
**FLAG**. Actions, Python, and stored procedures are now code-representable, but
still require implementation plus live side-effect/parity checks. Surface every
non-AUTO record before build. Never silently omit a macro.

### Phase 0c — Model map & intent (for "report drawn in cells" / planning models)

For a cell-drawn report, `xlsx-discover.py` inventories **ACTUAL** aggregations,
**DRIVER_GROWTH**, **MANUAL** literals among formulas, **DEPENDENCY_LINK** direct
cell references, and other **DERIVED** formulas. A direct reference such as
`13WCF!C7 = B23` is a live link to the prior week's ending cash; preserve its
source cell in the plan and recompute it. Do not replace it with a flat constant
or a cached formula result. A flat forecast is a separate, explicit policy that
needs source evidence; the syntax `=prior` alone does not prove one.

**Forecast path:** `migrate.py plan` -> `draft-forecast-plan.py` -> dry-run
`build-forecast-model.py` -> `build-forecast-model.py --post`. The drafter derives the
plan from the workbook, fails loudly on any shape it does not recognise (sheet, month
row, sections, a mixed or unparsable forecast row, missing GL columns), and recomputes
every line-month and GL month against Excel's cached values before writing it. It
raises `FLAT_CARRY_POLICY` for `=prior` lines; the dry run reports it as pending and
`--post` needs a source-bound disposition. The builder's local parity check compares
the plan to `parityTargets` and exits 1 on any mismatch. Workbook line charts whose
series are Total Revenue / Gross Profit / EBITDA / Net Income by month or quarter are
recorded as `sourceCharts` (every point checked against cached values) and the builder
emits a matching Sigma line chart; the drafter lists any other chart as not mapped, to
rebuild by hand before dispositioning `CHARTS_PRESENT`.

Present the detected map and confirm edit intent, source freshness, and formula
dependencies before selecting a build. The live-actuals/driver-growth union in
`refs/forecast-recipes.md` applies only when those source roles and grain are
present. Archetype builders have source binding **and shape preconditions**:
unknown sheets, tables, sections, or periods require source-specific MCP
construction or explicit review. Never coerce them into the bundled fixture
profile or freeze formulas merely to reproduce baseline values. Verify live
calculations and source-bound parity before calling a migration complete.

### Phase 0d — Template-family fingerprint & routing (financial-statement models)

Before choosing a build path, **fingerprint the file** (see `refs/research-template-coa.md`):
a **broker/FactSet equity-research model** (line-items down rows, YEARS across columns, sections
like PROFIT AND LOSS / PER SHARE DATA / BALANCE SHEET; often `__FDSCACHE__` + thousands of named
ranges) routes to the **research archetype**, NOT the FP&A forecast path:

```bash
python scripts/infer-canonical-formulas.py <file.xlsx> --sheet="FY results" \
       --first-row=7 --last-row=<end> --out plan.json --draft
python scripts/build-research-model.py plan.json --conn <writeConn> --folder <id>   # dry run
python scripts/build-research-model.py plan.json --conn <writeConn> --folder <id> \
       --review-dispositions review.json --post
```

The standalone inference CLI runs the source gate before parsing formulas; `--draft`
reports pending review issues instead of failing (it is strict by default). Use the
same source-bound review file for production inference and build. `infer-canonical-formulas.py` then extracts
the hard-coded grid + one canonical formula per derived line, records the absolute source
path and SHA256, breaks plug-cycles, and identifies
formula cells that need a cached-value fallback. Cached fallbacks can preserve displayed
values, but they are not a completed live-formula migration: any nonzero `parity.frozen`
adds `CACHED_FORMULA_FALLBACK` and requires its own source-bound disposition.
`build-research-model.py` verifies the saved source identity and gate before it writes local
specs or authenticates, then posts the DM (data page) + workbook (computation + transpose + pivot).
Use `--source <file.xlsx>` when a plan moved and its saved path no longer resolves; the
file must still match the plan's `sourceSha256`.

**For a fleet of similar files off one template** (the ~850-file case), use
`scripts/batch-convert.py` — it fingerprints, maps each file's line items to a canonical
chart-of-accounts (`refs/research-template-coa.md` + `coa.json`), converts, parity-gates, and
emits a **triage manifest** (AUTO_PARITY / NEEDS_REVIEW / BLOCKED / FAILED), including
the full audit status/issues and source SHA256, with no silent truncation. `--post-review`
does not bypass the gate; reviewed files need `--review-dispositions` (a JSON file for one
source or a directory containing `<sourceSha256>.json` for a batch).
Read `refs/research-template-coa.md` first. Everything else (a cell-drawn P&L with a data tab,
SUMIFS actuals, driver growth) stays on the FP&A path below.

## Phase 1 — Pick the grain & extract the seed (`scripts/xlsx-to-input-csv.py`)

For the fact Table, emit a **paste-ready CSV** with:
- **only the data-entry columns**, headers in `UPPER_SNAKE_CASE` matching the
  Sigma input-table column names exactly (so a clipboard paste aligns 1:1),
- **no system columns** — `Row ID` / `Created at|by` / `Last updated at|by`
  auto-populate in Sigma; including them breaks the paste.

Parse Excel date serials → ISO dates here.

## Phase 2 — Build the read/output DM (against a seed) + reuse-check

Before POSTing a new DM, check whether an existing Sigma data model already
covers the same grain (same formal-Table columns / warehouse view). Prefer
reusing or extending that DM over spawning another copy. When no match, land
the seed (inline `VALUES` custom-SQL for ≤~1k rows; PUT-to-stage + COPY INTO for
larger) and POST the DM (fact + dim elements + relationships + a flattened
`*_REPORT` join element for grouping).

**Post-DM readback (hard gate):** after `POST /v2/dataModels/spec`, GET the
live spec and map server-assigned element/column ids before any workbook build
(`build-forecast-model.py` / `build-research-model.py` already do this via
`map_dm*`). Never trust authored ids past the POST. Full build rules in
`refs/sigma-build-gotchas.md`.

## Phase 3 — Stand up the input table (`scripts/build-input-table-wb.py`)

Build the **empty input-table structure via REST**; seed rows through Sigma MCP
Code Mode when connected, or load them through the UI. See
`refs/input-tables.md`.

**Empty input table (API for structure).** POST an **empty input-table element** at
the fact grain (`source: { kind: empty, connectionId: <write-conn> }`,
`inputMode: explore`, data columns + system columns
`ID/CREATED_AT/CREATED_BY/UPDATED_AT/UPDATED_BY`). Then either pre-query the live
element and seed missing natural keys with MCP `InputTable.upsert_rows()`, or use
the UI to **paste / upload** the Phase-1 CSV and **Publish**. Finally use
**Warehouse views → Create new** in the UI.

> **Do NOT auto-build linked input tables via the spec.** It looks like it works
> (the POST succeeds, `/elements` shows the columns) but the **inherited columns
> resolve to "multiple values"** — the REST spec omits the linked correlation
> state (validated
> 2026-06-10, publish doesn't fix it). `build-input-table-wb.py --linked` only
> scaffolds the PK/grain + entry columns. If a usage pattern needs live context
> columns beside editable cells, use the established UI path or validate MCP
> `add_linked_input_table()` create/read/update behavior end to end.

## Phase 4 — Source-swap the DM onto the view (`scripts/build-dm-on-view.py`)

Re-point (or build) the DM's fact element to `SELECT … FROM <warehouse view>` on
the write connection. Display names stay identical, so the workbook + metrics are
unchanged. This is **API**. Verify the section rollups hit the same parity targets
as Phase 2.

## Phase 5 — Build / repoint the workbook, layout last, parity

Build the dashboard pages (Forecast Summary pivot + KPIs, trend charts) per
the `sigma-workbooks` companion skill when available, sourced from the DM. Builders author a nested
`pages[].elements` draft; **`scripts/lib/workbook_wire.py` assembles layout XML
as the last write**, then wraps via `code_rep` into
`{ name, folderId, contents: { schemaVersion, kind, pages, elements, layout } }`.
Live builders first validate with `POST /v2/workbooks` + `dryRun: true`, then
create through the same endpoint. Data-model specs stay unwrapped.

Confirm every element compiles and the totals tie out (parity hard gate —
Phase 0c/0d source-bound live evaluation, Phase 2/4 section rollups, research
`batch-convert.py` AUTO_PARITY bucket). Never skip the parity comparison.

### Security: RLS / CLS

Excel workbooks have no native row-/column-level security construct to port —
access control is file-share / workbook-protection only. Detect workbook
password protection / sheet protection during Phase 0 and note it for the
customer; do not invent Sigma RLS from spreadsheet structure. If the landed
warehouse tables already carry RLS policies outside Excel, leave those to the
warehouse / Sigma admin — this skill does not apply RLS automatically.

---

## Scriptability matrix (OpenAPI re-audited 2026-10)

| Step | Path |
|---|---|
| workbook create/validate/update | ✅ `POST /v2/workbooks` (`dryRun` then create), `PUT .../contents` |
| input-table **structure** (columns/types; title, style, sort) | ✅ code representation |
| input validation (literal/range/dynamic-list/file constraints) | ✅ code representation |
| **linked** input table (inherited columns resolve) | ⚠️ REST spec POST yields "multiple values"; UI works; MCP `add_linked_input_table()` exists but was not validated in the 2026-10-15 empty-table seed regression |
| seed **records inside REST workbook code representation** | ❌ records are excluded from the spec |
| seed/update rows in an existing input table | ✅ Sigma MCP Code Mode `build_workbook` with `InputTable.upsert_rows()` / `update_rows()`; pre-query natural keys because inserts do not deduplicate them automatically |
| **Publish** for UI edits | ⚠️ UI; MCP row writes persisted and were immediately queryable in the 2026-10-15 regression, while published-mode UI permissions remain untested |
| **warehouse view** on the input table | ⚠️ UI only |
| DM **source-swap** to `FROM <view>` | ✅ API (DM spec PUT/POST) |
| read/output DM + workbook build | ✅ API |
| API/writeback/navigation/stored-procedure actions | ✅ code representation; runtime-test every effect |
| Python computation | ✅ `code` + `code-output`; package/runtime + parity gate |
| scheduled/webhook automated action | ✅ limited document surface; ownership/failure review |
| column protection / broader admin policy | ⚠️ UI/admin policy |

For a REST-created empty input table, query it with the MCP companion tools, run
`scripts/input-sync.py architecture --workflow ...` for the one source workflow,
then `stage` with the output plan, exact source, named
approval, and target bindings. Emit construction/native joins only from the
approved manifest/receipt. After querying assigned IDs, re-stage those bindings
and run `plan` to reconcile typed natural keys. Review its Code Mode chunks,
execute through MCP, and query/read back again. The CLI never queries or mutates
MCP itself. `complete` requires all workflow-specific target, checkpoint,
edit/restore, persistence, and table evidence. Each table readback must report
the exact approved row count and typed `naturalKeys`; missing, extra, or
same-count substituted keys block completion. Otherwise hand off
CSV/clipboard import and **Publish**. In either path,
**Create warehouse view** remains an explicit UI hand-off. Linked mode remains
live-review until an end-to-end MCP create/read/update/query regression proves
inherited columns work.

`stage` audits the exact source bytes and always refuses `BLOCKED` or blocker
severity. Pending review issues may be built in the isolated test workspace
with explicit staging approval; this does not assert verified dispositions.
Approval includes the existing source/plan hashes, named `owner` and `reviewer`,
all formula `reviewItems`, exact architecture `mappedFeatures` and
`targetBindings`, plus `sourceReviewApproval`:

```json
{"status": "approved_for_staging", "issues": ["replace with the exact full audited issue objects"]}
```

Obtain the issue objects from `migration_gate.gate_plan_staging_source(plan,
source_arg=source, plan_path=plan_path)[1]["issues"]` and review their complete
scope. Omitted or changed issues fail approval. Finalize connection, folder,
input `editMode`, and all logical architecture before hashing the manifest;
rebuild and reapprove if the plan changes. The receipt reports
`APPROVED_STAGING`, `PENDING_STAGING`, `pendingSourceIssues`, and
`sourceReviewRequirements` (each full issue plus its `issueHash`). Cached or
unresolved formula mappings still cannot stage. Production `--post` source
gates retain their strict verified-disposition contract.

Record Task 2 component readback/edit/restore checks as evidence JSON while
source-feature work is pending; defer `complete` until the later workflow
acceptance gate. Global completion re-audits the source and requires exact
`manifest.sourceReviewEvidence` coverage, independent of the receipt. Each
record needs `code`, `issueHash`, `status: "passed"`, a real `evidenceId`,
`sourceHash`, `planHash`, `targetDocumentId`, `targetVersion`, `targetId`, and
`targetBinding` with actual document/version/element and optional column/check
IDs. `targetId` must match that binding. These are recorded runtime checks,
never synthesized from staging approval; chart rendering, validation behavior,
and formatting parity remain pending until actually tested.

---

## What this skill does NOT do (yet)

- One-shot `.xlsx` → finished migration. Phase 0–1 (discovery + formula
  translation) is spiked, not a hardened converter. The data-entry path (Phase
  3–4) is fully validated.
- Power Query / ODBC / SharePoint-Online source pipelines are detected and
  routed, but not automatically recreated. Land them as governed warehouse or
  connector sources and verify refresh/data parity.
- `.xlsm` / VBA / macros — **detected + classified + routed** (Phase 0b,
  `scripts/macro-classify.py` + `refs/macro-handling.md`); never blindly
  executed. Representable routes include Actions, Python, and stored procedures,
  but each still needs implementation and live verification.

See `refs/excel-translation.md` for the full converter-build design and the
~60–70% pipeline reuse from `tableau-to-sigma`.
