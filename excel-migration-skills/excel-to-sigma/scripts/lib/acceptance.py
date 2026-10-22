"""Append-only source/version-bound acceptance evidence and honest reports.

This validates captured evidence, not the authenticity of backend/session receipts.
The designated controller captures actual execution and the independent reviewer
attests its provenance. Offline templates/simulations can never count as runtime.
"""
from __future__ import annotations
import copy
import datetime as dt
import html
import json
import math
import re
from decimal import Decimal,ROUND_HALF_UP
try:
    from .input_sync import _digest, _approved_feature, _manifest_architecture, validate_artifact_receipt
    from .migration_manifest import validate_manifest
    from .workflow_repairs import extract_workflow_repairs
    from .source_validation import POLICY, POLICY_HASH, POLICY_VERSION, digest as source_digest
except ImportError:
    from input_sync import _digest, _approved_feature, _manifest_architecture, validate_artifact_receipt
    from migration_manifest import validate_manifest
    from workflow_repairs import extract_workflow_repairs
    from source_validation import POLICY, POLICY_HASH, POLICY_VERSION, digest as source_digest

class AcceptanceError(ValueError):pass
ROLE_MEMBERS={'Editor':{'memberId':'GrSnv8AzhaMdab23Tiiaj1xyypHxT','accountType':'build','grant':'edit'},
    'Explorer':{'memberId':'KOvKkJo5cZDfHQ1fPgaNFBBadNrKg','accountType':'build','grant':'explore'},
    'Viewer':{'memberId':'9mGhdRDiXObwlfLUIOc5fO6kwuesg','accountType':'view','grant':'view'}}
WORKFLOW_EXPLANATIONS={
'forecast':'Historical source literals plus live growth/manual/flat drivers feed computed monthly P&L and FY totals. Editable assumptions are distinct from calculated results.',
'research':'Source growth drives forecast Revenue, COGS and revenue-denominator ratios. Forecast gross profit and designated literal cash flows remain source overrides; source Segment Detail audit may legitimately become REVIEW after edits.',
'sales':'Authored opportunity Probability × ACV drives weighted pipeline; closed-stage precedence and both dates normalized to day grain determine timing. Editable rep targets join live weighted totals; stage reference probabilities do not replace authored ones.',
'inventory':'Available = On Hand − Allocated; Usage × Lead Days + Safety Stock determines reorder point. Equality means REORDER. Thirty-day MAX/ROUNDUP order quantity remains exact; Supplier reference values do not override item inputs.',
'expense':'Shared category policy and currency-cent reconciliation precede receipt and approval checks. Approval changes status/timestamp only and cannot erase higher-priority violations. Required Action is live; source-static dashboard expressions remain explicitly static.'}
VALIDATION_INPUT_FEATURE={'forecast':'forecastBusinessInput','research':'researchModelInputs',
    'sales':'salesBusinessInput','inventory':'inventoryBusinessInput','expense':'expenseBusinessInput'}


def _no_secrets(value):
    if isinstance(value,dict):
        for k,v in value.items():
            if re.search(r'^(authorization|cookie|password|token|access_token|refresh_token|client_secret|session_cookie)$',str(k),re.I):
                raise AcceptanceError('secret-bearing evidence key refused')
            _no_secrets(v)
    elif isinstance(value,list):
        for item in value:_no_secrets(item)
    elif isinstance(value,str) and re.search(r'\bBearer\s+\S+|-----BEGIN .*PRIVATE KEY',value):
        raise AcceptanceError('secret-bearing evidence value refused')


def seal_matrix(matrix):
    result=copy.deepcopy(matrix);result.pop('matrixHash',None)
    if result.get('version')!=1 or not result.get('workflows') or not isinstance(result.get('cases'),list):raise AcceptanceError('invalid acceptance matrix')
    ids=[c.get('id') for c in result['cases']]
    if not all(ids) or len(set(ids))!=len(ids):raise AcceptanceError('case identities must be unique')
    _no_secrets(result);result['matrixHash']=_digest(result);return result


def require_full_matrix_scope(matrix):
    """Validate embedded source/plan/receipt contracts on every matrix path."""
    for target in matrix.get('workflows',{}).values():
        contract=target.get('inputContract') or {}
        manifest=contract.get('manifest')
        receipt=contract.get('receipt') or {}
        if manifest is not None:
            validate_artifact_receipt(manifest,receipt)
        elif contract:
            raise AcceptanceError('complete approved input contract required')
        if receipt.get('scope')=='input-tables-only' or receipt.get('status')=='APPROVED_INPUT_STAGING':
            raise AcceptanceError('input-tables-only receipt cannot authorize full acceptance or production')
    return True


def validate_matrix(matrix):
    require_full_matrix_scope(matrix)
    if seal_matrix(matrix)!=matrix:raise AcceptanceError('acceptance matrix hash stale')
    return True


def _bound_inputs(target,manifest,receipt,*,validate_source=False):
    """Exact full assigned architecture, including settings and operation companions."""
    validate_artifact_receipt(manifest,receipt)
    if manifest.get('target')!={'documentId':target.get('documentId'),'version':target.get('version')}:
        raise AcceptanceError('manifest target document/version required')
    for key in ('sourceHash','planHash'):
        if key in target and target[key]!=manifest.get(key):raise AcceptanceError('input inventory source/plan stale')
    inputs=_manifest_architecture(manifest)['inputs'];tables=target.get('inputTables')
    if not inputs or not isinstance(tables,dict) or set(tables)!=set(inputs):
        raise AcceptanceError('input inventory must exactly cover every planned assigned feature')
    elements=set();warehouse=set()
    for feature,spec in inputs.items():
        _,binding,artifact=_approved_feature(manifest,receipt,feature,require_assigned=True)
        table=tables[feature]
        if any(not binding.get(k) or table.get(k)!=binding[k] for k in ('documentId','pageId','elementId')) or table.get('version')!=binding.get('version'):
            raise AcceptanceError('input inventory assigned destination stale/foreign')
        if (table.get('connectionId')!=spec.get('connectionId') or not table.get('connectionId')
                or table.get('targetBindingHash')!=artifact['targetBindingHash']
                or not table.get('identityEvidenceId') or not table.get('tableIdentity')):
            raise AcceptanceError('input inventory actual connection/storage/binding evidence required')
        element=(binding['documentId'],binding['elementId']);storage=(table['connectionId'],table['tableIdentity'])
        if element in elements or storage in warehouse:raise AcceptanceError('duplicate/shared assigned input identity')
        elements.add(element);warehouse.add(storage)
    return tables


def _matrix_inputs(matrix,*,validate_source=False):
    union={}
    for workflow,target in matrix['workflows'].items():
        contract=target.get('inputContract') or {}
        if not contract.get('manifest') or not contract.get('receipt'):raise AcceptanceError('complete approved input contract required')
        tables=_bound_inputs(target,contract['manifest'],contract['receipt'],validate_source=validate_source)
        union.update({workflow+':'+feature:table for feature,table in tables.items()})
    identities=[(t['connectionId'],t['tableIdentity']) for t in union.values()]
    if len(identities)!=len(set(identities)):raise AcceptanceError('shared staging warehouse input identity')
    return union


def _chart_category_value(category):
    if isinstance(category,dt.datetime):
        return {'type':'datetime','value':category.isoformat()}
    if isinstance(category,dt.date):
        return {'type':'date','value':category.isoformat()}
    if isinstance(category,float) and not math.isfinite(category):
        raise AcceptanceError('source chart category must be finite')
    if not isinstance(category,(str,int,float,bool)):
        raise AcceptanceError('source chart category has unsupported type')
    return category


def _source_chart_keys(charts):
    """One unambiguous key for each source chart series/category value."""
    keys=[]
    if len(charts)!=2 or len({chart['id'] for chart in charts})!=2:
        raise AcceptanceError('two distinct source charts required per workflow')
    for chart in charts:
        categories=chart['categories']
        if not categories or any(category is None for category in categories):
            raise AcceptanceError('source chart categories incomplete')
        series=chart['series']
        if not series or len({item['order'] for item in series})!=len(series):
            raise AcceptanceError('source chart series incomplete/duplicate')
        for item in series:
            if not item['name'] or len(item['expectedValues'])!=len(categories):
                raise AcceptanceError('source chart series/category values incomplete')
            for position,category in enumerate(categories):
                keys.append(json.dumps([chart['id'],item['order'],item['name'],position,_chart_category_value(category)],
                                       ensure_ascii=False,separators=(',',':'),allow_nan=False))
    if len(keys)!=len(set(keys)):raise AcceptanceError('source chart keys duplicate')
    return keys


def _reviewed_blank_outcome(review, *, branch_id, rule, source_hash):
    """A separate qualified source decision may set a route outcome.

    Runtime captures cannot supply this decision. Its exact rule, source,
    policy, field, and gesture are rebound during production recomputation.
    """
    if review is None:
        return 'UNRESOLVED_SOURCE_ROUTE'
    if (not isinstance(review, dict) or review.get('status') != 'REVIEWED_QUALIFIED'
            or review.get('branchId') != branch_id or review.get('sourceHash') != source_hash
            or review.get('ruleHash') != rule['sourceXml']['ruleHash']
            or review.get('policyHash') != POLICY_HASH
            or review.get('route') != 'edit-to-empty-commit'
            or review.get('expectedOutcome') not in {'SAVED', 'REJECTED_NO_WRITE'}
            or review.get('basis') not in {'source-runtime', 'qualified-source-contract'}
            or not all(isinstance(review.get(k), str) and review[k].strip()
                       for k in ('reviewer', 'reviewedAt', 'decisionId', 'rationale', 'sourceEvidenceId'))
            or review.get('recordHash') != source_digest({k: v for k, v in review.items() if k != 'recordHash'})):
        raise AcceptanceError('qualified source blank route review missing/stale/foreign')
    return review['expectedOutcome']


def _validation_contract(workflow,source,manifest,receipt,target):
    """Source Excel rules and their required native equivalence classes.

    The target IDs come only from the approved assigned input receipt. A missing
    source rule or column cannot be replaced with a generic successful test.
    """
    feature=VALIDATION_INPUT_FEATURE[workflow]
    binding=receipt['targetBindings'][feature]
    assigned=binding['columnIds']
    spec=_manifest_architecture(manifest)['inputs'][feature]
    table=target['inputTables'][feature]
    columns=[{'name':column['name'],'id':assigned[column['name']],'type':column['type']}
             for column in spec['columns']]
    table_contract={'feature':feature,'documentId':binding['documentId'],'version':binding['version'],
        'pageId':binding['pageId'],'elementId':binding['elementId'],
        'connectionId':table['connectionId'],'tableIdentity':table['tableIdentity'],
        'targetBindingHash':table['targetBindingHash'],'identityEvidenceId':table['identityEvidenceId'],
        'editMode':spec['editMode'],'keyColumns':[assigned[name] for name in spec['keyColumns']],
        'columns':columns,'rowCount':len(spec['rows']),
        'sourceKeys':[[row[name] for name in spec['keyColumns']] for row in spec['rows']]}
    rules=[];branches=[];unresolved_domains=[]
    expected_review_ids=set()
    for rule in source['validations']:
        if workflow=='research':
            match=re.fullmatch(r'C(\d+):C(\d+)',rule['range'])
            if not match:raise AcceptanceError('research validation source range changed')
            fields=['Model Inputs!C'+str(row) for row in range(int(match[1]),int(match[2])+1)]
            names={field:'i_model_inputs_c'+field.split('C')[-1] for field in fields}
        else:
            fields=rule['fields'];names={field:field for field in fields}
        if not fields or any(not assigned.get(names[field]) for field in fields):
            raise AcceptanceError('source validation target column unassigned')
        rule_target={'feature':feature,'elementId':binding['elementId'],
                'columnIds':{field:assigned[names[field]] for field in fields}}
        source_rule={key:copy.deepcopy(rule[key]) for key in ('id','sheet','range','field','fields','sourceType',
            'operator','allowBlank','formula1','formula2','inclusive','status','emission','sourceXml','blankSemantics')}
        if (source_rule['blankSemantics'] != {'version': POLICY_VERSION, 'policyHash': POLICY_HASH,
                'classification': rule['blankSemantics']['classification'], 'applicationRoute': 'UNRESOLVED',
                'storedValue': 'UNRESOLVED'} or rule['sourceXml']['sourceHash'] != manifest['sourceHash']):
            raise AcceptanceError('source blank semantics policy or raw rule stale')
        rules.append({**source_rule,'target':rule_target})
        if rule['status']!='supported' or rule['sourceType'] not in {'list','decimal','whole'}:
            unresolved_domains.append({'ruleId':rule['id'],'sourceType':rule['sourceType'],
                'range':rule['range'],'ruleHash':rule['sourceXml']['ruleHash'],
                'reason':'source nonblank validation domain has no reviewed native coverage'})
        if rule['status']=='supported' and rule['sourceType']=='list':
            formula=rule['formula1']
            if not isinstance(formula,str) or not re.fullmatch(r'"[^"\n]+"',formula):
                raise AcceptanceError('unsupported authored source list')
            values=formula[1:-1].split(',')
            if (not all(values) or '__not_in_source_list__' in values or
                    rule['emission']!={'values':values}):
                raise AcceptanceError('source list and native emission diverge')
            tests=[('valid',{'type':'text','value':values[0]},'SAVED'),
                   ('foreign',{'type':'text','value':'__not_in_source_list__'},'REJECTED_NO_WRITE')]
        elif rule['status']=='supported' and rule['sourceType'] in {'decimal','whole'}:
            if rule['sourceType']=='decimal':
                low=float(Decimal(rule['formula1']));high=float(Decimal(rule['formula2']))
                if rule['emission']!={'range':{'min':low,'max':high}}:
                    raise AcceptanceError('source decimal and native emission diverge')
            else:
                low,high=int(rule['formula1']),int(rule['formula2'])
                if rule['emission']!={'values':list(range(low,high+1))}:
                    raise AcceptanceError('source whole range and native emission diverge')
            if not isinstance(low,(int,float)) or not isinstance(high,(int,float)) or low>=high:
                raise AcceptanceError('invalid source validation bounds')
            tests=[('lower',{'type':'number','value':low},'SAVED'),
                   ('upper',{'type':'number','value':high},'SAVED'),
                   ('below',{'type':'number','value':low-1},'REJECTED_NO_WRITE'),
                   ('above',{'type':'number','value':high+1},'REJECTED_NO_WRITE'),
                   ('text',{'type':'text','value':'not-a-number'},'REJECTED_NO_WRITE')]
            if rule['sourceType']=='whole':
                tests.append(('fractional',{'type':'number','value':low+0.5},'REJECTED_NO_WRITE'))
        else:
            tests=[]  # Preserve the source rule and its blank branch without claiming an unreviewed domain.
        tests.append(('blank',{'type':'null','value':None},'UNRESOLVED_SOURCE_ROUTE'))
        for field in fields:
            for name,attempt,outcome in tests:
                branch_id=rule['id']+'-'+field+'-'+name
                review=(target.get('sourceBlankReviews') or {}).get(branch_id) if name=='blank' else None
                if name=='blank':
                    expected_review_ids.add(branch_id)
                    outcome=_reviewed_blank_outcome(review,branch_id=branch_id,rule=rule,source_hash=manifest['sourceHash'])
                branches.append({'id':branch_id,'ruleId':rule['id'],
                    'target':{'feature':feature,'elementId':binding['elementId'],
                              'columnId':rule_target['columnIds'][field],'sourceField':field},
                    'attempt':copy.deepcopy(attempt),'expectedOutcome':outcome,
                    **({'declaredBlankClass':rule['blankSemantics']['classification'],
                        'sourceRoute':'edit-to-empty-commit', 'sourceReview':copy.deepcopy(review)} if name=='blank' else {})})
    if not rules:raise AcceptanceError('source validation rules missing')
    if set(target.get('sourceBlankReviews') or {}) - expected_review_ids:
        raise AcceptanceError('foreign source blank route review')
    first=branches[0]
    branches.append({'id':'cancel-no-effect','ruleId':first['ruleId'],
        'target':copy.deepcopy(first['target']),'attempt':copy.deepcopy(first['attempt']),
        'expectedOutcome':'CANCELLED_NO_WRITE'})
    return {'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],'blankPolicy':copy.deepcopy(POLICY),
            'blankPolicyHash':POLICY_HASH,'table':table_contract,
            'rules':rules,'branches':branches,'unresolvedDomains':unresolved_domains,
            'expectedOutcomes':[{'id':branch['id'],'outcome':branch['expectedOutcome']} for branch in branches]}


def build_acceptance_matrix(manifests,targets,*,oracles=None,receipts=None):
    if set(manifests)!={'forecast','research','sales','inventory','expense'} or set(targets)!=set(manifests):
        raise AcceptanceError('all five workflows required')
    if not isinstance(receipts,dict) or set(receipts)!=set(manifests):raise AcceptanceError('approved assigned receipts for all five workflows required')
    result={'version':1,'workflows':{},'cases':[],'productionStatus':'BLOCKED'}
    def case(workflow,name,count=1,mode='query',**extra):
        entry={'id':workflow+'-'+name,'workflow':workflow,'count':count,'mode':mode,'mandatory':True,**extra}
        if oracles and entry['id'] in oracles:entry['oracle']=copy.deepcopy(oracles[entry['id']])
        result['cases'].append(entry)
    for workflow,manifest in manifests.items():
        validate_manifest(manifest);target=targets[workflow]
        if not target.get('documentId') or target.get('version') is None or not target.get('url'):raise AcceptanceError('actual staging target/version/URL required')
        _bound_inputs(target,manifest,receipts[workflow])
        contract=extract_workflow_repairs(manifest['source']['path'])
        if contract['workflow']!=workflow:raise AcceptanceError('source workflow mismatch')
        result['workflows'][workflow]={'sourceHash':manifest['sourceHash'],'planHash':manifest['planHash'],
            'sourceFormulaCount':len(contract['formulaCells']),'sourceStatus':target.get('sourceStatus','REVIEW_REQUIRED'),
            'unresolvedSourceFeatures':copy.deepcopy(target.get('unresolvedSourceFeatures',[])),
            'documentId':target['documentId'],'version':target['version'],'url':target['url'],
            'inputTables':copy.deepcopy(target['inputTables']),'inputContract':{'manifest':copy.deepcopy(manifest),'receipt':copy.deepcopy(receipts[workflow])}, 'process':WORKFLOW_EXPLANATIONS[workflow],
            'sourceBlankReviews':copy.deepcopy(target.get('sourceBlankReviews',{})),
            'implementation':copy.deepcopy(target.get('implementation',{'status':'UNRESOLVED_ACTUAL_TARGET_BINDINGS'})),
            'sourceFeatures':{'charts':[{'title':c['title'],'type':c['chartType'],'source':c['sourceLocation']} for c in contract['charts']],
                'validationRules':len(contract['validations']),'conditionalFormatRules':len(contract['conditionalFormats']),
                'formattedSourceCells':len(contract['semanticFormats']),
                'macroBehavior':'scenario/save/snapshot; reviewed allocation/goal/procedure ports' if workflow=='forecast' else 'approval status/timestamp with higher-priority exception preservation' if workflow=='expense' else 'none in source XLSX; native navigation and live inputs'},
            'limitations':['Source accounting/zero-as-dash format sections require qualified visual review; compact SDK captures establish only format/visibility.']}
        case(workflow,'staging-writeback-isolation')
        case(workflow,'formula-accounting',len(contract['formulaCells']))
        count={'forecast':144,'research':420,'sales':48,'inventory':36,'expense':48}[workflow]
        case(workflow,'baseline-values',count)
        for name in ('input-edit-reopen-restore','zero-and-invalid-entry','readonly-formats-and-colors','navigation-layout','full-input-id-audit'):
            extra={'validationContract':_validation_contract(workflow,contract,manifest,receipts[workflow],target)} if name=='zero-and-invalid-entry' else {}
            case(workflow,name,mode='browser' if name in ('zero-and-invalid-entry','readonly-formats-and-colors','navigation-layout') else 'query',
                 persistence=name=='input-edit-reopen-restore',**extra)
        case(workflow,'chart-1-visual',mode='browser');case(workflow,'chart-2-visual',mode='browser')
        chart_keys=_source_chart_keys(contract['charts'])
        case(workflow,'chart-aggregates',len(chart_keys),chartKeys=chart_keys)
        for role,member in ROLE_MEMBERS.items():
            case(workflow,'published-'+role.lower(),mode='browser',role=copy.deepcopy(member),
                 inputMode='published-explore',editEntitlement=role!='Viewer',persistence=role!='Viewer')
    for name,count in [('trend',36),('computed-pnl-fy',234),('scenario-apply',1),('scenario-save-retry-repeat',1),('snapshot-retry-repeat',1),
        ('wrong-context-no-write',1),('python-allocation',4),('python-allocation-failures',6),('goal-solve-single-write',1),
        ('goal-endpoints',2),('goal-bracket-null-zero-nonfinite-iterations',5),('goal-stale-pending-failed-output',3),
        ('procedure-typed-scalar',1),('procedure-raised-timeout-halt',3)]:
        case('forecast',name,count,mode='browser' if any(x in name for x in ('scenario','snapshot','wrong-context','python','goal','procedure')) else 'query',
            operationRequired=any(x in name for x in ('scenario','snapshot','goal','procedure')))
    case('sales','shared-asof-reopen-restore',persistence=True);case('sales','day-boundaries-midnight-noon',8)
    case('sales','editable-rep-targets',4,persistence=True)
    case('inventory','reorder-equality',1);case('inventory','purchase-plan',252);case('inventory','suppliers-reference',4)
    case('expense','policy-reopen-restore',persistence=True);case('expense','cent-boundary',4)
    case('expense','reconciliation',432);case('expense','dashboard-source-static-provenance',8)
    case('expense','approval-update-retry-wrong-row',mode='browser',operationRequired=True)
    case('expense','approval-preserves-higher-priority',mode='browser',operationRequired=True)
    case('expense','selection-zero-one-multiple',3,mode='browser')
    case('research','normalized-live-inputs',145);case('research','source-audit',16)
    for name in ('growth-edit-restored','historical-literal-edit-restored','zero-growth-restored'):
        case('research',name,420,persistence=True)
    return seal_matrix(result)


def compare_value(expected,actual,comparison,*,precision=None):
    if expected is None or actual is None:return expected is None and actual is None
    if comparison in ('money','ratio'):
        if isinstance(expected,bool) or isinstance(actual,bool):return False
        try:
            a,b=Decimal(str(expected)),Decimal(str(actual))
            if not a.is_finite() or not b.is_finite():return False
            if comparison=='money':return a.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)==b.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            if not isinstance(precision,int) or not 0<=precision<=15:return False
            quantum=Decimal(1).scaleb(-precision)
            return a.quantize(quantum,rounding=ROUND_HALF_UP)==b.quantize(quantum,rounding=ROUND_HALF_UP)
        except (ValueError,TypeError,ArithmeticError):return False
    if comparison=='date':
        try:return dt.datetime.fromisoformat(str(expected).replace('Z','+00:00')).date()==dt.datetime.fromisoformat(str(actual).replace('Z','+00:00')).date()
        except (TypeError,ValueError):return False
    if comparison!='exact':raise AcceptanceError('unknown comparison policy')
    return type(expected) is type(actual) and expected==actual


def _index_rows(rows,row_id,key_columns):
    indexed={};keys=set()
    if not isinstance(rows,list):raise AcceptanceError('complete rows required')
    for row in rows:
        rid=row.get(row_id)
        if not key_columns or any(row.get(k) is None for k in key_columns):raise AcceptanceError('complete business keys required')
        key=tuple((type(row.get(k)).__name__,str(row.get(k))) for k in key_columns)
        if not isinstance(rid,str) or not rid or rid in indexed or key in keys:raise AcceptanceError('duplicate/missing row identity')
        indexed[rid]=row;keys.add(key)
    return indexed


def verify_persistence(before,changed,reopened,restored,*,row_id,key_columns,allowed_changes):
    if not allowed_changes:raise AcceptanceError('persistence case requires an actual deliberate edit')
    old=_index_rows(before,row_id,key_columns);new=_index_rows(changed,row_id,key_columns)
    again=_index_rows(reopened,row_id,key_columns);back=_index_rows(restored,row_id,key_columns)
    if set(old)!=set(new) or _digest(new)!=_digest(again) or _digest(old)!=_digest(back):raise AcceptanceError('row identities/reopen/restore mismatch')
    expected=copy.deepcopy(old);policies={}
    for edit in allowed_changes:
        hits=[r for r in expected.values() if all(r.get(k)==v for k,v in edit['key'].items())]
        if len(hits)!=1 or edit['column'] not in hits[0] or edit['column'] in [row_id,*key_columns]:raise AcceptanceError('invalid edit target')
        old_value=hits[0][edit['column']];value=edit['value']
        if (old_value is not None and value is not None and
                ((isinstance(old_value,bool) != isinstance(value,bool)) or
                 (isinstance(old_value,(int,float)) != isinstance(value,(int,float))) or
                 (not isinstance(value,(int,float)) and type(old_value) is not type(value)))):
            raise AcceptanceError('edit value type differs from original business field')
        if isinstance(value,(int,float)) and not math.isfinite(value):raise AcceptanceError('finite edit value required')
        policy=edit.get('comparison','exact');precision=edit.get('precision')
        if not compare_value(edit['value'],edit['value'],policy,precision=precision):raise AcceptanceError('invalid edit comparison/value')
        policies[(hits[0][row_id],edit['column'])]=(policy,precision)
        hits[0][edit['column']]=edit['value']
    if _digest(expected)!=_digest(new):raise AcceptanceError('unexpected input change')
    if not any(not compare_value(old[rid][column],new[rid][column],policy,precision=precision)
            for (rid,column),(policy,precision) in policies.items()):
        raise AcceptanceError('persistence requires an effective saved business edit')
    return True


def assert_isolated_inputs(staging,original):
    def identities(tables):
        if not tables:raise AcceptanceError('nonempty complete input identity inventory required')
        values=[]
        for table in tables.values():
            if not table.get('connectionId') or not table.get('tableIdentity'):raise AcceptanceError('warehouse writeback identity required; element IDs alone do not prove isolation')
            values.append((table['connectionId'],table['tableIdentity']))
        if len(set(values))!=len(values):raise AcceptanceError('duplicate/shared input identity')
        return set(values)
    if identities(staging)&identities(original):raise AcceptanceError('staging shares original writeback identity')
    return True


def published_edit_allowed(entitlement,grant,mode):
    if type(entitlement) is not bool or grant not in {'view','explore','edit'} or mode not in {'draft','published-explore','published-all-users'}:
        raise AcceptanceError('actual entitlement/grant/input mode required')
    return entitlement and (mode=='published-all-users' or (mode=='published-explore' and grant in {'explore','edit'}))


def _same_typed(left,right):
    if isinstance(left,dict) or isinstance(right,dict):
        return isinstance(left,dict) and isinstance(right,dict) and left.keys()==right.keys() and all(
            _same_typed(left[key],right[key]) for key in left)
    if isinstance(left,list) or isinstance(right,list):
        return isinstance(left,list) and isinstance(right,list) and len(left)==len(right) and all(
            _same_typed(a,b) for a,b in zip(left,right))
    if isinstance(left,(int,float)) and not isinstance(left,bool):
        return isinstance(right,(int,float)) and not isinstance(right,bool) and math.isfinite(left) and math.isfinite(right) and left==right
    return type(left) is type(right) and left==right


def _assigned_rows(rows,table,row_id,physical_ids):
    columns={column['id']:column['type'] for column in table['columns']}
    keys=table['keyColumns']
    if not isinstance(rows,list) or len(rows)!=table['rowCount']:
        raise AcceptanceError('complete assigned input row population required')
    indexed=_index_rows(rows,row_id,keys)
    if (physical_ids is not None and set(indexed)!=physical_ids) or any(set(row)!={row_id,*columns} for row in rows):
        raise AcceptanceError('assigned physical IDs and complete schema required')
    actual_keys=[]
    for row in rows:
        actual_keys.append([row[key] for key in keys])
        for column,kind in columns.items():
            value=row[column]
            if value is None:continue
            if kind=='number':valid=isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
            elif kind in {'text','datetime','date'}:valid=isinstance(value,str)
            elif kind=='boolean':valid=type(value) is bool
            else:raise AcceptanceError('unsupported assigned source column type')
            if not valid:raise AcceptanceError('assigned source column value type mismatch')
    if sorted(_digest(key) for key in actual_keys)!=sorted(_digest(key) for key in table['sourceKeys']):
        raise AcceptanceError('assigned source business keys incomplete or foreign')
    return indexed


def _bound_validation_readback(readback,rows,contract,target,row_id,capture,execution_ids):
    table=contract['table'];execution=readback.get('executionId');reference={'kind':'query','id':execution}
    binding={key:table[key] for key in ('documentId','version','pageId','elementId','connectionId',
        'tableIdentity','targetBindingHash','identityEvidenceId')}
    if (not execution or execution in execution_ids or not readback.get('evidenceId') or
            readback.get('origin')!='sigma-query' or readback.get('sourceHash')!=contract['sourceHash'] or
            readback.get('planHash')!=contract['planHash'] or readback.get('binding')!=binding or
            readback.get('rowIdColumn')!=row_id or readback.get('columns')!=table['columns'] or
            readback.get('rowsHash')!=_digest(rows) or reference not in capture.get('references',[]) or
            (readback.get('receipt') or {}).get('status')!='COMPLETED' or
            (readback.get('receipt') or {}).get('executionId')!=execution or
            (readback.get('receipt') or {}).get('evidenceId')!=readback.get('evidenceId') or
            (readback.get('receipt') or {}).get('documentId')!=target['documentId'] or
            (readback.get('receipt') or {}).get('version')!=target['version'] or
            (readback.get('receipt') or {}).get('sourceHash')!=contract['sourceHash'] or
            (readback.get('receipt') or {}).get('planHash')!=contract['planHash'] or
            (readback.get('receipt') or {}).get('binding')!=binding or
            (readback.get('receipt') or {}).get('rowsHash')!=readback.get('rowsHash') or
            (readback.get('receipt') or {}).get('rowIdColumn')!=row_id or
            (readback.get('receipt') or {}).get('columns')!=table['columns']):
        raise AcceptanceError('assigned readback receipt, schema, storage or row reference missing')
    execution_ids.add(execution)


def _validate_validation_capture(case,target,capture):
    contract=case.get('validationContract') or {}
    bound=target.get('inputContract') or {}
    if not bound.get('manifest') or not bound.get('receipt'):
        raise AcceptanceError('source-bound validation input contract required')
    validate_manifest(bound['manifest'])
    _bound_inputs(target,bound['manifest'],bound['receipt'])
    source=extract_workflow_repairs(bound['manifest']['source']['path'])
    if not _same_typed(contract,_validation_contract(case['workflow'],source,bound['manifest'],bound['receipt'],target)):
        raise AcceptanceError('source validation contract changed or foreign')
    if contract.get('unresolvedDomains'):
        raise AcceptanceError('unresolved source validation domain blocks native case admission')
    expected=contract.get('branches') or []
    if any(branch['expectedOutcome']=='UNRESOLVED_SOURCE_ROUTE' for branch in expected):
        raise AcceptanceError('source blank route outcome unresolved; native capture cannot select its own oracle')
    evidence=capture.get('validationBranches')
    if (not isinstance(evidence,list) or len(evidence)!=len(expected) or
            [item.get('id') for item in evidence]!=[item['id'] for item in expected]):
        raise AcceptanceError('complete declared source-validation and Cancel branches required')
    session=capture.get('session') or {};entry=capture.get('dataEntry') or {}
    table=contract['table']
    if (session.get('accountType') not in {'build','admin'} or session.get('editInputTables') is not True or
            entry.get('inputMode')!=table['editMode'] or
            not published_edit_allowed(True,session.get('effectiveGrant'),entry.get('inputMode')) or
            entry.get('editDataAvailable') is not True):
        raise AcceptanceError('native validation requires actual permitted published session')
    execution_ids=set()
    inventory=capture.get('validationInventory') or {}
    inventory_rows=inventory.get('rows');row_id=inventory.get('rowIdColumn')
    if (not isinstance(row_id,str) or not row_id or row_id in {column['id'] for column in table['columns']} or
            not isinstance(inventory_rows,list)):
        raise AcceptanceError('assigned physical row-ID inventory required')
    _bound_validation_readback(inventory,inventory_rows,contract,target,row_id,capture,execution_ids)
    baseline=_assigned_rows(inventory_rows,table,row_id,None)
    physical_ids=set(baseline)
    identity_map=[{'sourceKey':[row[key] for key in table['keyColumns']],'physicalId':row[row_id]}
                  for row in inventory_rows]
    if not _same_typed(inventory.get('physicalIdMap'),identity_map):
        raise AcceptanceError('assigned source-key to physical-ID inventory required')
    for branch,observed in zip(expected,evidence):
        attempt=branch['attempt'];value=attempt['value']
        if (attempt['type']=='number' and (not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value)) or
                attempt['type']=='text' and not isinstance(value,str) or
                attempt['type']=='null' and value is not None):
            raise AcceptanceError('source attempt type invalid')
        if any(not _same_typed(observed.get(key),branch[key]) for key in ('id','ruleId','target','attempt')) or \
                observed.get('observedOutcome')!=branch['expectedOutcome']:
            raise AcceptanceError('source validation branch/target/outcome mismatch')
        if branch['id'].endswith('-blank') and any(
                not _same_typed(observed.get(key),branch[key])
                for key in ('sourceRoute','declaredBlankClass','sourceReview')):
            raise AcceptanceError('blank branch source route/review changed in runtime capture')
        execution_id=observed.get('executionId');receipt=observed.get('receipt') or {}
        reference={'kind':'browser','id':execution_id}
        if (not execution_id or execution_id in execution_ids or observed.get('origin')!='sigma-browser' or
                observed.get('sourceHash')!=target['sourceHash'] or observed.get('planHash')!=target['planHash'] or
                observed.get('publishedVersion')!=target['version'] or not _same_typed(observed.get('session'),session) or
                observed.get('inputMode')!=table['editMode'] or
                not observed.get('steps') or not observed.get('screenshots') or
                reference not in observed.get('references',[]) or reference not in capture['references'] or
                receipt.get('status')!='COMPLETED' or receipt.get('executionId')!=execution_id or
                receipt.get('documentId')!=target['documentId'] or receipt.get('version')!=target['version']):
            raise AcceptanceError('branch actual published runtime/session/receipt required')
        execution_ids.add(execution_id)
        proof=observed.get('rows') or {}
        key_columns=table['keyColumns']
        if proof.get('rowIdColumn')!=row_id or proof.get('keyColumns')!=key_columns:
            raise AcceptanceError('branch physical row/key binding required')
        snapshots=[proof.get(name) for name in ('before','after','reopened','restored')]
        if any(not isinstance(rows,list) or not rows for rows in snapshots):
            raise AcceptanceError('branch complete before/after/reopen/restore rows required')
        readbacks=proof.get('readbacks') or {}
        if set(readbacks)!={'before','after','reopened','restored'}:
            raise AcceptanceError('all assigned phase readbacks required')
        for phase,rows in zip(('before','after','reopened','restored'),snapshots):
            _bound_validation_readback(readbacks[phase],rows,contract,target,row_id,capture,execution_ids)
        before,after,reopened,restored=(_assigned_rows(rows,table,row_id,physical_ids) for rows in snapshots)
        if not _same_typed(before,baseline) or not _same_typed(restored,baseline):
            raise AcceptanceError('source input baseline and restored rows mismatch')
        if branch['expectedOutcome']=='SAVED':
            edits=proof.get('allowedChanges')
            if (type(observed.get('writeCount')) is not int or observed['writeCount']!=1 or
                    not isinstance(edits,list) or len(edits)!=1 or
                    edits[0].get('column')!=branch['target']['columnId'] or
                    not _same_typed(edits[0].get('value'),value) or
                    set(edits[0].get('key',{}))!=set(key_columns)):
                raise AcceptanceError('source-valid branch needs exact typed saved edit')
            ordered=[[indexed[rid] for rid in sorted(physical_ids)]
                     for indexed in (before,after,reopened,restored)]
            verify_persistence(*ordered,row_id=row_id,key_columns=key_columns,allowed_changes=edits)
        elif branch['expectedOutcome'] in {'REJECTED_NO_WRITE','CANCELLED_NO_WRITE'}:
            if (type(observed.get('writeCount')) is not int or observed['writeCount']!=0 or
                    not (_same_typed(before,after) and _same_typed(before,reopened) and _same_typed(before,restored))):
                raise AcceptanceError('invalid/Cancel branch must preserve every physical row')
        else:raise AcceptanceError('unknown declared source-validation outcome')
    oracle=case.get('oracle') or {};checks=oracle.get('checks') or []
    outcomes=contract.get('expectedOutcomes')
    actual=capture.get('actual') or []
    if (len(checks)!=1 or checks[0].get('key')!='source-validation-and-cancel' or
            checks[0].get('comparison')!='exact' or not _same_typed(checks[0].get('expected'),outcomes) or
            len(actual)!=1 or actual[0].get('key')!='source-validation-and-cancel' or
            not _same_typed(actual[0].get('value'),[{'id':item['id'],'outcome':item['observedOutcome']} for item in evidence])):
        raise AcceptanceError('independent source validation oracle/actual vector mismatch')


def _evaluate_capture(matrix,capture):
    _no_secrets(capture)
    cases=[c for c in matrix['cases'] if c['id']==capture.get('caseId')]
    if len(cases)!=1:raise AcceptanceError('unknown evidence case')
    case=cases[0];target=matrix['workflows'][case['workflow']]
    for k in ('sourceHash','planHash','documentId','version'):
        if capture.get(k)!=target[k]:raise AcceptanceError('stale source/plan/target evidence')
    if not capture.get('evidenceId') or not capture.get('executionId') or not capture.get('references'):raise AcceptanceError('actual runtime references required')
    expected_origin='sigma-browser' if case['mode']=='browser' else 'sigma-query'
    if capture.get('origin')!=expected_origin:raise AcceptanceError('actual runtime mode required; templates/local/service substitution refused')
    receipt=capture.get('receipt') or {}
    if (receipt.get('status')!='COMPLETED' or any(receipt.get(k)!=capture.get(k) for k in ('executionId','documentId','version'))):
        raise AcceptanceError('actual execution receipt mismatch')
    if case['mode']=='browser':
        if capture.get('published') is not True or capture.get('publishedVersion')!=target['version'] or not capture.get('steps') or not capture.get('screenshots'):
            raise AcceptanceError('published UI steps/screenshots/version required')
        session=capture.get('session') or {}
        if not session.get('memberId') or not session.get('identityEvidenceId') or session.get('adminBypass') is not False:
            raise AcceptanceError('actual non-bypass session identity required')
        role=case.get('role')
        if role and any(session.get(k)!=v for k,v in [('memberId',role['memberId']),('accountType',role['accountType']),('effectiveGrant',role['grant'])]):
            raise AcceptanceError('role/member/effective inherited grant mismatch')
        if role:
            if session.get('editInputTables') is not case['editEntitlement']:raise AcceptanceError('account data-entry entitlement mismatch')
            entry=capture.get('dataEntry') or {}
            allowed=published_edit_allowed(session['editInputTables'],session['effectiveGrant'],entry.get('inputMode'))
            if entry.get('inputMode')!=case['inputMode'] or entry.get('editDataAvailable') is not allowed:
                raise AcceptanceError('published entry mode/availability mismatch')
            if not allowed and (type(entry.get('writeCount')) is not int or entry['writeCount']!=0):
                raise AcceptanceError('denied role must prove zero writes')
            if allowed and (entry.get('validSaved') is not True or
                    type(entry.get('writeCount')) is not int or entry['writeCount']<1):
                raise AcceptanceError('permitted role requires actual native Save')
    if case['id'].endswith('-zero-and-invalid-entry'):
        _validate_validation_capture(case,target,capture)
    if case['id'].endswith('-staging-writeback-isolation'):
        _matrix_inputs(matrix)
        isolation=capture.get('isolation') or {}
        if not isolation.get('identityEvidenceId') or isolation.get('staging')!=target['inputTables']:raise AcceptanceError('actual full source-bound input identity evidence required')
        assert_isolated_inputs(isolation.get('staging'),isolation.get('original'))
    if case.get('operationRequired') and not capture.get('operationId'):raise AcceptanceError('durable operation identity required')
    if case.get('persistence'):
        p=capture.get('persistence') or {}
        if not p.get('reopenEvidenceId') or not p.get('restoreEvidenceId'):raise AcceptanceError('reopen and restore evidence required')
        verify_persistence(p.get('before'),p.get('changed'),p.get('reopened'),p.get('restored'),
            row_id=p['rowIdColumn'],key_columns=p['keyColumns'],allowed_changes=p['allowedChanges'])
    oracle=case.get('oracle') or {}
    if oracle.get('origin')!='independent-oracle' or not oracle.get('reviewer') or oracle.get('sourceHash')!=target['sourceHash']:
        raise AcceptanceError('named source-bound independent oracle required')
    checks=oracle.get('checks',[]);actual=capture.get('actual',[])
    if len(checks)!=case['count'] or len(actual)!=case['count']:raise AcceptanceError('incomplete evidence/oracle denominator')
    want={c['key']:c for c in checks};got={c['key']:c['value'] for c in actual}
    if len(want)!=len(checks) or len(got)!=len(actual) or set(want)!=set(got):raise AcceptanceError('evidence keys incomplete/duplicate')
    if case['id'].endswith('-chart-aggregates') and set(want)!=set(case.get('chartKeys',[])):
        raise AcceptanceError('chart oracle must cover every source series/category key')
    failures=[k for k,c in want.items() if not compare_value(c['expected'],got[k],c['comparison'],precision=c.get('precision'))]
    return {'status':'FAILED' if failures else 'PASSED','caseId':case['id'],'workflow':case['workflow'],'failures':failures}


def append_evidence(ledger,matrix,capture):
    validate_ledger(matrix,ledger)
    if any(r['capture']['evidenceId']==capture.get('evidenceId') for r in ledger):raise AcceptanceError('duplicate evidence/replay refused')
    result=_evaluate_capture(matrix,capture)
    entry={**result,'sequence':len(ledger),'previousHash':ledger[-1]['recordHash'] if ledger else None,
        'matrixHash':matrix['matrixHash'],'capture':copy.deepcopy(capture)}
    entry['recordHash']=_digest(entry)
    return [*copy.deepcopy(ledger),entry]


def validate_ledger(matrix,ledger):
    validate_matrix(matrix)
    previous=None;ids=set()
    for i,record in enumerate(ledger):
        if (record.get('sequence')!=i or record.get('previousHash')!=previous or record.get('matrixHash')!=matrix['matrixHash']
                or _digest({k:v for k,v in record.items() if k!='recordHash'})!=record.get('recordHash')):
            raise AcceptanceError('append-only evidence chain invalid')
        evaluated=_evaluate_capture(matrix,record['capture'])
        if any(record.get(k)!=v for k,v in evaluated.items()) or record['capture']['evidenceId'] in ids:raise AcceptanceError('evidence result changed/replayed')
        ids.add(record['capture']['evidenceId']);previous=record['recordHash']
    return True


def build_workflow_reports(matrix,ledger,*,final_review=None):
    validate_ledger(matrix,ledger);latest={r['caseId']:r for r in ledger};reports={}
    blockers=[]
    try:validate_production_matrix(matrix)
    except ValueError as error:blockers.append(str(error))
    if any(branch['expectedOutcome']=='UNRESOLVED_SOURCE_ROUTE'
           for case in matrix['cases'] if case['id'].endswith('-zero-and-invalid-entry')
           for branch in (case.get('validationContract') or {}).get('branches',[])):
        blockers.append('source blank edit/clear route remains unresolved')
    final=final_review or {}
    reviewed=(final.get('status')=='APPROVED' and final.get('reviewer') and final.get('matrixHash')==matrix['matrixHash']
              and final.get('ledgerHead')==(ledger[-1]['recordHash'] if ledger else None) and final.get('branchCommit'))
    for workflow,target in matrix['workflows'].items():
        mandatory=[c for c in matrix['cases'] if c['workflow']==workflow and c['mandatory']]
        passed=[c for c in mandatory if latest.get(c['id'],{}).get('status')=='PASSED']
        failed=[c['id'] for c in mandatory if latest.get(c['id'],{}).get('status')=='FAILED']
        unresolved=[c['id'] for c in mandatory if c['id'] not in latest]
        accepted=not blockers and len(passed)==len(mandatory) and target.get('sourceStatus') in {'SUPPORTED','REVIEWED_REPLACEMENT','VERIFIED'} and not target.get('unresolvedSourceFeatures')
        verdict='VERIFIED_COMPLETE' if accepted and reviewed else 'STAGING_ACCEPTANCE_PASSED_REQUIRES_FINAL_REVIEW' if accepted else 'BLOCKED'
        reports[workflow]={'workflow':workflow,'sourceHash':target['sourceHash'],'planHash':target['planHash'],
            'documentId':target['documentId'],'version':target['version'],'url':target['url'],
            'process':target.get('process',WORKFLOW_EXPLANATIONS.get(workflow,'')),'sourceFormulaCount':target['sourceFormulaCount'],
            'sourceFeatures':target.get('sourceFeatures',{}),'implementation':target.get('implementation',{}),'editableInputs':target.get('inputTables',{}),'limitations':target.get('limitations',[]),
            'mandatory':len(mandatory),'passed':len(passed),'failed':failed,'unresolved':unresolved,
            'unresolvedSourceFeatures':target.get('unresolvedSourceFeatures',[]),'verdict':verdict,
            'coverageStatus':'COMPONENT_ONLY' if blockers else 'FULL_MANDATORY_SUITE','completionBlockers':blockers,
            'evidence':[{'case':c['id'],'evidenceId':latest[c['id']]['capture']['evidenceId'],
                'references':latest[c['id']]['capture']['references'],'screenshots':latest[c['id']]['capture'].get('screenshots',[])} for c in passed]}
    return reports


def render_reports_markdown(reports):
    lines=['# Migration acceptance reports','']
    for workflow,r in reports.items():
        lines += ['## '+workflow.title(),'',r['process'],'',f"[{workflow.title()} workbook]({r['url']}) — version {r['version']}",
            '',f"Verdict: **{r['verdict']}**. Passed {r['passed']} of {r['mandatory']} mandatory cases; source formulas accounted: {r['sourceFormulaCount']}.",'']
        lines += ['Source features: '+json.dumps(r.get('sourceFeatures',{}),ensure_ascii=False),'','Editable input bindings: '+json.dumps(r.get('editableInputs',{}),ensure_ascii=False),'','Target implementation: '+json.dumps(r.get('implementation',{}),ensure_ascii=False),'']
        if r.get('completionBlockers'):lines+=['Completion blocked: '+'; '.join(r['completionBlockers']),'']
        if r['failed']:lines+=['Failed: '+', '.join(r['failed']),'']
        if r['unresolved']:lines+=['Unresolved: '+', '.join(r['unresolved']),'']
        for evidence in r['evidence']:lines+=['- '+evidence['case']+': '+evidence['evidenceId']+' — '+json.dumps(evidence['references'],ensure_ascii=False)]
        lines+=['']
    return '\n'.join(lines)


def run_integration(matrix,adapter,scope,*,enabled=False):
    """Explicit controller injection; credentials remain inside the adapter/environment.

    The adapter owns browser/query capture and returns evidence only. This module
    never logs its configuration or turns a service write into a browser result.
    """
    validate_production_matrix(matrix)
    if enabled is not True or scope.get('synthetic') is not True or not scope.get('connectionId') or not scope.get('folderId'):
        raise AcceptanceError('opt-in designated synthetic scope required')
    documents={t['documentId'] for t in matrix['workflows'].values()}
    if set(scope.get('documentIds',[]))!=documents:raise AcceptanceError('integration scope must name exactly the staging documents')
    if not scope.get('identityEvidenceId'):raise AcceptanceError('actual isolation query evidence required')
    if scope.get('stagingInputs')!=_matrix_inputs(matrix):raise AcceptanceError('integration scope must exactly cover the complete assigned input union')
    assert_isolated_inputs(scope.get('stagingInputs'),scope.get('originalInputs'))
    if any(t.get('connectionId')!=scope['connectionId'] for t in scope['stagingInputs'].values()):raise AcceptanceError('integration input connection outside designated scope')
    _no_secrets(scope);ledger=[]
    for case in matrix['cases']:
        request={'case':copy.deepcopy(case),'target':copy.deepcopy(matrix['workflows'][case['workflow']]),'scope':copy.deepcopy(scope)}
        ledger=append_evidence(ledger,matrix,adapter.capture(request))
    return ledger


def validate_production_matrix(matrix):
    """A caller cannot shrink the mandatory suite and then declare completion."""
    validate_matrix(matrix)
    counts={'forecast':278,'research':343,'sales':170,'inventory':442,'expense':632}
    if set(matrix['workflows'])!=set(counts):raise AcceptanceError('production acceptance requires all five workflows')
    common={'staging-writeback-isolation':1,'formula-accounting':None,'baseline-values':None,'input-edit-reopen-restore':1,'zero-and-invalid-entry':1,
        'readonly-formats-and-colors':1,'navigation-layout':1,'full-input-id-audit':1,'chart-1-visual':1,'chart-2-visual':1,'chart-aggregates':None,
        'published-editor':1,'published-explorer':1,'published-viewer':1}
    extra={'forecast':{'trend':36,'computed-pnl-fy':234,'scenario-apply':1,'scenario-save-retry-repeat':1,'snapshot-retry-repeat':1,
        'wrong-context-no-write':1,'python-allocation':4,'python-allocation-failures':6,'goal-solve-single-write':1,'goal-endpoints':2,
        'goal-bracket-null-zero-nonfinite-iterations':5,'goal-stale-pending-failed-output':3,'procedure-typed-scalar':1,'procedure-raised-timeout-halt':3},
        'sales':{'shared-asof-reopen-restore':1,'day-boundaries-midnight-noon':8,'editable-rep-targets':4},
        'inventory':{'reorder-equality':1,'purchase-plan':252,'suppliers-reference':4},
        'expense':{'policy-reopen-restore':1,'cent-boundary':4,'reconciliation':432,'dashboard-source-static-provenance':8,
            'approval-update-retry-wrong-row':1,'approval-preserves-higher-priority':1,'selection-zero-one-multiple':3},
        'research':{'normalized-live-inputs':145,'source-audit':16,'growth-edit-restored':420,'historical-literal-edit-restored':420,'zero-growth-restored':420}}
    _matrix_inputs(matrix,validate_source=True)
    actual={c['id']:c for c in matrix['cases']}
    for workflow,count in counts.items():
        if not matrix['workflows'][workflow].get('inputTables'):raise AcceptanceError('actual staged writeback identities missing')
        if matrix['workflows'][workflow]['sourceFormulaCount']!=count:raise AcceptanceError('source formula denominator changed')
        input_contract=matrix['workflows'][workflow]['inputContract']
        source_contract=extract_workflow_repairs(input_contract['manifest']['source']['path'])
        chart_keys=_source_chart_keys(source_contract['charts'])
        expected={**common,**extra[workflow],'formula-accounting':count,'baseline-values':{'forecast':144,'research':420,'sales':48,'inventory':36,'expense':48}[workflow],
            'chart-aggregates':len(chart_keys)}
        for name,n in expected.items():
            c=actual.get(workflow+'-'+name,{})
            if c.get('count')!=n or c.get('mandatory') is not True or c.get('workflow')!=workflow:raise AcceptanceError('mandatory suite case missing/changed: '+workflow+'-'+name)
            if name=='chart-aggregates' and c.get('chartKeys')!=chart_keys:
                raise AcceptanceError('mandatory source chart series/category keys changed: '+workflow)
            if name=='zero-and-invalid-entry' and not _same_typed(c.get('validationContract'),_validation_contract(
                    workflow,source_contract,input_contract['manifest'],input_contract['receipt'],matrix['workflows'][workflow])):
                raise AcceptanceError('mandatory declared source validation/Cancel coverage changed: '+workflow)
            if name=='zero-and-invalid-entry' and c['validationContract'].get('unresolvedDomains'):
                raise AcceptanceError('unresolved source validation domain blocks production: '+workflow)
            browser=name in {'zero-and-invalid-entry','readonly-formats-and-colors','navigation-layout','chart-1-visual','chart-2-visual'} or name.startswith('published-') or (workflow=='forecast' and any(x in name for x in ('scenario','snapshot','wrong-context','python','goal','procedure'))) or name.startswith('approval-') or name=='selection-zero-one-multiple'
            if c.get('mode')!=('browser' if browser else 'query'):raise AcceptanceError('mandatory runtime mode changed')
            if name.startswith('published-'):
                role=name.split('-')[1].title()
                if c.get('role')!=ROLE_MEMBERS[role] or c.get('inputMode')!='published-explore' or c.get('editEntitlement') is not (role!='Viewer'):
                    raise AcceptanceError('mandatory role contract changed')
            persistent=name in {'input-edit-reopen-restore','shared-asof-reopen-restore','editable-rep-targets','policy-reopen-restore','growth-edit-restored','historical-literal-edit-restored','zero-growth-restored','published-editor','published-explorer'}
            if persistent and c.get('persistence') is not True:raise AcceptanceError('mandatory persistence proof removed')
            operation=workflow=='forecast' and any(x in name for x in ('scenario','snapshot','goal','procedure')) or name.startswith('approval-')
            if operation and c.get('operationRequired') is not True:raise AcceptanceError('mandatory durable operation proof removed')
    return True
