# Native presentation migration

`scripts/build-presentation.py` is the reusable presentation entry point for the
five acceptance fixtures. It extracts native charts, data validation,
conditional formatting, semantic formats, and formula provenance directly from
OOXML. Chart caches are retained only as expected-value evidence; emitted Sigma
charts always use live formulas over runtime-bound elements.

Generate an inspectable logical artifact without touching Sigma:

```bash
python3 scripts/build-presentation.py source.xlsx \
  --fixture-bindings --openapi sigma-openapi-current.json \
  --plan-out presentation-plan.json --out presentation-artifact.json
```

Generate a version-guarded full-contents PUT body after input construction and
GET/readback discovery have supplied actual IDs:

```bash
python3 scripts/build-presentation.py source.xlsx \
  --bindings runtime-bindings.json \
  --manifest migration-manifest.json \
  --staging-receipt approved-staging-receipt.json \
  --contents workbook-readback.json \
  --document-version 7 --openapi sigma-openapi-current.json \
  --plan-out presentation-plan.json --out workbook-put-body.json
```

Actual emission recomputes the staging receipt hash and immutable input artifact
records, audits the exact source bytes again, checks the complete pending source
issue scope, and requires the manifest target document/version plus the assigned
edit-table columns. Placeholder labels cannot pass this gate. Runtime bindings
provide actual page, element, and column IDs for charts, views, validation,
formats, conditional formats, and editable business inputs. Logical fixture
bindings emit `LOGICAL_FIXTURE_ONLY` artifacts and are rejected with
`--contents`.

The emitted artifact creates separate overview and detail table elements so a
single element is never moved between pages. The edit page references the
ordinary input table. A repeat merge replaces only source-owned presentation
pages and elements, preserves unrelated content, and rejects foreign ID
collisions. Existing business input tables use a reconciliation contract rather
than being recreated.

Forecast, sales, inventory, and expense inputs are constructed as ordinary
input tables in published Explore edit mode. Only source-authored literals are seeded;
derived columns live on native downstream calculation tables owned by the same
immutable architecture. Sales calculates weighted value and cycle days on
`salesInputBase`, then consumes the reviewed Task 2 AsOfDate join. Inventory
owns its availability, reorder-point, days-cover, `ROUNDUP`, and status chain on
`inventory`. Expense consumes the reviewed Task 2 policy join and owns the
numeric-Amount count check on `expenseNumericAmountCount`. Companion settings
and policy inputs are constructed separately, never duplicated by the wiring.
Sales Cycle Days preserves Excel `=C-B` fractional days in both native wiring
and SDK construction using
`DateDiff("millisecond", start, end) * 0.000000011574074074074074`.
The floating days-per-millisecond factor preserves positive and negative one
millisecond differences. Dividing the integer `DateDiff` result by `86400000`
can truncate fractional days in the warehouse, even with a decimal divisor;
do not replace the multiplication with that division. The SDK's `const_num`
may render this factor as `1.1574074074074074e-8`.
Precision is limited to Sigma's integer millisecond result and the retained
source timestamps; finer-than-millisecond Excel values require separate parity
review. The independent fixture oracle retains timestamp fractions instead of
rounding expected values to whole days. Local tests do not replace runtime query
or production acceptance gates.
The artifact exposes this through `businessOperationalWiring`, produced by
`build_shared_input_architecture` and `build_operational_input_elements` rather
than a second formula contract. Research reuses its Task 2 shared input table and
adds the twelve source-authored `FY results!B56:M56` equity inputs in place.
The architecture contains `Scope` plus all 145 source inputs. Extension compares
an actual column readback, creates only missing columns, and never writes rows.
After assigned-ID readback, regenerate the 146-column receipt and use the normal
row-ID reconciliation path to seed only missing values; this preserves Scope and
prior user edits after a partial or complete retry.

Use the source-bound input entry point before presentation emission:

```bash
python3 scripts/presentation-inputs.py prepare source.xlsx \
  --connection CONNECTION --folder FOLDER --out-plan input-plan.json \
  --out-manifest input-manifest.json
python3 scripts/input-sync.py stage --source source.xlsx --plan input-plan.json \
  --manifest input-manifest.json --approval reviewed-approval.json \
  --out approved-preconstruction-receipt.json
python3 scripts/presentation-inputs.py emit --manifest input-manifest.json \
  --receipt approved-preconstruction-receipt.json \
  --feature forecastBusinessInput --out construction.json
```

After construction, read the assigned input/column IDs and restage those exact
bindings. The assigned native graph can then be emitted or merged into a complete
GET-back response without manual formula repair:

```bash
python3 scripts/presentation-inputs.py wiring --manifest input-manifest.json \
  --receipt assigned-receipt.json --contents current-get-response.json \
  --out native-wiring-put.json
python3 scripts/presentation-inputs.py bindings source.xlsx \
  --manifest input-manifest.json --receipt assigned-receipt.json \
  --out presentation-bindings.json
```

`--contents` requires `workbookId`, `documentVersion`, and the complete flat
`contents` document. It checks assigned input names, types, and column IDs,
preserves unrelated nodes, rejects foreign target collisions, and returns a
version-guarded contents PUT artifact. An existing native-model page must match
the exact generated page metadata and complete owned placement contract.
Foreign content on that page, or owned graph placements on another page, cause
a rejection without changing contents; owned graph nodes alone never establish
page ownership. Omitting `--contents` emits the assigned
fragments and pending query checks. Apply only `contents` and `documentVersion`
to the API; other artifact fields carry provenance. Refresh/restage the receipt
after the PUT changes the version before emitting presentation bindings.

The forecast graph joins the assigned wide input to `spineWrap` by Line Item.
`Method`, `Monthly Growth`, and each source month column feed `forecast` and
`pnlCombined`; there are no separate rate/manual inputs. Actual amounts are
source literals, and the last-actual base is aggregated by SQL at query time.
`forecastInputsView` joins the same wide row to source line metadata for the
editing/detail presentation. The library forecast builder also accepts
`approved_inputs={"manifest": manifest, "receipt": receipt}` for composing a
workbook draft around this graph in the existing document; its default create
CLI retains the legacy contract.

Unsupported-root review mappings must name an actual emitted target and match
its exact native formula. Inventory uses `logicalElementId=inventory` and
`logicalColumnId=reorder_qty`; expense uses
`logicalCheckId=expense-numeric-amount-count`, which owns the native numeric
Amount count KPI column. These are pending review/runtime targets, not approval
or parity evidence.

Sales Overview `B6`/`B7` scalar totals have a separate
[source-scoped native KPI append planner](source-scalar-kpis.md). Its contract is
exposed as `sourceScopedScalars`; its physical-row identity receipt and actual
assigned-ID readback are required before target ownership. Keep these additions
outside the full-contents path on workbooks containing private native actions.

Before the presentation PUT, run `presentation-inputs.py bind-target` with the
latest GET/readback document ID and version. Re-run it after a research column
extension changes the version, then approve the assigned post-extension
bindings against that manifest.

Research `prepare` also takes `--research-plan`. Its first `emit` consumes the
approved 134-column binding and an exact `--current-columns` readback, returning
only the twelve missing-column operations. Record their returned IDs with
`checkpoint-extension`, GET/read the exact fields, then stage a new receipt
containing all 146 assigned IDs. `seed-extension` accepts that receipt and proof;
it writes only created fields that were null at the checkpoint and remain null.
A non-null field is retained as a user edit. The checkpoint cannot be replayed,
and a partial retry emits only columns still absent from the latest approved
binding. Unsupported source formulas require explicit reviewed replacements via
`prepare --reviewed-formulas`; they are never silently promoted.
Persist the entire returned `{plan, programs}` file before attempting its
writes and supply that file (or its canonical nested plan) as the next
`--prior-seed`. The public and library boundaries normalize this exact envelope,
reject ambiguous/foreign shapes, and carry checkpoint consumption through later
normal reconciliation. New writes remain pending until an actual matching
readback confirms them; no null baseline is fabricated. Always retain the latest
persisted ledger: deliberately rolling back local state cannot prove that a
creation proof was previously consumed. The writer checks the approved seed-row
hash, reconciliation digest, action source values, and extension target scope.

Research runtime bindings should source the main and detail views from `calc`
(`Calc`): `Year` uses `yr`, and each metric uses the authored `c<row>`
column ID. The main view is Year, Revenue (`c8`), EBITDA (`c18`), EPS (`c37`),
and Net debt / EBITDA (`c57`). The detail view carries every populated FY-results
metric as a separate column. Each column takes its format from the first
formatted source period, preserving currency precision, percentages, and the
ratio `x` suffix. The emitter derives format exactness by comparing the complete
main/detail column contract; it does not trust a caller boolean. A generated runtime template records all
145 logical input IDs and source cells; replace its twelve post-extension column
placeholders with GET/readback IDs before integration.
The edit-table patch keeps `Scope` and `i_model_inputs_c2` through
`i_model_inputs_c7` visible in that order and formats the six growth assumptions
as percentages. The remaining source inputs stay in the same physical table and
remain available in Explore while the main edit grid stays compact.
The native conditional-format store accepts a finite numeric literal midpoint.
Source percentile and formula midpoints have no verified exact native mapping;
the entire color-scale rule remains explicitly unresolved and is omitted from
element patches. It is never replaced with a cached midpoint or approximated by
dropping the midpoint. Full source rule XML is retained in the immutable plan's
`presentationConditionalFormats` and the artifact's `ruleProvenance`. Finite
literal-midpoint scales remain supported. Generated page names include the
workflow, such as Sales Overview, Inventory Edit, and Expense Detail.

Horizontal financial conditional rules retain their metric row and source year
scope: B31:M31 targets detail `research_c31`, and B57:M57 targets
`research_c57` on the main/detail views. Unbound Audit Status rules remain
explicitly unresolved; no calculation/status field is invented.

Every chart helper formula records target check ownership. Other source formulas
are collected in one hash-bound unresolved scope per workflow until target
column ownership or an executable parity check is approved.

Local extraction and schema audits do not prove runtime behavior. Completion
still requires SDK compilation, a guarded API dry run, GET/readback inspection,
aggregate parity queries for every chart point, and UI checks for rendering,
editing, ordering, rule precedence, and blank route behavior. The version 2
source blank contract is defined in `refs/source-blank-validation.md`. An
omitted `allowBlank` is preserved as omission. Numeric zero membership is a
declared-rule classification; edit/clear enforcement and the saved value remain
unresolved until separately reviewed and captured.

### Physical input display configuration and readback

The workbook code-rep exporter omits persisted input-column visibility and
formats. Their presence in a REST request, or absence in a later GET, is not
input display evidence. Actual presentation artifacts remove those input-column
REST fields, retain validation ranges, and expose `inputDisplay` with
`PENDING_SDK_READBACK` status. Ordinary readonly currency formats use a raw d3
`$` marker; `currencySymbol` metadata alone is insufficient to render currency.

After the guarded REST PUT, capture the latest version/page/assigned IDs and
bind/restage the approved manifest/receipt. Then emit the metadata-only SDK pass:

```bash
python3 scripts/presentation-inputs.py display SOURCE.xlsx \
  --manifest current-manifest.json --receipt current-receipt.json \
  --out display.json
```

The default feature is the workflow's primary input (all five are supported);
`--feature` selects another approved input. Source formats without an exact
binding remain explicitly unresolved. The artifact includes `executionBinding`
with the exact workbook/version, the `program`, and a separate readonly
`readbackProgram`. Bind the SDK execution context to that workbook/version and
review/execute the program. It invokes only documented visibility/format
setters: no row, value, schema, filter, or validation writes. It checks the
assigned IDs/names/types before mutations, selects Scope plus six growth drivers
for research, and preserves all source columns. Other primary workflows show
all their literal input fields.

The entire assigned editable set must consist of the approved
`LiteralEditableColumn` objects with exact `type()` and name. Both programs
enforce the complete set before any setter. Exactly one extra system identity
column is allowed. The default remains `InputTableIDColumn`, name `Row ID`,
`kind() == row_id`, on the same element. Its documented SDK has no `type()`
getter, so readback records `type: null` and the actual system kind.

Authentic SDK observations after a REST roundtrip also expose a normalized
system alias: `FormulaColumn`, ID/name `ID`, formula `[New Input Table/ID]`.
That route requires an explicit independently reviewed descriptor in the
feature's approved target binding before the receipt artifacts are generated:

```json
{"systemColumn":{
  "id":"ID","name":"ID","columnClass":"FormulaColumn",
  "elementId":"ACTUAL_INPUT_TABLE_ID","formula":"[New Input Table/ID]",
  "type":null,"systemKind":null,
  "rowIdBinding":{"kind":"row_id","sourceColumn":"ID","valueType":"text",
                  "evidenceHash":"SHA256_OF_REVIEWED_ROW_IDENTITY_EVIDENCE"}
}}
```

The hash must be an actual 64-character lowercase SHA256 of the independently
reviewed row-ID identity/type evidence. The receipt hashes the complete target
binding, including that hash, and the display contract binds the descriptor.
Adding/changing the descriptor after approval fails. Parent review must establish
that this exact owning table's alias preserves real server row IDs and the text
source identity; naming a formula column `ID` does not establish that fact.

This bounded adapter accepts only the observed ID/name/formula and exact owning
`element_id()`. Apply/readback guards check all of them before setters. Formula
text comes from documented `formula()`; FormulaColumn has neither a documented
`type()` nor a system-kind getter. Readback therefore records `type: null` and
`systemKind: null`, retaining the reviewed row-ID value type separately in
`rowIdBinding`. It never invents those getters or labels their output as a
queried type. The verifier checks exact ID/class/name/formula/owner. A missing
descriptor, foreign owner, alternate formula, extra column or changed ID fails
closed. The alias receives no formula, schema, source, row or value setter; only
visibility is configured with the same approved visible-column list.

Readback records class, literal type, system kind where available, owner,
formula where available, visibility and format for the full set. Post-validation
editable classes remain pending acceptance: if a REST list rule converts a
literal to a select column, the guard stops for a newly reviewed schema/class
mapping. It does not broadly accept selects.

Run `readbackProgram` in a fresh readonly SDK session after a successful persisted
execution. The controller saves the exact submitted calls and unmodified raw MCP
results before checking metadata. SDK capture envelopes have this shape:

```json
{"request":{"workbookId":"ACTUAL_ID","documentVersion":9,"code":"EXACT_EMITTED_PROGRAM"},
 "result":{"structuredContent":{"type":"success-no-edits","persisted":false,
                                 "output":"COMPLETE_PRINTED_OBSERVATION"}}}
```

The execution capture submits `program` against the approved base version; its
raw `success` result must report `persisted: true`, the actual workbook ID and a
strictly newer integer version. The observation capture submits exactly
`readbackProgram` in that resulting version, with a `success-no-edits` result
and `persisted: false`. Preserve all fields from each raw tool result, not just
this example's minimum fields. No manually added `readbackId` is accepted.

A current-version capture is the controller's fresh workbook GET/context call:
`{"request":{"workbookId":"ACTUAL_ID"},"result":{"workbookId":"ACTUAL_ID","documentVersion":9}}`.
The result may retain the full GET response. REST columns are not display
evidence; this capture confirms only the workbook/version context.

First record the captures in the authoritative durable ledger:

```bash
python3 scripts/presentation-inputs.py checkpoint-display SOURCE.xlsx \
  --manifest current-manifest.json --receipt current-receipt.json \
  --execution sdk-display-execution.json --readback sdk-display-observation.json \
  --current-version post-observation-current.json --state display-ledger.json \
  --out display-checkpoint.json
```

Then acquire a fresh current-version capture and verify/consume that checkpoint:

```bash
python3 scripts/presentation-inputs.py verify-display SOURCE.xlsx \
  --manifest current-manifest.json --receipt current-receipt.json \
  --current-version fresh-current.json --state display-ledger.json \
  --out display-verification.json
```

These commands lock the ledger, atomically replace and fsync it before publishing
an output. Every attempt retains raw captures and their canonical hashes, the
contract/source/plan hashes and exact actual workbook/version. A verdict consumes
the pending proof, including a metadata failure. Reverification, rerecording the
same execution/observation, and older/equal versions on that workbook fail closed.
The library's `verify_input_display` consumes its ledger argument in place;
controllers using it directly must durably save that ledger before accepting the
verdict. Use the CLI for the lock/persist boundary.

The controller is responsible for recording authentic calls in order and making
both current-version captures fresh. The SDK has no documented version CAS or
signed provenance, so supplied JSON cannot authenticate itself. Keep one
controller-owned ledger; deleting, editing, cloning or rolling it back to bypass
consumption is outside this evidence contract. A new staged version and fresh
persisted execution/readonly capture form a new attempt. That newer same-workbook
checkpoint supersedes older pending captures while retaining their complete raw
evidence and proof; the ledger is never reset for a retry. This protocol establishes
one-use, version-bound controller evidence, not cryptographic attestation.

Mismatch produces `FAILED` and a nonzero exit. Supported settings can pass while
full source fidelity remains `PARTIAL`: research's 121 currency fields preserve
currency/grouping/precision/negative parentheses, but Excel's separate
zero-as-dash/accounting sections have no exact d3 equivalent. Original Excel
formats and the unresolved reason remain in the contract; unsupported patterns
are not silently applied. Raw percentage patterns preserve source grouping.
The verifier establishes SDK metadata state only. Actual visual rendering,
source values, validation behavior, and role acceptance require separate proof.
The SDK exposes no documented workbook-version CAS, so parent execution must
bind the intended current context and retain the fresh readback evidence.

Actual business bindings resolve companion columns through approved assigned input
IDs or exact source-identity native nodes (for example Policy to Expense Policy,
Actuals Detail to Actuals). Source fields absent from that graph remain explicit
`source-column-binding`/rule entries in `unresolved`; matching names elsewhere do
not authorize substitution. Sales stage/rep metadata, inventory suppliers, and
unrepresented summary scopes remain acceptance work. Expense PolicyExcess uses
scalar `Greatest(amount - limit, 0)`, retaining the missing-policy null guard;
source blank arithmetic and cent-boundary parity require separate runtime checks.
