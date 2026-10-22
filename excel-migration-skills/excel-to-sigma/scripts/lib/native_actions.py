"""Source-bound native action candidates. No VBA execution or live API calls.

Construction approval is deliberately separate from runtime acceptance. Programs
have no optimistic success UI: update_rows exposes no affected-row result. A
fresh controller readback must establish the business outcome before any success
is reported. Ordinary input tables provide no concurrent uniqueness guarantee.
"""
from __future__ import annotations

import ast
import hashlib
import json
import copy
import datetime as dt
import re
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from .macro_behavior import validate_macro_source, procedure_by_identity
    from .migration_manifest import build_manifest, validate_manifest
    from .input_sync import (_approved_feature, _digest, build_artifact_records,
        plan_input_extension, checkpoint_input_extension, emit_construction_program)
    from .input_display import _system_column_contract, _editable_column_contract
    from . import code_rep
except ImportError:
    from macro_behavior import validate_macro_source, procedure_by_identity
    from migration_manifest import build_manifest, validate_manifest
    from input_sync import (_approved_feature, _digest, build_artifact_records,
        plan_input_extension, checkpoint_input_extension, emit_construction_program)
    from input_display import _system_column_contract, _editable_column_contract
    import code_rep


class NativeActionError(ValueError):
    pass


APPROVAL_COLUMNS = [
    {'name':'ApprovedAt','type':'datetime','provenance':'macro-column16'},
    {'name':'Last Approval Operation ID','type':'text','provenance':'task4-safeguard'},
    {'name':'Applied Approval Operation IDs','type':'text','provenance':'task4-safeguard'},
]
OPERATION_FIELDS = [('Workflow','text'),('Target Row ID','text'),('Target Business Key','text'),
    ('Context','text'),('Source Hash','text'),('Plan Hash','text'),('Created At','datetime'),
    ('State','text'),('Completed At','datetime'),('Outcome','text')]
LIMITS = ['UNVERIFIED_PUBLISHED_SELECTION_CARDINALITY', 'UNVERIFIED_WRITE_OUTCOME',
    'UNVERIFIED_CONCURRENCY: read-then-write guards are not warehouse uniqueness constraints',
    'UNVERIFIED_REOPEN_RECOVERY: recover the same prepared operation before retry',
    'PARTIAL_FAILURE: multiple effects are sequential and have no cross-effect transaction']


def _architecture(manifest):
    value=manifest.get('planProjection',{}).get('nativeActionArchitecture')
    if not isinstance(value,dict) or value.get('version')!=1:
        raise NativeActionError('manifest has no hash-bound native action architecture')
    return value


def _review(decision):
    return (isinstance(decision,dict) and decision.get('reviewStatus')=='approved'
            and bool(str(decision.get('reviewer') or '').strip())
            and bool(str(decision.get('decisionId') or '').strip()))


def _rows(readback, key):
    if not isinstance(readback,dict) or not readback.get('rowIdColumn'):
        raise NativeActionError('input readback requires the real row-ID column')
    rows=readback.get('rows'); rid=readback['rowIdColumn']
    if not isinstance(rows,list):raise NativeActionError('input readback rows required')
    ids=[r.get(rid) for r in rows];keys=[r.get(key) for r in rows] if key else ids
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
        raise NativeActionError('missing or ambiguous physical row ID')
    if any(k is None for k in keys) or len(set(map(str,keys)))!=len(keys):
        raise NativeActionError('missing or ambiguous business key')
    return {r[rid]:r for r in rows}


def _complete_input_readback(readback, columns, *, row_ids=None, row_id_column=None):
    """Require every editable field and the physical ID, never a narrow SELECT."""
    names=[c['name'] for c in columns]
    if len(set(names))!=len(names):raise NativeActionError('preservation schema has duplicate fields')
    if not isinstance(readback,dict):raise NativeActionError('complete input schema readback is required')
    rid=readback.get('rowIdColumn')
    if not rid or rid in names or (row_id_column is not None and rid!=row_id_column):
        raise NativeActionError('complete input schema requires the approved physical ID field')
    rows=readback.get('rows')
    if not isinstance(rows,list) or any(not isinstance(r,dict) or set(r)!=set(names)|{rid} for r in rows):
        raise NativeActionError('complete input schema requires every original editable field plus physical ID')
    indexed=_rows(readback,None)
    if row_ids is not None and set(indexed)!=set(row_ids):
        raise NativeActionError('preservation requires exact original physical row ID coverage')
    return indexed


def _preservation_contract(manifest, feature):
    architecture=_architecture(manifest)
    contract=architecture.get('baseInputSchemas',{}).get(feature)
    if (not isinstance(contract,dict) or not isinstance(contract.get('columns'),list)
            or not contract.get('rowIdColumn') or not isinstance(contract.get('rowIds'),list)):
        raise NativeActionError('complete original schema preservation contract is required')
    spec=manifest['planProjection']['sharedInputArchitecture']['inputs'][feature]
    if (feature=='expenseBusinessInput' and (contract['columns']!=spec['columns'][:-3]
            or len(contract['columns'])!=11 or len(contract['rowIds'])!=48)):
        raise NativeActionError('expense preservation must bind all 11 original fields and 48 IDs')
    return contract


def _check_preservation(before, after, contract, additions):
    columns=contract['columns'];rid=contract['rowIdColumn'];ids=contract['rowIds']
    old=_complete_input_readback(before,columns,row_ids=ids,row_id_column=rid)
    new=_complete_input_readback(after,columns+additions,row_ids=ids,row_id_column=rid)
    for key,row in old.items():
        if any(new[key][name]!=value for name,value in row.items()):
            raise NativeActionError('extension did not preserve original field values')
        if any(new[key][c['name']] is not None for c in additions):
            raise NativeActionError('extension did not preserve all-null added fields')
    return len(old),len(old)*len(columns)


def _spec(template,name,fields):
    return {**{k:copy.deepcopy(template[k]) for k in ('connectionId','writebackSchemaId','editMode','frame') if k in template},
            'editMode':'published-explore',
            'name':name,'keyColumns':['Operation ID'] if name!='Workflow Operations' else [],
            'columns':[{'name':n,'type':t,'provenance':'task4-reviewed-workflow'} for n,t in fields], 'rows':[]}


def _procedure(analyses,decision):
    matches=[p for a in analyses for p in a['procedures'] if p['procedureId']==decision.get('procedureId')]
    if len(matches)!=1:raise NativeActionError('reviewed procedure must resolve exactly once')
    proc=matches[0]
    if proc['procedureSha256']!=decision.get('procedureSha256'):
        raise NativeActionError('reviewed procedure hash is stale')
    if proc['unresolvedDependencies'] or proc['externalSideEffects']:
        raise NativeActionError('unresolved helper/external side effect cannot authorize a native action')
    return proc


def _contract(workflow,proc,decision):
    """Narrow body facts plus explicit reviewed mappings authorize each route."""
    if proc.get('unresolvedDependencies') or proc.get('externalSideEffects'):
        raise NativeActionError('unresolved source call/mutation cannot authorize a native contract')
    writes=proc['writes'];body=proc['sourceBody']
    if workflow=='approval':
        if (not proc['selectedRecord'] or len(writes)!=2
                or [w.get('column') for w in writes]!=[9,16]
                or any(w.get('row')!=proc['selectedRecord']['variable'] for w in writes)
                or writes[0].get('value')!='"Approved"' or not writes[1].get('usesNow')
                or len(proc['guards'])!=2
                or not re.fullmatch(re.escape(proc['selectedRecord']['variable'])+r'\s*<\s*2',
                                    proc['guards'][0]['condition'],re.I)
                or not re.fullmatch(r'ActiveSheet\.Name\s*<>\s*"Expense Register"',
                                    proc['guards'][1]['condition'],re.I)):
            raise NativeActionError('approval body is not the reviewed selected-record update')
        for write in writes:
            # A partial suffix match is not a worksheet ownership proof.
            target=write['target']
            expected=r'(?:ActiveSheet\.|(?:Sheets|Worksheets)\(\s*"Expense Register"\s*\)\.)?Cells\(\s*'+re.escape(proc['selectedRecord']['variable'])+r'\s*,\s*'+str(write['column'])+r'\s*\)'
            if not re.fullmatch(expected,target,re.I):
                raise NativeActionError('approval write worksheet must resolve to guarded Expense Register')
        if decision.get('target')!='expenseBusinessInput':raise NativeActionError('approval target must be expenseBusinessInput')
    elif workflow=='navigation':
        if proc['disposition']['operation']!='navigate' or writes:
            raise NativeActionError('navigation body has unsupported behavior')
    elif workflow=='applyScenario':
        expected=[('B5','0.06'),('B6','0.02'),('B5','0.01'),('B6','0.01')]
        if ([(w.get('address'),w.get('value')) for w in writes]!=expected
                or any(w.get('sheet')!='Assumptions' for w in writes)
                or re.findall(r'Case\s+"([^"]+)"',body)!=['Aggressive','Conservative']):
            raise NativeActionError('scenario body differs from reviewed source assignments')
        if len(decision.get('assumptions') or [])!=2:raise NativeActionError('scenario needs two explicit assumption mappings')
    elif workflow=='saveScenario':
        if (not any(w['kind']=='append' and w.get('evidence')=='ListRows.Add' for w in writes)
                or {r['identity'] for r in proc['reads']}!={'Assumptions!B5','Assumptions!B6'}):
            raise NativeActionError('scenario save source contract differs')
        if len(decision.get('assumptions') or [])!=2:raise NativeActionError('save needs two explicit assumption mappings')
    elif workflow=='snapshot':
        ranges=proc['affectedRanges']
        if proc['disposition']['operation']!='append':raise NativeActionError('snapshot destination append is not proven')
        if not any(r['identity']=='P&L!H7:M33' and (r['rows'],r['columns'])==(27,6) for r in ranges):
            raise NativeActionError('snapshot source rectangle differs')
        if (decision.get('mappingKind')!='reviewed-replacement'
                or not decision.get('overwriteDisposition') or not decision.get('rangeMismatchDisposition')
                or not decision.get('projection')):
            raise NativeActionError('snapshot requires reviewed H7 overwrite and range-mismatch replacement')
        pairs=[(p.get('line'),p.get('period')) for p in decision['projection']]
        names=[p.get('name') for p in decision['projection']]
        if (any(not a or not b for a,b in pairs) or len(set(pairs))!=len(pairs)
                or len(set(names))!=len(names) or any(not n for n in names)):
            raise NativeActionError('snapshot requires unique explicit line/period identities')
    else:raise NativeActionError('unsupported Task4 workflow')
    if workflow in {'applyScenario','saveScenario'}:
        assumptions=decision['assumptions']
        if {a.get('sourceCell') for a in assumptions}!={'Assumptions!B5','Assumptions!B6'}:
            raise NativeActionError('assumption mappings must bind B5 and B6 explicitly')
        for a in assumptions:
            if not all(a.get(k) for k in ('feature','keyColumn','key','valueColumn','name')):
                raise NativeActionError('incomplete source-bound assumption identity')


def build_native_action_plan(*,workbook_source,base_manifest,base_receipt,presentation_bindings,
                             current_contents,input_readbacks,macro_analyses,decisions):
    validate_manifest(base_manifest,workbook_source)
    shared=copy.deepcopy(base_manifest['planProjection']['sharedInputArchitecture'])
    original_schemas={}
    for feature,spec in shared['inputs'].items():
        if feature=='expenseBusinessInput':
            complete=_complete_input_readback(input_readbacks.get(feature),spec['columns'])
            original_schemas[feature]={'columns':copy.deepcopy(spec['columns']),
                'rowIdColumn':input_readbacks[feature]['rowIdColumn'],'rowIds':sorted(complete)}
        _approved_feature(base_manifest,base_receipt,feature,require_assigned=True)
        key=(spec.get('keyColumns') or [None])[0]
        _rows(input_readbacks.get(feature),key)
    if (current_contents.get('workbookId')!=base_manifest.get('target',{}).get('documentId')
            or current_contents.get('documentVersion')!=base_manifest.get('target',{}).get('version')
            or code_rep.document(current_contents).get('kind')!='workbook'):
        raise NativeActionError('base target/version or workbook kind is stale')
    for analysis in macro_analyses:
        validate_macro_source(analysis)
        if analysis.get('sourceKind')!='raw-module' or Path(analysis['sourcePath']).suffix.lower() not in {'.bas','.cls','.frm','.vba','.txt'}:
            raise NativeActionError('native mapping requires separately hash-bound raw module artifacts')
    workflows={};unresolved=[]
    for workflow,decision in decisions.items():
        if not _review(decision):
            unresolved.append({'workflow':workflow,'reason':'mapping requires named approved review'});continue
        proc=_procedure(macro_analyses,decision);_contract(workflow,proc,decision)
        if decision.get('mappingKind') not in {'exact','reviewed-replacement'}:
            raise NativeActionError('unresolved mapping cannot emit')
        if decision.get('page') not in presentation_bindings.get('pages',{}):
            raise NativeActionError('workflow page lacks actual presentation binding')
        module=next(a for a in macro_analyses if proc in a['procedures'])
        workflows[workflow]={'procedureId':proc['procedureId'],'procedureSha256':proc['procedureSha256'],
            'moduleByteSha256':module['moduleByteSha256'],'sourceReads':proc['reads'],
            'sourceWrites':proc['writes'],'sourceOverwrites':proc['overwrites'],'guards':proc['guards'],
            'decision':copy.deepcopy(decision),'mappingKind':decision['mappingKind'],
            'operationPolicy':'insert_row returns physical operation ID; explicit prepare/new intent, reuse on retry',
            'successPolicy':'no toast; require fresh confirmed business readback', 'status':'STAGED_CANDIDATE'}
    for analysis in macro_analyses:
        mapped={w['procedureId'] for w in workflows.values()}
        for proc in analysis['procedures']:
            if proc['procedureId'] not in mapped:
                unresolved.append({'procedureId':proc['procedureId'],'procedureSha256':proc['procedureSha256'],
                    'reason':proc['unresolvedDependencies'] or proc['externalSideEffects'] or 'no reviewed native mapping'})
    template=next(iter(shared['inputs'].values()))
    operation_fields=list(OPERATION_FIELDS)
    if 'approval' in workflows:
        operation_fields += [('Before:'+c['name'],c['type']) for c in shared['inputs']['expenseBusinessInput']['columns']]
    if any(w in workflows for w in ('applyScenario','saveScenario')):
        operation_fields += [('Scenario Name','text')]
    captures={}
    for w in ('saveScenario','snapshot'):
        if w in workflows:
            values=workflows[w]['decision'].get('assumptions') or workflows[w]['decision'].get('projection')
            for a in values:
                captures['Captured:'+a['name']]='number'
    operation_fields += list(captures.items())
    shared['inputs']['workflowOperations']=_spec(template,'Workflow Operations',operation_fields)
    if 'approval' in workflows:
        spec=shared['inputs']['expenseBusinessInput']
        if len(spec['columns'])!=11 or len(spec['rows'])!=48:
            raise NativeActionError('expense extension requires reviewed 48×11 source shape')
        spec['columns']+=copy.deepcopy(APPROVAL_COLUMNS)
        for row in spec['rows']:row.update({c['name']:None for c in APPROVAL_COLUMNS})
    if 'saveScenario' in workflows:
        fields=[('Operation ID','text'),('Scenario Name','text')]+[(a['name'],'number') for a in workflows['saveScenario']['decision']['assumptions']]
        fields += [('Saved At','datetime'),('Source Hash','text'),('Plan Hash','text')]
        shared['inputs']['savedScenarios']=_spec(template,'Saved Scenarios',fields)
    if 'snapshot' in workflows:
        fields=[('Operation ID','text'),('Captured At','datetime'),('Source Hash','text'),('Plan Hash','text'),
                ('Source Procedure Hash','text'),('Replacement Decision ID','text')]
        fields += [(p['name'],'number') for p in workflows['snapshot']['decision']['projection']]
        shared['inputs']['forecastSnapshots']=_spec(template,'Forecast Snapshots',fields)
    architecture={'version':1,'base':{'sourceHash':base_manifest['sourceHash'],'planHash':base_manifest['planHash'],
        'stagingReceiptHash':_digest(base_receipt),'target':base_manifest['target']},
        'sourceModules':copy.deepcopy(macro_analyses),'sourcePresentation':copy.deepcopy(presentation_bindings),
        'baseInputReadbackHashes':{k:_digest(v) for k,v in input_readbacks.items()},
        'baseInputSchemas':original_schemas,
        'workflows':workflows,'reviewedDecisions':copy.deepcopy(decisions),'unresolved':unresolved,
        'limitations':LIMITS,'productionStatus':'BLOCKED'}
    projection=copy.deepcopy(base_manifest['planProjection'])
    projection.update(sharedInputArchitecture=shared,nativeActionArchitecture=architecture)
    projection['formulaCells']=copy.deepcopy(base_manifest['formulaCells'])
    manifest=build_manifest(workbook_source,projection);manifest['target']=copy.deepcopy(base_manifest['target'])
    validate_native_action_plan(manifest)
    return manifest


def validate_native_action_plan(manifest,*,rehash_sources=True):
    validate_manifest(manifest);architecture=_architecture(manifest)
    if architecture.get('productionStatus')!='BLOCKED':raise NativeActionError('native production gate must remain BLOCKED')
    for analysis in architecture['sourceModules']:
        if rehash_sources:validate_macro_source(analysis)
    for workflow,record in architecture['workflows'].items():
        decision=record['decision']
        if not _review(decision):raise NativeActionError('missing approved mapping review')
        proc=_procedure(architecture['sourceModules'],decision);_contract(workflow,proc,decision)
    return True


def emit_action_schema(manifest,receipt,feature,*,current_columns=None):
    validate_native_action_plan(manifest)
    if current_columns is not None:
        extension=plan_input_extension(manifest,receipt,feature,current_columns)
        extension['preservationRequired']=True
        extension['requiredBeforeHash']=_architecture(manifest)['baseInputReadbackHashes'].get(feature)
        extension['preservationContract']=copy.deepcopy(_preservation_contract(manifest,feature))
        extension['preservationContractHash']=_digest(extension['preservationContract'])
        return extension
    _approved_feature(manifest,receipt,feature)
    return {'feature':feature,'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],
            'program':emit_construction_program(manifest,receipt,feature),'productionStatus':'BLOCKED'}


def checkpoint_action_schema(extension,created_columns,*,result_version,before,after):
    """Additive columns are accepted only with unchanged existing values and IDs."""
    if _digest(before)!=extension.get('requiredBeforeHash'):
        raise NativeActionError('extension preservation baseline differs from reviewed source readback')
    contract=extension.get('preservationContract')
    if not isinstance(contract,dict) or extension.get('preservationContractHash')!=_digest(contract):
        raise NativeActionError('complete original schema preservation contract is missing or stale')
    preserved_rows,preserved_values=_check_preservation(before,after,contract,extension['missingColumns'])
    new=_rows(after,None)
    readback={k:after[k] for k in ('readbackId','elementId','version')}
    readback['columns']={n:{'columnId':cid,'values':[r[n] for r in new.values()]} for n,cid in created_columns.items()}
    proof=checkpoint_input_extension(extension,created_columns,result_version=result_version,readback=readback)
    proof.update(preservedRowCount=preserved_rows,preservedValueCount=preserved_values,
        originalEditableColumns=copy.deepcopy(contract['columns']),
        preservationContract=copy.deepcopy(contract),
        preservationReadbacks={'before':copy.deepcopy(before),'after':copy.deepcopy(after)},
        beforeHash=_digest(before),afterHash=_digest(after))
    proof['preservationHash']=_digest({k:v for k,v in proof.items() if k!='preservationHash'})
    return proof


def _document(current,manifest):
    target=manifest['target']
    if current.get('workbookId')!=target['documentId'] or current.get('documentVersion')!=target['version']:
        raise NativeActionError('current target document/version is stale')
    doc=code_rep.document(current)
    if doc.get('kind')!='workbook':raise NativeActionError('contents.kind must be workbook')
    try:layout=ET.fromstring('<Layout>'+re.sub(r'<\?xml[^?]*\?>','',doc.get('layout') or '')+'</Layout>')
    except ET.ParseError as e:raise NativeActionError('cannot prove layout ownership') from e
    return doc,layout



def _layout_element_owners(layout,element_id):
    owners=[]
    for page in layout.iter('Page'):
        for node in page.iter('Element'):
            public=node.get('elementId');legacy=node.get('id')
            if public and legacy and public!=legacy and element_id in (public,legacy):
                raise NativeActionError('ambiguous layout Element identity')
            if (public or legacy)==element_id:owners.append(page)
    return owners


def bind_native_action_target(manifest,receipt,*,current_contents,input_readbacks):
    validate_native_action_plan(manifest);doc,layout=_document(current_contents,manifest)
    architecture=_architecture(manifest);pages=architecture['sourcePresentation']['pages']
    tables={};specs=manifest['planProjection']['sharedInputArchitecture']['inputs']
    for page_id in pages.values():
        if (sum(p.get('id')==page_id for p in doc.get('pages',[]))!=1
                or sum(p.get('id')==page_id for p in layout.iter('Page'))!=1):
            raise NativeActionError('assigned page must occur once in pages and layout')
    for feature,spec in specs.items():
        _,target,_=_approved_feature(manifest,receipt,feature,require_assigned=True)
        matches=[e for e in doc['elements'] if e.get('id')==target['elementId']]
        if len(matches)!=1 or matches[0].get('kind')!='input-table':
            raise NativeActionError('assigned input table did not resolve exactly once')
        owners=_layout_element_owners(layout,target['elementId'])
        if len(owners)!=1 or owners[0].get('id')!=target['pageId']:
            raise NativeActionError('assigned input table has wrong/ambiguous page ownership')
        actual=matches[0].get('columns') or []
        for c in spec['columns']:
            match=[a for a in actual if a.get('id')==target['columnIds'][c['name']] and a.get('name')==c['name']]
            if len(match)!=1 or ('type' in match[0] and match[0]['type']!=c['type']):
                raise NativeActionError('assigned editable column identity/type is stale')
        readback=input_readbacks.get(feature);key=(spec.get('keyColumns') or [None])[0]
        _rows(readback,key)
        if feature=='expenseBusinessInput' and 'approval' in architecture['workflows']:
            contract=_preservation_contract(manifest,feature)
            _complete_input_readback(readback,spec['columns'],row_ids=contract['rowIds'],
                row_id_column=contract['rowIdColumn'])
        system=_system_column_contract(target)
        system['id']=system.get('id') or target.get('rowIdColumnId') or readback['rowIdColumn']
        tables[feature]={'target':copy.deepcopy(target),'systemColumn':system,'readbackHash':_digest(readback),
            'identities':[{'rowId':r[readback['rowIdColumn']], 'key':{k:r[k] for k in spec.get('keyColumns') or []}} for r in readback['rows']]}
    if 'expenseBusinessInput' in tables:
        tables['expenseBusinessInput']['inputReadback']=copy.deepcopy(input_readbacks['expenseBusinessInput'])
    reads={}
    for feature,target in architecture['sourcePresentation'].get('readTargets',{}).items():
        if not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',feature) or feature in tables:
            raise NativeActionError('read-target alias is unsafe or collides with input')
        matches=[e for e in doc['elements'] if e.get('id')==target.get('elementId')]
        if len(matches)!=1 or matches[0].get('kind')!='table' or _digest(matches[0])!=target.get('elementHash'):
            raise NativeActionError('reviewed live projection element/formula changed')
        owners=_layout_element_owners(layout,target['elementId'])
        if len(owners)!=1 or owners[0].get('id')!=target['pageId']:
            raise NativeActionError('live projection page ownership changed')
        for name,cid in target['columnIds'].items():
            if sum(c.get('id')==cid and c.get('name')==name for c in matches[0]['columns'])!=1:
                raise NativeActionError('live projection column identity changed')
        keys=target.get('keyColumns');readback=input_readbacks.get(feature) or {}
        if not keys or not isinstance(readback.get('rows'),list):
            raise NativeActionError('live projection requires composite-key readback')
        identities=[tuple(r.get(k) for k in keys) for r in readback['rows']]
        if any(None in t for t in identities) or len(set(identities))!=len(identities):
            raise NativeActionError('live projection keys missing or ambiguous')
        reads[feature]={'target':copy.deepcopy(target),'readbackHash':_digest(readback),
            'identities':[dict(zip(keys,t)) for t in identities]}
    result={'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],
        'target':manifest['target'],'pages':pages,'tables':tables,'readTargets':reads,'contentsHash':_digest(doc)}
    result['bindingHash']=_digest(result)
    return result


def _conjoin(values):
    if not values:return 'const_bool(True)'
    pending=list(values)
    while len(pending)>1:
        pending=[f'and_({pending[i]}, {pending[i+1]})' if i+1<len(pending) else pending[i]
                 for i in range(0,len(pending),2)]
    return pending[0]


def _c(feature,name):
    # SDK narrowing applies to local names, not repeated dictionary subscripts.
    # UTF-8 hex is collision-free for authored names, including punctuation.
    return 'c_'+feature+'_'+name.encode('utf-8').hex()


def _lit(value):return f'const_text({value!r})'


def _lookup_assumption(a):
    extras=''.join(', ('+_lit(e['value'])+', '+_c(a['feature'],e['column'])+')' for e in a.get('extraKeys',[]))
    return 'lookup('+_c(a['feature'],a['valueColumn'])+', '+_lit(a['key'])+', '+_c(a['feature'],a['keyColumn'])+extras+')'


def _native_action_authoring_plan(manifest,receipt,action_bindings,*,current_contents,staging_review=None):
    validate_native_action_plan(manifest);doc,layout=_document(current_contents,manifest)
    binding=action_bindings
    if (receipt.get('nativeActionBinding')!=binding or binding.get('sourceHash')!=manifest['sourceHash']
            or binding.get('planHash')!=manifest['planHash'] or binding.get('target')!=manifest['target']
            or binding.get('contentsHash')!=_digest(doc)
            or binding.get('bindingHash')!=_digest({k:v for k,v in binding.items() if k!='bindingHash'})):
        raise NativeActionError('native action binding/receipt/current contents is stale')
    for feature in binding['tables']:_approved_feature(manifest,receipt,feature,require_assigned=True)
    enabled=False
    if staging_review is not None:
        enabled=(staging_review.get('status')=='APPROVED_STAGING' and bool(staging_review.get('owner'))
            and staging_review.get('bindingHash')==binding['bindingHash']
            and staging_review.get('documentId')==manifest['target']['documentId']
            and staging_review.get('version')==manifest['target']['version'])
        if not enabled:raise NativeActionError('staging enable review is stale or targets a different document')
    architecture=_architecture(manifest)
    if 'approval' in architecture['workflows']:
        proof=(receipt.get('nativeActionSchemaProofs') or {}).get('expenseBusinessInput') or {}
        if (proof.get('status')!='CHECKPOINTED_EXTENSION'
                or proof.get('sourceHash')!=manifest['sourceHash'] or proof.get('planHash')!=manifest['planHash']
                or proof.get('beforeHash')!=architecture['baseInputReadbackHashes']['expenseBusinessInput']
                or proof.get('preservedRowCount')!=48
                or proof.get('documentId')!=manifest['target']['documentId']
                or proof.get('resultVersion',-1)>manifest['target']['version']
                or proof.get('preservationHash')!=_digest({k:v for k,v in proof.items() if k!='preservationHash'})):
            raise NativeActionError('expense action requires checkpointed extension preservation proof')
        contract=_preservation_contract(manifest,'expenseBusinessInput')
        snapshots=proof.get('preservationReadbacks') or {}
        if (proof.get('originalEditableColumns')!=contract['columns']
                or proof.get('preservationContract')!=contract
                or proof.get('preservedValueCount')!=528
                or _digest(snapshots.get('before'))!=proof.get('beforeHash')
                or _digest(snapshots.get('after'))!=proof.get('afterHash')):
            raise NativeActionError('expense preservation evidence omits complete original schema/readbacks')
        _check_preservation(snapshots.get('before'),snapshots.get('after'),contract,APPROVAL_COLUMNS)
        table=binding['tables']['expenseBusinessInput']
        bound_readback=table.get('inputReadback')
        _complete_input_readback(bound_readback,manifest['planProjection']['sharedInputArchitecture']['inputs']['expenseBusinessInput']['columns'],
            row_ids=contract['rowIds'],row_id_column=contract['rowIdColumn'])
        if _digest(bound_readback)!=table['readbackHash']:
            raise NativeActionError('bound complete expense schema readback is stale')
        columns=binding['tables']['expenseBusinessInput']['target']['columnIds']
        if proof.get('createdColumns')!={c['name']:columns[c['name']] for c in APPROVAL_COLUMNS}:
            raise NativeActionError('expense extension assigned columns are stale')
    lines=['# Native action construction candidate; productionStatus=BLOCKED',
        '# sourceHash='+manifest['sourceHash'],'# planHash='+manifest['planHash'],
        'from sigma.page import Page','from sigma.framing import GridFramed','from sigma.inputTable import InputTable, LiteralEditableColumn, SingleSelectEditableColumn, InputTableIDColumn',
        'from sigma.column import FormulaColumn','from sigma.levelTable import LevelTable','from sigma.control import add_text_control, add_number_control',
        'from sigma.action.inputTableEffects import insert_row, update_rows',
        'from sigma.action.navigateEffect import navigate_to',
        'from sigma.action.setControlValueEffect import set_control_value',
        'from sigma.action.controlFlow import if_else',
        'from sigma.formula import const_text, const_num, const_bool, eq, neq, and_, or_, not_, is_null, now, contains, ampersand, coalesce, as_text, as_num, count_if, count_distinct, lookup, if_, text']
    for i,(page,page_id) in enumerate(sorted(binding['pages'].items())):
        lines += [f'p{i} = sigma.workbook.get_page({page_id!r})',f'if not isinstance(p{i}, Page):',
                  "    raise RuntimeError('expected assigned page')"]
    pagevars={page:'p'+str(i) for i,page in enumerate(sorted(binding['pages']))}
    for feature,t in sorted(binding['tables'].items()):
        target=t['target'];system=t['systemColumn'];variable='t_'+feature
        lines += [f'h_{feature} = sigma.workbook.get_page({target["pageId"]!r})',
            f'if not isinstance(h_{feature}, Page):',"    raise RuntimeError('expected assigned input page')",
            f'{variable} = h_{feature}.get_element({target["elementId"]!r})',
            f'if not isinstance({variable}, InputTable):',"    raise RuntimeError('expected ordinary input table')",
            ]
        spec=manifest['planProjection']['sharedInputArchitecture']['inputs'][feature]
        for name,cid in sorted(target['columnIds'].items()):
            column=next(c for c in spec['columns'] if c['name']==name)
            contract=_editable_column_contract(manifest,target,column)
            v=_c(feature,name)
            lines += [f'{v} = {variable}.get_column({cid!r})',f'if not isinstance({v}, {contract["columnClass"]}):',
                      "    raise RuntimeError('expected assigned editable column class')",
                      f'if {v}.type() != {contract["type"]!r}:',"    raise RuntimeError('assigned column type changed')",
                      f'if {v}.name() != {name!r} or {v}.element_id() != {target["elementId"]!r}:',"    raise RuntimeError('assigned column name/owner changed')"]
            if contract['columnClass']=='SingleSelectEditableColumn':
                lines += [f'if {v}.allowed_values() != {contract["allowedValues"]!r}:',"    raise RuntimeError('source-list options changed')"]
        lines += [f'rid_{feature} = {variable}.get_column({system["id"]!r})']
        if system['columnClass']=='FormulaColumn':
            lines += [f'if not isinstance(rid_{feature}, FormulaColumn):',"    raise RuntimeError('expected reviewed row-ID alias')",
                f'if rid_{feature}.formula() != {system["formula"]!r} or rid_{feature}.element_id() != {system["elementId"]!r}:',
                "    raise RuntimeError('row-ID formula/owner changed')"]
        else:
            lines += [f'if not isinstance(rid_{feature}, InputTableIDColumn):',"    raise RuntimeError('expected physical system row-ID column')",
                f'if rid_{feature}.kind() != \"row_id\" or rid_{feature}.element_id() != {target["elementId"]!r} or rid_{feature}.name() != {system["name"]!r}:',
                "    raise RuntimeError('physical row-ID kind/owner changed')",
                ]
    for feature,read in sorted(binding.get('readTargets',{}).items()):
        target=read['target']
        lines += [f'h_{feature} = sigma.workbook.get_page({target["pageId"]!r})',
            f'if not isinstance(h_{feature}, Page):',"    raise RuntimeError('expected projection page')",
            f't_{feature} = h_{feature}.get_element({target["elementId"]!r})',
            f'if not isinstance(t_{feature}, LevelTable):',"    raise RuntimeError('expected native live projection')",
            ]
        for name,cid in sorted(target['columnIds'].items()):
            v=_c(feature,name)
            lines += [f'{v} = t_{feature}.get_column({cid!r})',f'if not isinstance({v}, FormulaColumn):',
                "    raise RuntimeError('expected assigned projection column')"]
    lines += ['audit_cursor = 1','for existing in h_workflowOperations.list_elements(flat=False):',
        '    if isinstance(existing, GridFramed):',
        '        audit_cursor = max(audit_cursor, existing.y() + existing.height())']
    artifacts=[]
    for workflow,record in sorted(architecture['workflows'].items()):
        decision=record['decision'];host=pagevars[decision['page']];prefix=workflow
        lines += [f'cursor = 1',f'for existing in {host}.list_elements(flat=False):',
            '    if isinstance(existing, GridFramed):',
            '        cursor = max(cursor, existing.y() + existing.height())']
        lines += [f'# workflow={workflow} procedureHash={record["procedureSha256"]}']
        if workflow=='navigation':
            destination=decision.get('destination','forecast-overview')
            if destination not in pagevars:raise NativeActionError('navigation destination lacks actual page ID')
            lines += [f'button = {host}.add_button("Go to forecast")',
                'button.set_frame(1, cursor, min(24, button.parent_grid_width()), 2)',
                f'sequence = button.on_click("Go to forecast", [navigate_to({pagevars[destination]})])',
                'sequence.set_disabled(True)', f'sequence.set_disabled({not enabled!r})',"print('action:navigation=' + sequence.id())"]
            artifacts.append(workflow);continue
        # A separate Prepare click is intentional: ActionVariable is ActionValue,
        # not FormulaResolvable, and same-sequence control reads are unproven.
        # Earlier workflows may have added buttons on the operations host.
        # Rescan before adding another control block rather than reuse a stale end.
        lines += ['for existing in h_workflowOperations.list_elements(flat=False):',
            '    if isinstance(existing, GridFramed):',
            '        audit_cursor = max(audit_cursor, existing.y() + existing.height())']
        op=prefix+'_operation';ctx=prefix+'_context';key=prefix+'_key';rowid=prefix+'_row';n=prefix+'_count'
        for var,label in [(op,'operation'),(ctx,'context'),(key,'record'),(rowid,'physical-row')]:
            lines += [f'{var} = add_text_control(h_workflowOperations, value="", variable_name={ (workflow+"-"+label)!r})',
                f'{var}.set_frame(1, audit_cursor, min(24, {var}.parent_grid_width()), 2)', 'audit_cursor = audit_cursor + 2']
        lines += [f'{n} = add_number_control(h_workflowOperations, value=0, variable_name={ (workflow+"-selection-count")!r})',
            f'{n}.set_frame(1, audit_cursor, min(24, {n}.parent_grid_width()), 2)', 'audit_cursor = audit_cursor + 2']
        if workflow=='approval':
            next_history=prefix+'_next_history'
            lines += [f'{next_history} = add_text_control(h_workflowOperations, value="", variable_name="approval-next-history")',
                f'{next_history}.set_frame(1, audit_cursor, min(24, {next_history}.parent_grid_width()), 2)', 'audit_cursor = audit_cursor + 2',
                f'if {next_history}.value() != "" or len({next_history}.list_targets()) != 0 or len({next_history}.list_action_sequences()) != 0:',
                "    raise RuntimeError('new approval History intermediary must be blank, unfiltered and action-free')"]
        if binding['pages'][decision['page']]==binding['tables']['workflowOperations']['target']['pageId']:
            lines += ['cursor = max(cursor, audit_cursor)']
        if workflow=='approval':
            table='expenseBusinessInput'
            view=decision.get('selectionView')
            if view:
                read=binding.get('readTargets',{}).get(view)
                rowfield=decision.get('selectionRowIdColumn','Input Row ID')
                if (not read or read['target']['pageId']!=binding['pages'][decision['page']]
                        or rowfield not in read['target']['columnIds'] or 'Expense ID' not in read['target']['columnIds']):
                    raise NativeActionError('approval selection view must bind row ID/business key on the action page')
                expected={(r['rowId'],r['key'].get('Expense ID')) for r in binding['tables'][table]['identities']}
                observed={(r.get(rowfield),r.get('Expense ID')) for r in read['identities']}
                if not observed or not observed.issubset(expected):
                    raise NativeActionError('selection view physical/business identity does not match expense input')
                selection_table='t_'+view;selection_id=_c(view,rowfield);selection_key=_c(view,'Expense ID')
            else:
                if binding['tables'][table]['target']['pageId']!=binding['pages'][decision['page']]:
                    raise NativeActionError('approval requires same-page input selection or a reviewed selectionView')
                selection_table='t_'+table;selection_id='rid_'+table;selection_key=_c(table,'Expense ID')
            # Private authoring AST anchor only. The public route compiler below
            # always removes this unsupported event from executable SDK output
            # and emits exact on-select Selection namespace fragments instead.
            lines += [f'capture = {selection_table}.on_select("Select expense", [',
                f'    set_control_value({rowid}, {selection_id}),',
                f'    set_control_value({key}, {selection_key}),',
                f'    set_control_value({n}, count_distinct({selection_id})),',
                f'    set_control_value({ctx}, {decision["page"]!r}),',
                f'    set_control_value({op}, "")])','capture.set_disabled(True)',f'capture.set_disabled({not enabled!r})']
            selection=_conjoin([f'eq({n}, const_num(1))',f'eq({ctx}, {_lit(decision["page"])})',
                f'neq({rowid}, const_text(""))',f'neq({key}, const_text(""))',
                f'eq(count_if({_conjoin([f"eq(rid_{table}, {rowid})",f"eq({_c(table, "Expense ID")}, {key})"])}), const_num(1))'])
        else:
            selection='const_bool(True)'
        # Escape changes highlighting, not captured controls/durable intent.
        lines += [f'clear_button = {host}.add_button("Clear selection context")',
                'clear_button.set_frame(1, cursor, min(24, clear_button.parent_grid_width()), 2)', 'cursor = cursor + 2',
                f'clear_sequence = clear_button.on_click("Clear captured context", [set_control_value({op}, ""), set_control_value({ctx}, ""), set_control_value({key}, ""), set_control_value({rowid}, ""), set_control_value({n}, 0.0)])',
                'clear_sequence.set_disabled(True)', f'clear_sequence.set_disabled({not enabled!r})']
        if workflow=='approval':
            summary_values={'state':f'if_({selection}, const_text("One expense is captured."), const_text("Select exactly one expense or clear this context."))',
                'record':f'if_({selection}, {key}, const_text("—"))','count':n}
            for name in ('Employee','Vendor','Amount'):
                summary_values[name.lower()]=f'if_({selection}, text(lookup({_c(table,name)}, {rowid}, rid_{table})), const_text("—"))'
            text='### Captured expense context\n{{state}}\n\nExpense: {{record}} · Employee: {{employee}} · Vendor: {{vendor}} · Amount: {{amount}}\n\nCaptured rows: {{count}}. Escape removes highlighting only. Clear selection context resets captured controls and keeps any prepared intent saved.'
            formula_values=', '.join(repr(k)+': '+v for k,v in summary_values.items())
            lines += [f'summary = {host}.add_text({text!r}, formulas={{{formula_values}}})',
                'summary.set_frame(1, cursor, min(24, summary.parent_grid_width()), 6)', 'cursor = cursor + 6']
        namevar=prefix+'_name'
        if workflow in {'applyScenario','saveScenario'}:
            lines += [f'{namevar} = add_text_control({host}, value="", variable_name={ (workflow+"-name")!r})',
                f'{namevar}.set_frame(1, cursor, min(24, {namevar}.parent_grid_width()), 2)', 'cursor = cursor + 2']
        prep_values={ 'Workflow':repr(workflow),'Target Row ID':rowid,'Target Business Key':key,
            'Context':repr(decision['page']),'Source Hash':repr(manifest['sourceHash']),
            'Plan Hash':repr(manifest['planHash']),'Created At':'now()','State':repr('PREPARED') }
        if workflow=='approval':
            original=manifest['planProjection']['sharedInputArchitecture']['inputs']['expenseBusinessInput']['columns'][:-3]
            for c in original:
                prep_values['Before:'+c['name']]=f'lookup({_c("expenseBusinessInput",c["name"])}, {rowid}, rid_expenseBusinessInput)'
        elif workflow in {'applyScenario','saveScenario'}:
            prep_values['Scenario Name']=namevar
        if workflow in {'saveScenario','snapshot'}:
            for a in decision.get('assumptions') or decision.get('projection'):
                target=({**binding['tables'],**binding.get('readTargets',{})}).get(a['feature'])
                if not target or a['valueColumn'] not in target['target']['columnIds']:
                    raise NativeActionError('live source lookup target/column is not bound')
                predicates=[f'eq({_c(a["feature"],a["keyColumn"])}, {_lit(a["key"])})']
                predicates += [f'eq({_c(a["feature"],e["column"])}, {_lit(e["value"])})' for e in a.get('extraKeys',[])]
                selection=_conjoin([selection,f'eq(count_if({_conjoin(predicates)}), const_num(1))'])
                prep_values['Captured:'+a['name']]=_lookup_assumption(a)
        values=', '.join(_c('workflowOperations',k)+': '+v for k,v in prep_values.items())
        pending_predicates=[f'eq({_c("workflowOperations","Workflow")}, {_lit(workflow)})',
            f'eq({_c("workflowOperations","Context")}, {_lit(decision["page"])})',
            f'eq({_c("workflowOperations","Source Hash")}, {_lit(manifest["sourceHash"])})',
            f'eq({_c("workflowOperations","Plan Hash")}, {_lit(manifest["planHash"])})',
            f'eq({_c("workflowOperations","Target Row ID")}, {rowid})',
            f'eq({_c("workflowOperations","Target Business Key")}, {key})',
            f'eq({_c("workflowOperations","State")}, const_text("PREPARED"))']
        lines += [f'pending_intent_count = as_num(coalesce(count_if({_conjoin(pending_predicates)}), const_num(0)))']
        lines += [f'prepare_insert = insert_row(t_workflowOperations, {{{values}}}, name="Prepare intent")',
            'prepared_id = prepare_insert.returns()',f'prepare_button = {host}.add_button({("Prepare "+workflow)!r})',
            'prepare_button.set_frame(1, cursor, min(24, prepare_button.parent_grid_width()), 2)', 'cursor = cursor + 2',
            f'prepare_sequence = prepare_button.on_click("Prepare new intent", [prepare_insert, set_control_value({op}, prepared_id)])',
            'prepare_sequence.set_disabled(True)', f'prepare_sequence.set_condition({_conjoin([selection,f"eq(as_text(coalesce({op}, const_text(''))), const_text(''))", 'eq(pending_intent_count, const_num(0))'])})',
            f'prepare_sequence.set_disabled({not enabled!r})',
            f'new_button = {host}.add_button({("Start new "+workflow)!r})',
            'new_button.set_frame(1, cursor, min(24, new_button.parent_grid_width()), 2)', 'cursor = cursor + 2',
            f'new_sequence = new_button.on_click("Start a new intentional operation", [update_rows(t_workflowOperations, eq(rid_workflowOperations, {op}), {{{_c("workflowOperations","State")}: "SUPERSEDED_NEW_INTENT"}}), set_control_value({op}, "")])',
            'new_sequence.set_disabled(True)', f'new_sequence.set_condition(eq(count_if(eq(rid_workflowOperations, {op})), const_num(1)))',
            f'new_sequence.set_disabled({not enabled!r})']
        # Recover a prepared operation by selecting its durable metadata row.
        # Physical ID + workflow + source/plan + context are rechecked on Apply.
        recovery=[f'set_control_value({op}, rid_workflowOperations)',
            f'set_control_value({rowid}, {_c("workflowOperations","Target Row ID")})',
            f'set_control_value({key}, {_c("workflowOperations","Target Business Key")})',
            f'set_control_value({ctx}, {_c("workflowOperations","Context")})',
            f'set_control_value({n}, count_distinct(rid_workflowOperations))']
        lines += [f'recover = t_workflowOperations.on_select({("Recover "+workflow+" intent")!r}, [{", ".join(recovery)}])',
            'recover.set_disabled(True)', f'recover.set_disabled({not enabled!r})']
        op_predicates=[f'eq(rid_workflowOperations, {op})',
            f'eq({_c("workflowOperations","Workflow")}, {_lit(workflow)})',
            f'eq({_c("workflowOperations","Context")}, {_lit(decision["page"])})',
            f'eq({_c("workflowOperations","Source Hash")}, {_lit(manifest["sourceHash"])})',
            f'eq({_c("workflowOperations","Plan Hash")}, {_lit(manifest["planHash"])})',
            f'eq({_c("workflowOperations","Target Row ID")}, {rowid})',
            f'eq({_c("workflowOperations","Target Business Key")}, {key})']
        if workflow=='applyScenario':
            op_predicates.append(f'eq({_c("workflowOperations","State")}, const_text("PREPARED"))')
        operation_guard=f'eq(count_if({_conjoin(op_predicates)}), const_num(1))'
        guard=_conjoin([selection,operation_guard,f'neq({op}, const_text(""))',f'not_(contains({op}, const_text("|")))'])
        effects=[]
        if workflow=='approval':
            history=_c('expenseBusinessInput','Applied Approval Operation IDs')
            token=f'ampersand(ampersand(const_text("|"), {op}), const_text("|"))'
            before_guards=[];scalar_before_guards=[]
            for c in manifest['planProjection']['sharedInputArchitecture']['inputs']['expenseBusinessInput']['columns'][:-3]:
                current=_c('expenseBusinessInput',c['name'])
                prior=f'lookup({_c("workflowOperations","Before:"+c["name"])}, {op}, rid_workflowOperations)'
                before_guards.append(f'or_(and_(is_null({current}), is_null({prior})), eq({current}, {prior}))')
                selected=f'lookup({current}, {rowid}, rid_expenseBusinessInput)'
                scalar_before_guards.append(f'or_(and_(is_null({selected}), is_null({prior})), eq({selected}, {prior}))')
            # Lookup comparisons inside CountIf have failed actual native
            # evaluation even when both scalar lookups match. Keep them scalar
            # in the event guard AND retain the full row predicate at the write.
            selected_history=f'lookup({history}, {rowid}, rid_expenseBusinessInput)'
            guard=_conjoin([guard,
                f'eq(lookup({_c("workflowOperations","State")}, {op}, rid_workflowOperations), const_text("PREPARED"))',
                f'not_(contains(as_text(coalesce({selected_history}, const_text(""))), {token}))',
                *scalar_before_guards])
            target_next_history=f'ampersand(ampersand(ampersand(as_text(coalesce({history}, const_text(""))), const_text("|")), {op}), const_text("|"))'
            selector=_conjoin([f'eq(rid_expenseBusinessInput, {rowid})',f'eq({_c("expenseBusinessInput","Expense ID")}, {key})',
                f'not_(contains(as_text(coalesce({history}, const_text(""))), {token}))',
                f'eq({next_history}, {target_next_history})']+before_guards)
            vals={ 'Approval Status':repr('Approved'),'ApprovedAt':'now()',
                'Last Approval Operation ID':op,'Applied Approval Operation IDs':next_history }
            # Native UpdateRows scalar History formulas failed validation even
            # after successful import. Stage the live text in a control first;
            # the write reads that control, retaining its complete row freeze.
            capture_history=f'ampersand(ampersand(ampersand(as_text(coalesce({selected_history}, const_text(""))), const_text("|")), {op}), const_text("|"))'
            effects=[f'set_control_value({next_history}, {capture_history})',
                'update_rows(t_expenseBusinessInput, '+selector+', {'+', '.join(_c('expenseBusinessInput',k)+': '+v for k,v in vals.items())+'}, name="Approve selected expense")']
        elif workflow=='applyScenario':
            scenario=f'lookup({_c("workflowOperations","Scenario Name")}, {op}, rid_workflowOperations)'
            for name,rates in [('Aggressive',[.06,.02]),('Conservative',[.01,.01])]:
                branch=[]
                for a,rate in zip(sorted(decision['assumptions'],key=lambda a:a['sourceCell']),rates):
                    if a['feature'] not in binding['tables']:raise NativeActionError('assumption input target absent')
                    identities=[r for r in binding['tables'][a['feature']]['identities'] if r['key'].get(a['keyColumn'])==a['key']]
                    if len(identities)!=1:raise NativeActionError('scenario assumption identity is missing or ambiguous')
                    selector=_conjoin([f'eq(rid_{a["feature"]}, {_lit(identities[0]["rowId"])})',
                        f'eq({_c(a["feature"],a["keyColumn"])}, {_lit(a["key"])})'])
                    guard=_conjoin([guard,f'eq(count_if({selector}), const_num(1))'])
                    branch.append(f'update_rows(t_{a["feature"]}, {selector}, {{{_c(a["feature"],a["valueColumn"])}: {rate!r}}})')
                lines += [f'{prefix}_{name} = [{", ".join(branch)}]']
            effects=[f'if_else([(eq({scenario}, const_text("Aggressive")), {prefix}_Aggressive), (eq({scenario}, const_text("Conservative")), {prefix}_Conservative)], [])']
        elif workflow=='saveScenario':
            captured_name=f'lookup({_c("workflowOperations","Scenario Name")}, {op}, rid_workflowOperations)'
            vals={'Operation ID':op,'Scenario Name':captured_name,'Saved At':'now()',
                  'Source Hash':repr(manifest['sourceHash']),'Plan Hash':repr(manifest['planHash'])}
            vals.update({a['name']:f'lookup({_c("workflowOperations","Captured:"+a["name"])}, {op}, rid_workflowOperations)' for a in decision['assumptions']})
            guard=_conjoin([guard,f'eq(as_num(coalesce(count_if(eq({_c("savedScenarios","Operation ID")}, {op})), const_num(0))), const_num(0))'])
            effects=['insert_row(t_savedScenarios, {'+', '.join(_c('savedScenarios',k)+': '+v for k,v in vals.items())+'})']
        elif workflow=='snapshot':
            vals={'Operation ID':op,'Captured At':'now()','Source Hash':repr(manifest['sourceHash']),
                'Plan Hash':repr(manifest['planHash']),'Source Procedure Hash':repr(record['procedureSha256']),
                'Replacement Decision ID':repr(decision['decisionId'])}
            for p in decision['projection']:
                # Only column handles in a uniquely keyed, reviewed native
                # projection are accepted, never cached workbook literals.
                a={'feature':p['feature'],'keyColumn':p['keyColumn'],'key':p['key'],'valueColumn':p['valueColumn']}
                if a['feature'] not in {**binding['tables'],**binding.get('readTargets',{})}:raise NativeActionError('snapshot live projection target absent')
                vals[p['name']]=f'lookup({_c("workflowOperations","Captured:"+p["name"])}, {op}, rid_workflowOperations)'
            guard=_conjoin([guard,f'eq(as_num(coalesce(count_if(eq({_c("forecastSnapshots","Operation ID")}, {op})), const_num(0))), const_num(0))'])
            effects=['insert_row(t_forecastSnapshots, {'+', '.join(_c('forecastSnapshots',k)+': '+v for k,v in vals.items())+'})']
        # IfElseAction cannot nest inside IfElseAction (ActionEffect-only lists).
        # ApplyScenario's one branch block is valid at sequence top level.
        lines += [f'confirm_button = {host}.add_button({("Confirm "+workflow)!r})',
            'confirm_button.set_frame(1, cursor, min(24, confirm_button.parent_grid_width()), 2)', 'cursor = cursor + 2',
            f'confirm_sequence = confirm_button.on_click({("Apply/retry "+workflow)!r}, [{", ".join(effects)}])',
            'confirm_sequence.set_disabled(True)', f'confirm_sequence.set_condition({guard})',f'confirm_sequence.set_disabled({not enabled!r})',
            "print('action:"+workflow+"=' + confirm_sequence.id())"]
        artifacts.append(workflow)
    program='\n'.join(lines)+'\n';compile(program,'native-action-program','exec')
    return {'program':program,'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],
        'bindingHash':binding['bindingHash'],'target':manifest['target'],'features':artifacts,
        'unresolved':architecture['unresolved'],'limitations':LIMITS,
        'stagingStatus':'ENABLED_REVIEWED_TEST_TARGET' if enabled else 'DISABLED_CANDIDATE',
        'productionStatus':'BLOCKED','acceptanceChecks':['published click','selection cardinality/context',
        'deleted/stale identity','retry A after B','new intentional save','reopen recovery',
        'failed/partial write','concurrent retries','before/after row and values','no optimistic success toast']}


def _timestamp(value):
    """Accept an aware timestamp object or ISO timestamp with an explicit zone."""
    if isinstance(value,str):
        try:value=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:return None
    if not isinstance(value,dt.datetime) or value.tzinfo is None:
        return None
    try:
        if value.utcoffset() is None:return None
        return value.astimezone(dt.timezone.utc)
    except (ValueError,OverflowError):return None


def _approval_timestamp_matches(value,expected,capture):
    observed=_timestamp(value)
    if observed is None:return False
    explicit='approvedAt' in expected
    window=capture.get('executionWindow')
    if not explicit and window is None:return False
    if explicit:
        wanted=_timestamp(expected['approvedAt'])
        if wanted is None or observed!=wanted:return False
    if window is not None:
        if not isinstance(window,dict):return False
        start=_timestamp(window.get('startedAt'));end=_timestamp(window.get('completedAt'))
        if start is None or end is None or not start<=observed<=end:return False
    return True


def audit_native_action_readback(expected,capture):
    """Audit controller-captured rows, not a simulator of an assumed Sigma write."""
    failures=[];workflow=expected.get('workflow');op=expected.get('operationId')
    if not capture.get('evidenceId'):failures.append('missing independent readback evidence')
    if capture.get('operationId')!=op or not op or '|' in op:failures.append('invalid operation identity')
    if capture.get('context')!=expected.get('context'):failures.append('wrong page/context')
    if capture.get('writeOutcome') not in {'confirmed','confirmed-noop'}:failures.append('write outcome unknown/failed')
    before=capture.get('before') or [];after=capture.get('after') or []
    if workflow=='approval':
        if capture.get('selectionCount')!=1:failures.append('selection must contain exactly one record')
        rid=expected['rowIdColumn'];key=expected['keyColumn']
        left={r.get(rid):r for r in before};right={r.get(rid):r for r in after}
        wanted=expected['selectedRowId'];business=expected['selectedBusinessKey']
        if (len(left)!=len(before) or len(right)!=len(after) or set(left)!=set(right)
                or wanted not in left or left.get(wanted,{}).get(key)!=business
                or right.get(wanted,{}).get(key)!=business):failures.append('missing/deleted/ambiguous selected identity')
        else:
            old=left[wanted];new=right[wanted];token='|'+op+'|'
            if token in (old.get('Applied Approval Operation IDs') or ''):
                if new!=old:failures.append('retry changed previously applied approval')
            else:
                if (new.get('Approval Status')!='Approved' or not _approval_timestamp_matches(new.get('ApprovedAt'),expected,capture)
                        or new.get('Last Approval Operation ID')!=op
                        or new.get('Applied Approval Operation IDs')!=(old.get('Applied Approval Operation IDs') or '')+token):
                    failures.append('approval write not confirmed atomically')
            allowed=set(expected.get('writeFields') or [])
            if any(old.get(n)!=new.get(n) for n in set(old)|set(new) if n not in allowed):
                failures.append('unrelated expense field changed')
            if any(left[k]!=right[k] for k in left if k!=wanted):failures.append('wrong expense changed')
    elif workflow in {'saveScenario','snapshot'}:
        old=[r for r in before if r.get('Operation ID')==op];new=[r for r in after if r.get('Operation ID')==op]
        if len(new)!=1 or len(old)>1:failures.append('operation insert missing/duplicated')
        elif old and old!=new:failures.append('retry changed saved values')
        elif any(new[0].get(k)!=v for k,v in (expected.get('values') or {}).items()):failures.append('saved line/period/source values differ')
        other=lambda rs:sorted(_digest(r) for r in rs if r.get('Operation ID')!=op)
        if other(before)!=other(after):failures.append('unrelated saved records changed')
    elif workflow=='applyScenario':
        if capture.get('writeOutcome')!='confirmed' or after!=expected.get('after'):
            failures.append('scenario writes partial or differ from expected persisted rates')
    else:failures.append('unsupported business audit workflow')
    return {'status':'FAILED' if failures else 'PASSED_COMPONENT_READBACK', 'failures':failures,
        'operationId':op,'beforeHash':_digest(before),'afterHash':_digest(after),
        'evidenceId':capture.get('evidenceId'),'sourceHash':expected.get('sourceHash'),
        'planHash':expected.get('planHash'),'productionStatus':'BLOCKED'}


def emit_input_identity_projection(manifest,receipt,feature,*,current_contents,destination_page,name):
    """Emit a new read-only view of assigned inputs, including physical row IDs.

    This uses documented to_source/add_table/FormulaColumn construction. It does
    not change source visibility, types, values or validation. Assigned view IDs
    and fresh readback must be reviewed as readTargets before action attachment.
    """
    validate_manifest(manifest);doc,layout=_document(current_contents,manifest)
    spec,target,artifact=_approved_feature(manifest,receipt,feature,require_assigned=True)
    system=_system_column_contract(target)
    if (sum(p.get('id')==destination_page for p in doc.get('pages',[]))!=1
            or sum(p.get('id')==destination_page for p in layout.iter('Page'))!=1):
        raise NativeActionError('projection destination page is absent or ambiguous')
    if 'Input Row ID' in target['columnIds']:raise NativeActionError('reserved identity projection name collides')
    system_id=system.get('id') or target.get('rowIdColumnId')
    if not system_id:raise NativeActionError('projection requires an assigned row-ID column ID or reviewed alias')
    lines=['from sigma.page import Page','from sigma.framing import GridFramed',
        'from sigma.inputTable import InputTable, InputTableIDColumn',
        'from sigma.column import FormulaColumn','from sigma.formula import text',
        '# artifactHash='+artifact['artifactHash'],
        f'source_host = sigma.workbook.get_page({target["pageId"]!r})',
        'if not isinstance(source_host, Page):',"    raise RuntimeError('expected assigned source page')",
        f'source = source_host.get_element({target["elementId"]!r})',
        'if not isinstance(source, InputTable):',"    raise RuntimeError('expected assigned ordinary input')",
        f'source_row_id = source.get_column({system_id!r})']
    if system['columnClass']=='FormulaColumn':
        lines += ['if not isinstance(source_row_id, FormulaColumn):',"    raise RuntimeError('expected reviewed row-ID alias')",
            f'if source_row_id.formula() != {system["formula"]!r} or source_row_id.element_id() != {target["elementId"]!r}:',
            "    raise RuntimeError('reviewed row-ID alias formula/owner changed')"]
    else:
        lines += ['if not isinstance(source_row_id, InputTableIDColumn):',"    raise RuntimeError('expected system row-ID column')",
            f'if source_row_id.kind() != "row_id" or source_row_id.element_id() != {target["elementId"]!r}:',
            "    raise RuntimeError('system row-ID kind/owner changed')"]
    lines += [f'host = sigma.workbook.get_page({destination_page!r})','if not isinstance(host, Page):',
        "    raise RuntimeError('expected destination page')",'cursor = 1',
        'for existing in host.list_elements(flat=False):','    if isinstance(existing, GridFramed):',
        '        cursor = max(cursor, existing.y() + existing.height())',
        'projection = host.add_table(source.to_source())',f'projection.set_name({name!r})',
        'projection.set_frame(1, cursor, min(24, projection.parent_grid_width()), 12)',
        'projection_row_id = projection.add_column("Input Row ID", text(source_row_id))',
        "print('projectionElementId=' + projection.id())", "print('projectionRowIdColumnId=' + projection_row_id.id())"]
    return {'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],
        'artifactHash':artifact['artifactHash'],'target':manifest['target'],'feature':feature,
        'destinationPage':destination_page,'sourceElementId':target['elementId'],
        'status':'PENDING_ASSIGNED_PROJECTION_READBACK','productionStatus':'BLOCKED',
        'program':'\n'.join(lines)+'\n'}


def _authored_routes(manifest,receipt,binding,current_contents,staging_review=None):
    """Compile only our known authored AST, never live opaque SDK expressions.

    The private authoring plan is not executable output. Its old Boolean/selection
    syntax is consumed here and cannot leave this function as an SDK program.
    """
    authored=_native_action_authoring_plan(manifest,receipt,binding,current_contents=current_contents,staging_review=staging_review)
    source=authored.pop('program');tree=ast.parse(source)
    markers=[(i+1,re.match(r'# workflow=(\w+)',line)[1]) for i,line in enumerate(source.splitlines()) if re.match(r'# workflow=(\w+)',line)]
    def workflow(node):return next((w for line,w in reversed(markers) if line<=node.lineno),None)
    def called(node,name):return isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id==name
    assignments={};controls={};buttons={};conditions={};branches={}
    for node in tree.body:
        w=workflow(node)
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id;assignments[(w,name)]=node.value
            if called(node.value,'add_text_control') or called(node.value,'add_number_control'):
                variable=next(k.value.value for k in node.value.keywords if k.arg=='variable_name')
                controls[name]={'variableId':variable,'type':'number' if called(node.value,'add_number_control') else 'text','workflow':w,'hostVariable':ast.unparse(node.value.args[0])}
            if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='add_button':
                buttons[(w,name)]={'text':ast.literal_eval(node.value.args[0]),'host':ast.unparse(node.value.func.value)}
            if isinstance(node.value,ast.List) and any(called(n,'update_rows') for n in ast.walk(node.value)):branches[(w,name)]=node.value
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='set_condition':
            conditions[(w,ast.unparse(node.value.func.value))]=node.value.args[0]
    def updates(node,w):
        found=[n for n in ast.walk(node) if called(n,'update_rows')]
        for n in ast.walk(node):
            if isinstance(n,ast.Name) and (w,n.id) in branches:found.extend(updates(branches[(w,n.id)],w))
        return found
    def eligible(update):
        if not isinstance(update.args[0],ast.Name) or not update.args[0].id.startswith('t_'):raise NativeActionError('unknown authored row target')
        feature=update.args[0].id[2:]
        return binding['tables'][feature]['systemColumn']['columnClass']=='InputTableIDColumn'
    def identity(update):
        feature=update.args[0].id[2:];rid='rid_'+feature
        found=[n.args[1] for n in ast.walk(update.args[1]) if called(n,'eq') and len(n.args)==2 and isinstance(n.args[0],ast.Name) and n.args[0].id==rid]
        if len(found)!=1:raise NativeActionError('authored row predicate must contain one exact target physical identity')
        return feature,found[0]
    deferred=[];drop=set();condition_additions={}
    for node in tree.body:
        if not isinstance(node,ast.Assign) or len(node.targets)!=1 or not isinstance(node.targets[0],ast.Name) or not isinstance(node.value,ast.Call):continue
        w=workflow(node);var=node.targets[0].id;call=node.value
        if not isinstance(call.func,ast.Attribute) or call.func.attr not in {'on_select','on_click'}:continue
        us=updates(call,w)
        if (call.func.attr=='on_select' or any(not eligible(u) for u in us) or var=='clear_sequence'
                or (w=='approval' and var=='confirm_sequence')):
            role='selection' if var=='capture' else 'recovery' if var=='recover' else 'new-intent' if var=='new_sequence' else 'confirm' if var=='confirm_sequence' else 'clear-context' if var=='clear_sequence' else None
            if role is None:raise NativeActionError('unsupported deferred authored event')
            deferred.append({'workflow':w,'role':role,'variable':var,'hostVariable':ast.unparse(call.func.value),
                'call':ast.unparse(call),'condition':ast.unparse(conditions[(w,var)]) if (w,var) in conditions else None,
                'rowPredicates':[ast.unparse(u.args[1]) for u in us],
                'branches':{name:ast.unparse(value) for (wf,name),value in branches.items() if wf==w}})
            if var!='clear_sequence':drop.add((w,var))  # Retain the known disabled native factory for restoration.
        elif us:
            # Dictionary selection cannot embed the frozen predicate. Preserve the
            # WHOLE predicate in its original event condition, with exact CountIf.
            if (w,var) not in conditions:raise NativeActionError('row update requires complete authored condition')
            condition_additions[(w,var)]=[u.args[1] for u in us]
    class SafeSDK(ast.NodeTransformer):
        def visit_Call(self,node):
            if called(node,'update_rows'):
                if not eligible(node):raise NativeActionError('unsupported selector escaped safe SDK route')
                feature,value=identity(node)
                node.args[1]=ast.Dict(keys=[ast.Name(id='rid_'+feature,ctx=ast.Load())],values=[value])
            return self.generic_visit(node)
    safe=[];component_records=[]
    for node in tree.body:
        w=workflow(node)
        if isinstance(node,ast.ImportFrom):node.names=[a for a in node.names if a.name!='count_distinct']
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            var=node.targets[0].id
            if (w,var) in drop:continue
            if (w,var) in branches and any(not eligible(u) for u in updates(node.value,w)):continue
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute):
            owner=ast.unparse(node.value.func.value)
            if (w,owner) in drop:continue
            if node.value.func.attr=='set_condition' and (w,owner) in condition_additions:
                expression=ast.unparse(node.value.args[0])
                for predicate in condition_additions[(w,owner)]:expression=f'and_({expression}, eq(count_if({ast.unparse(predicate)}), const_num(1)))'
                node.value.args[0]=ast.parse(expression,mode='eval').body
        # print(action id) references are not valid for deferred assignments.
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='print':
            if any(isinstance(n,ast.Name) and (w,n.id) in drop for n in ast.walk(node)):continue
        safe.append(SafeSDK().visit(node))
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            var=node.targets[0].id
            if var in controls or (w,var) in buttons:
                key=var if var in controls else w+':'+var
                safe.extend(ast.parse(f"print({{'component': {key!r}, 'elementId': {var}.id()}})").body)
                component_records.append(key)
    tree.body=safe;ast.fix_missing_locations(tree);program=ast.unparse(tree)+'\n';compile(program,'safe-native-actions','exec')
    for n in ast.walk(tree):
        if called(n,'count_distinct') or (called(n,'update_rows') and not isinstance(n.args[1],ast.Dict)):
            raise NativeActionError('known unsupported SDK syntax escaped routing')
    return {**authored,'program':program,'constructionStatus':'PARTIAL_REQUIRES_PUBLIC_ACTIONS' if deferred else 'SDK_CANDIDATE_REQUIRES_RUNTIME',
        'publicActionRequirements':deferred,'componentControls':controls,'componentButtons':{w+':'+name:record for (w,name),record in buttons.items()},
        'assignedComponentReadbackRequired':component_records,'authoringAstHash':_digest(source),
        'limitations':[*authored['limitations'],'Selection namespace has no SDK expression getter; exact reviewed public actions required.',
            'Approval requires a full public formula row selector; native action/selector execution must be qualified before business use.',
            'Single-row selectors plus full CountIf predicates require serialized staging; predicate evaluation/write have a TOCTOU race. No transaction/affected-row guarantee.',
            *(['Approval first-effect failure-halt and stale intermediary behavior require independent runtime qualification; control capture alone is not a successful row write.',
               'Public REST import of control-staged approval History remains unqualified; native construction evidence does not transfer to a public fragment.']
              if 'approval' in _architecture(manifest)['workflows'] else [])]}


def emit_native_action_program(manifest,receipt,action_bindings,*,current_contents,staging_review=None):
    """Emit disabled safe construction; review never authorizes constructor replay.

    Enabling saved native sequences needs the exact missing-only/configuration
    adapter and actual disabled/readback proof. This constructor cannot do that.
    """
    result=_authored_routes(manifest,receipt,action_bindings,current_contents)
    candidate_hash=hashlib.sha256(result['program'].encode()).hexdigest()
    if staging_review is not None:
        expected={'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],'bindingHash':action_bindings['bindingHash'],
            'documentId':manifest['target']['documentId'],'version':manifest['target']['version'],'candidateProgramHash':candidate_hash}
        owner=str(staging_review.get('owner') or '').strip()
        if (staging_review.get('status')!='APPROVED_STAGING' or not owner or re.match(r'(?i)^(pending|todo|tbd|unknown)\b',owner)
                or staging_review.get('enable',False) is not False
                or any(staging_review.get(k)!=v for k,v in expected.items())):raise NativeActionError('exact disabled source/binding/program construction review required; saved native enabling is separate')
        result['constructionReview']=copy.deepcopy(staging_review)
    result['candidateProgramHash']=candidate_hash
    result['programHash']=hashlib.sha256(result['program'].encode()).hexdigest()
    if result['publicActionRequirements']:result['stagingStatus']='PARTIAL_REQUIRES_PUBLIC_ACTIONS'
    return result


def _public_formula(node,columns,controls,*,local_element_id=None):
    def render(child):return _public_formula(child,columns,controls,local_element_id=local_element_id)
    if isinstance(node,ast.Constant):
        if node.value is None:return 'Null'
        if type(node.value) is bool:return 'True' if node.value else 'False'
        return json.dumps(node.value,ensure_ascii=False)
    if isinstance(node,ast.Name):
        if node.id in controls:return '['+controls[node.id]['variableId']+']'
        if node.id in columns:
            column=columns[node.id]
            if column['elementId']==local_element_id:
                identifier=column['name']
                if not isinstance(identifier,str) or not identifier or any(char in identifier for char in '[]'):
                    raise NativeActionError('unescaped public local column identifier refused')
                return '['+identifier+']'
            return '['+column['tableName']+'/'+column['name']+']'
        raise NativeActionError('unknown authored public formula name: '+node.id)
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
        name=node.func.id
        if name in {'const_text','const_num','const_bool','as_text','as_num','as_bool','as_date'} and len(node.args)==1:return render(node.args[0])
        binary={'eq':'=','neq':'!=','and_':'and','or_':'or','ampersand':'&'}
        if name in binary and len(node.args)==2:return '('+render(node.args[0])+' '+binary[name]+' '+render(node.args[1])+')'
        functions={'is_null':'IsNull','contains':'Contains','coalesce':'Coalesce','count_if':'CountIf','lookup':'Lookup','now':'Now','not_':'Not','if_':'If','text':'Text'}
        if name in functions:return functions[name]+'('+', '.join(render(v) for v in node.args)+')'
    raise NativeActionError('unsupported authored public formula AST; no opaque SDK inference')


def emit_public_native_action_fragments(manifest,receipt,action_bindings,*,current_contents,sdk_actions,assigned_components,staging_review=None):
    """Source-bound pure action edits after actual SDK component ID readback.

    No public Prepare representation is invented: its ActionVariable is retained
    in the exact SDK factory and protected by the existing restoration proof gate.
    """
    try:
        from .action_inventory import validate_action_inventory,digest as action_digest
    except ImportError:
        from action_inventory import validate_action_inventory,digest as action_digest
    routes=_authored_routes(manifest,receipt,action_bindings,current_contents)
    validate_action_inventory(sdk_actions,current_contents,require_recovery=True)
    doc,layout=_document(current_contents,manifest);elements={e['id']:e for e in doc['elements']}
    if len(elements)!=len(doc['elements']):raise NativeActionError('duplicate current element identity refused')
    for feature,record in {**action_bindings['tables'],**action_bindings.get('readTargets',{})}.items():
        target=record['target'];actual=elements.get(target['elementId'],{});owners=_layout_element_owners(layout,target['elementId'])
        spec=manifest['planProjection']['sharedInputArchitecture']['inputs'].get(feature)
        name=actual.get('name')
        if (not isinstance(name,str) or not name or (spec is not None and name!=spec['name'])
                or sum(str(e.get('name','')).casefold()==name.casefold() for e in elements.values())!=1):
            raise NativeActionError('public formula source name must equal the approved unique actual name')
        kind='input-table' if feature in action_bindings['tables'] else 'table'
        if (actual.get('kind')!=kind or len(owners)!=1 or owners[0].get('id')!=target['pageId']
                or any(sum(c.get('id')==cid and c.get('name')==name for c in actual.get('columns',[]))!=1 for name,cid in target['columnIds'].items())):
            raise NativeActionError('assigned public source kind/page/column schema changed')
    if (assigned_components.get('target')!=manifest['target'] or assigned_components.get('bindingHash')!=action_bindings['bindingHash']
            or assigned_components.get('contentsHash')!=_digest(doc)):raise NativeActionError('assigned public components target/binding/content stale')
    expected_actions={r['workflow']+':'+r['role'] for r in routes['publicActionRequirements']}
    if set(assigned_components.get('controls',{}))!=set(routes['componentControls']) or set(assigned_components.get('actions',{}))!=expected_actions or not set(assigned_components.get('buttons',{}))<=set(routes['componentButtons']):raise NativeActionError('assigned components must cover exact declared source roles')
    controls={};buttons={}
    for alias,expected in routes['componentControls'].items():
        observed=assigned_components.get('controls',{}).get(alias,{})
        element=elements.get(observed.get('elementId'),{})
        owners=_layout_element_owners(layout,element.get('id'))
        page_variables={'p'+str(i):action_bindings['pages'][key] for i,key in enumerate(sorted(action_bindings['pages']))}
        expected_page=action_bindings['tables']['workflowOperations']['target']['pageId'] if expected['hostVariable']=='h_workflowOperations' else page_variables.get(expected['hostVariable'])
        if (element.get('kind')!='control' or element.get('controlId')!=expected['variableId'] or element.get('controlType')!=expected['type']
                or observed.get('elementHash')!=_digest(element) or observed.get('pageId')!=expected_page
                or len(owners)!=1 or owners[0].get('id')!=expected_page):raise NativeActionError('assigned source control ID/type/variable/page/hash mismatch')
        controls[alias]={**expected,'elementId':element['id']}
    for key,expected in routes['componentButtons'].items():
        observed=assigned_components.get('buttons',{}).get(key,{})
        if not observed:continue  # Only deferred button hosts are required.
        element=elements.get(observed.get('elementId'),{});owners=_layout_element_owners(layout,element.get('id'))
        workflow=key.split(':')[0];page=action_bindings['pages'][_architecture(manifest)['workflows'][workflow]['decision']['page']]
        if (element.get('kind')!='button' or element.get('text')!=expected['text'] or observed.get('elementHash')!=_digest(element)
                or observed.get('pageId')!=page or len(owners)!=1 or owners[0].get('id')!=page):raise NativeActionError('assigned source button/page/hash mismatch')
        buttons[key]=element['id']
    columns={};tables={}
    for feature,record in {**action_bindings['tables'],**action_bindings.get('readTargets',{})}.items():
        target=record['target'];spec=manifest['planProjection']['sharedInputArchitecture']['inputs'].get(feature)
        name=spec['name'] if spec else elements[target['elementId']]['name'];tables['t_'+feature]=target['elementId']
        for field,cid in target['columnIds'].items():columns[_c(feature,field)]={'tableName':name,'name':field,'id':cid,'elementId':target['elementId']}
        if feature in action_bindings['tables']:
            system=record['systemColumn']
            columns['rid_'+feature]={'tableName':name,'name':system['name'],'id':system['id'],'elementId':target['elementId']}
    if any(any(char in record[field] for char in '[]') for record in columns.values() for field in ('tableName','name')) or any(any(char in record['variableId'] for char in '[]') for record in controls.values()):raise NativeActionError('unescaped public formula identifier refused')
    def value(node,*,selection=False):
        if isinstance(node,ast.Name) and node.id in controls:return {'type':'control','control':controls[node.id]['variableId']}
        if isinstance(node,ast.Name) and node.id in columns:return {'type':'column','columnId':columns[node.id]['id']}
        if isinstance(node,ast.Constant) and node.value is not None:
            typ='boolean' if type(node.value) is bool else 'text' if isinstance(node.value,str) else 'number'
            return {'type':'constant','value':{'type':typ,'value':node.value}}
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='count_distinct':
            if not selection or len(node.args)!=1 or not isinstance(node.args[0],ast.Name) or node.args[0].id not in columns:raise NativeActionError('Selection aggregate only allowed on assigned selection event')
            return {'type':'formula','formula':'CountDistinct([Selection/'+columns[node.args[0].id]['name']+'])'}
        return {'type':'formula','formula':_public_formula(node,columns,controls)}
    edits=[];authorities=[]
    for requirement in routes['publicActionRequirements']:
        workflow=requirement['workflow'];role=requirement['role'];call=ast.parse(requirement['call'],mode='eval').body
        selector_predicates=[];branches={k:ast.parse(v,mode='eval').body for k,v in requirement['branches'].items()}
        def effects(node):
            if isinstance(node,ast.Name) and node.id in branches:return effects(branches[node.id])
            if isinstance(node,ast.List):return [effect(e) for e in node.elts]
            raise NativeActionError('unsupported authored public effect list')
        def effect(node):
            if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name):raise NativeActionError('unsupported authored public effect')
            if node.func.id=='set_control_value':
                alias=node.args[0].id
                if alias not in controls:raise NativeActionError('unassigned public action control')
                return {'effect':'set-control-value','control':controls[alias]['variableId'],'value':value(node.args[1],selection=role in {'selection','recovery'})}
            if node.func.id=='update_rows':
                table=node.args[0].id
                if table not in tables:raise NativeActionError('foreign public row target')
                feature=table[2:];rid='rid_'+feature
                ids=[n.args[1] for n in ast.walk(node.args[1]) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='eq' and isinstance(n.args[0],ast.Name) and n.args[0].id==rid]
                if len(ids)!=1:raise NativeActionError('one assigned physical row predicate required')
                if workflow=='approval' and role=='confirm':
                    # Do not replace this write-boundary freeze with a physical
                    # ID alone or reintroduce CountIf(Lookup(...)) on the event.
                    return {'effect':'update-rows','tableElementId':tables[table],
                        'whichRows':{'type':'formula','formula':_public_formula(node.args[1],columns,controls,local_element_id=tables[table])},
                        'values':{columns[k.id]['id']:value(v) for k,v in zip(node.args[2].keys,node.args[2].values)}}
                selector_predicates.append(_public_formula(node.args[1],columns,controls))
                return {'effect':'update-rows','tableElementId':tables[table],'whichRows':{'type':'single-row','primaryKeys':{columns[rid]['id']:value(ids[0])}},
                    'values':{columns[k.id]['id']:value(v) for k,v in zip(node.args[2].keys,node.args[2].values)}}
            if node.func.id=='if_else':
                branches_out=[{'condition':{'type':'formula','formula':_public_formula(pair.elts[0],columns,controls)},'effects':effects(pair.elts[1])} for pair in node.args[0].elts]
                if not branches_out:raise NativeActionError('nonempty authored condition branches required')
                return {'effect':'if-else','if':branches_out[0],'elseif':branches_out[1:],'else':{'effects':effects(node.args[1])}}
            raise NativeActionError('unsupported public effect; native Prepare/returns are never serialized')
        compiled=effects(call.args[1]);condition=_public_formula(ast.parse(requirement['condition'],mode='eval').body,columns,controls) if requirement['condition'] else None
        for predicate in selector_predicates:condition='('+condition+') and (CountIf('+predicate+') = 1)' if condition else 'CountIf('+predicate+') = 1'
        host=tables.get(requirement['hostVariable']) if role in {'selection','recovery'} else buttons.get(workflow+':'+requirement['hostVariable'])
        if not host:raise NativeActionError('deferred action host has no assigned component')
        key=workflow+':'+role;assignment=assigned_components.get('actions',{}).get(key,{})
        sequence_id=assignment.get('sequenceId')
        if not isinstance(sequence_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',sequence_id):raise NativeActionError('explicit stable public action identity required')
        prior=[a for a in elements[host].get('actions',[]) if a['id']==sequence_id]
        foreign_rest=any(a['id']==sequence_id for eid,e in elements.items() if eid!=host for a in e.get('actions',[]))
        foreign_sdk=any(s['id']==sequence_id for eid,e in sdk_actions['elements'].items() if eid!=host for s in e['sequences'])
        if foreign_rest or foreign_sdk:raise NativeActionError('public action identity collides with unrelated existing sequence')
        before=assignment.get('beforeActionHash')
        if (len(prior)>1 or (before is None and prior) or (before is not None and (len(prior)!=1 or _digest(prior[0])!=before))):raise NativeActionError('existing public action pointer/hash stale')
        event='on-select' if role in {'selection','recovery'} else 'on-click'
        if prior:
            oldevent=prior[0]['trigger'];oldevent=oldevent if isinstance(oldevent,str) else oldevent.get('on')
            if oldevent!=event:raise NativeActionError('undeclared existing event replacement')
        action={'id':sequence_id,'name':ast.literal_eval(call.args[0]),'trigger':{'on':event,'condition':{'type':'formula','formula':condition}} if condition else event,
                'effects':compiled,'state':'disabled'}
        edits.append({'role':role,'workflow':workflow,'hostElementId':host,'sequenceId':sequence_id,'beforeActionHash':before,'afterActionHash':_digest(action),'afterAction':action})
        for index,e in enumerate(compiled):
            if e['effect']=='set-control-value' and e['value'].get('formula','').startswith('CountDistinct([Selection/'):
                ridnode=next(v.args[1].args[0] for v in call.args[1].elts if isinstance(v.args[1],ast.Call) and isinstance(v.args[1].func,ast.Name) and v.args[1].func.id=='count_distinct')
                column=columns[ridnode.id]
                if column['elementId']!=host:raise NativeActionError('Selection source must belong to its on-select host')
                authorities.append({'hostElementId':host,'hostWithoutActionsHash':_digest({k:v for k,v in elements[host].items() if k!='actions'}),'sequenceId':sequence_id,
                    'effectIndex':index,'controlId':e['control'],'controlElementId':next(c['elementId'] for c in controls.values() if c['variableId']==e['control']),'formula':e['value']['formula'],'sourceColumn':copy.deepcopy(column),'trigger':'on-select'})
    result={'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],'bindingHash':action_bindings['bindingHash'],'target':manifest['target'],
        'contentsHash':_digest(doc),'assignedComponentsHash':_digest(assigned_components),'sdkInventoryHash':action_digest(sdk_actions),
        'actionEdits':edits,'selectionAuthorities':authorities,'authoringAstHash':routes['authoringAstHash'],
        'allowedEditPaths':[{'hostElementId':e['hostElementId'],'sequenceId':e['sequenceId'],'beforeActionHash':e['beforeActionHash'],'afterActionHash':e['afterActionHash'],'role':e['role']} for e in edits],
        'status':'DISABLED_CANDIDATE_REQUIRES_REVIEW','productionStatus':'BLOCKED','limitations':routes['limitations']}
    result['fragmentHash']=_digest(result)
    if staging_review is not None:
        fields={'sourceHash':result['sourceHash'],'planHash':result['planHash'],'bindingHash':result['bindingHash'],'fragmentHash':result['fragmentHash'],
            'contentsHash':result['contentsHash'],'assignedComponentsHash':result['assignedComponentsHash'],'sdkInventoryHash':result['sdkInventoryHash'],
            'documentId':manifest['target']['documentId'],'version':manifest['target']['version']}
        if staging_review.get('status')!='APPROVED_STAGING' or (not str(staging_review.get('owner') or '').strip() or re.match(r'(?i)^(pending|todo|tbd|unknown)\b',str(staging_review.get('owner')))) or any(staging_review.get(k)!=v for k,v in fields.items()):raise NativeActionError('public native staging review stale/incomplete')
        activation=staging_review.get('activation','business-enable' if staging_review.get('enable') is True else 'disabled')
        if activation not in {'disabled','selection-probe','business-enable'}:raise NativeActionError('unknown reviewed native activation')
        control_roles={'selection','recovery','clear-context'}
        if activation=='selection-probe':
            if (staging_review.get('probeOnly') is not True or staging_review.get('enable',False) is not False
                    or staging_review.get('businessActionsDisabledInventoryHash')!=action_digest(sdk_actions)):
                raise NativeActionError('exact control-only probe review and disabled business inventory required')
            declared={(edit['hostElementId'],edit['sequenceId']):edit for edit in edits}
            for eid,element in sdk_actions['elements'].items():
                for seq in element['sequences']:
                    edit=declared.get((eid,seq['id']))
                    if edit is not None and edit['role'] not in control_roles:continue  # This exact edit disables it.
                    if not seq['disabled'] and any(block['kind'] not in {'TextSetControlValueEffect','FloatSetControlValueEffect','BooleanSetControlValueEffect','DateSetControlValueEffect','NavigateAction'} for block in seq['blocks']):
                        raise NativeActionError('selection probe requires every other business action disabled')
            for edit in edits:
                if edit['role'] in control_roles:
                    if any(effect['effect']!='set-control-value' for effect in edit['afterAction']['effects']):raise NativeActionError('selection probe cannot contain row writes')
                    edit['afterAction']['state']='enabled'
                    edit['afterActionHash']=_digest(edit['afterAction'])
            result['status']='CONTROL_ONLY_PROBE_REQUIRES_PUBLISHED_SELECTION_EVIDENCE'
        elif activation=='business-enable':
            if staging_review.get('enable') is not True or staging_review.get('disabledConstructionProofHash')!=action_digest(sdk_actions):raise NativeActionError('actual exact disabled construction SDK proof required before enabling')
            for authority in authorities:
                qualified=[q for q in sdk_actions['elements'][authority['hostElementId']].get('publicSelectionAuthority',[])
                    if q.get('authority')==authority and q.get('review',{}).get('documentId')==manifest['target']['documentId']
                    and q.get('review',{}).get('version')==manifest['target']['version'] and q.get('review',{}).get('contentsHash')==_digest(doc)]
                if len(qualified)!=1:raise NativeActionError('fresh qualified published Selection authority required before enabling')
            for edit in edits:
                prior=[a for a in elements[edit['hostElementId']].get('actions',[]) if a['id']==edit['sequenceId']]
                observed=[s for s in sdk_actions['elements'][edit['hostElementId']]['sequences'] if s['id']==edit['sequenceId']]
                expected_state='enabled' if edit['role'] in control_roles else 'disabled'
                if (len(prior)!=1 or prior[0].get('state')!=expected_state or len(observed)!=1 or observed[0]['disabled'] is not (expected_state=='disabled')
                        or {k:v for k,v in prior[0].items() if k!='state'}!={k:v for k,v in edit['afterAction'].items() if k!='state'}):raise NativeActionError('only exact previously constructed probe and disabled business actions may be enabled')
                edit['afterAction']['state']='enabled';edit['afterActionHash']=_digest(edit['afterAction'])
            result['status']='ENABLED_REVIEWED_STAGING_ONLY_REQUIRES_RUNTIME'
        elif staging_review.get('enable',False) is not False:raise NativeActionError('inconsistent reviewed native activation')
        result['activation']=activation
        result['allowedEditPaths']=[{k:edit[k] for k in ('hostElementId','sequenceId','beforeActionHash','afterActionHash','role')} for edit in edits]
        result['constructionReview']=copy.deepcopy(staging_review)
        result.pop('fragmentHash');result['fragmentHash']=_digest(result)
    return result
