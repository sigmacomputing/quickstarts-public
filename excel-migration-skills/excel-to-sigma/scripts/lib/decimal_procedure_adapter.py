"""Narrow reviewed decimal TEXT transport to the unchanged fixed-point procedure.

The original NUMBER action route remains separate and runtime-blocked. The new
wrapper must have actual indexed signature, caller, datetime and scalar evidence
before executable action emission. Provisioning by itself cannot authorize it.
"""
import copy
import datetime as dt
import re
from decimal import Decimal
try:
    from .input_sync import _digest
except ImportError:
    from input_sync import _digest
PATH=['SIGMA_WRITE_DB','SIGMA_TASK5_SP_TEST','TASK5_TYPED_ECHO_TEXT_AMOUNT']
TYPES=['VARCHAR','VARCHAR','NUMBER(38,0)','BOOLEAN','TIMESTAMP_NTZ(3)']
ACTION_TYPES=['text','text','integer','boolean','datetime']
ADAPTER_BODY='1df68a1cc86017ef93cebcc5e554873894080ff6f029ba46630393d3217b9abc'
CALLEE_BODY='f544541aa79453bcd828baa304c6c1ecc4c7249bf1f181fd3dfbe8642c1960ed'


def controlled_decimal_text_contract(connection_id):
    if not isinstance(connection_id,str) or not connection_id:raise ValueError('actual connection required')
    return {'connectionId':connection_id,'path':list(PATH),'declaredTypes':list(TYPES),'actionTypes':list(ACTION_TYPES),
        'signature':None,'returnType':'VARCHAR','executeAs':'CALLER','language':'SQL','overloads':1,'defaults':False,
        'sideEffects':[],'adapterBodySha256Trimmed':ADAPTER_BODY,'calleeBodySha256Trimmed':CALLEE_BODY,
        'calleePath':['SIGMA_WRITE_DB','SIGMA_TASK5_SP_TEST','TASK5_TYPED_ECHO'],
        'caller':{'user':'SIGMA_SERVICE_USER','role':'SIGMA_ROLE','warehouse':'SIGMA_WH'},
        'transport':'exact reviewed decimal text -> NUMBER(18,2) -> unchanged original typed business callee',
        'productionStatus':'BLOCKED','runtimeStatus':'PENDING_INDEXED_SIGNATURE_AND_NATIVE_CENTS_PARITY'}


def build_decimal_text_procedure_action(contract,arguments,*,prior_invocation=None):
    expected=controlled_decimal_text_contract(contract.get('connectionId'))
    for key in expected:
        if key not in {'signature'} and contract.get(key)!=expected[key]:raise ValueError('exact separate wrapper/callee contract required')
    signature=contract.get('signature')
    if (not isinstance(signature,str) or not signature.strip() or re.search(r'PENDING|ASSIGN|VARIANT|DEFAULT',signature,re.I)
        or any(not contract.get(k) for k in ('catalogObjectId','lookupEvidenceId','callerEvidenceId','scalarMappingEvidenceId','datetimeEvidenceId','provisioningEvidenceId','signatureEvidenceId'))):
        raise ValueError('actual wrapper indexed signature/caller/datetime/scalar evidence required')
    if contract.get('lookup')!={k:contract[k] for k in ('connectionId','path','signature','declaredTypes','actionTypes','returnType')}:
        raise ValueError('exact ordered wrapper indexed metadata required')
    if not isinstance(arguments,list) or len(arguments)!=5:raise ValueError('exact five ordered arguments required')
    op,amount,count,enabled,timestamp=arguments
    if not isinstance(op,str) or not op or any(c.isspace() for c in op) or '|' in op:raise ValueError('invalid operation ID')
    if (not isinstance(amount,str) or not re.fullmatch(r'-?(0|[1-9][0-9]{0,14})([.][0-9]{1,2})?',amount)
        or (amount.startswith('-') and Decimal(amount)==0)):raise ValueError('exact canonical decimal text required; binary floats and rounding refused')
    if type(count) is not int or not 0<=count<10**15 or type(enabled) is not bool:raise ValueError('strict integer count/logical required')
    if not isinstance(timestamp,str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}',timestamp):raise ValueError('fixed millisecond NTZ timestamp required')
    dt.datetime.fromisoformat(timestamp)
    invocation={'operationId':op,'argumentFingerprint':_digest(arguments),'contractHash':_digest(contract),
        'expectedScalar':f'operation_id={op}|amount={Decimal(amount):.2f}|count={count}|enabled={str(enabled).lower()}|occurred_at={timestamp}'}
    if prior_invocation and prior_invocation.get('operationId')==op and prior_invocation!=invocation:raise ValueError('same-operation retry changed wire input or contract')
    constants=[op,amount,count,enabled];kinds=['text','text','number','boolean']
    wire=[{'parameterIndex':i,'type':ACTION_TYPES[i],'value':{'type':'constant','value':{'type':kind,'value':value}}} for i,(kind,value) in enumerate(zip(kinds,constants))]
    # This exact native formula form passed the parent's independent date validation.
    wire.append({'parameterIndex':4,'type':'datetime','value':{'type':'formula','formula':'Datetime("'+timestamp+'")'}})
    return {'id':'task6-call-decimal-text-adapter','trigger':'on-click','effects':[{'effect':'call-stored-procedure',
        'storedProcedure':{k:copy.deepcopy(contract[k]) for k in ('connectionId','path','signature')},'arguments':wire,'name':'task6DecimalTextScalar'}],
        'successToast':{'showMessage':'hidden'},'invocation':invocation,'orderedArguments':copy.deepcopy(arguments),
        'contract':copy.deepcopy(contract),'failurePolicy':'halt-dependent-effects; no success and no automatic retry','productionStatus':'BLOCKED'}


def build_decimal_text_port_fragment(contract,arguments):
    try:
        from .workflow_repairs import _page
    except ImportError:
        from workflow_repairs import _page
    action=build_decimal_text_procedure_action(contract,arguments)
    button={'id':'task6DecimalTextProcedureButton','kind':'button','appearance':'filled','text':'Run reviewed decimal scalar',
        'actions':[{k:copy.deepcopy(action[k]) for k in ('id','trigger','effects','successToast')}]}
    return {**_page('task6DecimalTextProcedure','Reviewed decimal transport',[button]),'invocation':action['invocation'],'productionStatus':'BLOCKED'}
