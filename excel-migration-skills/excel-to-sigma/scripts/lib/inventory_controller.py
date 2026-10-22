"""Source-bound offline plans and exact post-write audits for Inventory actions.

No function here writes to Sigma or Snowflake. A plan is not a staging receipt.
The caller must bind real current IDs, execute through a reviewed native route,
then supply a fresh complete capture before any business success is shown.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date

try:
    from .inventory_behavior import (InventoryBehaviorError, adjust_demand,
        smooth_demand, snapshot_forecast, refresh_on_hand, select_purchase_orders)
except ImportError:
    from inventory_behavior import (InventoryBehaviorError, adjust_demand,
        smooth_demand, snapshot_forecast, refresh_on_hand, select_purchase_orders)

SOURCE_SHA256 = '461bee7b71f30822ea4d263ef529723d89dc9f11e7365e6434cefe89619c2f7e'
TEST_SCHEMA = 'SIGMA_WRITE_DB.SIGMA_MIGRATION8_INV_TEST'


class InventoryControllerError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _seal(plan):
    plan['planHash'] = _digest(plan)
    return plan


def _validate_plan(plan):
    if not isinstance(plan, dict) or plan.get('planHash') != _digest({k:v for k,v in plan.items() if k != 'planHash'}):
        raise InventoryControllerError('PLAN_HASH_MISMATCH')


def _capture(capture, required=()):
    if not isinstance(capture, dict) or capture.get('origin') != 'sigma-query':
        raise InventoryControllerError('ACTUAL_SIGMA_CAPTURE_REQUIRED')
    for field in ('executionId', 'evidenceId', 'documentId', 'version'):
        if not isinstance(capture.get(field), str) or not capture[field]:
            raise InventoryControllerError('INCOMPLETE_CAPTURE_IDENTITY')
    if capture.get('sourceSha256') != SOURCE_SHA256:
        raise InventoryControllerError('SOURCE_HASH_MISMATCH')
    binding = capture.get('binding')
    if not isinstance(binding, dict) or not binding.get('elementId') or not binding.get('rowIdColumn'):
        raise InventoryControllerError('PHYSICAL_BINDING_REQUIRED')
    columns = binding.get('columnIds')
    if not isinstance(columns, dict) or not set(required).issubset(columns):
        raise InventoryControllerError('PHYSICAL_COLUMN_BINDING_REQUIRED')
    if any(not isinstance(v, str) or not v for v in columns.values()) or len(set(columns.values())) != len(columns):
        raise InventoryControllerError('AMBIGUOUS_PHYSICAL_COLUMNS')
    rows = capture.get('rows')
    if not isinstance(rows, list):
        raise InventoryControllerError('COMPLETE_ROWS_REQUIRED')
    rid = binding['rowIdColumn']
    ids = [row.get(rid) if isinstance(row, dict) else None for row in rows]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise InventoryControllerError('AMBIGUOUS_PHYSICAL_ROW_IDS')
    if any(any(name not in row for name in required if name != rid) for row in rows):
        raise InventoryControllerError('INCOMPLETE_BUSINESS_ROWS')
    return rows


def _operation(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise InventoryControllerError('INVALID_OPERATION_ID')
    return value


def _base(capture, operation_id, workflow):
    return {'workflow': workflow, 'operationId': _operation(operation_id),
        'sourceSha256': SOURCE_SHA256, 'documentId': capture['documentId'],
        'version': capture['version'], 'elementId': capture['binding']['elementId'],
        'binding': copy.deepcopy(capture['binding']),
        'bindingHash': _digest(capture['binding']),
        'beforeExecutionId': capture['executionId'],
        'beforeEvidenceId': capture['evidenceId'],
        'beforeRows': copy.deepcopy(capture['rows']),
        'beforeFingerprint': _digest(capture['rows']),
        'status': 'NEEDS_ACTUAL_BINDING_AND_WRITE',
        'productionStatus': 'BLOCKED_PENDING_LIVE_EVIDENCE'}


def _update_plan(capture, operation_id, workflow, changed, field):
    before = capture['rows']
    if len(changed) != len(before):
        raise InventoryControllerError('CHANGED_ROW_COUNT')
    plan = _base(capture, operation_id, workflow)
    rid = capture['binding']['rowIdColumn']
    column_id = capture['binding']['columnIds'][field]
    updates, inverse = [], []
    for old, new in zip(before, changed):
        if old[rid] != new[rid] or old.get('Source Row') != new.get('Source Row') or old['SKU'] != new['SKU']:
            raise InventoryControllerError('CHANGED_ROW_IDENTITY')
        instruction = {'rowId': old[rid], 'columnId': column_id, 'column': field,
            'expectedValue': old[field], 'newValue': new[field],
            'sourceRow': old['Source Row'], 'sku': old['SKU']}
        updates.append(instruction)
        inverse.append({**instruction, 'expectedValue': new[field], 'newValue': old[field]})
    plan.update({'updates': updates, 'inverse': inverse, 'expectedRows': changed,
        'expectedFingerprint': _digest(changed),
        'writeContract': 'serialized native update_rows by exact physical ID; stop on stale before-state; query all rows after write'})
    return _seal(plan)


def plan_demand_update(capture, kind, operation_id, *, percentage=None):
    rows = _capture(capture, ('Input Row ID', 'Source Row', 'SKU', 'Week Start', 'Forecast Units', 'Planned Receipts'))
    try:
        if kind == 'adjust':
            changed = adjust_demand(rows, percentage)
        elif kind == 'smooth' and percentage is None:
            changed = smooth_demand(rows)
        else:
            raise InventoryControllerError('INVALID_DEMAND_OPERATION')
    except InventoryBehaviorError as error:
        raise InventoryControllerError(str(error)) from error
    plan = _update_plan(capture, operation_id, kind, changed, 'Forecast Units')
    if kind == 'adjust':
        plan['percentage'] = float(percentage)
    return _seal({k:v for k,v in plan.items() if k != 'planHash'})


def plan_refresh(sku_capture, erp_capture, operation_id):
    rows = _capture(sku_capture, ('Input Row ID', 'Source Row', 'SKU', 'Description', 'On Hand'))
    if not isinstance(erp_capture, dict) or erp_capture.get('origin') != 'warehouse-query' or not erp_capture.get('evidenceId') or erp_capture.get('schema') != TEST_SCHEMA or erp_capture.get('source') != 'synthetic-test-schema':
        raise InventoryControllerError('ISOLATED_ERP_CAPTURE_REQUIRED')
    try:
        date.fromisoformat(erp_capture['snapshotDate'])
        date.fromisoformat(erp_capture['warehouseCurrentDate'])
        if erp_capture['snapshotDate'] != erp_capture['warehouseCurrentDate']:
            raise InventoryControllerError('ERP_SNAPSHOT_NOT_CURRENT_DATE')
        changed = refresh_on_hand(rows, erp_capture['rows'])
    except (KeyError, TypeError, ValueError, InventoryBehaviorError) as error:
        raise InventoryControllerError('INVALID_ERP_SNAPSHOT: ' + str(error)) from error
    plan = _update_plan(sku_capture, operation_id, 'refresh-on-hand-repaired', changed, 'On Hand')
    plan['erpEvidenceId'] = erp_capture['evidenceId']
    plan['erpSnapshotDate'] = erp_capture['snapshotDate']
    plan['erpFingerprint'] = _digest(erp_capture['rows'])
    plan['sourceBugRepair'] = 'VBA CopyFromRecordset begins SKUs!A2 and overwrites Description; replacement updates only On Hand by SKU.'
    return _seal({k:v for k,v in plan.items() if k != 'planHash'})


def verify_update(plan, after):
    _validate_plan(plan)
    _capture(after, tuple(plan['binding']['columnIds']))
    if any(after.get(k) != plan[k] for k in ('documentId', 'version', 'sourceSha256')) or after['binding'] != plan['binding']:
        raise InventoryControllerError('STALE_OR_CHANGED_BINDING')
    if after['executionId'] == plan['beforeExecutionId'] or after['evidenceId'] == plan['beforeEvidenceId']:
        raise InventoryControllerError('FRESH_READBACK_REQUIRED')
    if _digest(after['rows']) != plan['expectedFingerprint']:
        raise InventoryControllerError('UNCONFIRMED_OR_WRONG_ROWS')
    return {'status': 'PERSISTED_COMPONENT_WRITE', 'operationId': plan['operationId'],
        'readbackEvidenceId': after['evidenceId'], 'readbackHash': _digest(after['rows']),
        'productionStatus': 'BLOCKED_PENDING_PUBLISHED_AND_ROLE_PROOF'}


def plan_restore_update(original_plan, current_after, restore_operation_id):
    """Exact inverse only while every current row still equals the prior target."""
    _validate_plan(original_plan)
    _capture(current_after, tuple(original_plan['binding']['columnIds']))
    if any(current_after.get(k) != original_plan[k] for k in ('documentId','version','sourceSha256')) or current_after['binding'] != original_plan['binding']:
        raise InventoryControllerError('STALE_OR_CHANGED_BINDING')
    if _digest(current_after['rows']) != original_plan['expectedFingerprint']:
        raise InventoryControllerError('RESTORE_CURRENT_STATE_MISMATCH')
    if current_after['executionId'] == original_plan['beforeExecutionId'] or current_after['evidenceId'] == original_plan['beforeEvidenceId']:
        raise InventoryControllerError('FRESH_RESTORE_CAPTURE_REQUIRED')
    field = original_plan['updates'][0]['column']
    restored = copy.deepcopy(original_plan['beforeRows'])
    plan = _update_plan(current_after, restore_operation_id,
        'restore-'+original_plan['workflow'], restored, field)
    plan['restoresPlanHash'] = original_plan['planHash']
    return _seal({k:v for k,v in plan.items() if k != 'planHash'})


def _append_capture(log, names):
    _capture(log, ('Input Row ID', *names))
    return log['rows']


def _same_intent(log_rows, expected, operation_id, fields):
    existing = [r for r in log_rows if r.get('Operation ID') == operation_id]
    if not existing:
        return expected
    indexed = {}
    for row in existing:
        ordinal = row.get('Source Row')
        if ordinal in indexed:
            raise InventoryControllerError('DUPLICATE_INTENT_SOURCE_ROW')
        indexed[ordinal] = {k: row.get(k) for k in fields}
    wanted = {row['Source Row']: {k: row.get(k) for k in fields} for row in expected}
    if not set(indexed).issubset(wanted) or any(value != wanted[key] for key, value in indexed.items()):
        raise InventoryControllerError('OPERATION_RETRY_INPUT_MISMATCH')
    return [row for row in expected if row['Source Row'] not in indexed]


def plan_snapshot(demand_capture, log_capture, operation_id, committed_at, invoker):
    rows = _capture(demand_capture, ('Input Row ID', 'Source Row', 'SKU', 'Week Start', 'Forecast Units', 'Planned Receipts'))
    fields = ('Operation ID', 'Source Row', 'Committed At', 'SKU', 'Week Start', 'Forecast Units', 'Committed By', 'Payload Fingerprint')
    log_rows = _append_capture(log_capture, fields)
    if demand_capture['documentId'] != log_capture['documentId'] or demand_capture['version'] != log_capture['version']:
        raise InventoryControllerError('CROSS_DOCUMENT_OR_VERSION')
    try:
        source_payload = snapshot_forecast(rows, operation_id, committed_at, invoker)
    except InventoryBehaviorError as error:
        raise InventoryControllerError(str(error)) from error
    payload_hash = _digest(source_payload)
    payload = [{**row, 'Payload Fingerprint': payload_hash} for row in source_payload]
    remaining = _same_intent(log_rows, payload, operation_id, fields)
    plan = _base(log_capture, operation_id, 'commit-forecast')
    plan.update({'sourceDemandEvidenceId': demand_capture['evidenceId'],
        'sourceDemandFingerprint': _digest(rows), 'appendRows': remaining,
        'payloadFingerprint': payload_hash, 'appendFingerprint': _digest(remaining), 'appendFields': fields,
        'nativeTarget': 'ordinary independent Sigma Snapshots input table',
        'retryContract': 'same operation ID and identical 72-row payload only; controller serialized native append and full readback required'})
    if not remaining:
        plan['status'] = 'ALREADY_PRESENT_READBACK_ONLY'
    elif len(remaining) < len(payload):
        plan['status'] = 'NEEDS_RECOVERY_WRITE'
    return _seal(plan)


def verify_append(plan, after):
    _validate_plan(plan)
    fields = plan['appendFields']
    _append_capture(after, fields)
    if plan['status'] not in ('NEEDS_ACTUAL_BINDING_AND_WRITE', 'NEEDS_RECOVERY_WRITE'):
        raise InventoryControllerError('NO_PENDING_APPEND')
    if any(after.get(k) != plan[k] for k in ('documentId', 'version', 'sourceSha256')) or after['binding'] != plan['binding']:
        raise InventoryControllerError('STALE_OR_CHANGED_BINDING')
    if after['executionId'] == plan['beforeExecutionId'] or after['evidenceId'] == plan['beforeEvidenceId']:
        raise InventoryControllerError('FRESH_READBACK_REQUIRED')
    rid = plan['binding']['rowIdColumn']
    before_ids = {r[rid] for r in plan['beforeRows']}
    actual_old = [r for r in after['rows'] if r[rid] in before_ids]
    actual_new = [r for r in after['rows'] if r[rid] not in before_ids]
    if _digest(actual_old) != plan['beforeFingerprint']:
        raise InventoryControllerError('EXISTING_LOG_CHANGED')
    actual_values = [{k:r.get(k) for k in fields} for r in actual_new]
    if _digest(actual_values) != plan['appendFingerprint']:
        raise InventoryControllerError('UNCONFIRMED_OR_EXTRA_APPEND_ROWS')
    return {'status': 'PERSISTED_COMPONENT_APPEND', 'operationId': plan['operationId'],
        'readbackEvidenceId': after['evidenceId'], 'readbackHash': _digest(after['rows']),
        'productionStatus': 'BLOCKED_PENDING_PUBLISHED_AND_ROLE_PROOF'}


def plan_purchase_orders(projection_capture, stage_capture, operation_id):
    rows = _capture(projection_capture, ('Input Row ID', 'Source Row', 'SKU', 'Reorder?', 'Suggested Qty'))
    fields = ('Operation ID', 'Source Row', 'SKU', 'Quantity', 'Batch Fingerprint')
    stage_rows = _append_capture(stage_capture, fields)
    if projection_capture['documentId'] != stage_capture['documentId'] or projection_capture['version'] != stage_capture['version']:
        raise InventoryControllerError('CROSS_DOCUMENT_OR_VERSION')
    try:
        selected = select_purchase_orders(rows)
    except InventoryBehaviorError as error:
        raise InventoryControllerError(str(error)) from error
    _operation(operation_id)
    batch_fingerprint = _digest(selected)
    payload = [{'Operation ID': operation_id, **row, 'Batch Fingerprint': batch_fingerprint} for row in selected]
    plan = _base(stage_capture, operation_id, 'stage-purchase-orders')
    plan.update({'sourceProjectionEvidenceId': projection_capture['evidenceId'],
        'sourceProjectionFingerprint': _digest(rows), 'stageRows': payload,
        'batchFingerprint': batch_fingerprint, 'stageFields': fields,
        'procedure': {'path': [*TEST_SCHEMA.split('.'), 'STAGE_PO'], 'argumentTypes': ['VARCHAR', 'NUMBER(2,0)', 'VARCHAR', 'NUMBER(38,0)', 'VARCHAR'],
            'returnFields': {'operation_id': 'VARCHAR', 'source_row': 'NUMBER(2,0)', 'sku': 'VARCHAR', 'quantity': 'NUMBER(38,0)',
                'status': 'VARCHAR', 'error_code': 'VARCHAR'}},
        'retryContract': 'serialized lock row, exact batch fingerprint, same-intent replay reads prior rows; partial/uncertain completion requires recovery'})
    if not payload:
        plan['status'] = 'NO_SELECTION_NO_WRITE'
    else:
        remaining = _same_intent(stage_rows, payload, operation_id, fields)
        plan['stageRows'] = remaining
        if not remaining:
            plan['status'] = 'ALREADY_PRESENT_READBACK_ONLY'
        elif len(remaining) < len(payload):
            plan['status'] = 'NEEDS_RECOVERY_WRITE'
    return _seal(plan)


def verify_po_stage(plan, after):
    """Only a fresh exact staged-row query establishes PO component outcome."""
    _validate_plan(plan)
    if plan.get('workflow') != 'stage-purchase-orders' or plan.get('status') not in (
            'NEEDS_ACTUAL_BINDING_AND_WRITE', 'NEEDS_RECOVERY_WRITE'):
        raise InventoryControllerError('NO_PENDING_PO_STAGE')
    fields = plan['stageFields']
    _append_capture(after, fields)
    if any(after.get(k) != plan[k] for k in ('documentId', 'version', 'sourceSha256')) or after['binding'] != plan['binding']:
        raise InventoryControllerError('STALE_OR_CHANGED_BINDING')
    if after['executionId'] == plan['beforeExecutionId'] or after['evidenceId'] == plan['beforeEvidenceId']:
        raise InventoryControllerError('FRESH_READBACK_REQUIRED')
    rid = plan['binding']['rowIdColumn']
    prior_ids = {r[rid] for r in plan['beforeRows']}
    old = [r for r in after['rows'] if r[rid] in prior_ids]
    new = [r for r in after['rows'] if r[rid] not in prior_ids]
    if _digest(old) != plan['beforeFingerprint']:
        raise InventoryControllerError('EXISTING_PO_STAGE_CHANGED')
    if [{key: row.get(key) for key in fields} for row in new] != plan['stageRows']:
        raise InventoryControllerError('UNCONFIRMED_OR_EXTRA_PO_ROWS')
    return {'status': 'PERSISTED_COMPONENT_PO_STAGE', 'operationId': plan['operationId'],
        'readbackEvidenceId': after['evidenceId'], 'readbackHash': _digest(after['rows']),
        'productionStatus': 'BLOCKED_PENDING_PUBLISHED_AND_ROLE_PROOF'}


def audit_po_results(plan, results):
    """Validate typed procedure scalars; they never prove persisted staging."""
    _validate_plan(plan)
    if plan.get('workflow') != 'stage-purchase-orders' or plan.get('status') not in (
            'NEEDS_ACTUAL_BINDING_AND_WRITE', 'NEEDS_RECOVERY_WRITE'):
        raise InventoryControllerError('NO_PENDING_PO_STAGE')
    pending = plan['stageRows']
    if not isinstance(results, list) or len(results) != len(pending):
        raise InventoryControllerError('UNCERTAIN_PROCEDURE_COMPLETION')
    fields = {'operation_id', 'source_row', 'sku', 'quantity', 'status', 'error_code'}
    failures = []
    for target, result in zip(pending, results):
        if not isinstance(result, dict) or set(result) != fields:
            raise InventoryControllerError('INVALID_TYPED_PROCEDURE_OUTPUT')
        if (type(result['operation_id']) is not str or type(result['source_row']) is not int
                or type(result['sku']) is not str or type(result['quantity']) is not int
                or type(result['status']) is not str or type(result['error_code']) is not str):
            raise InventoryControllerError('INVALID_TYPED_PROCEDURE_OUTPUT')
        if (result['operation_id'] != plan['operationId'] or result['source_row'] != target['Source Row']
                or result['sku'] != target['SKU'] or result['quantity'] != target['Quantity']):
            raise InventoryControllerError('PROCEDURE_OUTPUT_TARGET_MISMATCH')
        if result['status'] not in ('STAGED', 'RETRY_PRESENT', 'FAILURE'):
            raise InventoryControllerError('INVALID_PROCEDURE_STATUS')
        if result['status'] == 'FAILURE':
            if not result['error_code']:
                raise InventoryControllerError('MISSING_PROCEDURE_ERROR_CODE')
            failures.append({'sourceRow': result['source_row'], 'errorCode': result['error_code']})
        elif result['error_code']:
            raise InventoryControllerError('SUCCESS_WITH_ERROR_CODE')
    return {'status': 'PROCEDURE_FAILURE' if failures else 'NEEDS_STAGE_READBACK',
        'operationId': plan['operationId'], 'failures': failures,
        'procedureResultsHash': _digest(results),
        'productionStatus': 'BLOCKED_PENDING_PERSISTED_STAGE_READBACK'}
