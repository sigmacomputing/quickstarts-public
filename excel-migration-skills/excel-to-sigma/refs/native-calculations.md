# Source-bound native calculation candidates

`scripts/native-calculations.py` is an offline compiler and guarded artifact
preparer. It reads the source with `WorkbookContext` and the reviewed ordinary
input plan, retaining the exact source SHA256, every formula cell, bound AST,
source dependencies, range domains, and source-derived local expected values.
It never reads formula caches, writes a workbook, calls Sigma, or runs macros.

```sh
python3 scripts/native-calculations.py plan --source source.xlsx \
  --input-plan reviewed-input-plan.json --out native-plan.json
```

A source literal maps to an editable field only through the plan's exact
`sourceCells` reverse mapping. Reviewed external replacement formulas map to
their approved ordinary input field while preserving the original external
formula and binding identity. Ambiguous reshaped source headers, unmapped
business literals, Excel errors, unsupported functions/ranges and dependent
formulas remain named `unresolved` obligations. The planner reports these
without a cached or constant fallback. Formula status `ready-to-bind` means
local source-derived lowering is available; it does not claim Excel or Sigma
runtime parity.

The compiler's candidate form set is numeric/text/Boolean literals, exact
cell references, grouped unary `+`/`-`, percent, binary `+`, `-`, `*`, `/`,
`^`, comparisons and concatenation; scalar `IF`, `ROUND`, `ABS`, `INT`,
`MIN`, `MAX`, `SUM`; one-cell bound structured references; and rectangular
bound ranges expanded only inside `SUM`. Every referenced business literal
must have one unambiguous reviewed input provenance binding. Candidate forms
still require saved-source and fresh-value qualification.

Exact-lowering gaps include `SUMIFS`, `COUNTIFS`, `IFERROR`, `VLOOKUP`,
`XLOOKUP`, `INDEX`, `MOD`, `AND`, `ROUNDUP`, `CEILING`, `FORECAST.LINEAR`,
`FORECAST.ETS`, `NORM.S.INV`, `STDEV.S`, general criteria/range functions,
and text/Boolean coercion in arithmetic. Finite `INDIRECT` records its
alternatives and DAG edges, but remains unresolved until invalid-selector
and error behavior is exact. Whole-column or incomplete dynamic domains,
multi-cell arrays, source error cells, and ambiguous blanks stay explicit
obligations. Unsupported forms have no cached or constant fallback.

`lower-candidate` accepts actual physical row IDs and emits fully parenthesized
REST formula text plus a one-row scalar table and at most 64 independent formula
columns per shard. Formula dependencies move to a subsequent shard. Existing
ordinary input tables continue to expose their business fields. Scalar
`Lookup` references bind through the assigned input name, observed physical
row ID and observed row-ID column alias. The generated text uses documented
`Coalesce(..., 0)` numeric blank handling and explicit parentheses to avoid
the SDK export grouping defect. No raw formula parser method is assumed.

For a guarded full-contents update, save a complete fresh document GET and
full queried input rows, then run `backup` to persist the exact restoration
material. `prepare-update` requires that backup, the source input plan, a
manifest with matching input-plan hash and reviewed `live` formula mappings,
the `APPROVED_STAGING` assigned input receipt, the fresh document/version and
full queried rows. It checks actual input element, editable column, row-ID
alias and row identities. It emits one contents PUT body per shard while
copying all foreign contents, pages, events and schema. A prior shard must
have an exact saved readback receipt before the next can be prepared. Run
`confirm-readback` on the fresh saved GET; any changed expression structure
fails closed.

The native plan deliberately does not upgrade manifest review status or
complete any production gate. The current legacy manifest parser cannot mark
all new bound AST forms live; those mappings need separate reviewed manifest
integration. The REST artifact is a candidate until source, native and visual
runtime parity after input edit, reopen and restore are evidenced. Statistical
forecasting, dynamic locators, array spills, general criteria/range functions
and unreviewed source literal inputs remain unresolved.

## Typed native v2 (explicit opt-in)

Use `plan --exact` (Python `build_native_calculation_plan(..., exact=True)`) for
`nativePlanVersion: 2`. The legacy v1 default remains unchanged. V2 implements
`SUMIFS`, `COUNTIFS`, `COUNT`, `COUNTA`, `IFERROR`, exact `VLOOKUP`, exact
`XLOOKUP`, scalar and fixed-shape row/column `INDEX`, exact `MATCH`, `AND`,
`OR`, `MOD`, `ROUNDUP`, `CEILING`, `DATE`, `EDATE`, `EOMONTH`, `MONTH`, and
finite bound `INDIRECT`, alongside the preceding arithmetic form set. Approximate
lookup and binary search modes, dynamic array spills, incomplete whole-column
count domains, unknown dynamic locators, and statistical custom ports remain
explicit obligations.

Every scalar has separate `number`, `text`, `logical`, `kind`, and `error`
columns. `kind` distinguishes numeric, text (including the empty string), Boolean,
and true blank. `error` contains an Excel error code, or the empty string for no
error. A numeric lane containing zero is **not** the public answer without its
kind and error lanes. `IFERROR` selects by the Excel error lane; missing bindings
and unsupported compilation remain exceptions, which it never catches. The
source evaluator reports `sourceResultClass: excel-error` and
`localExpectedError`; `localExpected: null` alone must never be called equivalence.
All constructed and saved forms remain `UNVERIFIED_CANDIDATE` until independent
runtime value/type/error parity, input changes, reopen, and restore are measured.

The ordinary input tables remain the business editing surface. Complete formal
calculated columns lift to ordinary row formulas only when **every** original
row produces the identical symbolic expression after substituting its own
input fields. Literal overrides or absolute anchors cannot be inferred away.
`formalTemplateObligations` lists source formula cells whose append behavior
could not be proved by that check. Aligned criteria operations use ordinary row
predicate helpers and aggregate `Lookup(SumIf(...))` / `Lookup(CountIf(...))`.
Bounded explicit ranges restrict observed physical rows; complete formal data
bodies and whole-column sum domains include future input rows. Typed text
summands can be ignored without embedding unreviewed header text as constants.

Helpers share the source-cell and period DAG, including external row-table
prerequisites. Fully parenthesized formula strings are split into deduplicated
helpers, no more than 64 columns per table, at most 6,000 characters after actual
name/ID substitution, with an explicit depth limit of 256. The actual 13-source
replay is below 3,500 characters per formula. This is a bounded construction
candidate, not a measured runtime scale guarantee; table counts and depth are
reported per source. Summand/criteria calculation errors retain a companion
error rollup ordered by the original observed source rows. New appended rows
that can produce calculation errors require a reviewed stable source ordinal;
`rangeDomain.appendErrorOrderRequiresReviewedOrdinal` records that remaining
qualification rather than guessing their order.

### Source-bound review and assigned construction

A v2 manifest opt-in requires `nativeCalculationPlan`, matching `inputPlanHash`
and `sharedInputArchitecture`, plus `nativeReviewApproval` containing `status:
reviewed`, nonempty `owner`/`reviewer`, `sourceSha256`, and `nativePlanHash`.
The manifest recomputes the plan/formula/AST hashes and rebinds each candidate
against the original source text. Its default parser behavior is unchanged.
`nativeCandidate.runtimeStatus` remains `UNVERIFIED_CANDIDATE`; Audit cells retain
`mappingStatus: verification`. Compiler evidence never creates passed runtime
verification or bypasses source/staging/production gates.

After actual input IDs and full physical rows are queried, `lower-candidate`
produces the exact logical mappings for review. Mappings include five
`logicalLaneColumnIds`. Persist a full document and input-row backup. An actual
existing native page and a queried `SELECT 1 AS C0` seed element on the approved
connection are required for structural construction. The seed receipt includes
actual document/version/element IDs and exact `queriedRows: [{"C0": 1}]`.

`prepare-scaffold` requires the native/input plans, reviewed manifest, approved
assigned staging receipt, fresh current document, observed rows, backup,
`--seed-binding`, `--page-id`, and `--shard-index`. It emits **one** MCP program
using documented `get_page`, `add_table(source.element(...))`, `set_name`,
`add_column`, `const_num`, and column/element `id()` calls. Columns are clearly
unverified placeholders. `confirm-scaffold` reads actual server-assigned element
and column IDs; authored IDs are never substituted for returned identities.

Once a contiguous scaffold prefix through the current shard has assigned receipts,
`prepare-update --native-bindings`
emits one version-guarded full-contents REST packet to the observed assigned
columns. It copies foreign contents and verifies source/input/native/manifest
identity, complete row backup, scaffold receipts and previous exact saved-formula
readbacks. `confirm-readback` requires the exact parenthesized saved structure.
The SDK scaffold **does not emit the final arithmetic expressions**, so its
known nested-math export issue cannot silently erase grouping. The CLI executes
no MCP or REST calls itself.

For the actual source replay, run `tests/native_exact_source_replay.py --root
<task-root> --input-plans <reviewed-plan-directory> --out <report-directory>`.
It checks all 1,865 original-fixture and 1,786 broader-source formulas separately,
uses explicitly test-only UUID-shaped row IDs for offline construction, and
writes coverage plus receipt-pending SaaS/Cash root construction requests. These
test identities are never staging receipts or evidence of a target deployment.

### R1 conservation and semantics corrections

Scaffold proposals now retain the complete readback envelope and declare a
single page/frame. The MCP program explicitly sets that frame, captures only
the new table's inherited columns, adds the declared placeholders, then deletes
those inherited columns. Confirmation permits exactly one appended new table
with exactly the ordered requested columns and constant-zero formulas. Its
assigned element and column IDs must be new and unique. The source must be the
exact observed source. No unrelated element or column is admitted.

All other document envelope and contents fields—including pages, events and
private state—must be identical. The layout may add exactly one direct Element
placement on the declared page with the declared frame. Existing layout nodes,
attributes and non-whitespace text remain identical; only XML attribute order,
quote/self-closing syntax and indentation are normalized. Undocumented SDK
metadata or envelope changes fail closed until an observed, narrowly reviewed
contract is added. Pending scaffolds must still match their confirmed structure
before a formula update; extra columns cannot be silently overwritten.

Sigma `RoundUp` is a ceiling operation for negative numbers. Excel `ROUNDUP`
is therefore emitted as a sign multiplied by `RoundUp(Abs(number), digits)`.
The test-only native interpreter follows Sigma's published negative examples,
while the source evaluator retains Excel's separate away-from-zero operation.
Sigma `RoundDown` also floors negatives, so Excel integer truncations (precision,
date offsets and index positions) use documented `Trunc(value, 0)` instead.

Boolean criteria in `SUMIFS`/`COUNTIFS` are currently explicit unsupported
obligations pending an actual Excel oracle. This includes typed Boolean blank
inputs and formulas with possible Boolean branches, even when the current
baseline is numeric or blank. Internal type-domain evidence survives helper
materialization and formula references; it is not a sixth output lane. Neither
the source evaluator nor emitted lowering is treated as the truth for the
previously disagreeing Boolean cases. Ordinary Boolean arithmetic/logical
operations retain their existing behavior. The actual 13-source replay's
formula counts are unchanged by this restriction.


### Explicit input-only first staging phase

When formula lowering needs physical input row IDs, `input-sync.py stage
--inputs-only --input-plan <source-validated-plan>` uses a separate
`gate_input_only_staging`. The source/manifest/input hashes and architecture must
match, the plan and named `approved_for_staging` approval explicitly declare
`input-tables-only`, and every source formula ID must remain in the exact
`reviewItems` and `pendingFormulaIds` sets. Formula mappings, native review
aliases and runtime evidence are forbidden in this phase. Source blockers and
exact source issue staging review requirements still apply. Default full staging
continues to reject unresolved formula mappings.

The resulting `APPROVED_INPUT_STAGING` receipt is accepted only for ordinary
literal input creation/seeding. It is rejected by native construction and
completion. `native-calculations.py bind-input-rows` can validate fresh full
input rows/schema against that scope and produce observed physical bindings for
an offline `lower-candidate`; it authorizes no formula mutation. A separate
actual native plan/manifest review and full `APPROVED_STAGING` receipt are required
before native scaffolds or formula REST writes.

Native updates now accept an exact contiguous assigned scaffold prefix through
the current dependency-ordered shard. This permits a small construction canary
before later helper tables exist; holes, unknown receipts, changed pending
scaffolds and missing earlier exact formula readbacks still reject. This protocol
change is not runtime qualification or permission to deploy a large scalar
fallback. The Regional assessment explicitly blocks its current 309-table
candidate pending record/period grouping.

The complete emitted-table graph test now checks Lookup and conditional native
aggregates with source-row provenance. It caught a materialization variable
collision that changed SUMIFS into CountIf; criteria table names now use a
separate local variable so SUMIFS retains SumIf and a numeric summand lane.


### R1 input-only scope conservation

`executionScope` is enforced as an enum, not descriptive metadata. Legacy/full
plans omit it; the only defined explicit value is `input-tables-only`.
`validate_manifest` rejects that scope by default. Its explicit
`allow_input_only=True` is used only by the literal-input gate and read-only
assigned-row binder, and requires every formula's canonical status to remain
`unresolved`, with no target mapping/binding, runtime or verification claims.
Input-only Audit cells also start unresolved; ordinary full-plan Audit defaults
remain unchanged. Unknown/null scope values reject rather than becoming full
execution implicitly.

Full staging/completion and native consumers use the default common validator.
Artifact receipt checks independently enforce the same distinction, including
when a caller relabels an input-only receipt `APPROVED_STAGING`. Hash-only
acceptance/report paths reject scoped input manifests, and promotion finalization
checks its embedded reviewed acceptance matrix before preparing a request.
Claimed successful target/evidence fields cannot upgrade an input-only plan.
A later full native review is a new plan/manifest hash with no input-only scope;
it does not change or complete the immutable first-phase manifest.
