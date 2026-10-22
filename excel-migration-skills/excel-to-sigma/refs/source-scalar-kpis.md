# Source-scoped Sales Overview scalar KPIs

`scripts/source-scalar-kpis.py` is an offline, native-SDK append planner for the
two exact Sales source equations `Overview!B6` and `Overview!B7`. It emits no
public full-document update. Use this route when the workbook contains private
native actions that public code representation cannot preserve.

The supported source shape is deliberately narrow: `tblSalesPipeline!A1:N49`,
the complete explicit `SUM` lists `Pipeline!J2:J49` and `Pipeline!L2:L49`, and
every weighted row's exact `=I<row>*J<row>` equation. Source bytes, full equations,
formula hashes, source cells, original row/key identity, dependencies, currency
format and empty-sum policy are retained. A changed/unsupported shape fails
closed; it does not become an unrestricted `Sum` of the current table. Formula
caches and frozen totals are never construction inputs.

`presentation-inputs.py prepare` exposes this as
`sharedInputArchitecture.sourceScopedScalars`. It is separate from the legacy
full-contents `nativeWiring` graph and its `formulaTargets`. Declaring the two
logical names does not establish actual ownership. `build_business_input_plan`
continues to reject reviewed replacements that have no owned emitted target.
Other Sales workbook shapes keep the ordinary architecture path and expose
`sourceScopedScalars.status: UNRESOLVED_UNSUPPORTED_SOURCE_SHAPE`, a source hash,
the unsupported reason, an empty owner list and `productionStatus: BLOCKED`.
That unresolved descriptor cannot be used as an append contract. Direct scalar
preparation and validation of a previously prepared exact-source contract remain
strict: changed source equations/ranges/bytes fail rather than widening scope.

## Inputs

Prepare a contract, retain a reviewed original physical-row identity receipt,
and capture a fresh complete workbook/native observation:

```bash
python3 scripts/source-scalar-kpis.py prepare source.xlsx --out scalar-contract.json
python3 scripts/source-scalar-kpis.py plan --contract scalar-contract.json \
  --identity original-row-identity.json --snapshot current-native-snapshot.json \
  --out scalar-append-plan.json
```

The identity receipt is a construction/readback artifact, never a lookup of
current mutable Opportunity IDs. Its shape is:

```json
{
  "sourceHash": "exact source file sha256",
  "documentId": "actual document ID",
  "inputElementId": "actual existing input ID",
  "rowIdColumn": "ID",
  "evidenceId": "saved original assigned-row readback",
  "reviewer": "reviewer of this original identity mapping",
  "rows": [
    {"sourceRow": 2, "originalKey": "OPP-0001", "physicalId": "actual system ID"}
  ]
}
```

Supply all 48 rows in original source-row order. No staging physical ID is
embedded in shared plugin code. Reconciliation verifies that every original
physical ID still occurs exactly once in the fresh input query. Current business
key changes and extra rows, including duplicate business keys, do not change the
scope. Missing/deleted/recreated original rows require explicit reconciliation;
the planner never guesses a replacement from sort order or current labels.
Ordinary input creation/seeding remains the existing approved input-sync route,
which preserves edits and seeds only missing rows. This planner writes no inputs.

The normalized observation has the following fields; retain the raw queries and
native captures as evidence rather than inventing these values:

```json
{
  "documentId": "actual document ID",
  "version": 51,
  "published": true,
  "hasDraft": false,
  "input": {
    "elementId": "actual input ID", "pageId": "actual input page",
    "name": "Sales Business Inputs", "rowIdColumn": "ID",
    "columnIds": {"ID": "ID", "ACV": "actual ACV ID", "Probability": "actual probability ID"},
    "nativeIdFormula": "[New Input Table/ID]",
    "filters": [],
    "rows": [{"ID": "actual physical ID", "Opportunity ID": "current mutable key", "ACV": 18000, "Probability": 0.1}]
  },
  "contents": {"pages": [], "elements": [], "layout": "complete current layout XML"},
  "nativeActions": {"hosts": ["complete native action inventory, including unsupported private effects"]}
}
```

`contents` is the complete current public source observation, not the empty
example arrays above. `input.rows` contains the complete current input query.
`nativeActions` must retain complete action host/sequence details and enabled
states. Version 51 is an example, never a current-version constant. Capture the
actual current version and any concurrent edits immediately before planning.
The API consumes trusted observations; it does not authenticate their provenance,
prove their freshness, or turn a public action omission into a native inventory.

The native source ID may be an `InputTableIDColumn`, or an observed
`FormulaColumn` containing a direct ID projection. For the latter supply the exact
observed `nativeIdFormula`; the program guards it. An arbitrary expression such
as a constant is rejected. The new KPI resolves inherited `ID` by name, or uses
the documented `add_source_column('ID')` on the new KPI only, and guards its exact
`[Sales Business Inputs/ID]` source formula. Failure never falls back to mutable
Opportunity ID or changes the input table.

The source input observation `[New Input Table/ID]` does **not** prove a new
KPI's inherited-ID representation. The new-KPI expectation
`[Sales Business Inputs/ID]` is an explicit fail-closed live gate; it has not been
established by local tests or source-input preflight. Verify its actual native
readback in the admitted construction before treating the proposed inheritance
as supported. A different representation requires a separately reviewed change,
not removal of the guard.

## Append, assigned readback and retries

The plan's `program` uses only native page/input lookup and `add_kpi`, inherited
column lookup, aggregate formula construction, format and frame operations. It
appends peers at `(1,48,12,6)` and `(13,48,12,6)` on existing `sales-overview`.
Existing placement overlap blocks the plan. No element moves or input writes are
emitted. The totals source the direct existing input, with physical `ID` finite
membership, and include every original stage/status/rep/date row.
Each nonempty program contains exactly one constructor: the first missing owner.
`missingSourceIds` retains the complete pending set, while `emittedSourceIds`
names only the owner that this invocation may construct and bind. Publish/read
back that owner, bind its actual IDs, then capture a fresh snapshot and replan
with `--ownership` to obtain the next owner. Binding an un-emitted second owner
is rejected even if it appears fully configured in the supplied observation.

Review and typecheck the emitted restricted SDK program before running it through
the established authorized native route. Every nonempty program starts with an
unconditional admission fence and the artifact reports
`BLOCKED_EXTERNAL_RUN_RECEIPT_AND_INVERSE_REQUIRED`. It is deliberately not
executable as emitted. Only an authorized external controller may remove the
fence, after durably recording a run receipt bound to the plan/program and
admitting a guarded native inverse for returned assigned IDs, including partial
creation recovery. This module does not implement or simulate that external
admission service.

The controller must compare its saved
document/version/source/schema/input/action preimages to a new observation
immediately before execution. The generated program also checks the complete
overview page element inventory before its first mutation. This blocks direct
replay after a successful or partial append. These are compare-before-write
guards, not atomic CAS or a one-use execution service.

Retain printed actual element/value-column IDs, publish through the native route,
then capture a new complete native snapshot. The snapshot must show a later
published version, identical unrelated public contents/layout, identical full
native action inventory and identical input preimages. Bind the actual IDs:

```bash
python3 scripts/source-scalar-kpis.py bind --plan scalar-append-plan.json \
  --snapshot after-publish-native-snapshot.json --assignments assigned-ids.json \
  --out observed-scalar-ownership.json
```

The assignments file maps source IDs to returned IDs:

```json
{
  "Overview!B6": {"elementId": "actual KPI ID", "columnId": "actual value ID"},
  "Overview!B7": {"elementId": "actual KPI ID", "columnId": "actual value ID"}
}
```

The example above shows the eventual full mapping; each invocation supplies only
its `emittedSourceIds` entry. The ownership file accumulates the observed mapping
across the two separately admitted invocations.

Binding checks exact current direct source, scalar formula, selected value
column, ungrouped/unfiltered semantics and placement; records complete native
element hashes; and returns source-formula hashes plus actual document/version
bindings suitable for the existing `account_formula_targets` interface. It does
not replace that function's full-source-ID coverage requirement. Public formula
readback is intentionally exact: formatting or serializer differences require a
separately reviewed normalization, never silent semantic weakening.
Each new element ID is printed immediately after `add_kpi`, before fallible
setters. Resolved projection/value IDs are printed as soon as available, before
later formula/format operations, so partial failure recovery can target only the
newly assigned native elements.

A later plan passes `--ownership observed-scalar-ownership.json`. Unchanged owned
nodes produce an empty program. Partial returned/readback IDs allow only the
missing append. Stale source/scope/document bindings, changed actual element
hashes, foreign logical IDs, or similar names without an assigned readback reject
the retry. An unknown outcome with no returned IDs requires read-only recovery
and explicit ownership reconciliation; it never creates duplicates automatically.
Partial readback here means a subset of **fully configured** exact owners. An
element created before a setter/ID/formula/format failure is not an owner and
cannot be bound by this API. Preserve its immediately printed actual ID and use
only the separately admitted guarded native inverse packet to recover it; do
not pass it as ownership or silently delete/recreate it in a retry.

## Remaining gates

Every contract, plan and ownership receipt retains `verification: UNRESOLVED`
and/or `productionStatus: BLOCKED`. Neither successful construction nor assigned
readback proves scalar query cardinality, intended-role access, display fidelity,
runtime edit/reopen behavior, source validation parity, or complete migration
acceptance. Query only the designated value column and assert exactly one row;
run independently derived baseline/dependency/blank/negative/fractional/final-row/
out-of-scope/filter vectors, preserve input preimages, restore each edit and
reopen/query again. A zero-decimal currency display must retain raw cents.

Typed numeric/null aggregate behavior is supported by the formulas. Excel text,
booleans, errors, formula overwrites, arbitrary structural edits, and input-route
blank validation are not qualified by local arithmetic tests. Native query and
rendering results remain required. Keep the existing acceptance schema, formula
denominator and chart counts unchanged.

Rollback is a guarded native deletion of newly assigned KPI IDs only, after
checking their recorded hashes and actual ownership. This stage deliberately
emits no automated rollback or public full-document restore; unsupported private
actions cannot be recovered from a public snapshot.
