# Macros (VBA) — detect, classify, route, gate

`.xlsm`/`.xlsb`/`.xls` carry VBA. **Macros are not one thing** — like cells, you
classify them by *intent* and route each class. Actions, Python code elements,
stored-procedure calls, API connectors, and automated actions are now
code-representable. Representable does not mean automatically safe. The
non-negotiable rule:

> **Never silent.** Every macro is surfaced with a disposition. A dropped
> "Commit Forecast" button the user assumes still works is the FP&A equivalent of
> silently dropping row-level security. Macros are a **STOP/flag gate**, not a
> quiet delete.

## Extraction

VBA lives in `xl/vbaProject.bin` (an OLE compound stream) — `openpyxl` only sees
*that it exists*, not the code. Use **`olevba`** (oletools) to pull module source:

```bash
pip install oletools          # stable; not in the org's last-3-days window
python scripts/macro-classify.py path/to/model.xlsm          # human report
python scripts/macro-classify.py --json path/to/model.xlsm   # machine contract
```

`macro-classify.py` accepts a binary office file (extracts via olevba) **or** a
raw VBA module (`.bas/.cls/.frm/.vba/.txt`) for testing. It strips comments before
classifying (comments must never drive a classification — they lie).

## The taxonomy → Sigma mapping

| Class | VBA signals | Sigma target | Status |
|---|---|---|---|
| **RECALC** | `.Calculate(Full)`, `ScreenUpdating` | none after formula parity | ✅ AUTO (drop) |
| **EXTERNAL_DATA_REFRESH** | `RefreshAll`, QueryTables, ADODB, SQL/CommandText | governed warehouse/API source, DM, or stored procedure | 🔌 DATA_REVIEW |
| **TRANSFORM_ROLLUP** | `For…To` loop + `Cells(..).Value =`, `WorksheetFunction`, in-code SUMIFS | proven equivalent formulas/DM; otherwise Python | 🐍 PYTHON_REVIEW |
| **NAVIGATION** | `.Activate`, `.Select`, `.Goto`, `.Visible =` | page navigation / visibility | ✅ AUTO (map or drop) |
| **FORMAT_COSMETIC** | `.Font`, `.Interior`, `.Borders`, `AutoFit`, `.NumberFormat` | conditional formatting / styling | 🐍 PYTHON_REVIEW / render review |
| **WHATIF_SCENARIO** | `GoalSeek`, `Solver`, writes into assumption cells, `Select Case scenario` | controls / parameters / editable assumptions table | 🎛 CONTROL |
| **ACTION_WRITEBACK** | `PasteSpecial xlPasteValues`, `ListRows.Add`, append patterns/name verbs | `insert-rows`/`update-rows` input-table Action | ⚡ ACTION |
| **API_CALL** | `MSXML2`, `WinHttp`, HTTP verbs | connector-backed `call-api` Action | ⚡ ACTION + runtime review |
| **STORED_PROCEDURE** | `adCmdStoredProc`, CommandText `EXEC`/`CALL` | `call-stored-procedure` Action | 🗄 STORED_PROC |
| **PYTHON_AUTOMATION** | `RunPython`, xlwings, PyXLL | `code` element + `run-python-element` Action | 🐍 PYTHON_REVIEW |
| **EXTERNAL_IO** | Outlook/email, `Shell`, PDF/file I/O | scheduled delivery / external workflow | 🚩 FLAG |
| **OPAQUE** | bespoke math writing cells (`Sin/Cos/Rnd/…`), `Do While`, `GoTo` | — | 🚩 FLAG (human review) |
| **event-handler** | name `Workbook_*` / `Worksheet_*` (e.g. `Workbook_Open`) | decompose into its called actions; the auto-run wrapper itself drops | (follows contents) |

**Precedence** (when a macro matches several) favors external I/O, explicit
Python/procedure/API/data-source signatures, then writeback/control/transform
routes. Bespoke math (`Sin/Rnd/…`) overrides weak/AUTO matches to **OPAQUE**.
Action verbs are matched on the **procedure name** only, so a called helper like
`PostToGrid` does not trip “Post”; generic VBA `Call Helper` is never treated as
a stored procedure.

## Status meanings

- **AUTO** — reproduced by the data/formula conversion, or safely dropped after parity.
- **CONTROL** — becomes controls / parameters / an editable input table (the driver story in `refs/forecast-recipes.md`).
- **ACTION** — becomes an element Action; test arguments, permissions, side effects, retries, and failure UX.
- **STORED_PROC** — candidate for `call-stored-procedure`; confirm connection, path, signature, typed arguments, and transaction semantics.
- **PYTHON_REVIEW** — candidate for formulas/DM or a Python element; confirm packages, credentials, outputs, and parity.
- **DATA_REVIEW** — refresh/query logic must be rebuilt as a governed source and data parity-tested.
- **FLAG** — must be reviewed by a human (external I/O or opaque logic). Surface before build; never auto-port.

## Actions, Python, and procedure wiring

The workbook code representation now supports element Actions including
`call-api`, `call-stored-procedure`, input-table insert/update/delete,
`run-python-element`, navigation, controls, export, and refresh. A build step
consumes the classifier JSON and emits only reviewed routes:

```
CommitForecast_Click  → Action(on button): insert current forecast rows → "Snapshots" input table (+ timestamp)
SaveScenario_Click    → Action(on button): insert current assumption rates → "Scenarios" input table
ApplyScenario(name)   → Action(on select): set assumption controls to the chosen scenario's values
```

The classifier output is the routing contract, not proof that the emitted
behavior is correct. Every non-AUTO route remains gated on a live side-effect or
parity test.

## Worked example (`scripts/Sample Macros.bas` — the FP&A model's VBA)

The sample intentionally exercises automatic, control, action, data-review,
Python-review, and flag routes:

| Macro | Class | Status |
|---|---|---|
| `Workbook_Open` | RECALC + event | ✅ AUTO |
| `RefreshActuals_Click` | EXTERNAL_DATA_REFRESH | 🔌 DATA_REVIEW |
| `RebuildPnL` | TRANSFORM_ROLLUP | 🐍 PYTHON_REVIEW |
| `GoToForecast_Click` | NAVIGATION | ✅ AUTO |
| `FormatStatement` | FORMAT_COSMETIC | 🐍 PYTHON_REVIEW |
| `ApplyScenario` | WHATIF_SCENARIO | 🎛 CONTROL |
| `SolveForTarget` (GoalSeek) | WHATIF_SCENARIO | 🎛 CONTROL |
| `CommitForecast_Click` | ACTION_WRITEBACK | ⏳ ACTION |
| `SaveScenario_Click` | ACTION_WRITEBACK | ⏳ ACTION |
| `EmailReport_Click` | EXTERNAL_IO | 🚩 FLAG |
| `AllocateOverheadByHeadcount` | OPAQUE | 🚩 FLAG |

Extraction validated end-to-end through olevba on a real `.xlsm`; classification
validated on the full taxonomy above (2026-06-17).

## Source-bound native action candidates

For Forecast `SaveScenario_Click`, continue through
[forecast-scenario.md](forecast-scenario.md) after the source-bound native
mapping review. It requires a complete, hash-bound Operations/Saved audit
schema receipt and the versioned nullable `Scenario Name` policy before a
disabled lifecycle completion proposal can be emitted.

`macro-classify.py --json module.bas` includes static behavior facts and exact
raw-module/procedure hashes. Procedure names and comments never authorize an
append. Helpers are expanded transitively; missing helpers, refresh, email and
external integration behavior remain unresolved. No VBA is executed.

`macro-actions.py` provides `prepare`, `bind-target`, `emit-schema`,
`checkpoint-schema`, `emit-projection`, `emit-actions`, and `audit-readback`. Its Python interfaces
live in `lib/native_actions.py`. `prepare` embeds `nativeActionArchitecture` in
the existing manifest plan projection, so existing plan/source hashes cover the
source modules, reviewed decisions, payload schemas and logical mappings.
Restage this new manifest through `input-sync.py`; an old receipt cannot authorize
its schema or actions. `emit-schema` reuses the approved ordinary-input table
constructor and additive-extension planner. Expense extension checkpoints require
all 48 original physical IDs and 528 original values to remain unchanged and all
three added fields to be null. Forecast inputs stay 12 rows × 9 authored columns.

Every workflow decision names the exact `procedureId`, `procedureSha256`,
`decisionId`, `reviewer`, `reviewStatus=approved`, `mappingKind` and presentation
page. Scenario mappings explicitly bind `Assumptions!B5/B6` to a feature, business
key and value column. Snapshot decisions must explicitly review both the 27×6
source/fixture mismatch and destruction of copied `P&L!H7` by `Now`; the named
line/period projection is a reviewed replacement, never claimed as exact parity.
Live calculated projections can be supplied as hash-bound `readTargets` with
actual page/element/column IDs, composite `keyColumns`, and the exact current
`elementHash`. A `(line, period)` pair may use `extraKeys` in documented `lookup`
expressions. Cached formula results cannot be substituted by this emitter.

A separate Prepare action inserts a durable `workflowOperations` row and captures
`insert_row(...).returns()` as the operation ID. Confirm/retry reads the captured
control on a later invocation. This follows the SDK type boundary: ActionVariable
is an ActionValue, but is not a FormulaResolvable. Prepared rows freeze saved
scenario and snapshot payloads. Start new intent deliberately clears the control;
selecting a durable operation restores its identity after reopening. An orphan
prepared row after a capture failure blocks another Prepare for that workflow/context/record
until recovered. Start new intent explicitly marks the captured previous operation
`SUPERSEDED_NEW_INTENT` before clearing the control; it does not claim the business
write succeeded.
Selection values are captured on `on_select`, not assumed global to button clicks.
The selection-count formula's selected-row scope is a published runtime gate; if
it aggregates the full input table, the candidate fails closed. The parent must
verify no/one/multiple selection, deletion, selection changes and page transitions.

Approval uses one row-update effect with actual row ID, business key,
prepared original-field guards, and exact operation-history membership. It changes
only Approval Status, ApprovedAt and safeguard metadata. Receipt/reconciliation/
policy exception precedence remains intact. A reserved `|` token delimiter is
checked against the physical operation ID at runtime; retries of an older operation
after a later approval preserve the timestamp. Concurrent history lost updates
and read-then-insert races remain unresolved without warehouse ownership/uniqueness.
Sequential scenario writes preserve the VBA ordering and may partially fail.

Programs are disabled construction candidates. An exact named `APPROVED_STAGING`
construction review binds sourceHash, planHash, bindingHash, documentId, version
and candidateProgramHash; it cannot enable or replay saved constructors. Current
SDK output is explicitly `PARTIAL_REQUIRES_PUBLIC_ACTIONS`: Selection namespace
expressions and normalized FormulaColumn row IDs require the guarded public route
in [acceptance-and-promotion.md](acceptance-and-promotion.md). Native-ID SDK updates
use an InputTableIDColumn dictionary selector; the complete original predicate
remains in the trigger as CountIf(predicate)=1. Public single-row updates preserve
the same guard. These are serialized staging safeguards with a check/write TOCTOU
race. No transaction guarantee is inferred. The SDK offers no affected
row count on `update_rows`; candidates emit no optimistic success toast or APPLIED
claim. Independent current before/after readbacks must confirm the operation and
all expected values. `audit-readback` reports component evidence and still returns
`productionStatus=BLOCKED`; published clicks, permission roles, failure/retry and
concurrency evidence remain separate acceptance requirements. Reconciliation of
operation State/Completed At/Outcome after verified readback is a controller adapter
contract, not an invented native success primitive.

The reviewed post-REST row-ID alias uses the existing exact
`targetBinding.systemColumn` contract. Source list validation can also normalize
an editable field to SingleSelectEditableColumn. This is accepted only with an
explicit hash-bound `targetBinding.columnContracts[name]` descriptor containing
`id`, `columnClass`, `type`, exact `allowedValues`, `sourceValidationHash` and
`sdkEvidenceHash`. The helper reopens the XLSX and matches its parsed literal-list
or whole-number validation. Default literal guards remain strict. Generated display
and action programs compare `allowed_values()` and never mutate validation while
formatting or constructing actions.

`emit-projection` adds a new read-only SDK table from `InputTable.to_source()` and a
physical `Input Row ID` column. It never changes source input visibility/data/types.
Capture assigned projection IDs and rebind its exact element hash, columns and key
readback as a `readTargets` entry. Approval may use `selectionView` plus
`selectionRowIdColumn`; the view must be on the action page and every physical-ID /
Expense-ID pair must resolve to the actual expense input. Direct input selection
is accepted only when that input itself belongs to the action page.

After the first Task 4 review, preservation contracts additionally bind all original
editable field definitions and physical row IDs into the manifest/extension plan.
Before/after snapshots must contain exactly those fields plus the ID (and exactly
the three added fields after extension). The proof carries complete snapshots and
`preservedValueCount=528`; emission rechecks the complete snapshots and assigned
14-field input readback. Legacy narrow-snapshot plans/proofs must be regenerated.

The static analyzer inventories argument-bearing helper calls and calls in
expressions, expands their definitions, and leaves unsupported executable,
mutation, member-call and undeclared-expression forms unresolved. This bounded
subset is not a complete VBA interpreter. Approval write qualifications must
resolve to the guarded Expense Register worksheet; unknown/foreign ownership is
not authorized by a reviewed body hash.

For a new approval operation, `audit-readback` requires a timezone-aware
`expected.approvedAt` value or a controller-captured `capture.executionWindow`
with timezone-aware `startedAt` and `completedAt`. The observed ApprovedAt must
match the exact expectation or fall within those bounds (both if supplied).
Naive dates/times, invalid values and retained stale timestamps fail. A retry of
an operation already in durable history still requires exact row/timestamp
preservation and does not write a fresh timestamp.

For explicitly reviewed guarded allocation/goal-seek/scalar procedure ports, see
[custom-ports.md](custom-ports.md). This route binds new controlled source and
independent goldens; it does not relax automatic native analysis or production gates.
