# Explicitly reviewed custom ports

`custom-ports.py` and `lib/custom_ports.py` author candidates offline. They do not
execute VBA, Python in Sigma, SQL, grants or network calls. A Python availability
probe is not business parity. Production remains **BLOCKED** until actual runtime
acceptance; `validate_completion` checks the additional custom-port case ledger.

The controlled artifacts in `tests/fixtures/task5-controlled-*` are a newly
reviewed source, a real XLSX companion, model data, independent golden values,
and the exact reviewed V3 scalar procedure declaration. The BAS is raw source,
not a compiled XLSM. Do not execute it. The illustrative `Sample Macros.bas` stays
unchanged: missing `PostToGrid`, refresh and external email remain unresolved.
The Hello World binary demonstrates extraction only.

## Public interfaces

- `build_custom_port_plan(base_manifest, base_receipt, module_path=..., fixture_path=...,
  expected_path=..., reviews=..., scope=...)` extends the existing manifest with
  three ordinary input companions, exact source/procedure/helper hashes and named
  custom reviews. It preserves the prior formula mappings and shared inputs.
- `validate_custom_port_plan`, `source_helper_inventory` re-open/hash the source.
  The custom helper inventory distinguishes reviewed VBA intrinsics/labels from
  missing helpers; it does not change automatic native analyzer classifications.
- `build_port_input_specs(forecast_input_template)` adds headcount, overhead and
  one `Goal Seek Invocation` row with `State=UNPREPARED`. All new tables use SDK
  string `editMode='published-explore'`. Existing companion modes stay unchanged.
- `emit_python_programs(model_binding, column_maps=...)` returns standalone source,
  output schema, column order and code hashes. DOUBLE output cells become finite
  Python floats, INTEGER excludes Boolean/Decimal, BOOLEAN stays bool and STRING
  stays str; nonfinite numbers become null. A typed failure fallback prevents an
  invalid diagnostic cell from breaking output emission. The math kernel stays
  unchanged. `build_port_fragments` defaults to two code/run-button pairs only.
- `prepare_port_update(..., phase='code-first')` checks the exact source/title/
  connection graph, builds an append-only new page, and returns a
  `POST /v2/workbooks` dry-run body. `solver-outputs` and `guard-output` require
  previous_phase, output_evidence and phase_context. Atomic complete mode fails.
  `finalize_port_update` requires hash-bound actual HTTP 200/dryRun evidence and
  fresh unchanged contents/version before returning the versioned PUT request.
  Unknown existing IDs/titles are refused. `audit_port_update` compares readback.
- `solve_forecast`, `guard_goal_seek`, `plan_goal_seek_write`,
  `verify_goal_seek_write` expose pure computation/verification. They never mutate
  their inputs or persist assumptions. `build_goal_seek_actions` emits separate
  compute/guard/apply sequences for one exact operation, result and current model.
- `controlled_procedure_contract`, `build_procedure_action`,
  `audit_procedure_result` enforce the exact typed scalar contract and stop-on-error
  semantics. A pending signature cannot produce an action.

The CLI offers `prepare`, `emit-python`, `prepare-update`, `finalize-update` and
`prepare-goal-actions` and `procedure`; `--help` lists mandatory paths. All commands require `--out`. Review
and execution are separate; emitting an artifact does not authorize its submission.

## Construction and review runbook

1. Start with the current source-bound forecast manifest/approved input receipt.
   Obtain fresh staging contents and actual source/input/column/physical-ID rows.
   The scope binds `status=APPROVED_STAGING`, named `owner`, `documentId`, `version`,
   `folderId`, `connectionId`. Only the designated staging workbook is permitted.
2. Review all three mappings by exact `procedureId` and `procedureSha256` from
   `analyze_macro_source`. Each review has `mappingKind=reviewed-custom-port`,
   `reviewStatus=approved`, named `reviewer`, `decisionId`,
   `acknowledgeUnsupportedImperative=true`, `sourceOrigin=new-controlled-fixture`.
   This acknowledges the bounded analyzer's remaining imperative uncertainty; it
   is not automatic native approval. Bind the BAS, XLSX and independent goldens.
3. Build/restage the extended manifest with existing `input-sync.py` artifacts.
   An old receipt's plan hash cannot authorize these new tables. Use the existing
   ordinary-input constructors and resumable natural-key seed path for
   `task5Headcount`, `task5Overhead`, `task5Invocation`. Confirm published explore
   edit mode and preserve all original forecast rows/columns/values/IDs.
4. Add a reviewed **read-only** `Input Row ID` projection to Forecast Inputs View
   using the Task4 identity projection pattern. Do not turn a cached value into
   a live model. Actuals, Forecast Inputs View, Forecast Line Definitions,
   Forecast and PnL Combined must resolve to the same connection as all code
   elements; preserve the current actuals/manual/flat/growth equation graph.
5. Prepare `sources`: exact unique title -> `{elementId, elementHash}` using
   `_digest(actual_element)`. Required titles are Actuals, Forecast Inputs View,
   Forecast Line Definitions, Forecast, PnL Combined, Goal Seek Invocation,
   Task 5 Headcount Inputs and Task 5 Allocation Assumptions. The model binding
   hashes these sources, their full recursive element-source graph, workbook,
   controlled source files and equation version. Recheck that graph before every
   new solve/apply. Any model metadata change requires a new reviewed binding.
6. Inspect actual Snowpark `.columns`. Supply `column_maps` as title ->
   `{logical_display_name: actual_dataframe_column_name}`. Unmapped exact names
   are allowed; missing/duplicate names fail closed. No inferred case folding.
   Call `prepare_port_update`; review its complete diff and hash. The default
   code-first phase adds exactly allocation/solver code and their run buttons,
   with no output children, guard code, assumptions write or procedure action.
   It retains all original objects/layout and adds a dedicated page. Submit its dry-run body
   through the supported POST path. Capture `{httpStatus:200,dryRun:true,warnings,
   evidenceId,proposalHash}`; independently review nonempty warnings by hash.
7. GET immediately again, call `finalize_port_update`, and durably consume its
   proposalHash AND phaseId **before** sending the PUT exactly once. After timeout inspect
   actual state rather than replaying. This offline library takes a consumed-ID
   ledger; it cannot enforce concurrency against a caller that omits its ledger.
   Capture returned version/IDs and GET readback via `audit_port_update`.
   Server ID rewrites or any unexpected normalization stop for explicit rebinding.
   Full-contents REST may reset ordinary input display; apply final SDK display/
   visibility last, as a separately reviewed step.

## Output materialization phases and actual evidence

A successful Python execution is distinct from a successful business result.
An UNPREPARED/invalid-operation failure row can materialize the explicit schema;
it cannot qualify business parity. Python execution FAILED/old output never
qualifies a new child. Output metadata must be actually observed, with explicit
paired warehouse identifiers and Row.as_dict keys. Do not derive those pairs by
unquoting labels. Supplied expected schemas are not runtime observations.

`code-first` can emit a reviewable partial proposal without phase_context, but
finalize refuses it. Every submitable phase requires a current phase_context:
origin=sigma-controller-actual, evidenceId, documentId/version, contentsHash,
receiptHash, inputValuesHash, schemaDisplayHash and rawCaptureHash. Those hashes
refer to complete actual normalized input values/IDs and source-bound schema/
display captures, with the raw capture retained. A named APPROVED_STAGING review
binds captureHash of the entire context excluding review. sdkActions covers
exactly every non-Code element and must be recovery-ready, including actual
isolated known-artifact proof for actions omitted by REST. Current MCP omits Code;
do not manufacture SDK Code observations. codeObservations instead covers only
the exact owned Code IDs with origin=sigma-code-rest-ui-readonly, evidenceId,
current documentId/version, exact elementHash/codeHash and
inspection=public-code-schema-no-action-events. The current public Code schema
has id/kind/code/connectionId and no action events; unknown Code or actions block.
This explicitly scoped REST/UI qualification is separate from SDK provenance.

After construction, capture actual execution IDs and actual output metadata.
`solver-outputs` requires BOTH allocation and solver outputs from the installed
code-first proposal; it proposes allocation/goal output children and guard code/
run button. `guard-output` requires actual guard execution/metadata before its
child. Each phase seals ownedPortElementIds and phaseLineage across all previous
phases; later per-intent goal actions require the completed guard-output graph.
No successful source rehash or metadata capture clears runtimeStatus UNRESOLVED,
productionStatus BLOCKED or workflowComplete false.

output_evidence has origin=sigma-python-output-actual, evidenceId, current
documentId/version/contentsHash/receiptHash, sourceHash/planHash/modelBinding,
installedProposalHash and outputs keyed exactly by allocation+goalSeek or
applyGuard. Its named APPROVED_STAGING review binds captureHash excluding review.
installation records VERIFIED_COMPONENT_CONSTRUCTION, the previous proposalHash,
documentId, actual installed version/evidenceId and exact installed contentsHash.
Each output record binds codeElementId/codeHash/outputName/connectionId, and:

- execution: origin=sigma-run-python-actual, status=COMPLETED, actual executionId/
  evidenceId/documentId/version and exact codeElementId/codeHash. The execution
  version must be between actual installation and current capture. A business
  FAILURE is allowed only as materialization, never acceptance.
- metadata: origin=sigma-python-output-metadata-actual, evidenceId/executionId,
  current documentId/version, outputName, rawCaptureHash and actual sourceNamespace.
  observedFields contains exactly outputColumn, identifier, rowKey, type and
  formula for each observed field. INTEGER remains integer (not generic number).
  formula is the exact observed single-source reference from actual metadata;
  the native example is `[Code: AllocationResult/OperationId]`. The compiler
  copies it; it does not invent `[Code Output/...]` or infer a namespace.
- metadataHash seals that metadata. columnMap explicitly maps each logical output
  field to its observed outputColumn/identifier/rowKey/formula. Both names and
  observed types must match actual metadata uniquely. Each outputColumn must
  equal its fixed emitted semantic field name exactly; same-type field swaps
  are refused. Identifiers and row keys remain explicit observed pairs; no
  case-folding or unquoting inference. Guard code receives only
  actual GoalSeekResult Python output identifier/rowKey pairs, keyed by its
  `sigma.output` reference name; no fabricated ninth map.

`audit_port_update(proposal, readback, post_phase_context=...)` requires fresh
reviewed controller context, including complete supported-element SDK inventory
and separately qualified owned Code observations. Input-values/display hashes
must equal the reviewed pre-update context. Exact REST equality alone cannot
return construction/adoption success. Every next phase independently compares
the previous phase's original SDK inventory with current actual observations,
so REST-omitted native actions cannot disappear between phases. New SDK hosts
are restricted to declared phase additions or exactly observed adopted native
children; tables have no actions. EVERY owned port button, including buttons
already in an initial native-adoption inventory, must equal the known pure
RunPython constructor. Preparation, post-update audit, later-phase advancement
and fresh finalize require exactly one enabled unconditional on-click sequence
and one RunPythonElement targeting the assigned port code/name. Existing owned
inventory membership never exempts a button from this check. Unrelated old known
actions remain governed by exact preservation, without being reclassified as
port computation buttons. Runtime and production completion remain unresolved.

Every generated/adopted port button REST action has `successToast.showMessage`
exactly `hidden`. Actual SDK successToast must be None or the exact empty default
title/message/formulas object (null/empty text and empty formulas). Any custom
title, message or formula is refused, including an optimistic "Assumptions
updated" claim. The SDK provides no visibility getter: qualification explicitly
binds the exact hidden REST constructor and actual empty typed SDK observation;
it does not invent a getter or claim that successful computation wrote inputs.
Audit includes ownedPortButtonQualifications in its action-preservation proof.

Old ordered SDK sequence configurations and assigned IDs must stay exact. If an
actual known-artifact restoration assigns new IDs, current phase context includes
`actionRestorationReview` with named APPROVED_STAGING owner/evidenceId, current
documentId/version, beforeInventoryHash/afterInventoryHash (SDK inventory digests),
assignedSequenceIds mapping each changed host's old→actual new sequence IDs, and
restorationProofHashes mapping those hosts to the digest of their actual existing
isolated restoreProof. Every current sequence still needs the ordinary exact
reviewed missing-only restoration artifact/proof. This narrow qualification
cannot change sequence semantics/order, permit an unknown host or excuse a lost
sequence. Missing, stale or ambiguous restoration identity evidence is refused.

`finalize_port_update(...,fresh_phase_context=...)` rechecks current input/display
semantic hashes and complete SDK actions immediately before sending, alongside
the existing exact dry-run/version/content/consumed gates. It refuses stale,
missing, foreign, pending, failed and expected-only captures, changed owned code,
wrong paired names/types, skipped phases, collisions and consumed phaseId replay.
CLI prepare-update adds --phase, --previous-phase, --output-evidence,
--phase-context and --consumed-phases; finalize-update also takes --phase-context.

**Current platform limitation:** POST dry-run validates a scratch document and
has actually returned HTTP400 output-not-found even after a target execution
materialized AllocationResult. Phasing alone does not establish that route works.
The current finalizer refuses every400; it never fabricates200. Target-bound actual
metadata plus an explicitly reviewed supported native-child/adoption route is
required. Unknown normalization or unavailable metadata stops construction.
No HTTP400 exception is implemented. A remaining guard code/button installation
blocked by scratch validation stays blocked; saved guard component adoption is
outside this bounded implementation pending actual evidence.

Native children can be adopted explicitly in each output record using
nativeChildObservation: origin=sigma-native-code-output-child-actual, evidenceId,
current documentId/version, assigned elementId/elementHash, rawCaptureHash,
typedColumns (actual complete API entries/total/nextPage), typedColumnsHash and
columnIds (logical field -> actual assigned ID). Every observed label/formula/type
must match the explicit map and current native column; the exact code-output
source must be unique. Goal/guard children require the actual unique titles
`Goal Seek Result` / `Goal Seek Apply Guard` for workbook bindings. The guard
reads the solver output with `sigma.get_element('GoalSeekResult')` and maps its
columns under that same Python output reference name.
Allocation may retain an unnamed native view because it is queried by assigned
ID; no title is invented. The phase preserves all existing child objects/IDs/
layout, reports adoptedElementIds separately, and never claims the earlier PUT
created them. Later goal action bindings use the sealed native guard column-ID
map when REST omits column names, and its actual assigned guard element ID.

If the final phase only adopts a native child, restMutationRequired=false and
constructionStatus=VERIFIED_NATIVE_ADOPTION_NO_REST_SEND. audit_port_update checks
the same current version/contents and returns VERIFIED_COMPONENT_NATIVE_ADOPTION;
finalize refuses a redundant PUT, even with200 evidence. This establishes actual
component adoption, not computation/published business success.

For previously installed exact code-first objects after an independently reviewed
code repair, optional adoption_evidence uses origin=sigma-code-first-native-adoption-actual,
evidenceId, current documentId/version/contentsHash/receiptHash, sourceHash/planHash/
modelBinding and elementHashes for the exact two code/run-button pairs. A named
APPROVED_STAGING review binds captureHash excluding review; exact compiled object
bytes and assigned page ownership plus the complete current phase_context must
match. It returns a no-send adoption record. Subsequent installation evidence then
uses VERIFIED_COMPONENT_NATIVE_ADOPTION, not an invented executed PUT. Code bytes
from a different version/hash cannot be adopted. CLI prepare-update exposes
--adoption-evidence. No constructors, native edits, runtime runs or transport are
executed by these helpers.

## Python execution and stale-output protocol

The runtime uses provided `sigma` and `session`, standard-library math/json/
hashlib/decimal, `sigma.get_element('Unique title')`, `.columns`, `.collect()` and
`Row.as_dict()`. It does not require repository files in the warehouse. It creates
an explicit typed output DataFrame and calls `sigma.output` once unconditionally,
with a literal no-space name. There are no external packages/network integrations.

Allocation computes `(hc[i]/sum(hc))*overhead*(1+0.5*sin(i))` for one-based indices
1..4 in radians. Full doubles are returned, not rounded/normalized. Null/text/
boolean/nonfinite/negative/zero-total cases return one explicit failure row.
Golden values total `128096.06870260219`, intentionally exceeding `100000`.

The forecast solver reads every current keyed row, all six actual months and
June bases, all twelve forecast inputs and section definitions. It uses actual
plus manual/flat/growth forecasts; only Subscription Revenue's growth is replaced
in memory. It validates keys, periods, numeric values and methods, rejects zero
sensitivity/nonfinite endpoints/unbracketed targets, and uses at most 64 bisection
iterations in `[0,.25]`. ToleranceCents is **1** (`$0.01`), growth precision is 12
places using round-to-even, and the rounded solution is re-evaluated before success.
Fingerprints sort required rows and use Double `.17g` canonical strings, a single
zero, explicit null, and SHA-256 over canonical JSON. Numeric Decimal/float values
with the same Double representation bind identically. Output retains operation ID,
model binding, input fingerprint, physical subscription row ID and prior growth.

1. Prepare a durable Task4 operation (or explicitly supplied test UUID). A retry
   reuses the ID and payload; intentional new work uses a new ID. Store it in the
   one-row invocation with RequestKey=goal-seek and State=PENDING **before** Python.
2. Run the solver and read the output. Do not infer success from the run effect.
   Each attempt returns a new-operation failure row when input reads fail. If a
   platform failure leaves old materialized output, the new pending ID blocks it.
3. Set APPLY_PENDING using the same ID and run the separate apply guard. It reads
   the current inputs/invocation/result again and recomputes identity and residual.
   Check the new output/readback. Do not combine these phases until actual Sigma
   tests prove fresh output visibility to following effects.
4. `build_goal_seek_actions` takes actual element names/IDs and columnIds for
   invocation/assumption/guard plus the read-only inputView. Use current model rows
   and successful result; it refuses mismatches. It emits a conditional update of
   only Monthly Growth, keyed by both physical row ID and Subscription Revenue.
   False conditions do no write. Apply always hides the success toast and never
   marks APPLIED. The controller calls `prepare_goal_action_update` (CLI `prepare-goal-actions`) to
   append per-invocation buttons. This checks the immutable initial proposal,
   current full model graph, existing code/output objects and assigned input/
   column bindings, then uses the same dry-run/fresh-version/finalize gates.
   Each role must resolve to its exact initially approved object; guard must be
   the genuine GoalSeekApplyGuard code-output table, invocation must match its
   assigned input binding, and all titles/connections must remain unambiguous.
5. Compare complete before/after input rows using `verify_goal_seek_write`. Only
   after a verified exact 12-decimal growth and all other values unchanged may the
   controller reconcile invocation State=APPLIED, AppliedOperationId/AppliedGrowth.
   Read back that operation write too before reporting user success. A repeated
   applied operation no-ops only when the original fingerprint restored in memory
   and the current exact applied value both match.

Ordinary Sigma inputs do not give serializable multi-table compare-and-swap. The
controller must recheck model/row data immediately before the staging click and
prevent concurrent edits during the acceptance case. Interleaved input/model
changes after the guard remain a production concurrency prerequisite; the module
never claims that local guards prove transactional isolation.

## Typed procedure

Only `SIGMA_WRITE_DB.SIGMA_TASK5_SP_TEST.TASK5_TYPED_ECHO` is supported here; never
put it in writeback schema SIGMA_WRITE_DB.SIGMA_WRITE. The fixture SQL is the
reviewed V3 COMMENT-before-EXECUTE-AS declaration, CALLER rights, scalar-only and
no DML. It must not be reprovisioned by the worker. Parent receipts govern actual
schema/procedure/grant/index state.

Require exact unique Sigma lookup signature, connection/path, ordered declaration
types, return VARCHAR, no overload/default/VARIANT, catalog ID and actual lookup,
caller-grants, scalar mapping and datetime-coercion evidence IDs. `lookup` records
connectionId/path/signature/returnType/parameters/overloads/defaults exactly. The
caller must be SIGMA_SERVICE_USER/SIGMA_ROLE/SIGMA_WH. Ordered action types are
text, number, integer, boolean, datetime; indexes are 0..4. Null, fractional count,
negative count, invalid date, whitespace operation and changed retry inputs reject.
The reviewed formatting/Double-safe caller subset restricts absolute amount and
count below `1e15`, amount to at most two decimal places; this is deliberately
narrower than the warehouse declaration. Amount expectations are formatted from
`Decimal(json.dumps(the_emitted_number))`, preserving the exact JSON decimal
spelling instead of formatting a binary float. Decimal caller values that lose
cents during conversion to the emitted JSON number are rejected. Negative zero
is normalized to SQL numeric zero; all scalar comparisons remain exact. Datetime is a supplied millisecond NTZ
value. The emitted Z literal requires actual coercion evidence, not an assumption.

No optimistic scalar toast is emitted. Compare the actual scalar with the exact
expected string. A raised call, timeout or cancellation must record null scalar,
`dependentEffectsExecuted=false` and `successToastShown=false`. Same-ID retry is
safe only for the exact deterministic scalar-only input fingerprint. The procedure
itself has no durable deduplication storage. Failure-diagnostic negative/null calls
need their own narrowly reviewed test action, because the normal typed mapper
rejects them before submission. No artificial sleep or infinite-loop SQL is used.

## Acceptance

Every case in `RUNTIME_CASES` must carry actual Sigma runtime execution/evidence ID,
sourceHash/planHash, target workbook/version/element and passed status. Local
unit tests, dry-run validity and `print(4)` cannot satisfy this ledger. Preserve
published owner/editor/explorer/viewer tests, invalid/failure/timeout/halt/retry,
A-success then B-pending/failed stale output, changed model/input/row, exact single
assumption readback, and independent golden output comparisons. Unknown legacy
helpers/email/refresh remain separately BLOCKED after these components pass.
