# Forecast Save-scenario lifecycle component

`lib/forecast_scenario.py` and `scripts/forecast-scenario.py` provide an offline,
source-bound completion route for the reviewed `SaveScenario_Click` mapping.
The VBA appends a `tblScenarios` row before showing `InputBox`, then copies only
`Assumptions!B5` and `B6`. An empty name, canceled prompt result, or whitespace
name is preserved exactly. The two current numeric growths must be frozen in
the prepared operation and remain unchanged through completion. A deliberate
new Save uses a distinct physical operation ID; a retry uses the same ID and
must find exactly one matching Saved row.

The reviewed VBA has no blank/cancel guard. The definition therefore carries
version 1 of a narrow blank-name policy: only `Scenario Name` may normalize a
raw omitted field or JSON `null` to canonical empty text. A null name-control
readback has the same canonical value. Spaces are preserved exactly; every
other frozen field remains mandatory. Raw exports and their hashes remain
retained, and the capture records each name's original form. The disabled
native guard uses `as_text(coalesce(name, const_text('')))` for the control and
both stored name lookups. An actual blank Prepare was observed with a null
control and omitted `Scenario Name` in the REST Operations row. A later actual
Save inserted one Saved row with the same omitted name. Normalization applies
only to the raw row value after both audit tables' declared `Scenario Name`
columns have been verified as the reviewed text `LiteralEditableColumn` IDs.
Published Mark and Clear acceptance for this case requires fresh live checks.

`define --manifest ... --binding ... --audit-mapping ... --out ...` validates the existing native
action manifest and source module, then derives source/plan/procedure hashes,
the approved B5/B6 input mappings, assigned primary element/column IDs, and
all reviewed primary row IDs from the native action binding. It also binds the
authoring document/version and source-contents hash; later completion versions
must be on that document and keep the reviewed primary column IDs. The definition
contains no live IDs embedded in product source. The earlier generic Save
action schema has a smaller Saved payload; it is not an eight-field completion
receipt. The frozen operation must contain the 14 Save fields plus its actual
physical ID, and the Saved row must contain exactly eight payload fields plus
its physical ID. Extra nullable columns on the Operations table are allowed.
The separate versioned `--audit-mapping` receipt must contain the same
`sourceHash`, `planHash`, and authoring `target` as the native binding, plus a
`mappingHash` SHA-256 of its other JSON members. Its `tables.operations` and
`tables.saved` entries each contain `elementId`, `rowIdColumnId`, and complete
assigned SDK `columns` (ID, name, class, type; the physical ID uses
`InputTableIDColumn`/`kind: row_id`). The definition pins every required audit
payload column's assigned ID, type, and class. An incomplete legacy schema or
missing declared `Scenario Name` column cannot justify nullable row admission.

The hidden Operations and Saved tables may require REST JSON export. Use
`adapt-rest` separately for each role with retained absolute UTF-8 JSON files:
assigned bindings, exact unfiltered export request, job, matching download
request, actual invocation provenance, raw rows, UTC organization setting, and
identical same-version source GETs around the export. The export result must
be below `rowLimit`; native SDK `InputTableIDColumn` IDs and the public schema
must agree. `adapt-primary` uses a retained Sigma workbook query, assigned
column binding, structured/text result parity, and matching source GETs. Its
`ID` may be an approved `FormulaColumn`; it is never treated as an audit
`InputTableIDColumn`. Capture origins stay `sigma-rest-json-export` and
`sigma-query` respectively. These adapters check retained file consistency;
the controller must independently verify real invocation provenance.
When the Sigma query tool has no server execution ID, its `executionId` may be
a distinct, truthful `local-invocation:<ID>` from the actual call receipt;
`actualInvocation` records the tool and UTC call time. Never invent a remote
Sigma query ID or add invocation metadata retroactively to an older query.

`plan --definition ... --operation-id ... --operations ... --saved ...
--primary ... --target ... --name-control ... --control-value ... --out ...`
rebuilds each capture from retained files. It requires one owned, exact
source/plan/procedure-bound operation, one Saved row with all eight fields,
the complete reviewed primary identity set, and the same view's operation and
name controls. Use `--name-control-null` when actual readback is null, or
`--name-control ''` for empty text. Numeric growth fields must be typed, finite
numbers; stored timestamps must be valid UTC and preserve the full fractional precision of
the frozen `Created At`. The planner returns `MARK_CONFIRMED` only for a fully
persisted PREPARED intent with its own physical ID in the control. A fresh
terminal CONFIRMED or ABANDONED readback with the same control may return
`CLEAR_CONTROL`; an already empty terminal control returns `NONE`. Both
transition and retry proposals remain `productionStatus: BLOCKED`.

`render --phase mark|clear --definition ... --current ... --bindings ...
--completion-plan ... --operations ... --saved ... --primary ... --out ...`
recomputes the plan before emitting a disabled Code Mode constructor. It uses
the exact current contents from the retained capture source bracket and
documented `Page.get_element`, `InputTable.get_column`, `TextControl`,
`Button.on_click`, `sequence.set_condition`, `set_disabled`, `remove_success_toast`,
`update_rows`, `set_control_value`, and Sigma formula helpers. The renderer
checks an assigned primary `SingleSelectEditableColumn` class, type, and exact
allowed values when present; audit payload columns remain literal.
The renderer verifies the full assigned/public schema offline, then emits SDK
handles only for columns used in the guard or effect. This keeps sparse audit
tables with many unrelated nullable columns within transport limits while
preserving exact reviewed IDs for every required field.
The Mark guard pins the exact frozen `Created At` through `const_date` on both Operations and
Saved, along with the name, hashes, two frozen growths, physical IDs, and
unchanged primary rows. Its only effect updates the owned operation's State
through the actual native `InputTableIDColumn`. Clear has only a matching
terminal control effect. Both constructors remain disabled and emit a public
source hash/version precondition. They do not run the action or prove its
condition, selector, event, persisted transition, roles, recovery, concurrency,
or published acceptance. A controller must capture fresh readback after each
step and stop on partial failure.
