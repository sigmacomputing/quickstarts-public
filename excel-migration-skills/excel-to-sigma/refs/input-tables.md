# Input tables — the data-entry half (VALIDATED 2026-10-15)

This is the part that was blocked until input tables shipped. Empty-table MCP
seeding, updates, and downstream recalculation are live-verified with exact
parity. UI publish, warehouse-view creation, and MCP-created linked tables were
not tested in that regression. Read this before building the data-entry path.

## The mental model that matters

An Excel planning model is a **data-entry tool**. The faithful Sigma translation
keeps forecasters typing numbers — that's what input tables are for. But input
tables are **not** a data-model source kind. They are **workbook/document
elements** that write back to the warehouse, and the data model reads that
written-back data **through a warehouse view**.

```
Excel formal Table (forecasters type ForecastAmount)
      │  migrate the grain + values
      ▼
Sigma input table  (workbook element: kind: input-table, source.kind: empty)
      │  Sigma writes back on PUBLISH → SIGDS_-prefixed table (NOT directly queryable)
      ▼
Warehouse view on the input table   (UI: "Warehouse views → Create new")
      │
      ▼
Data model element  →  source: SELECT … FROM <database>.<schema>.<view>
      │
      ▼
Workbook charts / metrics  (unchanged — display names identical)
```

> **The original "flip the DM source to the input table, one line" plan was
> WRONG.** The swap targets a *warehouse view of* the input table. That adds one
> (UI) step the naive plan didn't account for. Everything else holds.

## The REST-vs-MCP-vs-UI split (the single most important fact)

OpenAPI re-audited 2026-10; linked behavior retains the 2026-06 live warning:

| Step | Path | Notes |
|---|---|---|
| input-table **structure** | ✅ code rep — `POST /v2/workbooks` | columns, types, title, style, sort; validate first with `dryRun:true`. |
| literal/range/dynamic-list/file **validation** | ✅ code rep | `values`, `valuesFrom`, inclusive `range`, and file constraints. Custom Excel validation formulas still need review. |
| **linked** input table (inherited columns resolve) | ⚠️ path-dependent | REST spec creation historically yielded inherited columns showing **"multiple values"** (publish did not fix; verified 2026-06-10). Sigma MCP Code Mode now exposes `add_linked_input_table()`, but this run did not validate create/read/update behavior. Use the established UI path or run an end-to-end MCP regression before shipping. |
| seed/update **rows** in an existing input table | ✅ **Sigma MCP Code Mode** | `build_workbook` with `InputTable.upsert_rows()` / `update_rows()`; verified live 2026-10-15. This is an MCP capability, not a REST endpoint or a feature of the CLI scripts in this skill. Query first: `upsert_rows()` does not enforce a natural-key uniqueness constraint. |
| seed **records inside REST workbook code representation** | ❌ REST | records remain excluded from the workbook spec. Create the structure with REST, then seed through MCP or the UI. |
| UI CSV/clipboard seed | ✅ UI | still available when MCP is not connected. |
| **Publish** for UI edits | ⚠️ UI | UI draft/publish behavior remains a separate workflow. MCP-seeded rows were immediately queryable in the live 2026-10-15 check; published UI permissions were not tested. |
| **warehouse view** | ⚠️ **UI only** | input-table element → Warehouse views → Create new |
| DM **source-swap** | ✅ API — `POST`/`PUT /v2/dataModels/spec` | `SELECT … FROM <view>` |
| data-entry mode | ✅ code rep | required `inputMode`: `edit` (draft editors), `explore` (published explore/edit), or `view` (published view/explore/edit). Test sharing and write permission live. |

So a converter can auto-build the input-table **structure** and the **DM-on-view**,
then seed an existing input table through Sigma MCP Code Mode. The REST builder
does not seed rows by itself, and warehouse-view creation remains a UI step.
(`swapSources` exists on dataModels but swaps between *registered sources*, not
to an ad-hoc input-table view.)

## Input-table element spec shape (proven)

```yaml
- id: forecastInput
  kind: input-table
  name: Forecast Entry          # element TITLE — persists in the spec & round-trips on GET
  source:
    kind: empty
    connectionId: cb2f5180-…    # MUST be a write-enabled connection (writeAccess: true)
  inputMode: explore            # published Explore/Edit users can enter data
  tableStyle: { preset: presentation }   # optional — tableStyle + sort round-trip too
  columns:
    - id: REGION                # data-entry columns: give a `type`
      type: text
    - id: MONTH_DATE
      type: datetime
    - id: CATEGORY_CODE
      type: number
    - id: FORECAST_AMOUNT
      type: number
    - id: ID                    # system columns: NO `type` — Sigma auto-manages them
    - id: CREATED_AT
    - id: CREATED_BY
    - id: UPDATED_AT
    - id: UPDATED_BY
```

- A write-enabled connection is required (`GET /v2/connections` → `writeAccess: true`).
- Column types: `text`, `number`, `datetime`, `checkbox`, `multi-select`, `file`.
- Data-entry columns may author literal `values`, `valuesFrom`, inclusive
  numeric/datetime `range`, file limits/types, and pill styling.
- The system columns (`ID` = Row ID; `CREATED_*`/`UPDATED_*` = row edit history)
  auto-populate. Exclude them from seed CSVs and MCP row dictionaries.
- **Titles & customizations now round-trip**: the element `name` is the visible
  title; `tableStyle` and `sort` persist too (treat like a `table` element).
  Column protection and broader admin policy remain UI/admin concerns.

## Linked input tables — REST spec warning; MCP path not yet validated here

> **⚠️ CORRECTION (2026-06-10). An earlier version of this file called linked
> input tables "the powerful path, API-authorable." That was wrong** — it was
> validated only by structure (`/elements`), never by querying the data. When you
> author a linked input table through REST workbook code representation, the **inherited
> columns don't resolve: every row shows "multiple values."** Publishing does not
> fix it, and re-POSTing a known-good UI-built linked table verbatim reproduces the
> break. The linked-column key-correlation is server state the REST spec can't
> carry. Sigma MCP Code Mode exposes `add_linked_input_table()`, but the empty-table
> seed regression in this document did not test it. Use the established UI path or
> prove MCP create/read/update end to end before shipping it.
>
> What a POST *does* create: the PK column + the grain (PK rows populate from the
> parent) + editable entry columns. What it *cannot* create: working inherited/
> linked context columns. So even the "blank forecast grid off a spine" idea gives
> rows whose dimension context columns read "multiple values" — poor UX; do it in
> the UI.

The idea below is the *intended* design (and how a UI-built linked table looks).
Do not POST it through the REST spec. Build it in the UI, or recreate it through
MCP only after a live regression proves inherited columns and row updates work:

```yaml
# 1) the spine: any element whose rows define the grain — a warehouse/data-model
#    dimension, or a custom-SQL cross-join (CALENDAR × CATEGORY × BU), etc.
- id: spine
  kind: table
  source: { kind: data-model, dataModelId: <dm>, elementId: <el> }   # or warehouse-table / sql
  columns:
    - { id: storeKey, formula: '[D_STORE/Store Key]' }
    - { id: storeName, formula: '[D_STORE/Store Name]' }

# 2) the linked input table — rows come FROM the spine
- id: forecastEntry
  kind: input-table
  source:
    kind: linked
    from: spine                 # the PARENT element id (rows are inherited from it)
  inputMode: explore
  columns:
    - id: pk
      key: storeKey             # PRIMARY KEY → references the PARENT's column id (static row identifier)
    - id: storeNameLinked
      formula: '[D_STORE/Store Name]'   # LINKED column — inherits live parent value, NOT editable
    - id: FORECAST_AMOUNT
      type: number              # OWN entry column — the only thing forecasters type
    - id: UPDATED_AT            # system edit-history columns (no type)
    - id: UPDATED_BY
```

Why it's still the right *design*:

- **Grain derives from a spine, not a paste.** Point the linked table at a freshly
  generated spine (e.g. a custom-SQL `CALENDAR × CATEGORY × BU` cross-join) and the
  grain is correct by construction — solves the stale-spine problem ("derive, don't
  port"). Forecasters fill only the measure; dimension columns are read-only.
- **The REST linkage is broken.** When built in the UI the inherited columns
  resolve correctly; when POSTed they show "multiple values" (see correction
  above). MCP has a dedicated linked-input-table SDK surface, but validate the
  full create/read/update path before treating it as the replacement.

Use **empty + CSV** (below) instead when you're seeding **starting values**
(e.g. last year's actuals as a baseline to adjust), where the rows aren't simply a
dimension cross-product. Use **linked** when the grain is a dimension product and
forecasters enter net-new measures.

## Seed rows through Sigma MCP Code Mode

For an existing empty input table, first `describe` and `query` it, resolve its
current page host, and narrow the fetched element and columns before writing:

```python
inputs = sigma.workbook.get_page('<CURRENT_PAGE_ID>')
it = inputs.get_element('<INPUT_TABLE_ID>')
if not isinstance(it, InputTable):
    raise RuntimeError('expected input table')
key = it.get_column_by_name('Line Item')
value = it.get_column_by_name('Rate')
if not isinstance(key, LiteralEditableColumn):
    raise RuntimeError('key is not editable')
if not isinstance(value, LiteralEditableColumn):
    raise RuntimeError('value is not editable')
row_ids = it.upsert_rows([
    {key: 'Subscription Revenue', value: 0.032},
])
it.update_rows([
    (row_ids[0], {value: 0.04}),
])
```

Pre-query the live table and insert only missing natural keys. An empty input
table uses `upsert_rows()` for inserts, but the method name does not mean it will
deduplicate a business key. `update_rows()` targets the input table's system row
ID. Re-query the input table and a downstream element after each write; for a
reversible check, restore the original value and verify the downstream result
returns exactly to baseline. The live forecast regression seeded 6 rate rows and
30 manual rows, then proved both input tables recalculated the P&L without adding
duplicates.

REST-created element IDs remained valid in that regression, but Code Mode
`get_element()` had to run against the element's current page host (`inputs`),
not the page used by the original REST layout.

### Repeatable planner and gate workflow

`scripts/input-sync.py` provides the reusable local half of this protocol. It
does not call MCP and generated programs do not invent a query method on
`QueryableSource`:

1. Run `input-sync.py architecture --workflow <sales|expense|research> ...`.
   The plan must contain validated source-derived input rows for that workflow;
   a research manifest never bundles sales or expense evidence. Rebuild the
   manifest whenever workflow, connection, folder, source rows, or reviewed
   formula replacements change.
2. Run `input-sync.py stage --manifest ... --plan ... --source ... --approval
   ...`. This re-runs the real source audit, rejects `BLOCKED` or unresolved
   review, and binds each construction seed plus target page/document/version
   to an immutable artifact hash.
3. Emit reviewed construction and native-join artifacts with `emit-create` and
   `emit-wiring`. MCP `describe`/`query` the created input table; retain the real
   row ID, assigned element/column IDs, query snapshot ID, and snapshot age.
4. Re-stage the assigned target bindings, then run `input-sync.py plan
   --manifest ... --receipt ... --feature ... --current-rows ... --row-id ...
   --snapshot-id ... --snapshot-age-seconds ...`.
5. Review conflicts/orphans and each generated chunk. Inserts are missing keys
   only; updates use real row IDs only when the current value still equals the
   last migration value. A business column named `ID` is preserved.
6. Execute at most 2,000 rows per checkpoint, query again, and retain readback
   evidence. Re-running after a partial write reconciles current state and emits
   no duplicate insert for rows already present. Confirmed migration baselines
   advance only after queried readback; planned but unexecuted update chunks stay
   pending and remain safely resumable.

Typed keys do not trim/case-fold/coerce strings or numbers; `0`, `"0"`, and
null remain distinct, and null business keys are rejected. Date-only values are
emitted at noon; datetimes retain their instant (timezone-aware values normalize
to UTC). System columns are excluded by provenance, never a name blacklist.
Input-table row writes have no documented compare-and-swap, so the snapshot is
not a transaction: re-query after interruptions and before later chunks.

## The seed CSV (UI fallback)

Emit only the data-entry columns, headers in `UPPER_SNAKE_CASE` matching the
input-table column ids exactly:

```
REGION,BRANCH,SUB_BRANCH,MONTH_DATE,CATEGORY_CODE,FORECAST_AMOUNT
West,Seattle,SEA-North,2025-09-01,4000,94592
…
```

Paste limit is 2,000 rows × 25 columns; CSV upload limit is 200 MB / UTF-8. For
the 540-row fixture, clipboard paste was used.

## The warehouse view

After publish, the input-table element menu → **Warehouse views → Create new**
lands a queryable view (e.g. `SIGMA_WRITE_DB.SIGMA_WRITE.FORECAST_ENTRY`). The
view exposes **only the data columns** (system columns dropped); a Snowflake
`datetime` lands as `TIMESTAMP_LTZ`. The UI dialog truncates the path — get the
full one from the dialog tooltip or via `snow`:

```bash
snow sql -c default --format json -q \
  "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME \
   FROM SIGMA_WRITE_DB.INFORMATION_SCHEMA.VIEWS WHERE TABLE_NAME ILIKE 'FORECAST_ENTRY%'"
```

## Gotchas that cost time (so they don't again)

1. **UI draft rows and MCP writes have different lifecycle evidence.** Continue
   to publish UI CSV/clipboard edits before judging them missing. In the live
   2026-10-15 MCP regression, `upsert_rows()` and `update_rows()` persisted and
   were queryable immediately. Published-mode UI permissions were not tested.
2. **Don't repoint a DM seeded with different data.** If you built the read-half
   DM against a different seed (different category codes / grain), build a *fresh*
   DM for the view rather than repointing — otherwise dimension joins silently
   miss and parity breaks.
3. **DM element `name` is not honored on POST** — every element reads back as
   "Custom SQL". Identify elements by inspecting columns, not name.
4. **DM element + column IDs are REASSIGNED on POST.** Always `describe` the live
   data model (Sigma MCP) to get the real element/column ids before querying.
5. **SIGDS_ tables aren't directly queryable** and must not be modified — always
   go through the warehouse view.

## Going further: governance for the forecaster experience

Author supported validation in code representation (for example `valuesFrom`
to turn `CATEGORY_CODE` into a governed list), then verify it live. Use UI/admin
policy for the remaining governance:
- **Column protection** — lock the dimension keys + system columns so only
  `FORECAST_AMOUNT` is editable.
- **Sharing and connection write permissions** — who can open and write.
