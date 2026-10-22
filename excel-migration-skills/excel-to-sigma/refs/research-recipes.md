# Equity-research model recipes (broker / FactSet house-template models)

The archetype for **sell-side equity-research models** — a covered-company model with
line-items down the rows, **YEARS across the columns**, grouped into statement sections
(PROFIT AND LOSS, PER SHARE DATA, EVALUATION, BALANCE SHEET, CHANGE IN NET DEBT, …). One
analyst maintains each; a single sell-side desk covers hundreds off **one house template** (can be ~850). This is a different shape from the FP&A forecast archetype in
`refs/forecast-recipes.md` (months across, actuals+driver-grown+manual, input-table entry).

**Validated end-to-end on a real broker equity-research model: 100.00% cell parity (3,263/3,263
cells across 24 years), 0 wrong, with ~81% of derived cells as LIVE Sigma formulas.** Built
entirely via REST — `infer-canonical-formulas.py` → plan JSON → `build-research-model.py`.

## The one big idea (why the hand build bloats, and the fix)

A hand build of one of these tends to explode: in the validated model, the manual P&L pivot had **97
columns** — every line item split into `X User` / `X Calc` / `X (1)` triplets with
`Coalesce([X User],[X Calc])` chains (some circular, one a literal placeholder) — because the
*same line is a hardcode in some years and a formula in others* (analyst overrides), and they
tried to honour every per-year exception. Per Share Data, done right, used **one formula per
line for all years** and stayed small. That is the whole lesson.

**Architecture (the clean version):**

1. **Data page** — *every typed number in the grid* as inline `VALUES` custom-SQL, WIDE:
   one row per YEAR, one column per line item (`c<row>` safe id). A typed cell is *always*
   data — a historical actual OR a forecast-year override; you never classify override-vs-actual.
2. **Computation table** — one calc COLUMN per line item (making each line a column, not a
   pivot row, is what lets each carry its OWN formula):
   - input line → `[data/c<row>]`
   - derived line → `Coalesce([data/c<row>], <ONE canonical formula>)` — the typed override
     wins automatically; the formula fills the blanks. **Exactly one Coalesce, one formula,
     all years. No `User`/`Calc`/`(1)` triplets.**
3. **Long** — a `transpose` (column-to-row) unpivot of the computation table → `(Year, LineId,
   Value)`.
4. **Labeled** — join Long ⋈ a line-dim (id → label / section / order).
5. **Display pivot** — `rowsBy` Section→Line Item (ordered), `columnsBy` Year, `Sum(Value)`.

## Canonical-formula inference (`infer-canonical-formulas.py`)

- **Year-relative normalisation.** Rewrite each Excel formula's refs to `(col_offset, row)` —
  offset 0 = same year, −1 = prior. Resolve `row` → the line item. Cells that differ only by
  which year-column collapse to the **same canonical key**; the row's formula is the **modal**
  key. `=F13-F8` → `[Gross profit] - [Turnover]`; `=F13/E13-1` → `[X]/Lag([X],1,[Year]) - 1`.
- **Refs are `[c<row>]` safe ids, not labels** — labels carry `/`, `%`, `&` which break Sigma
  refs. A line-dim maps `c<row>` → the real label for display.
- **Sigma idioms:** `Lag([c],k,[Year])` for prior-year (% change, CAGR); `[a]/[b]` for ratios;
  `^` for power; Excel `IF`→`If`, `SUM`→`Sum`; Excel `101%`→`(101*0.01)`.

## The three hard problems and how they're handled

1. **Plug cycles.** History types COGS→computes Gross profit; the forecast types Gross
   profit→computes COGS. One formula per row makes that a *static* cycle Sigma rejects. Detect
   cycles (incl. same-period self-refs; `Lag`/`Lead` prior-period refs are NOT cycles) from the
   **rendered** formulas, and **demote the most-typed cycle member to carried data** ("start
   from the hard-coded values"). It becomes a `[data/c]` leaf; the rest stay live.
2. **Blank-as-zero.** Excel treats a blank as 0 in `+`/`−`; Sigma propagates null. So **additive
   canonicals wrap each ref in `Coalesce(ref, 0)`** — the sum computes live and matches Excel.
   Ratios/products stay strict (a null there is real).
3. **Per-year structural differences & the parity gate (the trust anchor).** Preserve each
   source formula and literal at cell/year grain. Editable literal cells live in an ordinary
   input table keyed by one constant shared scope; its system row/audit IDs never enter grouping
   or join keys. Join that single shared row to every year in the calculation spine and let those literal overrides
   drive both displayed source periods and downstream formulas. Compare the resulting live
   workbook to Excel's cached values. A mismatch remains unresolved evidence; cached output is
   never relabeled as a live formula or used to declare completion.

## Build gotchas (verified live via the REST API)

- **`transpose` element takes NO explicit `name`** — Sigma auto-names it `Transpose of <source>`;
  its own columns must self-reference that auto name (`[Transpose of Calc/Year]`). Passthrough
  (non-merged) columns come through by their original name; the two new columns are named by
  `columnLabelForMergedColumns` / `columnLabelForValues`.
- A **data-model element can't be a `join`/`union` leg** — wrap it in a workbook `table` first
  (the line-dim → `Dim` wrapper).
- **No unary `+`** (`=+B8` → strip), **no `#,##0.0` format strings** (Sigma rejects; use its
  format objects or omit), **column names with `/` break refs** (use `c<row>` ids).
- **DM element formulas** = `[Custom SQL/<alias>]`; DM element `kind:"table"` + `source.kind:"sql"`.
- **FactSet cruft to strip** (log, don't silently drop): the `__FDSCACHE__` sheet, thousands of
  junk named ranges, `#REF!`/`#N/A`, external `[n]!` links. Don't trust cached values for
  broken-forecast years (they cache to `#REF!`) — rebuild from formula text.

## Verify

Export the `long` element to CSV and compare every `(c<row>, year)` to the Excel cached grid
(`data_only=True`) within €0.01 / 0.1%. Target: 0 wrong, 0 blank-where-Excel-has-a-value. Also
confirm the result is far smaller than a hand build (one column per line, not per-year triplets).

## Formula provenance and staging protocol

Current inference records formulas at source-cell and period grain before coalescing rows. The
plan keeps `periodFormulas`, `literalInputs`, and per-period `provenance` separately. Cross-sheet
literal drivers become source-bound `sourceInputs`; cached formula results never become literal
overrides. A shared parsed expression drives reference extraction, scalar parity evaluation, and
Sigma emission. The cell graph, rather than a row graph, decides cycles, so opposite formulas in
different years do not create a false cycle.

`migrationManifest` is the handoff contract for a later MCP orchestrator. Its `sourceHash` binds
the workbook bytes, and `planHash` binds logical formulas, source feature IDs, source input values,
and intended target scope. Runtime evidence, assigned target IDs and document versions do not
change the approved plan hash. Each source formula appears once with one of `live`, `cached`,
`unresolved`, or `verification`, plus target mapping and evidence fields kept separately.
`targetMapping` is logical intent only and uses explicit keys such as `logicalElementId`,
`logicalColumnId`, `logicalCheckId`, and `logicalSourceFeatureId`. Server-assigned document,
element, column/check, and version identifiers belong only in `targetBinding` (or `actualTarget`).
The manifest rejects assigned or ambiguous keys such as `elementId` or `columnId` when they are
placed under `targetMapping`.

Staging approval and completion are separate gates:

1. Before staging, call `gate_staging_manifest(manifest, approval)`. The approval must bind the
   source and plan hashes, name an owner, and explicitly list every mapped review item. It does
   not claim target verification.
2. After the target exists, attach passed verification evidence to every formula/check. Each
   record binds the source cell, source hash, plan hash, actual target ID, target document ID and
   document version, then call `gate_completion_manifest(manifest)`.
3. Source audit `BLOCKED` and existing `--post` behavior remain unchanged. Staging approval never
   overrides a source blocker, cached fallback, unresolved formula, or missing completion evidence.

For shared inputs, first put `targetScope` (connection/folder) and
`sharedInputArchitecture` into the plan with `architecture --workflow research`
and rebuild the manifest; a research source does not inherit sales or expense
features. Command-line IDs supplied later cannot inherit an old approval.
`scripts/input-sync.py stage --plan <architecture-output-plan>` re-runs the
source audit, calls the manifest staging gate, and requires a named reviewer,
the exact feature set, and reviewed target bindings. `emit-create`,
`emit-wiring`, and `plan` accept only that manifest/receipt pair; arbitrary
caller hashes, seed rows, or targets cannot be substituted. Query current rows
outside Code Mode, plan inserts/row-ID updates, execute, then read back and
checkpoint. An existing shared row is selected by its non-null `Scope`; an
intentional null input remains null rather than coalescing to the historical
literal. `complete` requires every approved table, mapped feature, checkpoint,
edit/restore check, unique-key count, and persistence readback for the exact
document/version. There is no compare-and-swap, so re-query after interruption.
