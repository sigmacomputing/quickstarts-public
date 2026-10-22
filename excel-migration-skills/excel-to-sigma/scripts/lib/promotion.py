"""Offline, source-bound promotion/rollback plans. Execution belongs to the controller.

These plans preserve original document identity. A successful API mutation is never
an acceptance result; complete row, document and SDK observations are mandatory.
"""
import copy
import hashlib
import json
try:
    from .action_inventory import validate_action_inventory,verify_action_preservation,action_restore_programs
    from .input_sync import _sdk_literal
except ImportError:
    from action_inventory import validate_action_inventory,verify_action_preservation,action_restore_programs
    from input_sync import _sdk_literal


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _sealed(value,field):
    result=copy.deepcopy(value);result[field]=_digest(value);return result


def _rows(capture):
    if capture.get('complete') is not True or capture.get('rowCount')!=len(capture.get('rows',[])):
        raise ValueError('complete full-row capture and exact count required')
    identity=capture.get('rowIdColumn');keys=capture.get('keyColumns')
    if not identity or not keys:raise ValueError('stable row ID and business keys required')
    result={};seen=set()
    for row in capture['rows']:
        rid=row.get(identity);key=tuple(row.get(k) for k in keys)
        if not isinstance(rid,str) or not rid or rid in result or key in seen or any(x is None for x in key):
            raise ValueError('row IDs/business keys must be complete and unique')
        result[rid]=row;seen.add(key)
    return result


def _comparable_rows(capture,column_types):
    """Only typed timestamps normalize; captured date-only values mean midnight."""
    return {rid:{name:(_sdk_literal(value,'datetime',date_only_hour=0)
            if column_types.get(name)=='datetime' else value) for name,value in row.items()}
        for rid,row in _rows(capture).items()}


def _display(capture,binding):
    if capture.get('elementId')!=binding['elementId'] or capture.get('editMode') not in {'draft','published-explore','published-all-users'}:
        raise ValueError('SDK capture owner/edit mode missing')
    columns=capture.get('columns',[]);expected=binding.get('sdkColumns',[])
    classes={'LiteralEditableColumn','SingleSelectEditableColumn','MultiSelectEditableColumn','FormulaColumn','InputTableIDColumn'}
    if any(c.get('columnClass') not in classes or c.get('type') not in {None,'text','number','boolean','datetime'} for c in expected):raise ValueError('unsupported actual SDK class/type contract')
    if len({c['id'] for c in expected})!=len(expected):raise ValueError('duplicate SDK column binding')
    for column in expected:
        if column['columnClass']=='SingleSelectEditableColumn':
            tuples=[c for c in columns if c[0]==column['id']]
            if 'allowedValues' not in column or len(tuples)!=1 or len(tuples[0])!=4 or tuples[0][3]!=column['allowedValues']:raise ValueError('complete select options capture required')

    if len(columns)!=len(expected) or {c[0] for c in columns}!={c['id'] for c in expected}:
        raise ValueError('complete actual SDK column display capture required')
    for column in columns:
        if len(column) not in (3,4) or type(column[1]) is not bool or (column[2] is not None and len(column[2])!=4):
            raise ValueError('invalid SDK display tuple')


def build_promotion_backup(scope,current,rows,sdk,data_models,sdk_actions=None):
    if not scope.get('owner') or current.get('workbookId')!=scope.get('documentId') or current.get('documentVersion')!=scope.get('version'):
        raise ValueError('fresh reviewed document/version binding required')
    if set(rows)!=set(scope['affectedTables']) or set(sdk)!=set(rows) or set(data_models)!=set(scope['affectedDataModels']):
        raise ValueError('all affected tables, SDK displays and data models must be backed up')
    for eid,capture in rows.items():
        _rows(capture);binding=capture.get('binding',{})
        if binding.get('elementId')!=eid or not binding.get('pageId'):raise ValueError('actual assigned table binding required')
        fields=set(binding.get('columnIds',{}))|{capture['rowIdColumn']}
        if not binding.get('columnIds') or any(set(row)!=fields for row in capture['rows']):raise ValueError('all original editable fields plus stored row ID must be backed up')
        if set(binding.get('columnTypes',{}))!=set(binding['columnIds']) or set(binding.get('columnClasses',{}))!=set(binding['columnIds']):raise ValueError('complete typed editable schema required')
        _display(sdk[eid],binding)
    for identity,model in data_models.items():
        if model.get('complete') is not True or model.get('dataModelId')!=identity or not isinstance(model.get('documentVersion'),int) or not isinstance(model.get('contents'),dict):raise ValueError('complete version-bound affected data-model backup required')
    sdk_actions=sdk_actions or scope.get('sdkActionInventory')
    actions=validate_action_inventory(sdk_actions,current)
    return _sealed({'sdkActions':sdk_actions,'actionRecovery':actions,'scope':scope,'document':current,'rows':rows,'sdk':sdk,'dataModels':data_models,
        'limitations':['Immutable system audit timestamps are not restorable; business values and display are verified separately.']},'backupHash')


def validate_backup(backup):
    payload={k:v for k,v in backup.items() if k!='backupHash'}
    if backup.get('backupHash')!=_digest(payload):raise ValueError('backup hash mismatch')
    rebuilt=build_promotion_backup(backup['scope'],backup['document'],backup['rows'],backup['sdk'],backup['dataModels'],backup['sdkActions'])
    if rebuilt!=backup:raise ValueError('invalid backup structure')
    return True


def _header(capture):
    b=capture['binding'];lines=['from sigma.page import Page','from sigma.inputTable import InputTable, LiteralEditableColumn, SingleSelectEditableColumn, MultiSelectEditableColumn, InputTableIDColumn','from sigma.column import FormulaColumn','from datetime import datetime',f"host = sigma.workbook.get_page({b['pageId']!r})",
        "if not isinstance(host, Page): raise RuntimeError('expected assigned page')",
        f"table = host.get_element({b['elementId']!r})",
        "if not isinstance(table, InputTable): raise RuntimeError('expected assigned input table')",
        f"approved_ids = {[c['id'] for c in b['sdkColumns']]!r}",
        'observed_ids = {}',
        'for column in table.list_columns():',
        "    if column.id() in observed_ids: raise RuntimeError('duplicate SDK column ID')",
        '    observed_ids[column.id()] = True',
        "if len(observed_ids) != len(approved_ids): raise RuntimeError('SDK columns changed')",
        'for approved_id in approved_ids:',
        "    if approved_id not in observed_ids: raise RuntimeError('SDK columns changed')"]
    for i,column in enumerate(b['sdkColumns']):
        var=f'c{i}';lines += [f"{var} = table.get_column({column['id']!r})",
            f"if not isinstance({var}, {column['columnClass']}): raise RuntimeError('column class changed')",
            f"if {var}.name() != {column['name']!r} or {var}.element_id() != {b['elementId']!r}: raise RuntimeError('column identity changed')"]
        if column.get('type') is not None:lines.append(f"if {var}.type() != {column['type']!r}: raise RuntimeError('column type changed')")
        if column['columnClass']=='InputTableIDColumn':lines.append(f"if {var}.kind() != 'row_id': raise RuntimeError('system row ID kind changed')")
        if column.get('formula') is not None:lines.append(f"if {var}.formula() != {column['formula']!r}: raise RuntimeError('system ID formula changed')")
        if 'allowedValues' in column:lines.append(f"if {var}.allowed_values() != {column['allowedValues']!r}: raise RuntimeError('select options changed')")
    return lines


def prepare_rollback(backup,fresh,current_rows,owned_added_rows=None,*,fresh_data_models=None,changed_edit_modes=None):
    validate_backup(backup);validate_action_inventory(backup['sdkActions'],backup['document'],require_recovery=True);scope=backup['scope'];owned_added_rows=owned_added_rows or {}
    if fresh.get('workbookId')!=scope['documentId'] or not isinstance(fresh.get('documentVersion'),int):raise ValueError('fresh original document required')
    if set(current_rows)!=set(backup['rows']):raise ValueError('complete current affected rows required')
    changed_edit_modes=changed_edit_modes or {}
    if not set(changed_edit_modes)<=set(backup['rows']):raise ValueError('edit mode restore references an unaffected input')
    fresh_data_models=fresh_data_models or {};dm_requests={}
    if set(fresh_data_models)!=set(backup['dataModels']):raise ValueError('fresh versions for every affected data model required')
    for identity,model in backup['dataModels'].items():
        current=fresh_data_models[identity]
        if current.get('dataModelId')!=identity or not isinstance(current.get('documentVersion'),int):raise ValueError('fresh affected data-model identity/version required')
        dm_requests[identity]={'method':'PUT','path':f'/v2/dataModels/{identity}/spec','body':{**copy.deepcopy(model['contents']),'documentVersion':current['documentVersion']}}
    row_programs={};display_programs={}
    for eid,original in backup['rows'].items():
        before=_rows(original);after=_rows(current_rows[eid]);extra=set(after)-set(before)
        if set(before)-set(after):raise ValueError('missing original immutable row ID cannot be recreated safely')
        if extra!=set(owned_added_rows.get(eid,[])):raise ValueError('unowned extra rows or stale deletion list')
        if current_rows[eid]['binding']!=original['binding']:raise ValueError('table binding changed')
        lines=_header(original);columns=original['binding']['sdkColumns'];by_id={c['id']:f'c{i}' for i,c in enumerate(columns)}
        fields=original['binding']['columnIds'];updates=[]
        for rid,row in before.items():
            changes=[]
            for name,cid in fields.items():
                if row.get(name)==after[rid].get(name):continue
                value=row[name];kind=original['binding']['columnTypes'][name]
                literal=_sdk_literal(value,kind,date_only_hour=0)
                changes.append(f'{by_id[cid]}: {literal}')
            if changes:updates.append(f"({rid!r}, {{{', '.join(changes)}}})")
        if updates:lines.append('table.update_rows(['+', '.join(updates)+'])')
        if extra:lines.append(f'table.delete_rows({sorted(extra)!r})')
        row_programs[eid]='\n'.join(lines)+'\n'
        display=_header(original)
        if eid in changed_edit_modes:
            observed_mode=changed_edit_modes[eid]
            if observed_mode not in {'draft','published-explore','published-all-users'}:raise ValueError('explicit current changed mode required')
            display += [f'if table.edit_mode() != {observed_mode!r}: raise RuntimeError("input mode changed since rollback review")',
                f'table.set_edit_mode({backup["sdk"][eid]["editMode"]!r})']
        for observed in backup['sdk'][eid]['columns']:
            cid,visible,fmt=observed[:3];var=by_id[cid];display.append(f'{var}.set_visible({visible!r})')
            if fmt is None:display.append(f"{var}.set_format('automatic')")
            elif fmt[3] is not None:display.append(f'{var}.set_format_pattern({fmt[3]!r})')
            else:
                kwargs=', '.join(f'{k}={v!r}' for k,v in [('decimals',fmt[1]),('currency',fmt[2])] if v is not None)
                display.append(f'{var}.set_format({fmt[0]!r}'+(', '+kwargs if kwargs else '')+')')
        # An unchanged REST input definition can still reset display. Always restore it last.
        display_programs[eid]='\n'.join(display)+'\n'
    return _sealed({'backupHash':backup['backupHash'],'order':['rows','dataModels','document','sdkActions','sdkDisplay','readback'],
        'rowPrograms':row_programs,'dataModelRequests':dm_requests,'dataModelBackups':copy.deepcopy(backup['dataModels']),
        'documentRequest':{'method':'PUT','path':f"/v2/workbooks/{scope['documentId']}/contents",'body':{'documentVersion':fresh['documentVersion'],'contents':copy.deepcopy(backup['document']['contents'])}},
        'sdkActionRestorationArtifacts':action_restore_programs(backup['sdkActions']),'sdkPrograms':display_programs,'status':'PENDING_DRY_RUN_AND_EXECUTION'},'rollbackHash')


def prepare_promotion(backup,fresh,candidate,review,acceptance):
    validate_backup(backup);scope=backup['scope']
    validate_action_inventory(backup['sdkActions'],backup['document'],require_recovery=True)
    try:
        from .acceptance import build_workflow_reports,validate_production_matrix
    except ImportError:
        from acceptance import build_workflow_reports,validate_production_matrix
    if not all(k in acceptance for k in ('matrix','ledger','finalReview')):raise ValueError('full acceptance matrix/ledger/final review required; status flags are not proof')
    validate_production_matrix(acceptance['matrix'])
    reports=build_workflow_reports(acceptance['matrix'],acceptance['ledger'],final_review=acceptance['finalReview'])
    relevant=[r for r in reports.values() if r['sourceHash']==scope['sourceHash'] and r['planHash']==scope['planHash']]
    if not relevant or any(r['verdict']!='VERIFIED_COMPLETE' for r in reports.values()):raise ValueError('all mandatory workflow evidence and final review required')
    if acceptance['finalReview'].get('candidateHash')!=_digest(candidate) or acceptance['finalReview'].get('targetDocumentId')!=scope['documentId']:
        raise ValueError('final review must bind exact original-target promotion candidate')
    if fresh!=backup['document']:raise ValueError('original document changed since reviewed backup')
    if not review.get('owner') or review.get('backupHash')!=backup['backupHash'] or review.get('candidateHash')!=_digest(candidate) or review.get('targetDocumentId')!=scope['documentId']:
        raise ValueError('named exact candidate/backup/target review required')
    for collection in ('pages','elements'):
        before={x['id']:x for x in fresh['contents'].get(collection,[])};after={x['id']:x for x in candidate.get(collection,[])}
        if len(after)!=len(candidate.get(collection,[])):raise ValueError('duplicate IDs')
        if set(before)-set(after):raise ValueError('promotion cannot delete existing objects')
        if not (set(after)-set(before)).issubset(set(review.get('allowNewIds',[]))):raise ValueError('unreviewed new object')
        if any(before[k]!=after[k] and k not in review.get('replacementIds',[]) for k in before):raise ValueError('unreviewed existing object modification')
    return _sealed({'sdkActionsBefore':copy.deepcopy(backup['sdkActions']),'backupHash':backup['backupHash'],'acceptance':acceptance,'preservedUrl':fresh['url'],
        'request':{'method':'PUT','path':f"/v2/workbooks/{scope['documentId']}/contents",'body':{'documentVersion':fresh['documentVersion'],'contents':candidate}},
        'dryRunRequired':True,'status':'PENDING_DRY_RUN_AND_EXECUTION'},'promotionHash')


def checkpoint_promotion(ledger,backup,event):
    validate_backup(backup);previous=None
    for index,record in enumerate(ledger):
        if record.get('sequence')!=index+1 or record.get('previousHash')!=previous or record.get('backupHash')!=backup['backupHash'] or record.get('checkpointHash')!=_digest({k:v for k,v in record.items() if k!='checkpointHash'}):raise ValueError('checkpoint chain changed')
        previous=record['checkpointHash']
    if not event.get('evidenceId') or not event.get('hash') or event.get('outcome') not in {'verified','failed'}:raise ValueError('actual step evidence required')
    if any(r['event']['evidenceId']==event['evidenceId'] or (r['event']['step']==event['step'] and r['event']['outcome']=='verified') for r in ledger):raise ValueError('step replay refused')
    if not ledger and (event.get('step')!='backup' or event['hash']!=backup['backupHash']):raise ValueError('verified backup must precede mutations')
    return copy.deepcopy(ledger)+[_sealed({'sequence':len(ledger)+1,'previousHash':previous,'backupHash':backup['backupHash'],'event':event},'checkpointHash')]


def verify_restoration(backup,fresh,rows,sdk,data_models=None,*,sdk_actions=None):
    validate_backup(backup)
    if fresh.get('workbookId')!=backup['scope']['documentId'] or fresh.get('contents')!=backup['document']['contents']:raise ValueError('original document not restored')
    if set(rows)!=set(backup['rows']) or sdk!=backup['sdk']:raise ValueError('complete SDK display and row readback required')
    for eid,capture in rows.items():
        types=backup['rows'][eid]['binding']['columnTypes']
        if _comparable_rows(capture,types)!=_comparable_rows(backup['rows'][eid],types):raise ValueError('business rows not restored')
    models=data_models or {}
    if set(models)!=set(backup['dataModels']):raise ValueError('all affected data-model readbacks required')
    for identity,model in backup['dataModels'].items():
        actual=models[identity]
        if actual.get('complete') is not True or actual.get('dataModelId')!=identity or not isinstance(actual.get('documentVersion'),int) or actual.get('contents')!=model['contents']:
            raise ValueError('affected data-model business document not restored')
    action_proof=verify_action_preservation(backup['sdkActions'],sdk_actions,fresh)
    return {'sdkActionProof':action_proof,'status':'RESTORED_BUSINESS_VALUES_AND_DOCUMENT_DISPLAY','backupHash':backup['backupHash'],'restorationHash':_digest({'document':fresh,'rows':rows,'sdk':sdk,'dataModels':data_models or {}}),'limitations':backup['limitations']}


def finalize_mutation(plan,fresh,dry_run,*,consumed=(),reviewed_warning_hash=None,fresh_sdk_actions=None):
    """Finalize promotion/rollback document PUT only after actual exact dry-run.

    Record the plan hash as consumed before dispatch. After an ambiguous network
    result, inspect the actual document and checkpoint; never blindly resend.
    """
    if 'promotionHash' in plan:
        try:
            from .acceptance import require_full_matrix_scope
        except ImportError:
            from acceptance import require_full_matrix_scope
        matrix=(plan.get('acceptance') or {}).get('matrix')
        if not isinstance(matrix,dict):raise ValueError('promotion requires its reviewed full-scope acceptance matrix')
        require_full_matrix_scope(matrix)
    field='promotionHash' if 'promotionHash' in plan else 'rollbackHash';identity=plan.get(field)
    if not identity or identity!=_digest({k:v for k,v in plan.items() if k!=field}):raise ValueError('mutation plan hash stale')
    if identity in consumed:raise ValueError('mutation replay refused')
    request=plan.get('request') or plan['documentRequest']
    expected=request['body']['documentVersion']
    if fresh.get('documentVersion')!=expected or request['path']!=f"/v2/workbooks/{fresh.get('workbookId')}/contents":raise ValueError('fresh original version mismatch')
    if dry_run.get('httpStatus')!=200 or dry_run.get('dryRun') is not True or dry_run.get('planHash')!=identity or not dry_run.get('evidenceId') or dry_run.get('errors') or dry_run.get('valid') is False:raise ValueError('actual hash-bound dry-run required')
    if dry_run.get('warnings') and reviewed_warning_hash!=_digest(dry_run['warnings']):raise ValueError('dry-run warnings require review')
    validate_action_inventory(fresh_sdk_actions,fresh)
    if field=='promotionHash':verify_action_preservation(plan['sdkActionsBefore'],fresh_sdk_actions,fresh)
    return {**copy.deepcopy(request),'consumeBeforeSend':identity}
