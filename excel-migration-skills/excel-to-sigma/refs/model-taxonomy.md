# Spreadsheet model taxonomy + the architecture decision

The hard part of Excel→Sigma is **classifying the model**: which cells are typed
sources, live references, aggregations, drivers, or other formulas. Discovery
records evidence; edit intent and the target architecture still need review.

This is the path that handles "report drawn in cells" workbooks (no formal Table)
— the common FP&A case the formal-Table router (`refs/excel-translation.md`) skips.

## Detect — the cell-level classifier (`xlsx-discover.py`)

For formulas and numeric literals among formulas on a non-Table sheet,
`classify_report_cells` emits counts. The JSON discovery report also records
the source coordinates of direct-reference formulas:

| Class | Excel signal | Sigma target |
|---|---|---|
| **ACTUAL** | `SUMIFS`/`SUMIF`/`SUMPRODUCT` over a transaction tab | live read-only DM element off that source |
| **DRIVER_GROWTH** | `=prior_cell * (1 ± Assumptions!rate)` | closed-form `base × (1+rate)^n` (rate from the drivers) |
| **MANUAL** | numeric literal sitting in a row that's otherwise formula-driven | editable input table (one cell per line×period) |
| **DEPENDENCY_LINK** | `=B23` or `='Owner''s Cash'!$B$6` | live formula edge to the recorded source sheet/cell |
| **DERIVED** | arithmetic of sibling cells / `IF` margins (totals, %s) | workbook calc columns |

Unresolved formulas, including external-workbook and 3D references, remain
`OTHER_FORMULA` for review. Do not represent them as local dependency edges.

It also reports detected **actuals source** sheets (SUMIFS targets) and
**driver/assumptions** sheets (the `(1±rate)` refs). Example, FY P&L model:

```
P&L: DERIVED=111, ACTUAL=60, DRIVER-grown=30, MANUAL=24, live dependency=6
  → actuals source: Data        (= live read-only DM element)
  → drivers:        Assumptions  (= editable rates table / controls)
```

The source's grain and usage determine the architecture. A P&L with verified
actuals and drivers may use **union [live ACTUAL] + [forecast]** and the
`forecast-recipes.md` builder. A cash roll-forward such as `C7=B23` needs a live
edge to the preceding ending-cash calculation. It cannot be replaced by a
constant base. Use a `flat` forecast branch only when an independent source
policy establishes a constant across the relevant periods; `=prior` syntax is
insufficient evidence.

## The decision — ask intent (don't guess)

Present the detected model map, then confirm these points where applicable:

**1. How is this model used?** (the load-bearing question)

| Answer | Actuals | Forecast | Drivers |
|---|---|---|---|
| **Read-only report** | live DM | computed, baked | reference table |
| **Editable plan** | live DM | editable input table(s) | reference table |
| **Live what-if model** (recommended for FP&A) | live DM | computed via closed-form | **editable rates + manual cells** that recompute |

**2. Which detected inputs stay editable?** (pre-fill from MANUAL + driver detection: the growth rates, the manual cells, or both)

**3. If actuals are present, are they live or a snapshot?** Match the source's
refresh behavior and confirm the target connection.

Confirm the source grain, sheets, sections, periods, and dependency links before
using an archetype builder. Source-hash binding alone does not prove that a
builder supports the workbook shape. Unknown structures route to source-specific
MCP construction or explicit review, never to a bundled fixture profile.

## Build + the trust gate

Use `refs/forecast-recipes.md` only when its actuals/driver/manual preconditions
hold. Verify that target calculations remain live, then compare against
source-bound cached totals where available. Freezing formula caches to match
baseline values is not formula parity and does not complete a migration.

## Macros

If `.xlsm`, run the **macro gate** (`refs/macro-handling.md`) in the same discovery
pass — macros often *are* the "how it's used" answer (a `CommitForecast` button ⇒
this is an editable plan with scenario history).
