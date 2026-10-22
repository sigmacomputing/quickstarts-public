"""Persist outcome only after a fresh complete native business readback.

Controller programs are explicit follow-ups, not action-chain success effects.
Input-table updates have no compare-and-swap transaction; serialize controller
reconciliation per workbook and read back the resulting row before reporting it.
"""
import copy
import datetime
import re
try:
    from .native_actions import audit_native_action_readback
    from .promotion import _header,_rows,_digest
    from .workflow_repairs import _project
    from .migration_manifest import validate_manifest
    from .input_sync import _approved_feature,_sdk_literal,_parse_datetime
    from .input_display import _system_column_contract, _editable_column_contract
except ImportError:
    from native_actions import audit_native_action_readback
    from promotion import _header,_rows,_digest
    from workflow_repairs import _project
    from migration_manifest import validate_manifest
    from input_sync import _approved_feature,_sdk_literal,_parse_datetime
    from input_display import _system_column_contract, _editable_column_contract


def _assigned_operations(expected,operations,manifest,receipt):
    if not isinstance(manifest,dict) or not isinstance(receipt,dict):raise ValueError('approved assigned workflowOperations manifest and receipt required')
    validate_manifest(manifest)
    spec,target,artifact=_approved_feature(manifest,receipt,'workflowOperations',require_assigned=True)
    if manifest.get('target')!={'documentId':expected.get('documentId'),'version':expected.get('version')}:
        raise ValueError('outcome target document/version stale')
    for key in ('sourceHash','planHash'):
        if expected.get(key)!=manifest.get(key):raise ValueError('outcome source/plan stale')
    for key in ('sourceHash','planHash','documentId','version'):
        if operations.get(key)!=expected.get(key):raise ValueError('operations capture source/plan/document/version stale')
    if operations.get('origin')!='sigma-query' or not operations.get('executionId') or not operations.get('evidenceId'):
        raise ValueError('fresh actual complete operations query required')
    binding=operations.get('binding') or {}
    if any(binding.get(k)!=v for k,v in target.items()) or not target.get('pageId'):
        raise ValueError('operations destination differs from approved assigned target')
    columns=binding.get('sdkColumns',[])
    system=_system_column_contract(target);system_id=system.get('id') or target.get('rowIdColumnId')
    if not system_id or system_id in target['columnIds'].values():raise ValueError('approved physical system row ID required')
    schema=[]
    for column in spec['columns']:
        contract=_editable_column_contract(manifest,target,column)
        schema.append({**contract,'name':column['name']})
    schema.append({**system,'id':system_id})
    if len(columns)!=len(schema) or len({c.get('id') for c in columns})!=len(schema):raise ValueError('complete actual operations SDK schema required')
    by_id={c.get('id'):c for c in columns}
    for column in schema:
        observed=by_id.get(column['id'],{})
        if any(observed.get(k)!=v for k,v in column.items()):raise ValueError('operations typed SDK schema differs from assigned source')
    if binding.get('columnTypes')!={c['name']:c['type'] for c in spec['columns']} or binding.get('columnClasses')!={c['name']:by_id[target['columnIds'][c['name']]]['columnClass'] for c in spec['columns']}:
        raise ValueError('complete source typed operations schema required')
    identity=operations.get('rowIdBinding') or {}
    if (set(identity)!={'sourceColumnId','readbackColumn','targetBindingHash','evidenceHash'}
            or identity.get('sourceColumnId')!=system_id or identity.get('readbackColumn')!=operations.get('rowIdColumn')
            or identity.get('targetBindingHash')!=artifact['targetBindingHash']
            or not re.fullmatch(r'[0-9a-f]{64}',str(identity.get('evidenceHash') or ''))):raise ValueError('actual operations row-ID query binding required')
    indexed=_rows(operations)
    if operations.get('keyColumns')!=[operations['rowIdColumn']] or any(set(row)!={*target['columnIds'],operations['rowIdColumn']} for row in indexed.values()):
        raise ValueError('complete original operations fields and stable ID required')
    return indexed


def reconcile_operation(expected,capture,operations,*,completed_at,manifest=None,receipt=None):
    indexed=_assigned_operations(expected,operations,manifest,receipt)
    if capture.get('origin')!='sigma-query' or not capture.get('executionId') or not capture.get('evidenceId'):
        raise ValueError('actual fresh business query required')
    for key in ('sourceHash','planHash','documentId','version','operationId','context'):
        if not expected.get(key) or expected[key]!=capture.get(key):raise ValueError('operation readback binding mismatch')
    timestamp=_parse_datetime(datetime.datetime.fromisoformat(completed_at.replace('Z','+00:00'))).isoformat()
    audit=audit_native_action_readback(expected,capture)
    if audit['status']!='PASSED_COMPONENT_READBACK':raise ValueError('business outcome not confirmed: '+', '.join(audit['failures']))
    row=indexed.get(expected['operationId'])
    if not row or row.get('State') not in {'PENDING','PREPARED'}:raise ValueError('pending original operation required; no replay')
    for name,key in [('Workflow','workflow'),('Context','context'),('Source Hash','sourceHash'),('Plan Hash','planHash')]:
        if row.get(name)!=expected[key]:raise ValueError('durable operation context mismatch')
    columns=operations['binding']['sdkColumns'];variables={c['name']:f'c{i}' for i,c in enumerate(columns)}
    if not {'State','Outcome','Completed At'}<=set(variables):raise ValueError('missing operation outcome columns')
    outcome='Business readback confirmed; evidence='+capture['evidenceId']
    intended=copy.deepcopy(indexed);intended[expected['operationId']].update({'State':'CONFIRMED','Outcome':outcome,'Completed At':timestamp})
    lines=_header(operations)
    lines += [f'# sourceHash={expected["sourceHash"]}; planHash={expected["planHash"]}; evidence={capture["evidenceId"]}',
        '# Controller must serialize this follow-up and capture the updated row; no SDK return proves a write.',
        'from datetime import datetime',
        f"table.update_rows([({expected['operationId']!r}, {{{variables['State']}: 'CONFIRMED', {variables['Outcome']}: {outcome!r}, {variables['Completed At']}: {_sdk_literal(timestamp,'datetime',date_only_hour=0)}}})])"]
    result={'businessAudit':audit,'operationId':expected['operationId'],'operationsBeforeHash':_digest(operations),
        'expected':copy.deepcopy(expected),'manifest':copy.deepcopy(manifest),'receipt':copy.deepcopy(receipt),
        'operationsBefore':copy.deepcopy(operations),'intendedRows':intended,
        'program':'\n'.join(lines)+'\n','status':'PENDING_OUTCOME_ROW_READBACK','productionStatus':'BLOCKED'}
    result['outcomePlanHash']=_digest(result)
    return result


def verify_outcome_row(plan,rows):
    if plan.get('outcomePlanHash')!=_digest({k:v for k,v in plan.items() if k!='outcomePlanHash'}):raise ValueError('outcome plan hash stale')
    before=plan['operationsBefore']
    if plan['operationsBeforeHash']!=_digest(before):raise ValueError('operations original capture stale')
    index=_assigned_operations(plan['expected'],rows,plan['manifest'],plan['receipt'])
    if rows['binding']!=before['binding'] or rows['rowIdBinding']!=before['rowIdBinding'] or rows['executionId']==before['executionId'] or rows['evidenceId']==before['evidenceId']:
        raise ValueError('fresh same-destination outcome readback required')
    row=index.get(plan['operationId'])
    if not row:raise ValueError('persisted outcome row missing')
    index=copy.deepcopy(index)
    try:index[plan['operationId']]['Completed At']=_parse_datetime(datetime.datetime.fromisoformat(row['Completed At'].replace('Z','+00:00'))).isoformat()
    except (ValueError,TypeError,AttributeError,KeyError):raise ValueError('persisted exact completion timestamp required')
    if _digest(index)!=_digest(plan['intendedRows']):raise ValueError('persisted exact outcome/full original rows not confirmed')
    return {'status':'CONFIRMED_COMPONENT_OUTCOME','operationId':plan['operationId'],'outcomePlanHash':plan['outcomePlanHash'],'readbackHash':_digest(rows),'productionStatus':'BLOCKED'}


def build_outcome_view(binding):
    if not binding.get('elementId') or not binding.get('name'):raise ValueError('assigned operations table required')
    name=binding['name']
    return _project('workflow-confirmed-outcomes','Workflow results',binding,
        [(n,f'[{name}/{n}]') for n in ('Workflow','Target Business Key','Context','Created At','Completed At','Outcome')]+[
        ('Result',f'If([{name}/State] = "CONFIRMED", "Confirmed by business readback", [{name}/State] = "FAILED", "Failed; inspect and recover", "Pending verification")')])
