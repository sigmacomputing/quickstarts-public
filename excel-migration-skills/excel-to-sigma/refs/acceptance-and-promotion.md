# Workflow repair and acceptance controller

All tools here are offline authoring and evidence validators. The approved parent
controller makes actual Sigma calls and captures receipts, rows and browser steps.
A generated fragment, mapping review or successful SDK mutation is not runtime
acceptance. Existing code-rep/SDK input construction and display ledgers still apply.
Do not run this suite against customer data. The integration adapter requires an
explicit synthetic scope and opt-in; credentials stay inside the controller's
environment, never JSON bundles, Git, captures or reports.

## Repair workflow

Use `scripts/migration-acceptance.py COMMAND --bundle arguments.json --out result.json`.
The bundle is a JSON object of the public library's named arguments. `repair-contract`
instead takes `--source SOURCE.xlsx`. All output JSON is deterministic except the
caller's actual evidence. Python modules are in `scripts/lib`.

1. Extract `workflow_repairs.extract_workflow_repairs(source_path)`. This records
   every original formula (1865 across all fixtures), exact source formats,
   secondary literal metadata and explicit unresolved runtime status. It never
   uses formula cached values as inputs. Forecast currency display retains source
   zero decimal precision; Excel's separate zero-as-dash sections remain partial.
2. For Sales, `extend_repair_manifest(base_manifest, receipt, contract, review)`
   introduces exactly four Rep Target rows. Review binds `contractHash`, named
   `owner`, `status=APPROVED_STAGING`. Prepare new artifacts/approval with the
   existing `build_artifact_records`/staging APIs, construct the ordinary input
   using `emit_construction_program`, then capture all assigned IDs and seed/read
   back. Existing receipts cannot authorize an extended plan. Source stage and
   supplier lists are literal reference data; they do not override item inputs.
3. `prepare_repair_update(manifest, receipt, contract, current, bindings,
   scope=scope, review=review)` consumes actual assigned bindings. `scope` names
   documentId, version, connectionId, folderId and actual `folderEvidenceId`.
   Do not infer a folder UUID from the workbook GET's string `path`.
   `bindings.calculation` contains elementId, name and exact elementHash;
   Sales also requires `bindings.repTargets` from the approved receipt.
   Review contains owner, status, contractHash, planHash, beforeHash,
   identical `sourceBindings`, and `inputSystems[feature]` for every input:
   targetBindingHash, columnId and evidenceHash. The columnId is the actual
   code-rep-readable row-ID column/projection established by SDK and query
   evidence, not an invented alias or an assumption that SDK IDs equal REST IDs.
   If a native SDK row ID is not addressable in code-rep, first use the existing
   `native_actions.emit_input_identity_projection`, read back its assigned IDs,
   and review the projection as the source. Do not substitute a normalized REST
   `ID` for a different native SDK row ID without proof.
4. `readonlyFormats[elementId]` supplies exact elementHash and `sourceCells`
   mapping actual view column IDs to source cells. Supported formats and rules
   propagate to ordinary readonly tables; source rule priority is preserved.
   `technicalVisibility[elementId]` supplies elementHash and exact technical
   columnIds to hide after the SDK's additive propagation. Formula/order/chart
   encoding properties remain intact. `cleanup` supplies named owner,
   individually hashed scaffold pages/elements and actual landingPageId;
   foreign placements or active input storage cannot be hidden. New pages
   provide calculated results, reference access, navigation and full input IDs.
5. Expense additionally requires `review.currencyPatch` with elementHash,
   actual Exception columnId, exact beforeFormula and
   decisionHash=`digest(contract.currencyDecision)`. This is an explicit
   sourcePrecision=2 replacement: compare rounded integer cents, preserving
   original stored amounts. It is not claimed to equal raw FLOAT subtraction.
6. Review the generated complete contents. Call actual create dry-run
   `POST /v2/workbooks` with `proposal.dryRunRequest`. Record httpStatus=200,
   dryRun=true, evidenceId, proposalHash, errors/warnings. Then fetch fresh
   original contents and call `finalize_repair_update`; consume proposalHash
   durably before sending its fresh-version PUT. Ambiguous sends require
   readback, never blind replay. Any warning needs exact warning hash review.
7. REST can reset input display even when input JSON is unchanged. Reapply and
   verify the approved SDK display programs after the contents PUT. Rebuild
   receipts against the fresh actual version/IDs; do not merely bump an old
   receipt's version. Capture rows, names/types/classes, options and full display.
   Width/CF evidence requires separate document/browser observation; the compact
   SDK tuples establish format and visibility only.
8. `account_formula_targets(contract, targets, document_id=..., version=...)`
   requires one actual native column or explicit audit check for every source
   formula with sourceFormulaHash. Mapping does not set runtime verification.
   Research's source Audit can legitimately say REVIEW after an input edit.

Existing physical input names stay stable. Research adds a source-derived guide
for raw growth field names and a normalized metadata spine joined to the LIVE
wide input by Scope; Switch reads every numeric input and stored row ID. It
never displays original seed values as a substitute for live edits. Parent must
review/query the actual join and every normalized value after construction.
SourceOrder is the existing hidden metadata column and sort refers to its declared
ID. The edit grid must retain at least14 grid rows: `4 / 18` means height14.
`repair_research_edit_layout` makes the source/hash-bound Research input placement
`4 / 18` and guidance `20 / 34`, preserving element objects and unrelated XML;
unknown or colliding placements fail. Optional `review.researchEditLayout` supplies
its named arguments in `prepare_repair_update`, with layout_hash bound to the
generated merged layout. It must target the assigned primary input. Generic
`inputLayout` reductions also refuse heights below14. Guidance preserves a blank
paragraph before the audit explanation.

## Split native action construction

Actual SDK gaps require two reviewed routes. `native_actions.emit_native_action_program`
emits safe disabled construction and `PARTIAL_REQUIRES_PUBLIC_ACTIONS`, including
`publicActionRequirements`, `componentControls` and `componentButtons`. It never
emits whole-table CountDistinct as selected count or a Boolean update_rows selector.
Supported native-ID dictionary updates retain CountIf of the complete prior row
predicate in their event condition. The exact Prepare insert/returns factory stays
native. Clear selection context resets five controls/count0 without a row write;
the summary labels captured context. Escape clears highlighting only. Construct
once, save assigned component IDs, and capture fresh complete rows/schema/display,
REST contents and SDK actions. A construction review binds the exact disabled
candidateProgramHash, source/plan/binding/document/version. It cannot enable or
replay the constructor; saved native enabling needs its separately reviewed exact
configuration/known-artifact adapter after disabled proof.

`public-native-actions` calls `emit_public_native_action_fragments(manifest, receipt,
action_bindings, current_contents=..., sdk_actions=..., assigned_components=...)`.
The assigned_components object binds target, bindingHash, contentsHash and these maps:

- controls: emitted local alias to actual elementId, pageId and elementHash.
- buttons: emitted `workflow:local` role to actual elementId, pageId and elementHash.
- actions: exact `workflow:role` to stable sequenceId and beforeActionHash, null for
  a new action. Roles come from publicActionRequirements; undeclared roles fail.

All controls must match their actual variable-name controlId, type, source host
and assigned physical ID. Every deferred button must be present. Every table ID,
column ID, source class/options, source/plan and current document hash stays bound.
Selection count uses `CountDistinct([Selection/<verified host ID column name>])`
only on that host's on-select event. Public single-row primaryKeys uses its physical
ID, while the original event condition AND CountIf(the COMPLETE original row
predicate)=1 retains business key, original fields, context, history and operation
identity. No optimistic success or affected-row assertion is added. Staging must
serialize executions: validation and write have a TOCTOU race.

`native-action-update` calls `prepare_native_action_update` with those arguments,
the generated fragments, current contents, scope and review. This narrow adapter
rebuilds and compares the compiler output; it only appends/replaces the declared
action IDs with exact before/after hashes. Review binds beforeHash, sourceHash,
planHash, bindingHash, fragmentHash, assignedComponentsHash, sdkInventoryHash,
allowedActionEdits, `sdkAllowedChanges` for exactly the edited hosts (complete
`{sequences:[...]}` semantic configurations), and `readbackEvidenceHashes` containing
fullRows/schemaDisplay/sourceGraph actual capture hashes. Rows, input definitions,
other actions, formulas, charts, display and layout remain exact. Existing full
SDK inventory/restoration proof, actual dry-run, fresh documentVersion, one-use
send and post-REST gates still apply. REST absence never waives native Prepare
restoration; no public ActionVariable return syntax is invented.

`qualify-public-selection` calls `action_inventory.qualify_public_selection_capture`
for the one known SDK getter gap. Record unsupported getter value as
`{type:'unavailable',reason:'SDK_SELECTION_NAMESPACE_NO_GETTER'}`, never a repr.
The actual FloatSetControlValueEffect must bind both `controlId` (variable name)
and `controlElementId` (physical control ID). A named review binds actual current
document/version/contents, captureHash, fragmentHash, sourceHash/planHash/bindingHash,
plus publishedSelectionEvidence keyed by `hostElementId:controlElementId`, each
containing zero/one/multiple/clear. Every source/count-control pair, including
Operations recovery, needs its own observations; Expense proof cannot qualify it.
Each observation includes those exact hostElementId/controlElementId values and
contains evidenceId, origin=sigma-browser, published=true, current documentId/version,
memberId, identityEvidenceId, adminBypass=false and actualCount0/1/2/0 respectively.
The exact public host/source/action/effect literal must match. Qualification adds
provenance outside semantic configuration and removes stale restoration proof;
new exact restoration artifacts/proof are still required before a future full PUT.
Arbitrary opaque expressions and Missing-node repr are rejected.

The default public candidate is disabled. A separately reviewed staging probe uses
`activation='selection-probe'`, `probeOnly=true`, and
`businessActionsDisabledInventoryHash` equal to the complete current SDK inventory
digest, together with every ordinary source/current/component/fragment review hash.
It enables only Selection/recovery/clear-context handlers, each restricted to
set-control-value effects. Every other SDK write/side-effect sequence, including
REST-omitted Prepare, must be disabled unless this exact edit disables it. Existing
restoration proof is still mandatory. Clear resets all five captured controls.
This probe permits actual published 0/1/2/clear observations without a row write.

Only an enabled exact REST and SDK probe may supply published qualification. A
later `activation='business-enable'`, `enable=true` review binds the fresh disabled
candidate hashes and `disabledConstructionProofHash` of the current complete SDK
inventory. Exact control handlers must already be enabled, exact business handlers
disabled, and each Selection authority qualified at that current probe version.
Old evidence versions are never rewritten. Obtain another adapter review for the
final action deltas. Acceptance and production remain BLOCKED.

Public formula sources require the approved exact actual input name and unique
case-insensitive title among current elements. Renamed or ambiguous sources are
refused even when their IDs, columns and refreshed binding hashes are valid.

After the PUT, `native-action-readback` calls `verify_native_action_update_readback`
with proposal/readback/sdk_actions and a fresh named review binding proposalHash,
contentsHash, actionInventoryHash and allowedSemanticChangesHash. It requires exact
REST content, complete SDK semantics and preservation of every unrelated sequence.
`qualify_public_selection_construction` bridges only the exact known REST literal
and typed SDK control/host binding. It records `publicSelectionConstruction`, never
runtime authority, and needs no fabricated published counts for disabled handlers.
The readback status is `VERIFIED_NATIVE_ACTION_CONSTRUCTION_RUNTIME_UNRESOLVED`.
Actual published runtime, failure/retry,
role, persisted outcome and restoration evidence remain separate mandatory gates.

## Persisted workflow result UI

Read-only Expense formatting also handles REST columns whose names are omitted.
`propagate_readonly_presentation(..., technical_source=...)` accepts the exact
current owned Expense Register element/hash and target view hash. The view must
directly source that element and its description must bind the Expense source
contract. Only whole direct references to that exact source's Last Approval
Operation ID and Applied Approval Operation IDs become hidden. Foreign sources,
expressions/comments and ApprovedAt are preserved. `prepare_repair_update` derives
this binding from its already validated calculation source and reviewed view
hash; no column IDs, formulas, order or names change.

`operation_outcomes.build_outcome_view(binding)` projects persisted operation
state. Pending/prepared states say "Pending verification". It has no optimistic
action-chain success effect. `reconcile_operation(expected,capture,operations,
completed_at=...,manifest=...,receipt=...)` requires the validated source manifest
and its APPROVED_STAGING receipt for the assigned workflowOperations input.
The complete operations capture must carry sourceHash/planHash/documentId/version,
origin=sigma-query, executionId/evidenceId, exact assigned binding, typed SDK
schema and a rowIdBinding (sourceColumnId, readbackColumn, targetBindingHash,
reviewed evidenceHash). The approved target supplies rowIdColumnId, or the
reviewed systemColumn alias. This separates the physical SDK row ID from the
query label. The reconciler then runs the existing native business audit against complete
before/after rows, exact operation/context/source/plan/document/version and a
fresh sigma-query evidence reference. It emits a narrow SDK follow-up setting
CONFIRMED only for the original pending operation. Execute it serially per
workbook, query every operations row again, and use `verify_outcome_row`. Its
sealed plan binds the original capture, assigned destination, complete intended
rows, exact outcome text and completion timestamp. Verification requires a new
query/evidence identity, the same target/version/schema/row-ID binding, and
exact intended fields with every unrelated row preserved. The SDK has no
compare-and-swap/concurrent uniqueness guarantee; cross-effect partial failure,
wrong-row prevention and recovery still require published UI acceptance. Failed
or unconfirmed business reads produce no CONFIRMED write.

## Mandatory acceptance and reports

`acceptance.build_acceptance_matrix(manifests, targets, receipts=..., oracles=...)` requires all
five validated source manifests and their APPROVED_STAGING assigned receipts.
Each manifest must name its current target document/version. Targets record actual staging documentId,
version, url, sourceStatus, unresolvedSourceFeatures and isolated warehouse input
identities (connectionId + tableIdentity). inputTables must cover exactly every
feature in the final sharedInputArchitecture, including settings, companions and
operations. Each descriptor names assigned documentId/version/pageId/elementId,
source connectionId, tableIdentity, targetBindingHash and identityEvidenceId.
The sealed matrix retains the approved manifest/receipt; production and isolation
validation recheck coverage and reject omitted, extra, stale, foreign or duplicate
assignments. `assert_isolated_inputs` refuses
original/shared writeback identities; a copied workbook ID alone is insufficient.
All mandatory case templates remain unresolved until evidence is recorded.
Oracles are independently reviewed source equations/goldens, not translator
outputs: origin=independent-oracle, reviewer, sourceHash, keyed checks with
expected/comparison (money, ratio with explicit precision, date, exact).

`record --bundle {matrix,capture} --state ledger.json --out checkpoint.json`
locks and atomically appends the hash chain. Capture includes exact caseId,
evidenceId, sourceHash, planHash, documentId, version, executionId, references,
origin=sigma-query or sigma-browser, actual keyed values, receipt containing
COMPLETED and the same execution/document/version. Browser proof additionally
requires published=true/publishedVersion, steps, screenshots, actual session
memberId/accountType/effectiveGrant/editInputTables, identityEvidenceId and
adminBypass=false. Role cases also require dataEntry.inputMode and
editDataAvailable. Editor and Explorer each require validSaved=true, a positive
writeCount, and complete
changed/reopened/restored physical-row persistence; Viewer requires writeCount=0.
The roles do not each claim invalid-entry or Cancel branches. Real published availability derives from entitlement,
effective inherited grant AND table mode. Explorer is the selected Build user
with Explore document grant, not Analyze-account parity. Do not broaden roles.
Each workflow's existing count-one `zero-and-invalid-entry` browser case carries
a source-derived `validationContract`: every authored Excel rule, assigned input
element/column, boundary or list equivalence branch, and one Cancel/no-effect
branch. The production validator recomputes the contract from the pinned source
and approved input receipt. Its independent oracle must declare that exact branch
outcome vector. Each branch needs its own actual published browser execution,
matching session/target/typed attempted value, steps/screenshots and COMPLETED
receipt. Each branch binds the exact source/plan and has a browser execution
reference in both its branch record and the parent capture. Complete physical
rows must show a saved/reopened/restored change for a
source-valid entry, or exact unchanged rows after rejection or Cancel. A generic
`true`, a query/service write, an omitted rule or a foreign target cannot fill
the case. A source field without Excel validation is not assigned an invented
rejection rule; Sales `Assumptions!F2` is such a field, and its observed NULL
save remains an unresolved usability safeguard outside this source-rule case.
The contract also pins the approved input's exact editMode, full assigned
column IDs/types, source business keys and row count, plus its page/element,
connection/storage and target binding. Parent `dataEntry.inputMode` and each
branch `inputMode` must equal that approved editMode; the session grant must
permit it. The parent `validationInventory` is a fresh `sigma-query` readback
of the complete assigned input. It carries `rows`, the actual `rowIdColumn`,
`physicalIdMap` entries `{sourceKey:[...], physicalId:...}`, all assigned
`columns`, `binding`, `rowsHash`, execution/evidence IDs, source/plan hashes,
and a COMPLETED receipt repeating those binding/schema/hash/ID fields.
Every `rows.before/after/reopened/restored` phase has its own distinct
`rows.readbacks[phase]` query receipt with the same metadata and a hash of
that phase's complete rows. Every query execution has a reference in the
parent capture. All phases must preserve the inventory's complete source-key
to physical-ID map and exact column set; before/restored equal the inventory,
and only the declared target cell may change on a saved branch. The controller
must obtain physical IDs from the actual assigned readback; source rows alone
cannot supply them. Older captures without these receipts remain unresolved.
Persistence captures contain complete before/changed/reopened/restored rows,
rowIdColumn, keyColumns, allowedChanges and reopen/restore evidence IDs. At
least one final business value must differ from before; same-value and cancelling
edits fail. Each allowedChanges entry may declare comparison/precision (default
exact); changes below its declared money/ratio/date precision do not prove an edit.
Reopened, restored and allowed-delta snapshots still compare complete typed rows.

`reports --bundle {matrix,ledger,final_review} --out reports.json` renders portable
per-workflow structured results and Markdown. Each report explains workflow
rules and shows genuinely passed, failed and unresolved mandatory denominators,
source formulas, URL/version and evidence references. Final review binds matrix,
ledger head and exact branchCommit. Source REVIEW_REQUIRED/unresolved features
cannot become VERIFIED_COMPLETE. Reports call
`validate_production_matrix` before any completion verdict. Reduced component
reports retain their own denominators, but say coverageStatus=COMPONENT_ONLY,
verdict=BLOCKED and explain completionBlockers; final approval cannot bypass
the full mandatory suite. Promotion retains the same production gate.
`run_integration(matrix,adapter,scope,enabled=True)` is opt-in controller injection:
adapter.capture receives case/target/designated synthetic scope and returns
actual evidence. Before the first adapter call, scope.stagingInputs must equal
the exact matrix union keyed workflow:feature, with no missing/extra table,
shared original storage, duplicate storage or connection outside scope. It does not log credentials or invent an HTTP/SDK execution API.

## Original URL preserving promotion and rollback

`promotion.build_promotion_backup(scope,current,rows,sdk,data_models)` requires
named owner/sourceHash/planHash, original documentId/version, full contents,
every affected input row with stable ID and unique business key, complete typed
SDK schema and display/visibility/options tuples, and complete affected DM
contents/versions. Hashes bind the entire backup. Capture before any warehouse
write. System audit timestamps cannot be recreated; do not claim otherwise.

`prepare_promotion(backup,fresh,candidate,review,acceptance)` preserves the original
ID and URL. Review names owner/backupHash/candidateHash/targetDocumentId,
replacementIds and allowNewIds. Acceptance is the full {matrix,ledger,finalReview}
bundle; a boolean or "complete" string is rejected. All five complete mandatory
suites and final reviewed exact candidate/original target are required.
`finalize_mutation` additionally requires actual hash-bound dry-run and fresh
version, then returns a consume-before-send PUT. Checkpoint each real outcome
with `checkpoint --bundle {backup,event} --state ... --out ...`; no successful
step replay. Inspect actual state after ambiguous/failed calls before resuming.

`prepare_rollback(backup,fresh,current_rows,owned_added_rows=...,fresh_data_models=...)`
restores original business values by immutable row ID, affected DMs with fresh
versions, original workbook document, then SDK display LAST, then complete
readback. It refuses missing original IDs and unrelated extra rows. Only
explicitly owned added row IDs can be deleted. Its narrow SDK programs guard
page/table/complete classes/names/types/options before mutation. Reverting REST
alone cannot undo warehouse values or restore display. Run `verify_restoration`
with the complete actual document, rows, SDK display and DMs after rollback.

Generated rollback/outcome headers and input display/readback programs use explicit
loops and dictionary membership for full column inventory. They reject duplicate,
missing or extra schema/ID entries before setters or row effects. SDK programs do
not use set(), set literals/generators, subset methods or tuple-class isinstance;
select metadata is read only inside its explicit concrete class branch. Display
programs import their public SDK classes and preserve source allowed values.
These known-dialect AST checks and effect-recorder tests are offline admission
regressions, not proof of actual MCP typechecking or rollback execution. Original
URL promotion remains blocked until actual source-bound runtime/rollback proof.

Construction and resumable seeds preserve fractional datetime microseconds as an
integer seventh constructor argument, after existing UTC normalization. Zero
fractions retain the six-argument form and date-only values retain the explicit
noon policy. The actual read-only SDK admitted this constructor; actual input
storage precision and reopen/rollback roundtrips still require runtime evidence.
Backup/promotion/checkpoint JSON cannot authenticate itself: the designated
controller captures real calls; independent review verifies their provenance.

`secondary-input-hosts --bundle {contract}` emits dedicated new assumption pages.
New Rep Targets placement starts below its source guide; bind the new input to
that dedicated reviewed page, never to an old page with unreviewed overlapping
frames. `published-mode` consumes manifest, receipt, feature and exact reviewed
restricted published-mode decision and returns the SDK program. Existing primary
input modes are preserved; only reviewed SalesSettings/ExpensePolicy are changed.
The repair proposal automatically includes a persisted Workflow results view
when the receipt contains workflowOperations.

`rebind-repair` calls `rebind_after_repair(manifest,receipt,proposal,readback,
sdk_observations,review)`. SDK observations have documentId, version, evidenceId,
and tables[feature] with elementId and actual column descriptors. Review binds
contentsHash/sdkHash and systemColumns[feature].observationHash,
rowIdEvidenceHash and, for a FormulaColumn normalized alias, approvedAlias using
the existing complete row-ID contract. Source-list conversions require fresh
columnContracts. Exact added contents must round-trip; unknown normalization
stops. The result is a fresh assigned receipt/target version, never an edit of
an old receipt's version field. Formula accounting also requires fresh
current_contents and actual elementHash; explicit audit checks additionally
name independently reviewed source equations.

The five functions in `fixture_regression.py` are reusable independent hand
source equations for the designated fixtures, including edits keyed by exact
source cell. They read literals only and reject a formula cell in the literal
path. They cover Forecast144 monthly values and234 P&L/FY values,132 expanded
records plus secondary rows, and420 Research values including all equity inputs.
Research's archived JSON golden rounded EPS before some downstream ratios;
source39/44 formulas instead divide by live EPS. Tests keep this distinction
explicit and compare source equations rather than freezing that rounded cache.
The existing native/AST regression suite remains in place. Actual null entry,
validation, cent boundary and all published behavior still require actual tests.

## Separate decimal text transport adapter

Parent actual provisioning established the distinct
`SIGMA_WRITE_DB.SIGMA_TASK5_SP_TEST.TASK5_TYPED_ECHO_TEXT_AMOUNT` wrapper; exact
reference source is `tests/fixtures/task6-decimal-text-procedure.sql`.
`decimal_procedure_adapter.controlled_decimal_text_contract(connection_id)`
starts with signature=null and BLOCKED. It binds wrapper body trimmed SHA256
`1df68a1cc86017ef93cebcc5e554873894080ff6f029ba46630393d3217b9abc`
and unchanged original callee
`f544541aa79453bcd828baa304c6c1ecc4c7249bf1f181fd3dfbe8642c1960ed`.
It rejects binary floating amount transport. The exact reviewed ASCII text
amount is checked before fixed-point conversion by the wrapper. All five
original business arguments remain ordered and typed; count is integer and
NTZ timestamp uses the independently date-validated native Datetime formula.

`decimal-adapter --bundle {contract,arguments,prior_invocation}` emits an action
only after actual catalogObjectId, lookupEvidenceId, callerEvidenceId,
scalarMappingEvidenceId, datetimeEvidenceId, provisioningEvidenceId and
signatureEvidenceId, plus exact ordered lookup metadata, are present. No guessed
or PENDING signature is accepted. `build_decimal_text_port_fragment` provides a
new, guarded-merge-compatible isolated button page. Same-operation retries bind
the exact text spelling/contract. Verify returned exact scalar, invalid/NULL
cases, no dependent effects after error/timeout and actual roles. Provisioning
is not native scalar parity. Original NUMBER transport remains separate and
blocked: actual Sigma lost1234.56 cents while direct typed SQL preserved them.

Warehouse Python runtime maps are exact per element/logical column. When actual
metadata requires distinct Snowpark identifier and collected Row key, pass
`{"identifier":"\"Line Item\"","rowKey":"Line Item"}`; a string means both
are identical. The emitted program validates both, with no casefold, unquoting
or fallback. Every Sigma accessor/output name is a literal. Native MCP action
programs use individual isinstance-narrowed local column handles, not dictionary
subscript narrowing or unsupported Python annotations.

## Mandatory SDK action backups after actual REST omission findings

Public REST GET has actually omitted persisted SDK-native Prepare and selection
sequences. It is not a complete action backup. Before every repair/promotion PUT,
provide a fresh SDK action inventory covering **every document element**, including
explicit SDK observations of zero sequences. `action_inventory.empty_action_capture`
is only a `TEMPLATE_NOT_RUNTIME` shape helper and cannot pass validation.

Inventory: `{documentId, version, evidenceId, origin:"sigma-sdk-readonly",
complete:true, elements:{elementId:{elementId, complete:true,
inspection:"list_action_sequences"|"sdk-type-no-action-events", sequences:[...]}}}`.
Each sequence records actual id/name/trigger/disabled/condition/ordered blocks/
successToast. Typed blocks record all table/control/page targets, values,
selectors and insert return-variable bindings. Toasts include title/message/
formulas. Unknown or incomplete block types stop. Known API-created Python or
procedure blocks may use an explicitly reviewed dual REST/SDK artifact when the
SDK cannot represent that effect; REST absence alone never establishes absence.

Current SDK Formula has no expression getter. Store opaque observations verbatim
and bind them to the exact known construction artifact and assigned IDs; never
decompile or evaluate their repr. For nonempty sequences, `semanticHash` is the
canonical digest of `configuration(element)`, which preserves all observable
configuration except assigned sequence IDs. It is recomputed, so changing a
condition, disabled flag, block or toast without updating the actual reviewed
configuration cannot pass preservation.

Every action-bearing element requires `restorationArtifact`: elementId,
documentId, reviewer, sourceObservationHash (digest of the element observation
excluding that artifact), semanticHash, program/programHash, constructionArtifactHash,
bindingHash, guardPolicy exactly
`missing-sequences-only; exact-current-target-and-bindings; no-constructor-replay`.
Its `restoreProof` must record actual PASSED_ISOLATED_RESTORATION,
beforeMissingSequences=true, evidenceId, isolated documentId,
sdkReadbackEvidenceId and identical programHash/bindingHash/semanticHash.
These are reviewed per-action restoration programs; the tool does not generate
a fictitious generic SDK action decompiler. Opaque/unknown actions without that
actual proof remain BLOCKED_ACTION_RESTORATION. Full constructor replay after
partial persistence is prohibited. Only reviewed, current-state, missing-sequence
restoration is eligible for execution, followed by full fresh SDK readback.

`build_promotion_backup` additionally takes `sdk_actions` (or the explicit
`scope.sdkActionInventory` capture). Repair review also requires
`sdkActionInventory`. Both document finalizers require `fresh_sdk_actions`.
`rebind_after_repair` requires post-REST `sdk_actions`; `verify_restoration`
requires complete final `sdk_actions`. `verify_action_preservation` compares all
old elements' observed configuration before/after independently of REST JSON.
Rollback order is rows → data models → document → reviewed missing SDK actions →
SDK display → actual readback. When an edit mode was explicitly changed,
`changed_edit_modes` names the expected current mode; only those modes are
restored. Recreated sequence IDs and immutable warehouse audit timestamps are
qualified separately rather than falsely claimed identical.

Generated rollback/outcome SDK programs use integer `datetime(...)` constructor
literals; `datetime.fromisoformat` is not exposed by the actual MCP SDK. Parsing
stays in the controller. Aware timestamps normalize to UTC, with every
microsecond retained; typed timestamp readbacks must match that exact instant.
Captured date-only values restore at midnight, while authored source-only dates
retain the seeding policy of noon. Other fields and row IDs remain exact. Local
constructor/effect-recorder tests do not establish actual storage precision or
successful rollback: fresh complete row/display/action proof is still required.

The parent observed a partially persisted native constructor at Operational v7:
SDK typing succeeded, but a BoolFormula row selector failed `invalid_formula`
after five controls, two buttons and Prepare/selection sequences persisted.
Consumed attempts cannot be replayed. The selector/recovery and zero/one/multiple
selection behavior remain actual runtime acceptance gates. A global
CountDistinct(column) is not assumed to equal the selected-row count and is
never silently replaced with constant1. Forecast source inspection subsequently
proved quoted identifiers differ from collected Row keys at v9; explicit paired
runtime maps address that compiler/runtime boundary.

Actual ordinary input factories may expose native `InputTableIDColumn` with name
`ID` and an assigned physical column ID. Preserve that observed name: the
default `Row ID` contract is not a reason to rename it. Bind `target.systemColumn`
to exact `id`, `name: ID`, `columnClass: InputTableIDColumn`, `type: null`,
`systemKind: row_id`, `formula: null`, `elementId`, and `sdkEvidenceHash`. Its
ID must equal `target.rowIdColumnId` and differ from every editable column ID.
The evidence hash is reviewed capture provenance bound into the receipt, not an
SDK getter. This explicit route retains physical-ID/name/class/kind/owner guards;
it grants no arbitrary name normalization or row persistence proof. The existing
`Row ID` default and explicitly evidenced FormulaColumn alias route remain.
