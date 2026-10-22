# Corrected Forecast snapshot component

`lib/forecast_snapshot.py` implements the explicitly reviewed replacement for
`CommitForecast_Click`: all 18 financial lines in `Monthly Model!I:N`
(July–December), 108 numbers, with one separate frozen timestamp. It does not
claim literal parity with the broken `P&L!H7:M33` copy/timestamp overwrite.

`build_snapshot_definition(source, plan_hash=..., procedure_hash=..., decision=...)`
reads formula-bearing source bytes (`data_only=False`). The decision must name
an approved 18-line/108-value July–December scope and separate timestamp policy.
The definition contains financial source identities and 96 editable input field
identities; it contains no cached formula results or fallback values.

`render_snapshot_candidate(definition, current, bindings, phase="prepare")`
returns a disabled Code Mode constructor and exact controller precondition.
Bindings contain four roles (`primary`, `finance`, `operations`, `snapshots`),
actual assigned element/page IDs, complete SDK schemas, and the twelve stored
primary row IDs. Its single Prepare insert freezes 108 live numbers and 96
editable values, then carries the insert's native returned operation ID into a
hidden control. Timestamp metadata is captured once with `now()`.

After actual assigned-control readback, use `phase="confirm"`, the actual
`operation_control_id`, and the unchanged `prepared_contract` returned by
Prepare. Confirm checks the original input identities/96 values, complete
source/plan/decision metadata, and every existing snapshot key before effects.
Its 108 missing-key branches read only frozen operation columns. Existing
conflicts, duplicate keys, and foreign keys block the entire action. Both
constructors remain disabled and remove custom success toasts. Neither writes
primary inputs or automatically marks an operation successful.

Confirm balances adjacent AND/OR operands instead of accumulating deep left
folds. Operand order, duplicates, all 96 input checks, all 108 snapshot checks,
and the foreign-key blocker are preserved. This changes only boolean grouping;
lookup keys, frozen values, arithmetic, and effects remain unchanged. A staging
condition setter rejected the depth-220 fold and accepted equivalent depth-23
grouping while the existing sequence remained disabled. This is condition-setter
admission only; it establishes no general engine depth limit or event acceptance.

For an existing snapshot key, the native guard first requires exactly one row
for both the operation ID and key. It then compares all 14 stored fields with
scalar `lookup` calls keyed by that same pair, outside `CountIf`. This preserves
the missing-key zero default and every conflict/duplicate/foreign-key blocker.
In a published read-only diagnostic, `CountIf` with a cross-element `Lookup`
inside its predicate returned zero for a known matching row, while the
composite-key scalar comparisons returned true. The repaired action guard
still requires disabled native admission and a fresh full readback.

`reconcile_snapshot_rows` is a pure PREPARED-only insertion planner; its unit
data is not live evidence. `plan_snapshot_reconciliation` requires complete
captures bound to the same document/version/source/plan, table IDs, and native
row-ID column IDs. It accepts the existing `sigma-query` contract unchanged.
For hidden elements that require a REST JSON export, first call
`adapt_rest_json_export_capture` with the retained raw result, export request,
job, download request, request-provenance record, UTC organization setting,
assigned bindings, and identical same-version source GETs before and after the
export. That adapter keeps `origin: sigma-rest-json-export`, raw paths and
SHA-256 hashes, the query ID, and any reconstructed-request qualification. It
maps only the native `ID` and timezone-naive timestamps, preserving numeric
values and recording known schema fields omitted by the export. It rejects a
result at its row limit, an unsupported timezone or timestamp precision, and
missing or unexpected fields. Export requests must have exactly `elementId`,
JSON `format`, and `rowLimit`; scope options such as `offset`, `parameters`,
`tag`, and `exportAs` are rejected. It does not claim a network wire capture or
authenticate the saved request. Each normalized row includes `nativeRowId`.
Same-operation retries reuse that exact ID and frozen payload; a deliberate
new commit requires a distinct stored ID and retains old snapshot rows.

`plan_snapshot_completion` is separate from insertion reconciliation. It
requires all 108 exact rows, the owned operation's physical ID and metadata,
and a current control-value readback. It plans a disabled mark of only the
operation State to `SNAPSHOT_COMPONENT_COMPLETE`; after a fresh terminal row
readback, it can plan a separate disabled clear of the matching control.
The plan binds the observed operation state and full row-readback hashes to
its action. A terminal operation with missing rows cannot enter the completion
route. The current control readback and REST request provenance still require
independent controller review, and the native `update_rows` physical-ID
selector requires attached-action runtime admission. All completion candidates
remain `productionStatus: BLOCKED` until those gates pass.

The parent controller must freshly verify the returned public source hash and
actual rows before submitting a constructor, independently review backend type
admission, and capture resulting assigned state. Stop on any partial constructor
failure; do not replay it. A successful local compile is not backend admission.
Native actions have no multi-effect transaction or version CAS. Published roles,
recovery, concurrency, outcome reconciliation, rollback, and whole-workflow
acceptance remain separate gates. A new intent must not clear a pending
operation; clear/recover only after actual reconciliation or an explicitly
reviewed abandonment.
