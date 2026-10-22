"""Reviewed Python/procedure construction adapters; no live execution or credentials."""
try:
    from .custom_port_math import *
except ImportError:
    from custom_port_math import *

import copy
import datetime as dt
import re
from pathlib import Path

try:
    from .macro_behavior import analyze_macro_source, validate_macro_source
    from .input_sync import _digest, _approved_feature
    from .migration_manifest import build_manifest, validate_manifest
except ImportError:
    from macro_behavior import analyze_macro_source, validate_macro_source
    from input_sync import _digest, _approved_feature
    from migration_manifest import build_manifest, validate_manifest

# This host inventory is used only for explicit custom-port review. It does not
# alter the native analyzer or authorize its unresolved imperative statements.
VBA_HOST_INTRINSICS = {'IsError','VarType','Round','Fix','InStr','IsDate','Replace','If','ElseIf'}


def source_helper_inventory(analysis):
    validate_macro_source(analysis)
    source = Path(analysis['sourcePath']).read_text()
    labels = set(re.findall(r'^\s*([A-Za-z_]\w*):\s*$', source, re.M))
    unknown = {item['name'] for proc in analysis['procedures']
               for item in proc['unresolvedDependencies'] if item['kind']=='missing-helper'}
    return {'definedHelpers':sorted(p['name'] for p in analysis['procedures']),
            'missingHelpers':sorted(unknown - VBA_HOST_INTRINSICS - labels),
            'hostIntrinsics':sorted(unknown & VBA_HOST_INTRINSICS), 'labels':sorted(labels),
            'automaticNativeStatus':'UNRESOLVED', 'analysisHash':_digest(analysis)}


OUTPUT_SCHEMAS = {
    'allocation': [('OperationId','STRING'),('Status','STRING'),('ErrorCode','STRING'),('Department','STRING'),
                   ('SourceIndex','INTEGER'),('Headcount','DOUBLE'),('Overhead','DOUBLE'),('Allocation','DOUBLE')],
    'goalSeek': [('OperationId','STRING'),('Status','STRING'),('ErrorCode','STRING'),('ModelBinding','STRING'),
        ('InputFingerprint','STRING'),('Target','DOUBLE'),('LowerBound','DOUBLE'),('UpperBound','DOUBLE'),
        ('LowerNetIncome','DOUBLE'),('UpperNetIncome','DOUBLE'),('SolvedGrowth','DOUBLE'),('SolvedNetIncome','DOUBLE'),
        ('Residual','DOUBLE'),('Iterations','INTEGER'),('ToleranceCents','DOUBLE'),('GrowthPrecisionDigits','INTEGER'),
        ('Converged','BOOLEAN'),('Endpoint','BOOLEAN'),('SubscriptionRowId','STRING'),('PreviousGrowth','DOUBLE')],
    'applyGuard': [('OperationId','STRING'),('ResultOperationId','STRING'),('ModelBinding','STRING'),
        ('ResultFingerprint','STRING'),('CurrentFingerprint','STRING'),('SubscriptionRowId','STRING'),
        ('PreviousGrowth','DOUBLE'),('CurrentGrowth','DOUBLE'),('SolvedGrowth','DOUBLE'),
        ('RecomputedNetIncome','DOUBLE'),('Residual','DOUBLE'),('ReadyToApply','BOOLEAN'),('ErrorCode','STRING')]
}
OUTPUT_NAMES = {'allocation':'AllocationResult','goalSeek':'GoalSeekResult','applyGuard':'GoalSeekApplyGuard'}
SOURCE_TITLES = {'actuals':'Actuals','inputs':'Forecast Inputs View','definitions':'Forecast Line Definitions',
                 'invocation':'Goal Seek Invocation','result':'Goal Seek Result',
                 'headcount':'Task 5 Headcount Inputs','overhead':'Task 5 Allocation Assumptions'}


def emit_python_programs(model_binding, *, column_maps=None):
    """Return fully standalone warehouse Python. Embed actual Snowpark column maps.

    get_element resolves unique source element titles or another Python output's
    reference name on the selected connection. A reviewed read-only inputs
    projection must include the physical Input Row ID.
    Output schemas are explicit because failure rows contain null-only columns.
    """
    if not isinstance(model_binding,str) or not model_binding:
        raise PortError('MODEL_BINDING_REQUIRED')
    kernel=Path(__file__).with_name('custom_port_math.py').read_text()
    maps=json.loads(json.dumps(column_maps or {},sort_keys=True))
    header=kernel+'\nCOLUMN_MAPS = '+repr(maps)+'\n'
    header+='''
def read_rows(frame, title, required):
    observed = list(frame.columns)
    mapping = COLUMN_MAPS.get(title, {})
    names = {}
    row_keys = {}
    for name in required:
        bound = mapping.get(name, name)
        if isinstance(bound, str):
            names[name] = bound
            row_keys[name] = bound
        elif isinstance(bound, dict) and set(bound) == {'identifier', 'rowKey'} and all(isinstance(v, str) and v for v in bound.values()):
            names[name] = bound['identifier']
            row_keys[name] = bound['rowKey']
        else:
            raise PortError('INVALID_RUNTIME_COLUMN_BINDING')
    if len(set(names.values())) != len(names) or any(observed.count(n) != 1 for n in names.values()):
        raise PortError('RUNTIME_COLUMN_MISMATCH')
    if len(set(row_keys.values())) != len(row_keys):
        raise PortError('RUNTIME_ROW_KEY_MISMATCH')
    rows = []
    for row in frame.collect():
        values = row.as_dict()
        if any(key not in values for key in row_keys.values()):
            raise PortError('RUNTIME_ROW_KEY_MISMATCH')
        rows.append({name: values[key] for name, key in row_keys.items()})
    return rows


def one_invocation(invocation_frame):
    rows = read_rows(invocation_frame, 'Goal Seek Invocation', ('RequestKey','OperationId','State','Target','LowerBound',
                    'UpperBound','ToleranceCents','MaxIterations','ModelBinding'))
    if len(rows) != 1 or rows[0]['RequestKey'] != 'goal-seek':
        raise PortError('INVALID_INVOCATION_ROWS')
    return rows[0]


def read_model(actuals_frame, inputs_frame, definitions_frame):
    actuals = read_rows(actuals_frame, 'Actuals', ('Line Item','Month','Section','Amount'))
    inputs = read_rows(inputs_frame, 'Forecast Inputs View', ('Line Item','Input Row ID','Method','Monthly Growth',*MONTHS))
    definitions = read_rows(definitions_frame, 'Forecast Line Definitions', ('Line Item','Section'))
    return actuals, inputs, definitions
'''
    bodies={
        'allocation': '''    invocation_frame = sigma.get_element('Goal Seek Invocation')
    request = one_invocation(invocation_frame)
    counts_frame = sigma.get_element('Task 5 Headcount Inputs')
    counts = read_rows(counts_frame, 'Task 5 Headcount Inputs', ('Department','Headcount'))
    by_department = keyed(counts, 'Department')
    if set(by_department) != set(DEPARTMENTS):
        raise PortError('INVALID_DEPARTMENT_KEYS')
    assumptions_frame = sigma.get_element('Task 5 Allocation Assumptions')
    assumptions = read_rows(assumptions_frame, 'Task 5 Allocation Assumptions', ('Key','Value'))
    if len(assumptions) != 1 or assumptions[0]['Key'] != 'Overhead':
        raise PortError('INVALID_OVERHEAD_ROWS')
    rows = allocate_overhead([by_department[d]['Headcount'] for d in DEPARTMENTS], assumptions[0]['Value'], request['OperationId'])
''',
        'goalSeek': '''    invocation_frame = sigma.get_element('Goal Seek Invocation')
    request = one_invocation(invocation_frame)
    actuals_frame = sigma.get_element('Actuals')
    inputs_frame = sigma.get_element('Forecast Inputs View')
    definitions_frame = sigma.get_element('Forecast Line Definitions')
    actuals, inputs, definitions = read_model(actuals_frame, inputs_frame, definitions_frame)
    rows = [solve_forecast(actuals, inputs, definitions, request, expected_binding=EXPECTED_BINDING)]
''',
        'applyGuard': f'''    invocation_frame = sigma.get_element('Goal Seek Invocation')
    request = one_invocation(invocation_frame)
    actuals_frame = sigma.get_element('Actuals')
    inputs_frame = sigma.get_element('Forecast Inputs View')
    definitions_frame = sigma.get_element('Forecast Line Definitions')
    actuals, inputs, definitions = read_model(actuals_frame, inputs_frame, definitions_frame)
    results_frame = sigma.get_element({OUTPUT_NAMES['goalSeek']!r})
    results = read_rows(results_frame, {OUTPUT_NAMES['goalSeek']!r}, RESULT_COLUMNS)
    if len(results) != 1:
        raise PortError('INVALID_RESULT_ROWS')
    rows = [guard_goal_seek(actuals, inputs, definitions, request, results[0], expected_binding=EXPECTED_BINDING)]
'''}
    programs={}
    for name,body in bodies.items():
        fields=OUTPUT_SCHEMAS[name];columns=[n for n,t in fields]
        schema=', '.join('"'+n+'" '+t for n,t in fields)
        code=header+'\nEXPECTED_BINDING = '+repr(model_binding)+'\nRESULT_COLUMNS = '+repr([n for n,t in OUTPUT_SCHEMAS['goalSeek']])+'\nrequest = {}\ntry:\n'+body
        code+='''except Exception as error:
    rows = [dict(OperationId=request.get('OperationId'), Status='FAILURE', Converged=False,
                 ReadyToApply=False, ModelBinding=request.get('ModelBinding'),
                 ErrorCode=str(error) if isinstance(error, PortError) else 'RUNTIME_INPUT_ERROR')]
'''
        code+='COLUMNS = '+repr(columns)+'\nOUTPUT_TYPES = '+repr(dict(fields))+'\n'
        code+='''# Null-only failure columns need explicit types; never infer a schema.
def output_value(value, kind):
    if value is None:
        return None
    if kind == 'DOUBLE':
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise PortError('INVALID_OUTPUT_TYPE')
        number = float(value)
        return number if math.isfinite(number) else None
    expected = {'INTEGER': int, 'BOOLEAN': bool, 'STRING': str}[kind]
    if type(value) is not expected:
        raise PortError('INVALID_OUTPUT_TYPE')
    return value

try:
    values = [[output_value(row.get(k), OUTPUT_TYPES[k]) for k in COLUMNS] for row in rows]
except Exception:
    # Keep failure emission typed even if an invalid request value was copied
    # into a diagnostic result field (for example a Boolean target).
    fallback = dict(OperationId=request.get('OperationId') if isinstance(request.get('OperationId'), str) else None,
                    Status='FAILURE', Converged=False, ReadyToApply=False, ErrorCode='RUNTIME_OUTPUT_TYPE_ERROR')
    values = [[output_value(fallback.get(k), OUTPUT_TYPES[k]) for k in COLUMNS]]
'''
        code+='output_frame = session.create_dataframe(values, schema='+repr(schema)+')\n'
        code+='sigma.output('+repr(OUTPUT_NAMES[name])+', output_frame)\n'
        programs[name]={'code':code,'columns':columns,'schema':fields,'output':OUTPUT_NAMES[name],
            'codeHash':hashlib.sha256(code.encode()).hexdigest(),'runtime':'Snowflake warehouse Python + provided sigma/session',
            'packages':['standard library: math, json, hashlib, decimal'], 'productionStatus':'BLOCKED'}
    return programs


PROCEDURE_PATH=['SIGMA_WRITE_DB','SIGMA_TASK5_SP_TEST','TASK5_TYPED_ECHO']
PROCEDURE_TYPES=['VARCHAR','NUMBER(18,2)','NUMBER(38,0)','BOOLEAN','TIMESTAMP_NTZ(3)']
ACTION_TYPES=['text','number','integer','boolean','datetime']


def controlled_procedure_contract(connection_id):
    if not isinstance(connection_id,str) or not connection_id:
        raise PortError('CONNECTION_REQUIRED')
    return {'connectionId':connection_id,'path':list(PROCEDURE_PATH),'declaredTypes':list(PROCEDURE_TYPES),
            'actionTypes':list(ACTION_TYPES),'returnType':'VARCHAR','signature':None,'executeAs':'CALLER',
            'sideEffects':[], 'caller':{'user':'SIGMA_SERVICE_USER','role':'SIGMA_ROLE','warehouse':'SIGMA_WH'},
            'defaults':False,'overloads':1,'timeoutPolicy':'stop-dependent-effects-no-success-no-automatic-retry',
            'retryPolicy':'same-operation-and-ordered-typed-fingerprint-only','productionStatus':'BLOCKED'}


def _decimal_wire_amount(number):
    value=Decimal(json.dumps(number,allow_nan=False))
    return Decimal(0) if value==0 else value


def _typed_arguments(values):
    if not isinstance(values,list) or len(values)!=5 or any(v is None for v in values):
        raise PortError('REQUIRED_ORDERED_ARGUMENTS')
    op,amount,count,enabled,timestamp=values
    operation(op)
    if any(c.isspace() for c in op):
        raise PortError('INVALID_OPERATION_ID')
    number=finite(amount);integer=finite(count)
    # Actions carry JSON numbers. Bind the exact decimal spelling emitted for
    # that Double, not its binary .2f rendering. Decimal inputs that lose cents
    # when converted to this wire value are outside the supported caller subset.
    decimal_amount=Decimal(str(amount))
    wire_amount=_decimal_wire_amount(number)
    if (abs(number)>=1e15 or decimal_amount.as_tuple().exponent < -2 or decimal_amount!=wire_amount
            or integer<0 or not integer.is_integer() or integer>=1e15 or type(enabled) is not bool):
        raise PortError('INVALID_TYPED_ARGUMENT')
    if not isinstance(timestamp,str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}',timestamp):
        raise PortError('INVALID_TIMESTAMP')
    try:dt.datetime.fromisoformat(timestamp)
    except ValueError:raise PortError('INVALID_TIMESTAMP')
    return op,number,int(integer),enabled,timestamp


def build_procedure_action(contract, arguments, *, prior_invocation=None):
    signature=contract.get('signature')
    if (not isinstance(signature,str) or not signature.strip() or any(t in signature.upper() for t in ('PENDING','ASSIGN','VARIANT','DEFAULT'))
            or contract.get('path')!=PROCEDURE_PATH or contract.get('declaredTypes')!=PROCEDURE_TYPES
            or contract.get('actionTypes')!=ACTION_TYPES or contract.get('returnType')!='VARCHAR'
            or contract.get('executeAs')!='CALLER' or contract.get('sideEffects')!=[]
            or contract.get('defaults') is not False or contract.get('overloads')!=1
            or contract.get('caller')!={'user':'SIGMA_SERVICE_USER','role':'SIGMA_ROLE','warehouse':'SIGMA_WH'}
            or any(not contract.get(k) for k in ('connectionId','catalogObjectId','lookupEvidenceId','callerEvidenceId','scalarMappingEvidenceId','datetimeEvidenceId'))):
        raise PortError('EXACT_PROCEDURE_LOOKUP_AND_CALLER_EVIDENCE_REQUIRED')
    lookup=contract.get('lookup',{})
    expected_lookup={'connectionId':contract.get('connectionId'),'path':PROCEDURE_PATH,'signature':signature,
                     'returnType':'VARCHAR','parameters':PROCEDURE_TYPES,'overloads':1,'defaults':False}
    if lookup!=expected_lookup:
        raise PortError('EXACT_ORDERED_LOOKUP_SIGNATURE_MISMATCH')
    op,amount,count,enabled,timestamp=_typed_arguments(arguments)
    invocation={'operationId':op,'argumentFingerprint':fingerprint(arguments),'contractHash':_digest(contract),
        'expectedScalar':f"operation_id={op}|amount={_decimal_wire_amount(amount):.2f}|count={count}|enabled={str(enabled).lower()}|occurred_at={timestamp}"}
    if prior_invocation and prior_invocation.get('operationId')==op and prior_invocation!=invocation:
        raise PortError('OPERATION_RETRY_INPUT_MISMATCH')
    typed=[op,amount,count,enabled,timestamp+'Z']
    # Sigma timestamps use constant tag 'date'; outer type stays 'datetime'
    # and the full timestamp is preserved.
    kinds=['text','number','number','boolean','date']
    return {'id':'task5-call-typed-echo','trigger':'on-click','effects':[{'effect':'call-stored-procedure',
        'storedProcedure':{k:copy.deepcopy(contract[k]) for k in ('connectionId','path','signature')},
        'arguments':[{'parameterIndex':i,'type':typ,'value':{'type':'constant','value':{'type':kind,'value':value}}}
            for i,(typ,kind,value) in enumerate(zip(ACTION_TYPES,kinds,typed))], 'name':'task5TypedEchoResult'}],
        'successToast':{'showMessage':'hidden'},'invocation':invocation,
        'contract':copy.deepcopy(contract),'orderedArguments':[op,amount,count,enabled,timestamp]}


def audit_procedure_result(invocation,capture):
    if capture.get('operationId')!=invocation['operationId'] or not capture.get('evidenceId'):
        raise PortError('STALE_PROCEDURE_RESULT')
    status=capture.get('status')
    if status=='SUCCESS':
        if capture.get('scalar')!=invocation['expectedScalar']:
            raise PortError('SCALAR_MISMATCH')
    elif status in ('FAILURE','TIMEOUT','CANCELLED'):
        if (capture.get('scalar') is not None or capture.get('dependentEffectsExecuted') is not False
                or capture.get('successToastShown') is not False):
            raise PortError('FAILURE_SEQUENCE_VIOLATION')
    else:raise PortError('UNKNOWN_PROCEDURE_OUTCOME')
    return {'status':'VERIFIED_COMPONENT_SUCCESS' if status=='SUCCESS' else 'VERIFIED_COMPONENT_FAILURE',
            'operationId':invocation['operationId'],'evidenceId':capture['evidenceId'],'productionStatus':'BLOCKED'}

FEATURE_PROCEDURES={'allocation':'AllocateOverheadByHeadcount','goalSeek':'SolveForTarget','procedure':'Task5TypedEcho'}
RUNTIME_CASES=('allocation-success','allocation-null','allocation-text','allocation-nonfinite','allocation-zero',
    'goal-success','goal-lower-endpoint','goal-upper-endpoint','goal-invalid-bracket','goal-invalid-model',
    'goal-iteration-limit','goal-single-assumption-write','goal-stale-output','goal-failed-python','goal-retry',
    'procedure-success','procedure-null','procedure-negative','procedure-invalid-type','procedure-retry',
    'procedure-failure-halt','procedure-timeout-halt','published-owner','published-editor','published-explorer','published-viewer')


def _file_record(path):
    path=Path(path).resolve()
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def build_custom_port_plan(base_manifest,base_receipt,*,module_path,fixture_path,expected_path,reviews,scope):
    validate_manifest(base_manifest)
    _approved_feature(base_manifest,base_receipt,'forecastBusinessInput')
    if (scope.get('status')!='APPROVED_STAGING' or not str(scope.get('owner') or '').strip()
            or not scope.get('documentId') or scope.get('version') is None
            or scope.get('documentId')!=(base_manifest.get('target') or {}).get('documentId')
            or scope.get('version')!=(base_manifest.get('target') or {}).get('version')
            or not scope.get('folderId') or not scope.get('connectionId')):
        raise PortError('EXPLICIT_STAGING_SCOPE_REQUIRED')
    prior_scope=base_manifest['planProjection']['sharedInputArchitecture']['targetScope']
    if any(scope[k]!=prior_scope.get(k) for k in ('connectionId','folderId')):
        raise PortError('BASE_INPUT_SCOPE_MISMATCH')
    if Path(fixture_path).suffix.lower()!='.xlsx' or Path(module_path).suffix.lower()!='.bas':
        raise PortError('RAW_MODULE_AND_XLSX_COMPANION_REQUIRED')
    analysis=analyze_macro_source(module_path)
    inventory=source_helper_inventory(analysis)
    if any(p['externalSideEffects'] for p in analysis['procedures']):
        raise PortError('EXTERNAL_CUSTOM_SOURCE_FORBIDDEN')
    if inventory['missingHelpers']:
        raise PortError('UNRESOLVED_CUSTOM_HELPER')
    files={name:_file_record(path) for name,path in [('module',module_path),('fixture',fixture_path),
        ('expected',expected_path),('kernel',Path(__file__).with_name('custom_port_math.py')),
        ('modelData',Path(module_path).parent/'task5-controlled-model.json'),
        ('procedure',Path(module_path).parent/'task5-controlled-procedure-v3.sql')]}
    architecture={'version':1,'sourceModules':[analysis],'helperInventory':inventory,'files':files,
        'reviews':copy.deepcopy(reviews),'scope':copy.deepcopy(scope),'basePlanHash':base_manifest['planHash'],
        'baseReceiptHash':_digest(base_receipt),'equationVersion':'forecast-actuals-plus-manual-flat-growth-v1',
        'sourceOrigin':'new-controlled-fixture','legacyUnresolved':['RebuildPnL:PostToGrid','RefreshAll','EmailReport_Click'],
        'runtimeRequired':list(RUNTIME_CASES),'productionStatus':'BLOCKED'}
    projection=copy.deepcopy(base_manifest['planProjection'])
    projection['customPortArchitecture']=architecture
    shared=projection['sharedInputArchitecture']
    specs=build_port_input_specs(shared['inputs']['forecastBusinessInput'])
    if set(shared['inputs']) & set(specs):raise PortError('EXISTING_PORT_INPUT_SPEC_REFUSED')
    shared['inputs'].update(specs)
    shared['mappedFeatures']=list(shared.get('mappedFeatures',[]))+list(specs)
    shared.setdefault('featureToInput',{}).update({key:key for key in specs})
    projection['formulaCells']=copy.deepcopy(base_manifest['formulaCells'])
    manifest=build_manifest(base_manifest['source']['path'],projection)
    manifest['target']=copy.deepcopy(base_manifest['target'])
    validate_custom_port_plan(manifest)
    return manifest


def validate_custom_port_plan(manifest):
    validate_manifest(manifest)
    arch=manifest.get('planProjection',{}).get('customPortArchitecture',{})
    if arch.get('version')!=1 or arch.get('productionStatus')!='BLOCKED':
        raise PortError('CUSTOM_PRODUCTION_GATE_MUST_REMAIN_BLOCKED')
    for record in arch.get('files',{}).values():
        if _file_record(record['path'])!=record:
            raise PortError('CUSTOM_SOURCE_HASH_STALE')
    if set(arch.get('files',{}))!={'module','fixture','expected','kernel','modelData','procedure'}:
        raise PortError('CUSTOM_SOURCE_FILES_REQUIRED')
    analysis=arch['sourceModules'][0]
    validate_macro_source(analysis)
    if source_helper_inventory(analysis)!=arch.get('helperInventory') or arch['helperInventory']['missingHelpers']:
        raise PortError('CUSTOM_HELPER_INVENTORY_STALE')
    if any(p['externalSideEffects'] for p in analysis['procedures']):raise PortError('EXTERNAL_CUSTOM_SOURCE_FORBIDDEN')
    by_name={p['name']:p for p in analysis['procedures']}
    if set(arch.get('reviews',{}))!=set(FEATURE_PROCEDURES):
        raise PortError('EXPLICIT_CUSTOM_REVIEWS_REQUIRED')
    for feature,name in FEATURE_PROCEDURES.items():
        decision=arch['reviews'][feature];proc=by_name.get(name,{})
        if (decision.get('mappingKind')!='reviewed-custom-port' or decision.get('reviewStatus')!='approved'
                or not str(decision.get('reviewer') or '').strip() or not decision.get('decisionId')
                or decision.get('procedureId')!=proc.get('procedureId')
                or decision.get('procedureSha256')!=proc.get('procedureSha256')
                or decision.get('acknowledgeUnsupportedImperative') is not True
                or decision.get('sourceOrigin')!='new-controlled-fixture'):
            raise PortError('EXPLICIT_SOURCE_BOUND_CUSTOM_REVIEW_REQUIRED')
    return True


def validate_custom_port_completion(manifest):
    validate_custom_port_plan(manifest)
    records=manifest.get('customPortRuntimeEvidence',[])
    if not isinstance(records,list):raise PortError('actual runtime acceptance evidence required')
    indexed={r.get('case'):r for r in records}
    if len(indexed)!=len(records) or set(indexed)!=set(RUNTIME_CASES):
        raise PortError('actual runtime acceptance cases missing')
    target=manifest.get('target') or {}
    for case,record in indexed.items():
        if (record.get('status')!='passed' or record.get('origin')!='sigma-runtime'
                or not record.get('runtimeExecutionId') or not record.get('evidenceId')
                or record.get('sourceHash')!=manifest['sourceHash'] or record.get('planHash')!=manifest['planHash']
                or record.get('targetDocumentId')!=target.get('documentId')
                or record.get('targetVersion')!=target.get('version') or not record.get('targetElementId')):
            raise PortError('actual runtime acceptance binding missing or stale: '+case)
    return True


def _port_run_button(key):
    prefix=PORT_PREFIX[key]
    return {'id':prefix+'Button','kind':'button','appearance':'filled','text':{'allocation':'Allocate overhead',
        'goalSeek':'Run prepared solve','applyGuard':'Validate prepared apply'}[key],
        'actions':[{'id':prefix+'Run','trigger':'on-click',
            'effects':[{'effect':'run-python-element','codeElementId':prefix+'Python','name':prefix+'RunResult'}],
            'successToast':{'showMessage':'hidden'}}]}


def _port_templates(model_binding,connection_id,*,column_maps=None,procedure_action=None):
    programs=emit_python_programs(model_binding,column_maps=column_maps)
    ids={'allocation':'task5Allocation','goalSeek':'task5GoalSeek','applyGuard':'task5GoalSeekApplyGuard'}
    titles={'allocation':'Allocation Result','goalSeek':'Goal Seek Result','applyGuard':'Goal Seek Apply Guard'}
    elements=[]
    for key,program in programs.items():
        prefix=ids[key];code_id=prefix+'Python'
        elements.append({'id':code_id,'kind':'code','connectionId':connection_id,'code':program['code']})
        elements.append({'id':prefix+'Result' if key!='applyGuard' else prefix,'kind':'table','name':titles[key],
            'source':{'kind':'code-output','elementId':code_id,'output':program['output']},
            'order':[prefix+'C'+str(i) for i in range(len(program['columns']))],
            'columns':[{'id':prefix+'C'+str(i),'name':name}
                       for i,name in enumerate(program['columns'])]})
        # Running goal/apply guard requires the controller to set invocation state
        # beforehand. These hidden-toast computation actions never write assumptions.
        elements.append(_port_run_button(key))
    if procedure_action:
        expected=build_procedure_action(procedure_action.get('contract',{}),procedure_action.get('orderedArguments'))
        if procedure_action!=expected:raise PortError('PROCEDURE_ACTION_ARTIFACT_MISMATCH')
        if procedure_action['contract']['connectionId']!=connection_id:raise PortError('PROCEDURE_CONNECTION_MISMATCH')
        action={k:copy.deepcopy(procedure_action[k]) for k in ('id','trigger','effects','successToast')}
        elements.append({'id':'task5ProcedureButton','kind':'button','appearance':'filled','text':'Run reviewed scalar procedure','actions':[action]})
    page={'id':'task5Ports','name':'Reviewed Custom Ports'}
    layout='<Page type="grid" id="task5Ports" gridTemplateColumns="repeat(24, 1fr)">'
    cursor=1
    for element in elements:
        height=8 if element['kind']=='button' else 14
        layout+=f'<Element elementId="{element["id"]}" gridColumn="1 / 25" gridRow="{cursor} / {cursor+height}"/>'
        cursor+=height
    layout+='</Page>'
    return {'pages':[page],'elements':elements,'layout':layout,'programs':programs}


def _snapshot(current):
    contents=current.get('contents',current.get('document'))
    if not isinstance(contents,dict) or contents.get('kind')!='workbook':
        raise PortError('CONTENTS_KIND_WORKBOOK_REQUIRED')
    return contents


def _connection_ids(element,elements,stack=()):
    def visit(source):
        result=set()
        if not isinstance(source,dict):return result
        if 'connectionId' in source:result.add(source['connectionId'])
        if source.get('kind') in ('table','code-output') and 'elementId' in source:
            eid=source['elementId']
            if eid in stack or eid not in elements:raise PortError('UNRESOLVED_SOURCE_CONNECTION')
            result.update(_connection_ids(elements[eid],elements,stack+(eid,)))
        for key,value in source.items():
            if isinstance(value,dict):result.update(visit(value))
            elif isinstance(value,list):
                for item in value:result.update(visit(item))
        return result
    return visit(element.get('source',{})) | ({element['connectionId']} if element.get('connectionId') else set())


PHASE_KEYS={'code-first':('allocation','goalSeek'),'solver-outputs':('allocation','goalSeek'),'guard-output':('applyGuard',)}
PORT_PREFIX={'allocation':'task5Allocation','goalSeek':'task5GoalSeek','applyGuard':'task5GoalSeekApplyGuard'}


def _phase_layout(elements,*,start=1):
    cursor=start;placements=''
    for element in elements:
        height=8 if element['kind']=='button' else 14
        placements+=f'<Element elementId="{element["id"]}" gridColumn="1 / 25" gridRow="{cursor} / {cursor+height}"/>'
        cursor+=height
    return placements


def build_port_fragments(model_binding,connection_id,*,column_maps=None,procedure_action=None,phase='code-first'):
    """Safe initial fragments only. Outputs require prepare_port_update evidence.

    Code elements have no documented construction API in the current MCP SDK;
    these are public REST fragments, never an executable SDK construction claim.
    """
    if phase!='code-first' or procedure_action is not None:raise PortError('PHASED_OUTPUT_EVIDENCE_OR_SEPARATE_PROCEDURE_ROUTE_REQUIRED')
    templates=_port_templates(model_binding,connection_id,column_maps=column_maps)
    elements=[e for e in templates['elements'] if e['id'] in {'task5AllocationPython','task5AllocationButton','task5GoalSeekPython','task5GoalSeekButton'}]
    return {'pages':templates['pages'],'elements':elements,'layout':'<Page type="grid" id="task5Ports" gridTemplateColumns="repeat(24, 1fr)">'+_phase_layout(elements)+'</Page>',
        'programs':{k:templates['programs'][k] for k in PHASE_KEYS['code-first']},'phase':'code-first','runtimeStatus':'UNRESOLVED','productionStatus':'BLOCKED'}


def _phase_context(context,current,receipt_hash,owned_code_ids):
    """Fresh actual controller observations; never label unsupported Code as SDK.

    SDK inventory covers exactly non-Code elements. Only our exact known owned
    code may use separate current public-schema/UI observations, since current
    SDK list_elements omits Code and its public schema has no action events.
    """
    try:
        from .action_inventory import validate_action_inventory
    except ImportError:
        from action_inventory import validate_action_inventory
    if not isinstance(context,dict) or not re.fullmatch('[a-f0-9]{64}',str(receipt_hash)):raise PortError('CURRENT_INPUT_DISPLAY_ACTION_CONTEXT_REQUIRED')
    fields={'documentId':current['workbookId'],'version':current['documentVersion'],'contentsHash':_digest(_snapshot(current)),'receiptHash':receipt_hash}
    review=context.get('review',{});owner=str(review.get('owner') or '').strip()
    if (context.get('origin')!='sigma-controller-actual' or not context.get('evidenceId') or any(context.get(k)!=v for k,v in fields.items())
            or review.get('status')!='APPROVED_STAGING' or not owner or re.match(r'(?i)^(pending|todo|tbd|unknown)\b',owner)
            or review.get('captureHash')!=_digest({k:v for k,v in context.items() if k!='review'})
            or any(not re.fullmatch('[a-f0-9]{64}',str(context.get(k,''))) for k in ('inputValuesHash','schemaDisplayHash','rawCaptureHash'))):
        raise PortError('FRESH_REVIEWED_INPUT_DISPLAY_ACTION_CONTEXT_REQUIRED')
    codes={e['id']:e for e in _snapshot(current)['elements'] if e.get('kind')=='code'}
    observations=context.get('codeObservations',{})
    if set(codes)!=set(owned_code_ids) or set(observations)!=set(codes):raise PortError('UNKNOWN_OR_UNOBSERVED_UNSUPPORTED_CODE_ELEMENT')
    for eid,element in codes.items():
        observed=observations[eid]
        if (element.get('actions') or observed.get('origin')!='sigma-code-rest-ui-readonly' or not observed.get('evidenceId')
                or observed.get('documentId')!=current['workbookId'] or observed.get('version')!=current['documentVersion']
                or observed.get('elementHash')!=_digest(element) or observed.get('codeHash')!=hashlib.sha256(element['code'].encode()).hexdigest()
                or observed.get('inspection')!='public-code-schema-no-action-events'):
            raise PortError('EXACT_CURRENT_CODE_REST_UI_OBSERVATION_REQUIRED')
    supported=copy.deepcopy(current);supported['contents']=copy.deepcopy(_snapshot(current));supported['contents']['elements']=[e for e in supported['contents']['elements'] if e['id'] not in codes]
    validate_action_inventory(context.get('sdkActions'),supported,require_recovery=True)
    return context


def _materialized_outputs(evidence,keys,manifest,receipt,current,previous,model_binding):
    """Validate recorded actual executions plus actual typed paired output names.

    The controller supplies observations, never infer metadata from expected
    schemas. A completed Python failure row can materialize output schema, but
    provides no successful computation/operation evidence.
    """
    if not isinstance(evidence,dict):raise PortError('ACTUAL_TYPED_OUTPUT_METADATA_REQUIRED')
    fields={'documentId':current['workbookId'],'version':current['documentVersion'],'sourceHash':manifest['sourceHash'],
        'planHash':manifest['planHash'],'modelBinding':model_binding,'contentsHash':_digest(_snapshot(current)),
        'receiptHash':_digest(receipt),'installedProposalHash':previous['proposalHash']}
    review=evidence.get('review',{});owner=str(review.get('owner') or '').strip()
    if (evidence.get('origin')!='sigma-python-output-actual' or not evidence.get('evidenceId') or any(evidence.get(k)!=v for k,v in fields.items())
            or review.get('status')!='APPROVED_STAGING' or not owner or re.match(r'(?i)^(pending|todo|tbd|unknown)\b',owner)
            or review.get('captureHash')!=_digest({k:v for k,v in evidence.items() if k!='review'}) or set(evidence.get('outputs',{}))!=set(keys)):
        raise PortError('FRESH_SOURCE_BOUND_ACTUAL_OUTPUT_REVIEW_REQUIRED')
    installed=evidence.get('installation',{})
    adoption=previous.get('restMutationRequired') is False
    if (installed.get('status')!=('VERIFIED_COMPONENT_NATIVE_ADOPTION' if adoption else 'VERIFIED_COMPONENT_CONSTRUCTION') or installed.get('proposalHash')!=previous['proposalHash']
            or installed.get('documentId')!=current['workbookId'] or not isinstance(installed.get('version'),int)
            or not previous['documentVersion']+(0 if adoption else 1)<=installed['version']<=current['documentVersion'] or not installed.get('evidenceId')
            or installed.get('contentsHash')!=_digest(previous['dryRunRequest']['contents'])):
        raise PortError('ACTUAL_PREVIOUS_PHASE_INSTALLATION_PROOF_REQUIRED')
    elements={e['id']:e for e in _snapshot(current)['elements']};result={}
    for key in keys:
        record=evidence['outputs'][key];prefix=PORT_PREFIX[key];code_id=prefix+'Python';code=elements.get(code_id,{})
        if code.get('code')!=emit_python_programs(model_binding,column_maps=previous['runtimeColumnMaps'])[key]['code']:raise PortError('INSTALLED_CODE_DIFFERS_FROM_REVIEWED_PORT_SOURCE')
        code_hash=hashlib.sha256(str(code.get('code','')).encode()).hexdigest();execution=record.get('execution',{})
        if (code.get('kind')!='code' or record.get('codeElementId')!=code_id or record.get('codeHash')!=code_hash or record.get('outputName')!=OUTPUT_NAMES[key]
                or execution.get('origin')!='sigma-run-python-actual' or execution.get('status')!='COMPLETED'
                or not execution.get('executionId') or not execution.get('evidenceId') or execution.get('documentId')!=current['workbookId']
                or type(execution.get('version')) is not int or not installed['version']<=execution['version']<=current['documentVersion']
                or execution.get('codeElementId')!=code_id or execution.get('codeHash')!=code_hash
                or record.get('connectionId')!=manifest['planProjection']['customPortArchitecture']['scope']['connectionId']):
            raise PortError('COMPLETED_ACTUAL_EXACT_CODE_EXECUTION_REQUIRED')
        metadata=record.get('metadata',{});mapping=record.get('columnMap',{})
        expected={n:('text' if t in {'VARCHAR','STRING'} else 'boolean' if t=='BOOLEAN' else 'integer' if t=='INTEGER' else 'number') for n,t in OUTPUT_SCHEMAS[key]}
        if (metadata.get('origin')!='sigma-python-output-metadata-actual' or not metadata.get('evidenceId')
                or metadata.get('executionId')!=execution['executionId'] or metadata.get('outputName')!=OUTPUT_NAMES[key]
                or metadata.get('documentId')!=current['workbookId'] or metadata.get('version')!=current['documentVersion']
                or record.get('metadataHash')!=_digest(metadata) or not re.fullmatch('[a-f0-9]{64}',str(metadata.get('rawCaptureHash','')))
                or set(mapping)!=set(expected) or not isinstance(metadata.get('observedFields'),list)):
            raise PortError('ACTUAL_OBSERVED_TYPED_OUTPUT_FIELDS_REQUIRED')
        observed=metadata['observedFields']
        namespace=metadata.get('sourceNamespace')
        if not isinstance(namespace,str) or not namespace or any(x in namespace for x in '[]/') or len(observed)!=len(expected) or any(not isinstance(c,dict) or set(c)!={'outputColumn','identifier','rowKey','type','formula'} for c in observed):raise PortError('EXACT_OBSERVED_OUTPUT_SCHEMA_AND_NAMESPACE_REQUIRED')
        for field in ('outputColumn','identifier','rowKey'):
            values=[c[field] for c in observed]
            if any(not isinstance(v,str) or not v or any(x in v for x in '[]') for v in values) or len(values)!=len(set(values)):raise PortError('AMBIGUOUS_OUTPUT_COLUMN_IDENTIFIER_OR_ROW_KEY')
        used=set()
        for name,typ in expected.items():
            pair=mapping[name]
            if not isinstance(pair,dict) or set(pair)!={'outputColumn','identifier','rowKey','formula'}:raise PortError('ACTUAL_PAIRED_OUTPUT_COLUMN_MAP_REQUIRED')
            if pair['outputColumn']!=name:raise PortError('SEMANTIC_OUTPUT_FIELD_NAME_MISMATCH')
            if pair['formula']!='['+namespace+'/'+pair['outputColumn']+']':raise PortError('EXACT_OBSERVED_CODE_OUTPUT_FORMULA_REQUIRED')
            matches=[i for i,c in enumerate(observed) if all(c[k]==v for k,v in pair.items()) and c['type']==typ]
            if len(matches)!=1 or matches[0] in used:raise PortError('OUTPUT_FIELD_TYPE_OR_PAIRED_NAME_MISMATCH')
            used.add(matches[0])
        native=record.get('nativeChildObservation')
        same=[e for e in elements.values() if e.get('source')=={'kind':'code-output','elementId':code_id,'output':OUTPUT_NAMES[key]}]
        if native is not None:
            child=elements.get(native.get('elementId'),{});typed=native.get('typedColumns',{});columns=typed.get('entries',[]);ids=native.get('columnIds',{})
            title={'goalSeek':'Goal Seek Result','applyGuard':'Goal Seek Apply Guard'}.get(key)
            if (native.get('origin')!='sigma-native-code-output-child-actual' or not native.get('evidenceId')
                    or native.get('documentId')!=current['workbookId'] or native.get('version')!=current['documentVersion']
                    or child.get('kind')!='table' or len(same)!=1 or same[0]['id']!=child.get('id') or native.get('elementHash')!=_digest(child)
                    or (title and (child.get('name')!=title or sum(e.get('name')==title for e in elements.values())!=1))
                    or native.get('typedColumnsHash')!=_digest(typed) or set(ids)!=set(expected) or not re.fullmatch('[a-f0-9]{64}',str(native.get('rawCaptureHash','')))
                    or len(columns)!=len(expected) or typed.get('total')!=len(expected) or typed.get('nextPage') is not None
                    or len(set(ids.values()))!=len(expected) or set(ids.values())!={c.get('id') for c in child.get('columns',[])}):
                raise PortError('EXACT_ACTUAL_NATIVE_CHILD_ADOPTION_PROOF_REQUIRED')
            for name,typ in expected.items():
                observed=[c for c in columns if c.get('columnId')==ids[name]];physical=[c for c in child['columns'] if c['id']==ids[name]]
                if (len(observed)!=1 or len(physical)!=1 or observed[0].get('label')!=mapping[name]['outputColumn']
                        or observed[0].get('type')!={'type':typ} or observed[0].get('formula')!=mapping[name]['formula'] or physical[0].get('formula')!=mapping[name]['formula']):
                    raise PortError('ACTUAL_NATIVE_CHILD_FORMULA_TYPE_OR_ASSIGNED_ID_CHANGED')
        elif same:raise PortError('EXPLICIT_EXISTING_NATIVE_CHILD_ADOPTION_REQUIRED')
        result[key]=copy.deepcopy(record)
    return result


def _validate_owned_port_buttons(current,context,owned_ids):
    """All owned buttons, including initial native adoptions, are pure Python.

    SDK has no toast visibility getter. The exact hidden REST constructor plus
    an absent/empty typed SDK toast qualifies this known gap; custom title,
    message or formulas cannot claim a persisted business write succeeded.
    """
    elements={e['id']:e for e in _snapshot(current)['elements']}
    known={PORT_PREFIX[key]+'Button':_port_run_button(key) for key in PORT_PREFIX};qualified={}
    for eid in owned_ids:
        element=elements.get(eid)
        if element is None:raise PortError('OWNED_PORT_ACTION_HOST_MISSING')
        if eid not in known:
            if element['kind']=='button':raise PortError('UNKNOWN_OWNED_PORT_ACTION_HOST')
            continue
        if element!=known[eid]:raise PortError('OWNED_PORT_ACTION_DIFFERS_FROM_KNOWN_HIDDEN_RUN_PYTHON_CONSTRUCTOR')
        sequences=context['sdkActions']['elements'][eid]['sequences'];effect=known[eid]['actions'][0]['effects'][0]
        expected=[{'kind':'RunPythonElement','fields':{'codeElementId':effect['codeElementId'],'name':effect['name']}}]
        if (len(sequences)!=1 or sequences[0]['trigger']!='on-click' or sequences[0]['condition'] is not None
                or sequences[0]['disabled'] is not False or sequences[0]['blocks']!=expected):raise PortError('OWNED_PORT_ACTION_DIFFERS_FROM_KNOWN_RUN_PYTHON_CONSTRUCTOR')
        toast=sequences[0]['successToast']
        if toast is not None and (set(toast)!={'title','message','formulas'} or toast['title'] not in (None,'') or toast['message'] not in (None,'') or toast['formulas']!={}):raise PortError('OWNED_PORT_OPTIMISTIC_OR_UNQUALIFIED_TOAST_REFUSED')
        qualified[eid]={'hiddenRestActionHash':_digest(element['actions'][0]),'actualSequenceId':sequences[0]['id'],
            'actualSdkToast':copy.deepcopy(toast),'toastVisibilityGetter':None,'authority':'exact-hidden-REST-constructor-and-empty-typed-SDK-toast'}
    return qualified


def _verify_phase_action_preservation(previous,current,context,*,native_child_ids=()):
    """Prove persisted old SDK actions, including REST-omitted sequences.

    Added hosts may only be the declared phase objects or exact observed native
    children. Changed assigned sequence IDs require independently reviewed exact
    restoration proof; semantic equality alone cannot authorize a new identity.
    """
    try:
        from .action_inventory import verify_action_preservation,digest as action_digest
    except ImportError:
        from action_inventory import verify_action_preservation,digest as action_digest
    before=(previous.get('phaseContext') or {}).get('sdkActions')
    if before is None:raise PortError('PREVIOUS_PHASE_SDK_ACTION_PROOF_REQUIRED')
    buttons=_validate_owned_port_buttons(current,context,previous['ownedPortElementIds'])
    after=context['sdkActions'];elements={e['id']:e for e in _snapshot(current)['elements']}
    supported=copy.deepcopy(current);supported['contents']=copy.deepcopy(_snapshot(current));supported['contents']['elements']=[e for e in supported['contents']['elements'] if e['kind']!='code']
    proof=verify_action_preservation(before,after,supported)
    extra=set(after['elements'])-set(before['elements'])
    declared=set(previous['addedElementIds'])|set(native_child_ids)
    if not extra<=declared:raise PortError('UNDECLARED_POST_PHASE_SDK_ACTION_HOST')
    for eid in extra:
        if elements[eid]['kind']!='button' and after['elements'][eid]['sequences']:raise PortError('NEW_OUTPUT_TABLE_MUST_HAVE_NO_ACTIONS')
    remapped={eid:{old['id']:new['id'] for old,new in zip(element['sequences'],after['elements'][eid]['sequences']) if old['id']!=new['id']}
        for eid,element in before['elements'].items()}
    remapped={eid:mapping for eid,mapping in remapped.items() if mapping}
    if remapped:
        review=context.get('actionRestorationReview') or {};owner=str(review.get('owner') or '').strip()
        fields={'documentId':current['workbookId'],'version':current['documentVersion'],'beforeInventoryHash':action_digest(before),
            'afterInventoryHash':action_digest(after),'assignedSequenceIds':remapped,
            'restorationProofHashes':{eid:action_digest(after['elements'][eid]['restorationArtifact']['restoreProof']) for eid in remapped}}
        if (review.get('status')!='APPROVED_STAGING' or not owner or re.match(r'(?i)^(pending|todo|tbd|unknown)\b',owner)
                or not review.get('evidenceId') or any(review.get(k)!=v for k,v in fields.items())):raise PortError('EXACT_ACTUAL_RESTORED_SEQUENCE_ID_REVIEW_REQUIRED')
    proof['ownedPortButtonQualifications']=buttons
    return proof


def prepare_port_update(manifest,receipt,current,sources,*,column_maps=None,procedure_action=None,phase='code-first',previous_phase=None,output_evidence=None,phase_context=None,consumed_phases=(),adoption_evidence=None):
    validate_custom_port_plan(manifest)
    _approved_feature(manifest,receipt,'forecastBusinessInput',require_assigned=True)
    arch=manifest['planProjection']['customPortArchitecture'];scope=arch['scope']
    doc=_snapshot(current)
    if (current.get('workbookId')!=scope['documentId'] or current.get('documentVersion')!=(manifest.get('target') or {}).get('version') or manifest.get('target',{}).get('documentId')!=scope['documentId']
            or current.get('folderId')!=scope['folderId']):
        raise PortError('STAGING_DOCUMENT_VERSION_FOLDER_MISMATCH')
    elements={e['id']:e for e in doc.get('elements',[])}
    if len(elements)!=len(doc.get('elements',[])):raise PortError('DUPLICATE_ELEMENT_IDS')
    required=(set(SOURCE_TITLES.values())-{'Goal Seek Result'}) | {'Forecast','PnL Combined'}
    if set(sources)!=required:raise PortError('EXACT_SOURCE_BINDINGS_REQUIRED')
    for title,binding in sources.items():
        matches=[e for e in elements.values() if e.get('name')==title]
        if (len(matches)!=1 or matches[0]['id']!=binding.get('elementId')
                or _digest(matches[0])!=binding.get('elementHash')
                or _connection_ids(matches[0],elements)!={scope['connectionId']}):
            raise PortError('SOURCE_ELEMENT_HASH_TITLE_CONNECTION_MISMATCH')
    model_binding=_digest({'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],
        'files':arch['files'],'documentId':scope['documentId'],'sources':sources,
        'sourceGraph':_source_graph_hashes(elements,[v['elementId'] for v in sources.values()]),'equation':arch['equationVersion']})
    if phase not in PHASE_KEYS or procedure_action is not None:raise PortError('PHASED_OUTPUT_EVIDENCE_OR_SEPARATE_PROCEDURE_ROUTE_REQUIRED')
    templates=_port_templates(model_binding,scope['connectionId'],column_maps=column_maps)
    previous=previous_phase;owned=[];lineage=[];actual_outputs={};maps=copy.deepcopy(column_maps or {});adopted=[]
    if phase=='code-first':
        if previous is not None or output_evidence is not None:raise PortError('INITIAL_PHASE_CANNOT_REUSE_PRIOR_OUTPUTS')
        fragments=build_port_fragments(model_binding,scope['connectionId'],column_maps=maps)
        reserved={e['id'] for e in templates['elements']};names={e.get('name') for e in templates['elements'] if e.get('name')}
        if adoption_evidence is not None:
            review=adoption_evidence.get('review',{});owner=str(review.get('owner') or '').strip()
            fields={'documentId':current['workbookId'],'version':current['documentVersion'],'contentsHash':_digest(doc),'receiptHash':_digest(receipt),
                'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],'modelBinding':model_binding,'elementHashes':{e['id']:_digest(e) for e in fragments['elements']}}
            if (adoption_evidence.get('origin')!='sigma-code-first-native-adoption-actual' or not adoption_evidence.get('evidenceId')
                    or review.get('status')!='APPROVED_STAGING' or not owner or re.match(r'(?i)^(pending|todo|tbd|unknown)\b',owner)
                    or review.get('captureHash')!=_digest({k:v for k,v in adoption_evidence.items() if k!='review'}) or any(adoption_evidence.get(k)!=v for k,v in fields.items())
                    or any(elements.get(e['id'])!=e for e in fragments['elements']) or sum(p['id']=='task5Ports' for p in doc['pages'])!=1):raise PortError('EXACT_CURRENT_CODE_FIRST_ADOPTION_REVIEW_REQUIRED')
            import xml.etree.ElementTree as ET
            try:
                from .native_actions import _layout_element_owners
            except ImportError:
                from native_actions import _layout_element_owners
            root=ET.fromstring('<Layout>'+re.sub(r'<\?xml[^?]*\?>','',doc.get('layout',''))+'</Layout>')
            if any([p.get('id') for p in _layout_element_owners(root,e['id'])]!=['task5Ports'] for e in fragments['elements']):raise PortError('CODE_FIRST_ADOPTION_ASSIGNED_PAGE_CHANGED')
            adopted=[e['id'] for e in fragments['elements']];owned=adopted[:];new=[];contents=copy.deepcopy(doc);added_pages=[]
        else:
            if set(elements)&reserved or any(e.get('name') in names for e in elements.values()) or any(p['id']=='task5Ports' for p in doc.get('pages',[])):raise PortError('EXISTING_PORT_OBJECT_REFUSED_NO_OVERWRITE')
            new=fragments['elements'];contents=copy.deepcopy(doc);contents['pages']+=fragments['pages'];contents['elements']+=new;contents['layout']=doc.get('layout','')+'\n'+fragments['layout'];added_pages=['task5Ports']
    else:
        if adoption_evidence is not None:raise PortError('CODE_ADOPTION_ONLY_IN_INITIAL_PHASE')
        expected_previous={'solver-outputs':'code-first','guard-output':'solver-outputs'}[phase]
        if not isinstance(previous,dict) or previous.get('proposalHash')!=_digest({k:v for k,v in previous.items() if k!='proposalHash'}) or previous.get('phase')!=expected_previous:raise PortError('EXACT_ORDERED_PREVIOUS_PHASE_REQUIRED')
        if (previous['workbookId']!=current['workbookId'] or previous['folderId']!=scope['folderId'] or not previous['documentVersion']+(0 if previous.get('restMutationRequired') is False else 1)<=current['documentVersion']
                or previous['sourceHash']!=manifest['sourceHash'] or previous['planHash']!=manifest['planHash'] or previous['modelBinding']!=model_binding
                or previous['sourceBindings']!=sources or previous['sourceGraph']!=_source_graph_hashes(elements,[v['elementId'] for v in sources.values()])):raise PortError('PREVIOUS_PHASE_SOURCE_MODEL_OR_VERSION_STALE')
        owned=previous['ownedPortElementIds'];prior_elements={e['id']:e for e in previous['dryRunRequest']['contents']['elements']}
        if any(elements.get(eid)!=prior_elements.get(eid) for eid in owned):raise PortError('INSTALLED_PORT_CODE_OR_OBJECT_CHANGED')
        lineage=[*previous.get('phaseLineage',[]),previous['proposalHash']]
        if column_maps is not None and column_maps!=previous['runtimeColumnMaps']:raise PortError('EXISTING_RUNTIME_COLUMN_MAP_CHANGED')
        maps=copy.deepcopy(previous['runtimeColumnMaps']);actual_outputs=copy.deepcopy(previous.get('actualOutputBindings',{}))
        observed=_materialized_outputs(output_evidence,PHASE_KEYS[phase],manifest,receipt,current,previous,model_binding);actual_outputs.update(observed)
        if phase=='solver-outputs':maps[OUTPUT_NAMES['goalSeek']]={n:{k:pair[k] for k in ('identifier','rowKey')} for n,pair in observed['goalSeek']['columnMap'].items()}
        templates=_port_templates(model_binding,scope['connectionId'],column_maps=maps)
        ids={'solver-outputs':{'task5AllocationResult','task5GoalSeekResult','task5GoalSeekApplyGuardPython','task5GoalSeekApplyGuardButton'},'guard-output':{'task5GoalSeekApplyGuard'}}[phase]
        new=[copy.deepcopy(e) for e in templates['elements'] if e['id'] in ids]
        for key,record in observed.items():
            eid=PORT_PREFIX[key]+'Result' if key!='applyGuard' else PORT_PREFIX[key]
            table=next(e for e in new if e['id']==eid)
            for col in table['columns']:col['formula']=record['columnMap'][col['name']]['formula']
            if record.get('nativeChildObservation'):
                adopted.append(record['nativeChildObservation']['elementId']);new.remove(table)
        owned=[*owned,*adopted]
        ids={e['id'] for e in new}
        if set(elements)&ids or any(e.get('name')==n['name'] for e in elements.values() for n in new if n.get('name')):raise PortError('EXISTING_PHASE_OUTPUT_REFUSED_NO_OVERWRITE')
        import xml.etree.ElementTree as ET
        layout=doc.get('layout','');matches=list(re.finditer(r'<Page\b[^>]*\bid=["\']task5Ports["\'][^>]*>.*?</Page>',layout,re.S))
        if len(matches)!=1 or sum(p['id']=='task5Ports' for p in doc['pages'])!=1:raise PortError('EXACT_EXISTING_PORT_PAGE_REQUIRED')
        node=ET.fromstring(matches[0].group());cursor=1
        for placement in node.iter('Element'):
            row=re.fullmatch(r'(\d+) / (\d+)',placement.get('gridRow',''))
            if not row:raise PortError('UNKNOWN_PORT_PAGE_PLACEMENT')
            cursor=max(cursor,int(row[2]))
        contents=copy.deepcopy(doc);contents['elements']+=new;pos=matches[0].end()-len('</Page>');contents['layout']=layout[:pos]+_phase_layout(new,start=cursor)+layout[pos:];added_pages=[]
    owned_codes=[eid for eid in owned if elements[eid]['kind']=='code']
    context=_phase_context(phase_context,current,_digest(receipt),owned_codes) if phase_context is not None or phase!='code-first' else None
    if context is not None:_validate_owned_port_buttons(current,context,owned)
    if previous is not None:
        _verify_phase_action_preservation(previous,current,context,native_child_ids=[v['nativeChildObservation']['elementId'] for v in actual_outputs.values() if v.get('nativeChildObservation')])
    phase_id=_digest({'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],'modelBinding':model_binding,'phase':phase,'previous':lineage,'contentsHash':_digest(doc),'version':current['documentVersion']})
    if phase_id in consumed_phases:raise PortError('CONSUMED_PHASE_REPLAY_REFUSED')
    proposal={'phase':phase,'phaseId':phase_id,'phaseLineage':lineage,'previousProposalHash':previous['proposalHash'] if previous else None,
        'workbookId':scope['documentId'],'documentVersion':current['documentVersion'],'folderId':scope['folderId'],
        'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],'modelBinding':model_binding,
        'beforeHash':_digest(doc),'beforeContents':copy.deepcopy(doc),'sourceBindings':copy.deepcopy(sources),
        'sourceGraph':_source_graph_hashes(elements,[v['elementId'] for v in sources.values()]),'receiptHash':_digest(receipt),
        'addedElementIds':[e['id'] for e in new],'ownedPortElementIds':[*owned,*[e['id'] for e in new]],'addedPageIds':added_pages,
        'adoptedElementIds':adopted,'adoptionEvidence':copy.deepcopy(adoption_evidence),'restMutationRequired':bool(new),
        'runtimeColumnMaps':maps,'actualOutputBindings':actual_outputs,'phaseContext':copy.deepcopy(context),
        'outputEvidence':copy.deepcopy(output_evidence),'runtimeStatus':'UNRESOLVED','workflowComplete':False,
        'constructionStatus':('READY_FOR_ACTUAL_DRY_RUN' if new else 'VERIFIED_NATIVE_ADOPTION_NO_REST_SEND') if context else 'PARTIAL_REQUIRES_CURRENT_INPUT_DISPLAY_ACTION_EVIDENCE',
        'dryRunRequest':{'name':current.get('name','Reviewed custom ports staging'),'folderId':scope['folderId'],'contents':contents,'dryRun':True},'productionStatus':'BLOCKED'}
    proposal['proposalHash']=_digest(proposal)
    return proposal


def finalize_port_update(proposal,fresh,dry_run,*,consumed_proposals=(),reviewed_warning_hash=None,fresh_phase_context=None):
    if _digest({k:v for k,v in proposal.items() if k!='proposalHash'})!=proposal.get('proposalHash'):
        raise PortError('PROPOSAL_HASH_MISMATCH')
    if proposal['proposalHash'] in consumed_proposals or proposal.get('phaseId') in consumed_proposals:raise PortError('CONSUMED_PROPOSAL_REPLAY_REFUSED')
    if proposal.get('restMutationRequired') is False:raise PortError('NATIVE_ADOPTION_REQUIRES_NO_REST_SEND')
    doc=_snapshot(fresh)
    if (fresh.get('workbookId')!=proposal['workbookId'] or fresh.get('documentVersion')!=proposal['documentVersion']
            or fresh.get('folderId')!=proposal['folderId'] or _digest(doc)!=proposal['beforeHash']):
        raise PortError('STALE_DOCUMENT_VERSION_OR_CONTENTS')
    if proposal.get('phase'):
        before=proposal.get('phaseContext')
        if not before:raise PortError('CURRENT_INPUT_DISPLAY_ACTION_CONTEXT_REQUIRED')
        code_ids=[e['id'] for e in doc['elements'] if e.get('kind')=='code']
        context=_phase_context(fresh_phase_context,fresh,proposal['receiptHash'],code_ids)
        present={e['id'] for e in doc['elements']}
        _validate_owned_port_buttons(fresh,context,[eid for eid in proposal['ownedPortElementIds'] if eid in present])
        if any(context[k]!=before[k] for k in ('inputValuesHash','schemaDisplayHash')):raise PortError('INPUT_OR_DISPLAY_CHANGED_SINCE_PHASE_REVIEW')
        try:
            from .action_inventory import verify_action_preservation
        except ImportError:
            from action_inventory import verify_action_preservation
        supported=copy.deepcopy(fresh);supported['contents']=copy.deepcopy(doc);supported['contents']['elements']=[e for e in doc['elements'] if e['id'] not in code_ids]
        verify_action_preservation(before['sdkActions'],context['sdkActions'],supported)
    if (dry_run.get('httpStatus')!=200 or dry_run.get('dryRun') is not True or dry_run.get('valid') is False or dry_run.get('errors')
            or not dry_run.get('evidenceId') or dry_run.get('proposalHash')!=proposal['proposalHash']):
        raise PortError('HASH_BOUND_ACTUAL_DRY_RUN_REQUIRED')
    warnings=dry_run.get('warnings',[])
    if warnings and reviewed_warning_hash!=_digest(warnings):raise PortError('DRY_RUN_WARNINGS_REQUIRE_REVIEW')
    return {'method':'PUT','path':'/v2/workbooks/'+proposal['workbookId']+'/contents',
            'body':{'documentVersion':fresh['documentVersion'],'contents':copy.deepcopy(proposal['dryRunRequest']['contents'])},
            'proposalHash':proposal['proposalHash'],'consumeBeforeSend':True,'productionStatus':'BLOCKED'}


def audit_port_update(proposal,readback,*,post_phase_context=None):
    if proposal.get('proposalHash')!=_digest({k:v for k,v in proposal.items() if k!='proposalHash'}):raise PortError('PROPOSAL_HASH_MISMATCH')
    if proposal.get('phase') and not proposal.get('phaseContext'):raise PortError('CURRENT_INPUT_DISPLAY_ACTION_CONTEXT_REQUIRED')
    if post_phase_context is None:raise PortError('POST_PHASE_SDK_ACTION_PROOF_REQUIRED')
    owned={e['id']:e for e in proposal['dryRunRequest']['contents']['elements']}
    code_ids=[eid for eid in proposal['ownedPortElementIds'] if owned[eid]['kind']=='code']
    context=_phase_context(post_phase_context,readback,post_phase_context.get('receiptHash'),code_ids)
    if any(context[k]!=proposal['phaseContext'][k] for k in ('inputValuesHash','schemaDisplayHash')):raise PortError('POST_PHASE_INPUT_OR_DISPLAY_CHANGED')
    action_proof=_verify_phase_action_preservation(proposal,readback,context)
    if proposal.get('restMutationRequired') is False:
        if readback.get('workbookId')!=proposal['workbookId'] or readback.get('documentVersion')!=proposal['documentVersion'] or _snapshot(readback)!=proposal['beforeContents']:raise PortError('NATIVE_ADOPTION_READBACK_CHANGED')
        return {'status':'VERIFIED_COMPONENT_NATIVE_ADOPTION','documentId':proposal['workbookId'],'version':readback['documentVersion'],
            'elementIds':proposal['adoptedElementIds'],'proposalHash':proposal['proposalHash'],'restMutationRequired':False,'actionPreservation':action_proof,'productionStatus':'BLOCKED'}
    if (readback.get('workbookId')!=proposal['workbookId'] or type(readback.get('documentVersion')) is not int or readback['documentVersion']<=proposal['documentVersion']
            or _snapshot(readback)!=proposal['dryRunRequest']['contents']):
        raise PortError('PORT_UPDATE_READBACK_MISMATCH')
    return {'status':'VERIFIED_COMPONENT_CONSTRUCTION','documentId':proposal['workbookId'],
            'version':readback['documentVersion'],'elementIds':proposal['addedElementIds'],
            'proposalHash':proposal['proposalHash'],'actionPreservation':action_proof,'productionStatus':'BLOCKED'}


def _constant(value):
    kind='boolean' if isinstance(value,bool) else 'number' if isinstance(value,(float,int)) else 'text'
    return {'type':'constant','value':{'type':kind,'value':value}}


def build_goal_seek_actions(binding,request,actuals,inputs,definitions,result,*,expected_binding):
    """Compile separate Compute, Guard and Apply action sequences for one intent.

    The controller supplies/reuses the durable Task4 operation ID, backs up the
    invocation and input rows, and attaches these fragments using a fresh guarded
    contents update. Apply is authored only after independent current model and
    solved-result validation. It never marks APPLIED: an independent full row
    readback via verify_goal_seek_write is required before operation reconciliation.
    """
    request_contract(request,expected_binding)
    change=plan_goal_seek_write(actuals,inputs,definitions,{**request,'State':'APPLY_PENDING'},result,
                               expected_binding=expected_binding)
    if change is None:raise PortError('RETRY_ALREADY_APPLIED')
    for name in ('invocation','assumption','guard','inputView'):
        entry=binding.get(name,{})
        if not entry.get('elementId') or not entry.get('name') or any(t in entry['elementId'].upper() for t in ('PENDING','PLACEHOLDER')):
            raise PortError('ACTUAL_ACTION_ELEMENT_BINDINGS_REQUIRED')
    inv,assumption,guard,view=[binding[n] for n in ('invocation','assumption','guard','inputView')]
    needed={'invocation':set(request)|{'RequestKey'},'assumption':{'Line Item','Input Row ID','Monthly Growth'},
            'guard':{n for n,t in OUTPUT_SCHEMAS['applyGuard']}}
    for name,names in needed.items():
        cols=binding[name].get('columnIds',{})
        if not names<=set(cols) or any(not cols[k] for k in names) or len(set(cols.values()))!=len(cols):
            raise PortError('ACTUAL_ACTION_COLUMN_BINDINGS_REQUIRED')
    def update_inv(state):
        values={**request,'RequestKey':'goal-seek','State':state}
        return {'effect':'update-rows','tableElementId':inv['elementId'],
            'whichRows':{'type':'single-row','primaryKeys':{inv['columnIds']['RequestKey']:_constant('goal-seek')}},
            'values':{inv['columnIds'][k]:_constant(v) for k,v in values.items()}}
    def sequence(name,effects):
        return {'id':'task5-'+name,'trigger':'on-click','effects':effects,'successToast':{'showMessage':'hidden'}}
    text=lambda value:json.dumps(value,ensure_ascii=False)
    lookup=lambda table,column,key,key_column:'Lookup(['+table+'/'+column+'], '+text(key)+', ['+table+'/'+key_column+'])'
    op=request['OperationId'];fp=result['InputFingerprint'];row_id=result['SubscriptionRowId']
    g=lambda column:lookup(guard['name'],column,op,'OperationId')
    i=lambda column:lookup(inv['name'],column,'goal-seek','RequestKey')
    v=lambda column:lookup(view['name'],column,SUBSCRIPTION,'Line Item')
    # Parent verifies each source/input/column binding against fresh readback.
    # Dynamic operation, row and previous-value checks also fail closed at click.
    predicates=[f'Count([{guard["name"]}/OperationId]) = 1',f'Count([{inv["name"]}/RequestKey]) = 1',
        g('ReadyToApply')+' = True',i('OperationId')+' = '+text(op),i('State')+' = "APPLY_PENDING"',
        i('ModelBinding')+' = '+text(expected_binding),g('ModelBinding')+' = '+text(expected_binding),
        g('ResultOperationId')+' = '+text(op),g('ResultFingerprint')+' = '+text(fp),g('CurrentFingerprint')+' = '+text(fp),
        g('SubscriptionRowId')+' = '+text(row_id),v('Input Row ID')+' = '+text(row_id),
        v('Monthly Growth')+' = '+repr(result['PreviousGrowth']),g('SolvedGrowth')+' = '+repr(result['SolvedGrowth'])]
    for key in ('Target','LowerBound','UpperBound','ToleranceCents','MaxIterations'):
        predicates.append(i(key)+' = '+repr(request[key]))
    write={'effect':'update-rows','tableElementId':assumption['elementId'],
        'whichRows':{'type':'single-row','primaryKeys':{assumption['columnIds']['Line Item']:_constant(SUBSCRIPTION),
                                                     assumption['columnIds']['Input Row ID']:_constant(row_id)}},
        'values':{assumption['columnIds']['Monthly Growth']:{'type':'formula','formula':g('SolvedGrowth')}},
        'name':'task5ApplySolvedGrowth'}
    return {'compute':sequence('compute-goal',[update_inv('PENDING'),
                 {'effect':'run-python-element','codeElementId':'task5GoalSeekPython'}]),
        'guard':sequence('guard-goal',[update_inv('APPLY_PENDING'),
                 {'effect':'run-python-element','codeElementId':'task5GoalSeekApplyGuardPython'}]),
        'apply':sequence('apply-goal',[{'effect':'if-else','if':{'condition':{'type':'formula',
            'formula':' and '.join('('+p+')' for p in predicates)},'effects':[write]}}]),
        'change':change,'requiredReadback':'verify_goal_seek_write before marking invocation APPLIED',
        'concurrency':'Current model hash must be rechecked immediately before click; ordinary input tables do not provide serializable multi-table compare-and-swap.',
        'productionStatus':'BLOCKED'}


def build_port_input_specs(forecast_input_template):
    """Additive ordinary-input companions, seeded by the existing resumable path.

    The persisted invocation takes the operation ID returned by the reviewed
    Task4 Prepare workflow (or a test-driver UUID). UNPREPARED cannot compute or
    apply. ModelBinding is populated only after fresh source graph binding.
    """
    if not forecast_input_template.get('connectionId'):
        raise PortError('FORECAST_CONNECTION_REQUIRED')
    def spec(name,keys,columns,rows):
        return {**{k:copy.deepcopy(forecast_input_template[k]) for k in ('connectionId','writebackSchemaId')
                   if k in forecast_input_template},'kind':'input-table','name':name,'keyColumns':keys,
                'editMode':'published-explore','columns':[{'name':n,'type':t,'provenance':'task5-controlled-fixture'} for n,t in columns],
                'rows':rows}
    fields=[('RequestKey','text'),('OperationId','text'),('State','text'),('Target','number'),
            ('LowerBound','number'),('UpperBound','number'),('ToleranceCents','number'),('MaxIterations','number'),
            ('ModelBinding','text'),('AppliedOperationId','text'),('AppliedGrowth','number')]
    request=dict(RequestKey='goal-seek',OperationId=None,State='UNPREPARED',Target=2000000,LowerBound=0,
                 UpperBound=.25,ToleranceCents=1,MaxIterations=64,ModelBinding=None,AppliedOperationId=None,AppliedGrowth=None)
    return {'task5Headcount':spec('Task 5 Headcount Inputs',['Department'],[('Department','text'),('Headcount','number')],
                [{'Department':d,'Headcount':h} for d,h in zip(DEPARTMENTS,[40,30,20,10])]),
            'task5Overhead':spec('Task 5 Allocation Assumptions',['Key'],[('Key','text'),('Value','number')],
                [{'Key':'Overhead','Value':100000}]),
            'task5Invocation':spec('Goal Seek Invocation',['RequestKey'],fields,[request])}


def _source_graph_hashes(elements,roots):
    seen={}
    def visit(eid):
        if eid in seen:return
        if eid not in elements:raise PortError('MISSING_MODEL_SOURCE')
        element=elements[eid];seen[eid]=_digest(element)
        def descend(value):
            if isinstance(value,dict):
                if value.get('kind') in ('table','code-output') and value.get('elementId'):
                    visit(value['elementId'])
                for sub in value.values():descend(sub)
            elif isinstance(value,list):
                for sub in value:descend(sub)
        descend(element.get('source',{}))
    for root in roots:visit(root)
    return seen


def prepare_goal_action_update(manifest,receipt,current,initial_proposal,binding,request,actuals,inputs,definitions,result):
    """Append per-intent buttons after reviewing the actual solver output.

    Only source/port objects from the immutable first proposal and actual assigned
    input bindings can authorize follow-up actions. Arbitrary supplied actions are
    never accepted. The result is subject to the same fresh dry-run/finalize gates.
    """
    validate_custom_port_plan(manifest)
    _approved_feature(manifest,receipt,'forecastBusinessInput',require_assigned=True)
    prior=initial_proposal
    if prior.get('phase') and prior['phase']!='guard-output':raise PortError('FULL_ACTUAL_OUTPUT_PHASE_CHAIN_REQUIRED')
    if _digest({k:v for k,v in prior.items() if k!='proposalHash'})!=prior.get('proposalHash'):
        raise PortError('INITIAL_PROPOSAL_HASH_MISMATCH')
    if (current.get('workbookId')!=prior['workbookId'] or current.get('folderId')!=prior['folderId']
            or prior.get('sourceHash')!=manifest['sourceHash'] or prior.get('planHash')!=manifest['planHash']):
        raise PortError('FOLLOWUP_SOURCE_SCOPE_MISMATCH')
    doc=_snapshot(current);elements={e['id']:e for e in doc['elements']}
    graph=_source_graph_hashes(elements,[v['elementId'] for v in prior['sourceBindings'].values()])
    if graph!=prior.get('sourceGraph'):raise PortError('MODEL_SOURCE_GRAPH_CHANGED')
    prior_elements={e['id']:e for e in prior['dryRunRequest']['contents']['elements']}
    owned=prior.get('ownedPortElementIds',prior['addedElementIds'])
    if any(elements.get(eid)!=prior_elements[eid] for eid in owned):
        raise PortError('PORT_SOURCE_OBJECT_CHANGED')
    if len(elements)!=len(doc['elements']):raise PortError('DUPLICATE_ELEMENT_IDS')
    assigned=receipt['targetBindings']['forecastBusinessInput']
    _,invocation_assigned,_=_approved_feature(manifest,receipt,'task5Invocation',require_assigned=True)
    expected_ids={'assumption':assigned['elementId'],
        'invocation':prior['sourceBindings']['Goal Seek Invocation']['elementId'],
        'inputView':prior['sourceBindings']['Forecast Inputs View']['elementId'],
        'guard':prior.get('actualOutputBindings',{}).get('applyGuard',{}).get('nativeChildObservation',{}).get('elementId','task5GoalSeekApplyGuard')}
    if invocation_assigned['elementId']!=expected_ids['invocation']:
        raise PortError('ASSIGNED_INVOCATION_TARGET_MISMATCH')
    connection=manifest['planProjection']['customPortArchitecture']['scope']['connectionId']
    # Warehouse get_element and action Lookup both resolve titles. Protect every
    # original runtime source/output against compatible duplicate-title objects.
    runtime_ids={v['elementId'] for v in prior['sourceBindings'].values()} | {
        eid for eid in owned if prior_elements[eid].get('kind')=='table'}
    for eid in runtime_ids:
        title=prior_elements[eid].get('name')
        if not title and prior_elements[eid].get('source')=={'kind':'code-output','elementId':'task5AllocationPython','output':'AllocationResult'}:
            continue  # This result is queried by assigned ID, never sigma.get_element(title).
        if not title or sum(e.get('name')==title for e in doc['elements'])!=1:
            raise PortError('AMBIGUOUS_RUNTIME_SOURCE_TITLE')
    for role in ('invocation','assumption','guard','inputView'):
        value=binding.get(role,{})
        eid=expected_ids[role]
        element=elements.get(eid,{})
        approved=prior_elements.get(eid,{})
        kind='input-table' if role in ('invocation','assumption') else 'table'
        if (value.get('elementId')!=eid or not approved or element!=approved
                or value.get('name')!=approved.get('name') or element.get('kind')!=kind
                or sum(e.get('name')==approved.get('name') for e in doc['elements'])!=1
                or _connection_ids(element,elements)!={connection}):
            raise PortError('APPROVED_ACTION_ROLE_IDENTITY_MISMATCH')
        if role=='guard' and element.get('source')!={'kind':'code-output',
                'elementId':'task5GoalSeekApplyGuardPython','output':'GoalSeekApplyGuard'}:
            raise PortError('APPROVED_GUARD_CODE_OUTPUT_REQUIRED')
        columns={c.get('name'):c.get('id') for c in element.get('columns',[])}
        if role=='guard':
            adopted=prior.get('actualOutputBindings',{}).get('applyGuard',{}).get('nativeChildObservation')
            if adopted and adopted.get('elementId')==eid and adopted.get('elementHash')==_digest(element):columns.update(adopted['columnIds'])
        target=invocation_assigned if role=='invocation' else assigned if role=='assumption' else None
        if target and any(value.get('columnIds',{}).get(n)!=cid
                for n,cid in target['columnIds'].items() if n in value.get('columnIds',{})):
            raise PortError('ASSIGNED_ACTION_COLUMN_BINDING_MISMATCH')
        for name,cid in value.get('columnIds',{}).items():
            if columns.get(name)==cid:continue
            system=value.get('systemColumn')
            allowed=assigned.get('systemColumn') if role=='assumption' else None
            if not (name=='Input Row ID' and system and system==allowed and cid==system.get('id')):
                raise PortError('ACTUAL_ACTION_COLUMN_BINDING_MISMATCH')
    actions=build_goal_seek_actions(binding,request,actuals,inputs,definitions,result,expected_binding=prior['modelBinding'])
    suffix=hashlib.sha256(operation(request['OperationId']).encode()).hexdigest()[:16]
    page_id='task5Intent'+suffix
    new=[]
    for phase in ('compute','guard','apply'):
        action=copy.deepcopy(actions[phase]);action['id']+=suffix
        new.append({'id':page_id+phase,'kind':'button','appearance':'filled','text':{'compute':'Prepare and solve',
            'guard':'Prepare and validate apply','apply':'Apply verified growth'}[phase], 'actions':[action]})
    if page_id in {p['id'] for p in doc['pages']} or set(elements)&{e['id'] for e in new}:
        raise PortError('EXISTING_INTENT_ACTION_REFUSED_NO_REPLAY')
    contents=copy.deepcopy(doc);contents['pages'].append({'id':page_id,'name':'Goal seek '+request['OperationId']})
    contents['elements']+=new
    contents['layout']+='\n<Page type="grid" id="'+page_id+'" gridTemplateColumns="repeat(24, 1fr)">'+''.join(
        f'<Element elementId="{e["id"]}" gridColumn="1 / 25" gridRow="{1+n*8} / {9+n*8}"/>' for n,e in enumerate(new))+'</Page>'
    proposal={'workbookId':prior['workbookId'],'documentVersion':current['documentVersion'],'folderId':prior['folderId'],
        'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],'modelBinding':prior['modelBinding'],
        'beforeHash':_digest(doc),'beforeContents':copy.deepcopy(doc),'addedElementIds':[e['id'] for e in new],
        'addedPageIds':[page_id],'initialProposalHash':prior['proposalHash'],'operationId':request['OperationId'],
        'inputFingerprint':result['InputFingerprint'],'dryRunRequest':{'name':current.get('name','Reviewed goal actions'),
        'folderId':prior['folderId'],'contents':contents,'dryRun':True},'productionStatus':'BLOCKED'}
    proposal['proposalHash']=_digest(proposal)
    return proposal
