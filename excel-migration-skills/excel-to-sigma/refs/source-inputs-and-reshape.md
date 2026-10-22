# Reviewed ordinary source inputs and explicit unpivot

`scripts/source-inputs.py` constructs local, source-bound records. It reads the
workbook without saving it or evaluating formulas. Its output is a plan for
review and later staging, not approval or runtime verification.

## Input decisions

Provide a JSON object with the exact workbook SHA256 and at least one reviewed
feature. Each feature selects one formal table (`sheet` + `table`) or bounded
cell block (`sheet` + `range` + ordered `headers`). Selection does not imply
editability; `role` must be `input` or maintained `reference` and `reviewed`
must be `true`.

```json
{
  "sourceSha256": "<exact 64-character lowercase SHA256>",
  "features": [{
    "featureId": "sales-forecast",
    "sheet": "Forecast Input",
    "table": "tblSalesForecast",
    "role": "input",
    "reviewed": true,
    "keyColumns": ["Region", "Product Line", "Month"],
    "literalColumns": ["Region", "Product Line", "Month", "Units", "Avg Price"],
    "columnTypes": {
      "Region": "text", "Product Line": "text", "Month": "datetime",
      "Units": "number", "Avg Price": "number"
    }
  }]
}
```

Types are `text`, `number`, `datetime`, and `boolean`. A natural key must be
unique, present, immutable by review, and separate from Sigma's physical row ID.
The planner refuses duplicate/missing keys, type disagreements, Excel error
cells even when their displayed value is text, formula cells selected for
literal seeding, and unreviewed all-blank columns. All formula
cells across the workbook remain `formulaObligations`, including those outside
selected inputs. Reviewed external replacements have a distinct
`reviewed-replacement-input` status. The plan records source row numbers and exact source cells for
every seeded value; displayed names remain intact.

For a single-row cell-drawn assumption block, use `range: "B2:C2"` and
`headers: ["Setting", "Value"]`. For a literal override in an otherwise
computed column, include the column in `literalColumns` and list its exact
literal addresses in `overrideCells`, such as `{"Adjustment": ["F17"]}`.
The computed column stays in `derivedColumns` and `derivedMappings`; it is
absent from the main input's editable schema. A separate keyed ordinary
input feature named in `overrideInputFeatures` contains only the reviewed
literal override rows and their source-cell mappings. Both input features
need staging bindings and readback evidence. Formula cells remain live
calculation obligations and are omitted from both seed row sets. An empty
formal table can supply a schema only when
`emptySchema: true`, `reviewedBlankColumns` exactly names all editable columns,
and `typeReviewEvidence` explains the source of each explicit type. It seeds
zero rows and still needs separate runtime evidence before completion.

For a user-approved replacement of an external formula, add a separate
`role: "replacement"` feature with `displayName`, `replacementFor`,
`replacementReview: {"approved": true, "basis": "..."}`, one natural key,
one editable value, and explicit `suppliedRows`. Each row needs a matching
`replacementBindings` entry with the exact key, source cells for both fields,
the original source label, and the original external formula. For example:

```json
{
  "featureId": "corporate-allocations",
  "role": "replacement", "reviewed": true,
  "displayName": "Corporate Allocations",
  "replacementFor": "FY26 Corporate Allocations external workbook",
  "keyColumns": ["Period"],
  "literalColumns": ["Period", "Allocation"],
  "columnTypes": {"Period": "text", "Allocation": "number"},
  "suppliedRows": [{"Period": "FY26-Q3", "Allocation": 61000}],
  "replacementBindings": [{
    "key": {"Period": "FY26-Q3"},
    "sourceCells": {"Period": "Budget!F4", "Allocation": "Budget!F21"},
    "sourceLabel": "Q3 FY26 Bud",
    "originalFormula": "='[FY26 Corporate Allocations.xlsx]Alloc'!$C$4"
  }],
  "replacementReview": {
    "approved": true,
    "basis": "User-approved persistent editable replacement of current allocation"
  }
}
```

The supplied amount is read from the decision, never from a formula cache.
The planner checks the source label and exact formula against current source
bytes. The ordinary staging receipt and target binding are still required to
emit construction or writes.

Run:

```sh
python3 scripts/source-inputs.py plan --source SOURCE.xlsx --decisions decisions.json \
  --connection WRITE_CONNECTION_ID --folder TARGET_FOLDER_ID --out source-input-plan.json
```

`build_source_input_plan(source_path, decisions, *, connection_id, folder_id)`
returns the plan. `validate_source_input_plan(plan, source_path=None)` checks
its digest and optionally rebuilds against exact source bytes. New plans use
`inputPlanVersion: 2` and retain cell-state/format metadata. Saved version-1
plans from the prior contiguous/unpivot/replacement contract remain valid:
source-backed validation reconstructs those decisions and compares the exact
version-1 projection and original hash. Version-1 plans cannot claim new
record bindings or version-2 metadata. A changed source still fails.
`plan_source_seed(plan, feature_id, current_rows, *, row_id_column,
prior_seed=None)` delegates to `input_sync.plan_seed`. Query target rows first;
pass the real system row-ID column and retain prior seed checkpoints. This
uses the existing three-way comparison to preserve user edits and refuses
duplicate natural keys. Date-only source values use ISO dates plus the
`datetime` column type; queried midnight/noon datetimes for those keys are
normalized to the same calendar date. Other key times are rejected.

The plan's `sharedInputArchitecture` is compatible with the existing
`input_sync` artifact constructor. Build a source manifest from the plan,
complete the source/formula review and approved staging gate, and only then
use the existing `emit_construction_program` or `emit_write_programs`. Both
emitters require an `APPROVED_STAGING` receipt bound to exact source, plan,
feature artifact and target. A reviewed role alone cannot emit a write.
The manifest version and production gate are unchanged.

## Explicit unpivot

`unpivot_source_table(source_path, *, sheet, table, key_columns,
value_columns, axis_name, value_name, axis_values=None)` returns long `rows`,
key columns, and reverse cell provenance. It refuses overlapping or unknown
columns, duplicate resulting keys, and conflicting axis mappings. Month-like
headers require explicit `axis_values` with full dates: `Jan` never implies a
year. `tblDeptBudget` can use Department plus a reviewed 2026 month mapping
to produce 60 rows. `tblHistory` can use Month with the three SKU headers as
axis values to produce 108 observations. The raw result is a read-only
reshape artifact. To make the long rows editable, add an explicit reviewed
`role: "input"` feature to the source-bound decisions with a `reshape`
object. `build_source_input_plan` recomputes that reshape from the exact
source bytes and checks the reviewed keys, columns and types before adding
it to `sharedInputArchitecture`:

```json
{
  "featureId": "budget-long", "role": "input", "reviewed": true,
  "keyColumns": ["Department", "Month"],
  "literalColumns": ["Department", "Month", "Budget"],
  "columnTypes": {"Department": "text", "Month": "datetime", "Budget": "number"},
  "reshape": {
    "kind": "unpivot", "sheet": "Dept Budget", "table": "tblDeptBudget",
    "keyColumns": ["Department"],
    "valueColumns": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "axisName": "Month", "valueName": "Budget",
    "axisValues": {"Jan": "2026-01-01", "Feb": "2026-02-01",
                   "Mar": "2026-03-01", "Apr": "2026-04-01",
                   "May": "2026-05-01", "Jun": "2026-06-01",
                   "Jul": "2026-07-01", "Aug": "2026-08-01",
                   "Sep": "2026-09-01", "Oct": "2026-10-01",
                   "Nov": "2026-11-01", "Dec": "2026-12-01"}
  }
}
```

The plan retains source measure cells and source header cells for each long
row. `plan_source_seed` and the existing staging receipt/constructor/write
emitters apply to this reviewed feature exactly as for a regular table.

```sh
python3 scripts/source-inputs.py unpivot --source SOURCE.xlsx \
  --sheet 'Dept Budget' --table tblDeptBudget --key-column Department \
  --value-column Jan --value-column Feb --axis-name Month --value-name Budget \
  --axis-values months-2026.json --out budget-long.json
```

`months-2026.json` must cover every selected month header exactly. Both CLI
commands refuse an output path that aliases the source workbook.

## Reviewed noncontiguous business records

Use `recordBindings` when a business row draws typed fields from separate
source cells. Each record names one actual `Sheet!A1` cell for every field in
`literalColumns`; the planner reads only source literals and verifies the
declared type. Addresses must lie within Excel's `A1:XFD1048576` grid. Missing
cells become `null`, while an explicit empty string stays
`""`. The plan keeps per-field `sourceCells`, `sourceCellStates`, and
`sourceCellFormats`, including date and percent number formats. Contiguous
tables and reviewed unpivots carry the same cell-state and format metadata;
an unpivot axis marked `reviewed-axis-mapping` retains its explicit header map.
Formula cells,
Excel errors, duplicate source-cell assignments, duplicate or missing typed
keys, and unsupported values fail closed. A source formula cannot be seeded
through a record binding; use the existing explicit replacement or override
review path where appropriate.

For example, a 13-week cash grid can keep Week, Rent, and Debt as three business
fields in one row, even though each field appears on a different source row:

```json
{
  "featureId": "manual-cash", "role": "input", "reviewed": true,
  "keyColumns": ["Week"],
  "literalColumns": ["Week", "Rent", "Debt"],
  "columnTypes": {"Week": "number", "Rent": "number", "Debt": "number"},
  "recordBindings": [
    {"sourceCells": {"Week": "13WCF!B4", "Rent": "13WCF!B16", "Debt": "13WCF!B18"}}
  ]
}
```

Use actual source fields as natural keys when they are unique. If records have
no unique business key, declare a `recordIdentity` with
`kind: "frozen-source-record"`, a text key column, `reviewed: true`, the exact
source SHA256 and a nonempty `reviewBasis`. Every record then supplies
`sourceRecordId: "Sheet!row:N"`; all its source fields must occupy that
physical worksheet row. This identity is valid only for the reviewed source
bytes. Reordering or changing the source invalidates the plan and requires a
new review, so a synthetic row label cannot silently become a new business key.
The identity column has no source-cell provenance and is never mistaken for a
source literal by native formula binding.

For fixed source labels or calendar axes represented as records, use
`role: "reference"` and an `immutableReview` containing the exact source
SHA256, `reviewed: true`, and a source-specific basis. The proof records why
the literal can remain fixed; it does not invent a cache value. The target
input-table construction, row seeding, assigned-ID readback, and promotion
gates remain the same as for the other reviewed input features.
