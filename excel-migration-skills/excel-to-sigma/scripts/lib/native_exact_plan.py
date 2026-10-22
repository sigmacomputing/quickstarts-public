"""Offline exact native candidates, bounded helper graph and construction receipts.

No function in this module calls a target. Source types, errors, and unresolved
bindings remain separate. REST formula text is used after scaffold readback so
SDK expression export cannot silently drop nested arithmetic parentheses.
"""
from __future__ import annotations
from dataclasses import replace
import copy
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
try:
    from .native_exact import (Scalar, Literal, Vector, compile_expression, evaluate_bound,
        q, iff, both, either, eq, ne, first_error, criteria, criterion_spec, Fault, EMPTY, lane_dict, can_be_boolean)
    from .excel_expression import UnsupportedExpression, ExcelCalcError
    from .workbook_expression import WorkbookContext
    from .source_inputs import validate_source_input_plan
except ImportError:
    from native_exact import (Scalar, Literal, Vector, compile_expression, evaluate_bound,
        q, iff, both, either, eq, ne, first_error, criteria, criterion_spec, Fault, EMPTY, lane_dict, can_be_boolean)
    from excel_expression import UnsupportedExpression, ExcelCalcError
    from workbook_expression import WorkbookContext
    from source_inputs import validate_source_input_plan


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def _map_helpers(formula,prefix,callback):
    """Internal bare tokens cannot collide with source text or column names."""
    parts=[];start=0;i=0
    while i<len(formula):
        if formula[i] in ('"','['):
            if start<i:parts.append(re.sub(re.escape(prefix)+r'\d+__',callback,formula[start:i]))
            end='"' if formula[i]=='"' else ']';j=i+1
            while j<len(formula):
                if end=='"' and formula[j]=='\\':j+=2;continue
                if formula[j]==end:j+=1;break
                j+=1
            parts.append(formula[i:j]);i=j;start=j
        else:i+=1
    parts.append(re.sub(re.escape(prefix)+r'\d+__',callback,formula[start:]))
    return ''.join(parts)

def _helper_tokens(formula,prefix):
    tokens=[]
    def record(match):tokens.append(match.group());return match.group()
    _map_helpers(formula,prefix,record)
    return set(tokens)


def _formula_result(value):
    """Excel scalar formula results turn a successful blank into numeric zero."""
    if isinstance(value,Vector):return value
    blank=both(eq(value.kind,'"z"'),eq(value.error,EMPTY))
    return replace(value,number=iff(blank,'0',value.number),kind=iff(blank,'"n"',value.kind))


def build_exact_native_calculation_plan(source_path,source_input_plan=None):
    try:from .native_calculations import _ast,_input_bindings,_replacement_external_inputs,_symbol
    except ImportError:from native_calculations import _ast,_input_bindings,_replacement_external_inputs,_symbol
    path=Path(source_path);source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    if source_input_plan is not None:validate_source_input_plan(source_input_plan,path)
    external,provenance=_replacement_external_inputs(source_input_plan)
    context=WorkbookContext.from_path(path,external_inputs=external)
    epoch='1904' if context.workbook.epoch.year==1904 else '1900'
    bindings=_input_bindings(source_input_plan) if source_input_plan else {}
    records={};active=[];local_memo={}
    source_formulas={f'{s}!{a}':f for (s,a),f in context.formulas.items()}
    for cell,formula in sorted(source_formulas.items()):
        record={'sourceCellId':cell,'originalFormula':str(formula),'formulaSha256':hashlib.sha256(str(formula).encode()).hexdigest(),
                'columnId':_symbol(cell),'status':'unresolved','reason':None,'dependencies':[],
                'layer':None,'ast':None,'runtimeStatus':'UNVERIFIED_CANDIDATE'}
        if bindings.get(cell,{}).get('kind')=='input':record['status']='reviewed-replacement-input'
        else:
            try:
                s,a=cell.rsplit('!',1);bound=context.bind_formula(formula,sheet=s,address=a)
                record['ast']=_ast(bound);record['astHash']=digest(record['ast'])
                deps,domains,complete=context._bound_evidence(bound)
                record['dependencies']=deps;record['bindingEvidence']=domains
                if not complete:raise UnsupportedExpression('incomplete dynamic or whole-column dependency domain')
            except (UnsupportedExpression,ValueError,TypeError) as error:record['reason']=str(error)
        records[cell]=record
    def source_value(cell):
        if cell in local_memo:return local_memo[cell]
        if cell in active:raise UnsupportedExpression('formula dependency cycle: '+' -> '.join(active+[cell]))
        if cell in source_formulas and records[cell]['status']!='reviewed-replacement-input':
            if not records[cell]['ast']:raise UnsupportedExpression(records[cell]['reason'] or 'unbound source AST')
            active.append(cell)
            try:value=evaluate_bound(records[cell]['ast'],source_value,epoch=epoch)
            except ExcelCalcError as error:value=Fault(error.code)
            finally:active.pop()
            if value is None:value=0
        else:
            s,a=cell.rsplit('!',1);value=context.literals.get((s,a))
            source=context.workbook[s][a]
            if source.data_type=='e':value=Fault(source.value)
            elif (s,a) in context.formulas:
                binding=bindings[cell];value=source_input_plan['sharedInputArchitecture']['inputs'][binding['featureId']]['rows'][binding['rowIndex']][binding['column']]
            else:value=context._normal_value(value)
        local_memo[cell]=value;return value
    planning={};visiting=[]
    def check(cell):
        record=records[cell]
        if cell in planning:return planning[cell]
        if cell in visiting:raise UnsupportedExpression('formula dependency cycle: '+' -> '.join(visiting+[cell]))
        if record['status']=='reviewed-replacement-input':return input_scalar(cell,bindings,lambda b:'[input]')
        if not record['ast']:raise UnsupportedExpression(record['reason'] or 'unbound AST')
        visiting.append(cell);depths=[]
        def resolve(c):
            if c in records:
                v=check(c);depths.append(records[c]['layer'] or 0)
                return replace(v,number='[number]',text='[text]',logical='[logical]',kind='[kind]',error='[error]')
            return input_scalar(c,bindings,lambda b:'[input]')
        try:
            # The helper callback avoids exponential inlining during eligibility.
            value=compile_expression(record['ast'],resolve,emit=lambda f:'[helper]',epoch=epoch)
            if isinstance(value,Vector):raise UnsupportedExpression('non-scalar source result requires array port')
            value=_formula_result(value)
            expected=source_value(cell)
            record['localExpected']=None if isinstance(expected,Fault) else expected
            record['sourceResultClass']='excel-error' if isinstance(expected,Fault) else 'blank' if expected is None else 'logical' if type(expected)is bool else 'text' if isinstance(expected,str) else 'number'
            if isinstance(expected,Fault):record['localExpectedError']=expected.code
            record['status']='ready-to-bind';record['reason']=None;record['layer']=max(depths,default=-1)+1
            planning[cell]=value;return value
        except (UnsupportedExpression,ValueError,TypeError,ArithmeticError) as error:
            record['reason']=str(error);record['status']='unresolved';raise UnsupportedExpression(str(error))
        finally:visiting.pop()
    for cell,record in records.items():
        if record['status']=='reviewed-replacement-input':continue
        try:check(cell)
        except UnsupportedExpression:pass
    logical={'nativePlanVersion':2,'sourceSha256':source_hash,'sourcePath':str(path.resolve()),'dateEpoch':epoch,
             'inputPlanHash':source_input_plan['inputPlanHash'] if source_input_plan else None,
             'targetScope':source_input_plan['sharedInputArchitecture']['targetScope'] if source_input_plan else None,
             'formulaCount':len(records),'bindings':bindings,'replacementExternalBindings':provenance,
             'formulas':records,'status':'SOURCE_BOUND_PENDING_STAGING',
             'semantics':'typed-number-text-logical-blank-and-excel-error-v2'}
    return {**logical,'nativePlanHash':digest(logical)}


def input_scalar(cell,bindings,lookup):
    b=bindings.get(cell)
    if not b:raise UnsupportedExpression(f'unmapped source literal {cell}')
    if b['kind']!='input':raise UnsupportedExpression(f'ambiguous source input {cell}')
    value=lookup(b);kind=b['valueType']
    nullable=iff(f'IsNull({value})','"z"',{'number':'"n"','text':'"t"','boolean':'"b"','logical':'"b"','date':'"n"','datetime':'"n"'}.get(kind,'"n"'))
    if kind=='number':return Scalar(number=f'Coalesce({value}, 0)',kind=nullable)
    if kind=='text':return Scalar(text=f'Coalesce({value}, "")',kind=nullable)
    if kind in ('boolean','logical'):return Scalar(logical=f'Coalesce({value}, False)',kind=nullable,may_be_boolean=True)
    if kind in ('date','datetime'):
        # Source input dates are date-only civil dates; the epoch is adjusted by
        # caller for 1904 sources. Time-zone validation remains a runtime gate.
        serial=f'((DateDiff("second", Date("1899-12-31"), {value}) / 86400) + If({value} >= Date("1900-03-01"), 1, 0))'
        return Scalar(number=iff(f'IsNull({value})','0',serial),kind=nullable)
    raise UnsupportedExpression(f'unqualified input type {kind} for {cell}')


class HelperGraph:
    def __init__(self,max_formula_length=1200,prefix="__native_h"):self.nodes=[];self.index={};self.max_formula_length=max_formula_length;self.prefix=prefix
    def emit(self,formula):
        if formula in self.index:return self.index[formula]
        while len(formula)>self.max_formula_length:
            # Split only complete parenthesized expressions/function calls;
            # quoted text and column names are opaque. This bounds both source
            # strings and their longer assigned-name/row lookup substitution.
            stack=[];candidates=[];quote=None;bracket=False;i=0
            while i<len(formula):
                ch=formula[i]
                if quote:
                    if ch=='\\':i+=1
                    elif ch==quote:quote=None
                elif ch=='"':quote=ch
                elif ch=='[':bracket=True
                elif ch==']':bracket=False
                elif not bracket and ch=='(':
                    start=i
                    while start>0 and (formula[start-1].isalpha() or formula[start-1]=='_'):start-=1
                    stack.append(start)
                elif not bracket and ch==')' and stack:
                    start=stack.pop()
                    if 100<=i+1-start<self.max_formula_length and not(start==0 and i+1==len(formula)):candidates.append((start,i+1))
                i+=1
            if not candidates:
                # A flat parenthesized addition/AND/OR can have many small
                # leaves without an individually large child expression.
                matches=[];level=0;quote=None;in_ref=False;j=0
                while j<len(formula):
                    ch=formula[j]
                    if quote:
                        if ch=='\\':j+=1
                        elif ch==quote:quote=None
                    elif ch=='"':quote=ch
                    elif ch=='[':in_ref=True
                    elif ch==']':in_ref=False
                    elif not in_ref and ch=='(':level+=1
                    elif not in_ref and ch==')':level-=1
                    elif not in_ref and level==1:
                        for op in (' + ',' or ',' and '):
                            if formula.startswith(op,j):matches.append((j,op))
                    j+=1
                if not matches and formula.startswith('((') and formula.endswith('))'):
                    formula=formula[1:-1];continue
                if not matches or not(formula.startswith('(') and formula.endswith(')')):
                    raise UnsupportedExpression(f'native helper formula cannot be split below {self.max_formula_length} characters')
                middle,op=min(matches,key=lambda p:abs(p[0]-len(formula)//2))
                left=self.emit('('+formula[1:middle]+')');right=self.emit('('+formula[middle+len(op):-1]+')')
                formula='('+left+op+right+')';continue

            start,end=max(candidates,key=lambda p:p[1]-p[0]);token=self.emit(formula[start:end]);formula=formula[:start]+token+formula[end:]

        token=f'{self.prefix}{len(self.nodes)}__';deps=[int(x[len(self.prefix):-2]) for x in _helper_tokens(formula,self.prefix)]
        depth=max((self.nodes[d]['depth'] for d in deps),default=-1)+1
        self.nodes.append({'token':token,'formula':formula,'depth':depth});self.index[formula]=token;return token


def lower_exact_native_calculations(plan,assigned_rows,*,max_columns=64):
    if plan.get('nativePlanVersion')!=2 or digest({k:v for k,v in plan.items() if k!='nativePlanHash'})!=plan.get('nativePlanHash'):raise ValueError('native plan hash is stale')
    if not plan.get('targetScope',{}).get('connectionId'):raise ValueError('reviewed input target scope is required')
    if not 6<=max_columns<=64:raise ValueError('exact native shard limit must be between 6 and 64')
    graph=HelperGraph();outputs={};aggregate_elements=[];aggregate_index={}
    bindings=plan['bindings']
    for b in bindings.values():
        if b['kind']!='input':continue
        a=assigned_rows.get(b['featureId'],{})
        if not a.get('elementId') or not a.get('name') or not a.get('rowIdColumn') or not a.get('rows',{}).get(str(b['rowIndex'])):raise ValueError('actual assigned row ID is required')
    for feature in {b['featureId'] for b in bindings.values() if b['kind']=='input'}:
        rows=assigned_rows[feature]['rows']
        if len(set(rows.values()))!=len(rows):raise ValueError('actual assigned row IDs must be unique within each input table')
    def epoch_value(value,b):
        return replace(value,number=iff(eq(value.kind,'"z"'),'0',f'({value.number} - 1462)')) if plan['dateEpoch']=='1904' and b['valueType'] in ('date','datetime') else value
    def lookup(b):
        a=assigned_rows[b['featureId']]
        return f'Lookup([{a["name"]}/{b["column"]}], {q(a["rows"][str(b["rowIndex"])])}, [{a["name"]}/{a["rowIdColumn"]}])'
    def resolve(cell):
        if cell in outputs:return outputs[cell]
        return epoch_value(input_scalar(cell,bindings,lookup),bindings[cell])
    # Lift complete formal calculated columns to ordinary row formulas. A
    # template is accepted only when EVERY source row emits the same symbolic
    # expression with its own input fields substituted. Historical literal
    # overrides/absolute anchors therefore cannot become inferred row formulas.
    source_context=WorkbookContext.from_path(plan['sourcePath'])
    row_columns={};row_active=set();row_descriptors={}
    def row_column(cell):
        if cell in row_descriptors:return row_descriptors[cell]
        sheet,address=cell.rsplit('!',1);col=re.match(r'[A-Z]+',address).group();row=int(re.search(r'\d+$',address).group())
        table=next((t for t in source_context.tables.values() if t.sheet==sheet and t.body_first<=row<=t.body_last and t.first_col<=__import__('openpyxl').utils.cell.column_index_from_string(col)<=t.last_col),None)
        if table is None:return None
        identity=(sheet,table.name,col)
        if identity in row_active:return None
        row_active.add(identity)
        cells=[f'{sheet}!{col}{r}' for r in range(table.body_first,table.body_last+1)]
        if any(c not in plan['formulas'] or plan['formulas'][c]['status']!='ready-to-bind' for c in cells):row_active.remove(identity);return None
        feature=None;indices=[];compiled=[];first_graph=None
        for c in cells:
            rr=int(re.search(r'\d+$',c).group());candidates=[b for source,b in bindings.items() if source.startswith(sheet+'!') and re.search(r'\d+$',source).group()==str(rr) and b['kind']=='input']
            features={b['featureId'] for b in candidates}
            if len(features)!=1:row_active.remove(identity);return None
            f=next(iter(features));row_indices={b['rowIndex'] for b in candidates}
            if len(row_indices)!=1 or feature is not None and f!=feature:row_active.remove(identity);return None
            feature=f;indices.append(next(iter(row_indices)));a=assigned_rows[f];rg=HelperGraph(prefix='__native_r')
            def relative(target):
                target_sheet,target_address=target.rsplit('!',1)
                same_row=target_sheet==sheet and re.search(r'\d+$',target_address).group()==str(rr)
                if same_row and target in bindings and bindings[target]['kind']=='input' and bindings[target]['featureId']==feature:
                    return epoch_value(input_scalar(target,bindings,lambda b:f'[{a["name"]}/{b["column"]}]'),bindings[target])
                if same_row and target in plan['formulas']:
                    desc=row_column(target)
                    if desc is None:raise UnsupportedExpression('formal calculated-column dependency is not a row template')
                    return desc['scalar']
                return resolve(target)
            try:value=_formula_result(compile_expression(plan['formulas'][c]['ast'],relative,emit=rg.emit,epoch=plan['dateEpoch']))
            except UnsupportedExpression:row_active.remove(identity);return None
            signature=([n['formula'] for n in rg.nodes],lane_dict(value),can_be_boolean(value))
            if compiled and signature!=compiled[0]:row_active.remove(identity);return None
            compiled.append(signature);first_graph=rg
        a=assigned_rows[feature];prefix='Native Rows '+digest(identity)[:10];row_handles={};new=[]
        def row_formula(formula):
            return _map_helpers(formula,'__native_r',lambda m:row_handles[m.group()])
        for start in range(0,len(first_graph.nodes),max_columns-1):
            batch=first_graph.nodes[start:start+max_columns-1];name=prefix+' '+str(len(new)+1);columns=[{'id':'native_row_id','name':'native_row_id','formula':f'[{a["name"]}/{a["rowIdColumn"]}]'}]
            for i,node in enumerate(batch,start):
                columns.append({'id':f'r{i}','name':f'r{i}','formula':row_formula(node['formula'])})
                row_handles[node['token']]=f'Lookup([{name}/r{i}], [{a["name"]}/{a["rowIdColumn"]}], [{name}/native_row_id])'
            new.append({'id':'native_rows_'+digest((identity,start))[:16],'kind':'table','name':name,'source':{'kind':'table','elementId':a['elementId']},'columns':columns,'sourceFormulaCells':[]})
        final_name=prefix+' Results';columns=[{'id':'native_row_id','name':'native_row_id','formula':f'[{a["name"]}/{a["rowIdColumn"]}]'}]
        lanes={}
        for lane,formula in compiled[0][1].items():
            columns.append({'id':lane,'name':lane,'formula':row_formula(formula)})
            lanes[lane]=f'Lookup([{final_name}/{lane}], [{a["name"]}/{a["rowIdColumn"]}], [{final_name}/native_row_id])'
        new.append({'id':'native_rows_'+digest(identity)[:16],'kind':'table','name':final_name,'source':{'kind':'table','elementId':a['elementId']},'columns':columns,'sourceFormulaCells':[],
                    'calculatedColumnDomain':{'sourceCells':cells,'sourceTable':table.name,'appendPolicy':'live-formal-table'}})
        aggregate_elements.extend(new)
        desc={'featureId':feature,'column':col,'valueType':'number','scalar':Scalar(**lanes,may_be_boolean=compiled[0][2]),'rows':dict(zip(cells,indices))}
        for c in cells:row_descriptors[c]=desc
        row_active.remove(identity);return desc
    def aggregate(node,run):
        # Aligned ordinary-input columns become one row predicate + aggregate
        # lookup instead of N scalar expressions per source row. Explicit
        # finite ranges filter observed physical IDs; formal table data bodies
        # include future input rows and therefore preserve append behavior.
        name,args=node['name'],node['arguments']
        if name not in ('SUMIFS','COUNTIFS','SUM','COUNT','COUNTA'):return None
        if name in ('SUMIFS','COUNTIFS'):
            off=int(name=='SUMIFS');range_nodes=args[:1]+args[1::2] if off else args[::2]
            criterion_nodes=args[off+1::2]
        else:
            if len(args)!=1:return None
            range_nodes=args;criterion_nodes=[]
        if any(n.get('kind')!='range' or not n.get('cells') for n in range_nodes):return None
        maps=[]
        if name in ('SUMIFS','SUM'):
            # A typed text summand never contributes, even when its criteria
            # match; dropping such header positions does not freeze its label.
            keep=[i for i,c in enumerate(range_nodes[0]['cells']) if not(bindings.get(c,{}).get('kind')=='input' and bindings[c]['valueType'] in ('text','boolean','logical'))]
            if len(keep)!=len(range_nodes[0]['cells']):
                range_nodes=[{**n,'cells':[n['cells'][i] for i in keep]} for n in range_nodes]
        for n in range_nodes:
            bs=[bindings.get(c) for c in n['cells']]
            if any(not b or b['kind']!='input' for b in bs):
                desc=row_column(n['cells'][0])
                if not desc or any(row_descriptors.get(c) is not desc for c in n['cells']):return None
                bs=[{**desc,'kind':'row-formula','rowIndex':desc['rows'][c]} for c in n['cells']]
            if len({(b['featureId'],b['column'],b['valueType']) for b in bs})!=1:return None
            # One physical row predicate cannot represent repeated source
            # positions. Preserve those through the scalar compiler instead.
            if len({b['rowIndex'] for b in bs})!=len(bs):return None
            maps.append(bs)
        if len({bs[0]['featureId'] for bs in maps})!=1:return None
        if any([b['rowIndex'] for b in bs]!=[b['rowIndex'] for b in maps[0]] for bs in maps):return None
        feature=maps[0][0]['featureId'];a=assigned_rows[feature]
        identity=digest(node)
        if identity in aggregate_index:return aggregate_index[identity]
        prefix='Native Range '+str(len(aggregate_elements)+1)
        element={'id':'native_range_'+identity[:16],'kind':'table','name':prefix,
                 'source':{'kind':'table','elementId':a['elementId']},'columns':[],
                 'sourceFormulaCells':[],'rangeDomain':{'cells':[n['cells'] for n in range_nodes],
                 'appendPolicy':'live-formal-table' if all((n['sourceKind'].startswith('table:') or n['sourceKind'].startswith('structured:') or n['sourceKind']=='whole_column') and '#this row' not in n['sourceKind'] for n in range_nodes) else 'observed-physical-rows'}}
        all_formal=element['rangeDomain']['appendPolicy']=='live-formal-table'
        included='True' if all_formal else '('+' or '.join(f'([{a["name"]}/{a["rowIdColumn"]}] = {q(a["rows"][str(b["rowIndex"])])})' for b in maps[0])+')'
        # Large explicit domains use bounded helpers; do not emit giant IN text.
        if len(included)>2000:return None
        conditions=[included];errors=[];row_graph=HelperGraph(prefix="__native_r")
        def row_emit(formula):
            if len(formula)<20:return formula
            return row_graph.emit(formula)
        for bs,cn in zip(maps[int(name=='SUMIFS'):],criterion_nodes):
            row=bs[0]['scalar'] if bs[0]['kind']=='row-formula' else epoch_value(input_scalar('_row',{'_row':bs[0]},lambda b:f'[{a["name"]}/{b["column"]}]'),bs[0])
            condition,error=criteria(row,criterion_spec(cn,run),emit=row_emit);conditions.append(condition);errors.append(error)
        typed_count=name in ('COUNT','COUNTA') and maps[0][0]['kind']=='row-formula'
        if typed_count:
            # Numeric lanes also hold placeholders for text/logical/error
            # results. Count the typed result, including future formal rows.
            row=maps[0][0]['scalar']
            conditions.append(both(eq(row.kind,'"n"'),eq(row.error,EMPTY)) if name=='COUNT'
                              else either(ne(row.kind,'"z"'),ne(row.error,EMPTY)))
        cond=row_emit(both(*conditions))
        summand=maps[0][0].get('scalar') if name in ('SUMIFS','SUM') else None
        needs_row_error=any(bs[0]['kind']=='row-formula' for bs in maps)
        # Criteria errors propagate for every requested row, even when its
        # predicate does not match, but never from rows outside a finite range.
        row_error=iff(included,first_error(*errors,iff(cond,summand.error,EMPTY) if summand else EMPTY),EMPTY) if needs_row_error else EMPTY
        row_error=row_emit(row_error)
        order='0'
        if needs_row_error:
            order=str(len(maps[0])+1)
            for ordinal,b in reversed(list(enumerate(maps[0],1))):
                order=row_emit(iff(f'([{a["name"]}/{a["rowIdColumn"]}] = {q(a["rows"][str(b["rowIndex"])])})',str(ordinal),order))
        row_handles={};row_nodes=[]
        def materialize_rows(formula):
            return _map_helpers(formula,'__native_r',lambda m:row_handles[m.group()])
        for start in range(0,len(row_graph.nodes),max_columns-1):
            batch=row_graph.nodes[start:start+max_columns-1];helper_name=prefix+' Criteria '+str(start//(max_columns-1)+1)
            columns=[{'id':'native_row_id','name':'native_row_id','formula':f'[{a["name"]}/{a["rowIdColumn"]}]'}]
            for i,node in enumerate(batch,start):
                columns.append({'id':f'r{i}','name':f'r{i}','formula':materialize_rows(node['formula'])})
                row_handles[node['token']]='[r'+str(i)+']'
            aggregate_elements.append({'id':'native_criteria_'+identity[:12]+'_'+str(start),'kind':'table','name':helper_name,'source':{'kind':'table','elementId':a['elementId']},'columns':columns,'sourceFormulaCells':[]})
            for i,node in enumerate(batch,start):row_handles[node['token']]=f'Lookup([{helper_name}/r{i}], [{a["name"]}/{a["rowIdColumn"]}], [{helper_name}/native_row_id])'
        cond=materialize_rows(cond)
        element['columns']=[{'id':'native_key','name':'native_key','formula':'1'},
                            {'id':'native_match','name':'native_match','formula':cond},
                            {'id':'native_error','name':'native_error','formula':materialize_rows(row_error)},
                            {'id':'native_order','name':'native_order','formula':materialize_rows(order)}]
        result_field=maps[0][0]['column'];typ=maps[0][0]['valueType']
        if name in ('SUMIFS','SUM'):
            if typ not in ('number','date','datetime'):return None
            if maps[0][0]['kind']=='row-formula':summand_formula=maps[0][0]['scalar'].number
            elif typ in ('date','datetime'):
                raw=epoch_value(input_scalar('_row',{'_row':maps[0][0]},lambda b:f'[{a["name"]}/{b["column"]}]'),maps[0][0])
                summand_formula=iff(eq(raw.kind,'"n"'),raw.number,'0')
            else:summand_formula=f'[{a["name"]}/{result_field}]'
            element['columns'].append({'id':'native_value','name':'native_value','formula':summand_formula})
            expression=f'Coalesce(Lookup(SumIf([{prefix}/native_value], [{prefix}/native_match]), 1, [{prefix}/native_key]), 0)'
        else:
            condition=f'[{prefix}/native_match]'
            if name in ('COUNT','COUNTA') and not typed_count:
                # A source column can share a reserved helper name. Keep the
                # copied value distinct from both generated and source columns.
                occupied={b['column'] for b in bindings.values() if b.get('featureId')==feature}
                occupied.update(c[k] for c in element['columns'] for k in ('id','name'))
                occupied.add(a['rowIdColumn'])
                count_field='native_count_value';suffix=0
                while count_field in occupied:
                    suffix+=1;count_field=f'native_count_value_{suffix}'
                element['columns'].append({'id':count_field,'name':count_field,'formula':f'[{a["name"]}/{result_field}]'})
                present=f'Not(IsNull([{prefix}/{count_field}]))'
                condition=both(condition,'False' if name=='COUNT' and typ not in ('number','date','datetime') else present)
            expression=f'Coalesce(Lookup(CountIf({condition}), 1, [{prefix}/native_key]), 0)'
        error_formula=f'Coalesce(Lookup([{prefix}/native_error], Lookup(MinIf([{prefix}/native_order], [{prefix}/native_error] != ""), 1, [{prefix}/native_key]), [{prefix}/native_order]), "")'
        value=Scalar(number=graph.emit(expression),error=graph.emit(error_formula) if needs_row_error else first_error(*errors))
        element['rangeDomain']['appendErrorOrderRequiresReviewedOrdinal']=needs_row_error
        aggregate_elements.append(element);aggregate_index[identity]=value;return value
    expression_cache={}
    for cell,r in sorted(plan['formulas'].items(),key=lambda kv:(kv[1].get('layer') or 0,kv[0])):
        if r['status']!='ready-to-bind':continue
        value=_formula_result(compile_expression(r['ast'],resolve,emit=graph.emit,aggregate=aggregate,epoch=plan['dateEpoch'],expression_cache=expression_cache))
        outputs[cell]=value
    formal_obligations=[]
    for cell in outputs:
        desc=row_column(cell)
        s,addr=cell.rsplit('!',1);rr=int(re.search(r'\d+$',addr).group());cc=__import__('openpyxl').utils.cell.column_index_from_string(re.match(r'[A-Z]+',addr).group())
        if desc is None and any(t.sheet==s and t.body_first<=rr<=t.body_last and t.first_col<=cc<=t.last_col for t in source_context.tables.values()):formal_obligations.append(cell)
    # External ordinary row tables participate in the same source DAG. Their
    # dependencies must affect scalar packing, otherwise independent-looking
    # scalar nodes can share a shard with a row table's own prerequisite.
    external_by_name={e['name']:e for e in aggregate_elements}
    dependency_edges={};node_depths={};node_active=set()
    def dependencies(formula):
        edges=_helper_tokens(formula,'__native_h')
        for name in re.findall(r'\[([^\[\]/]+)/[^\[\]]+\]',formula):
            if name in external_by_name:edges.add(external_by_name[name]['id'])
        return edges
    for node in graph.nodes:dependency_edges[node['token']]=dependencies(node['formula'])
    for element in aggregate_elements:
        dependency_edges[element['id']]=set().union(*(dependencies(c['formula']) for c in element['columns']))-{element['id']}
    def depth_of(vertex):
        if vertex in node_depths:return node_depths[vertex]
        if vertex in node_active:raise UnsupportedExpression('native source/helper dependency cycle')
        node_active.add(vertex);depth=max((depth_of(d)for d in dependency_edges.get(vertex,())),default=-1)+1
        node_active.remove(vertex);node_depths[vertex]=depth;return depth
    for node in graph.nodes:node['depth']=depth_of(node['token'])
    # Group only independent helper columns. Every reference becomes an
    # explicit singleton-key lookup on a previously created table.
    shards=[];handles={};ordered=sorted(enumerate(graph.nodes),key=lambda kv:(kv[1]['depth'],kv[0]))
    for depth in sorted({n['depth'] for n in graph.nodes}):
        nodes=[(i,n) for i,n in ordered if n['depth']==depth]
        for start in range(0,len(nodes),max_columns-1):
            batch=nodes[start:start+max_columns-1];number=len(shards)+1;name=f'Native Exact {number}'
            columns=[{'id':'native_key','name':'native_key','formula':'1'}]
            for i,n in batch:
                formula=n['formula']
                formula=_map_helpers(formula,'__native_h',lambda m:handles[m.group()])
                columns.append({'id':f'h{i}','name':f'h{i}','formula':formula})
                handles[n['token']]=f'Lookup([{name}/h{i}], 1, [{name}/native_key])'
            shards.append({'id':f'native_exact_{plan["sourceSha256"][:8]}_{number}','kind':'table','name':name,
                           'source':{'kind':'sql','connectionId':plan['targetScope']['connectionId'],'statement':'SELECT 1 AS C0'},
                           'columns':columns,'sourceFormulaCells':[]})
    def materialize(formula):
        return _map_helpers(formula,'__native_h',lambda m:handles[m.group()])
    for e in aggregate_elements:
        for c in e['columns']:c['formula']=materialize(c['formula'])
    formula_outputs={};public=[]
    for cell,value in outputs.items():
        r=plan['formulas'][cell];lanes={k:materialize(v) for k,v in lane_dict(value).items()}
        columns=[{'id':r['columnId']+'_'+k,'name':r['columnId']+'_'+k,'formula':formula} for k,formula in lanes.items()]
        # Five typed lanes are intentional: a mixed IF result must not rely on
        # implicit SQL type conversion and an error must remain inspectable.
        formula_outputs[cell]={'lanes':lanes,'sourceResultClass':r['sourceResultClass'],'runtimeStatus':'UNVERIFIED_CANDIDATE'}
        public.append((cell,columns))
    for start in range(0,len(public),max(1,(max_columns-1)//5)):
        batch=public[start:start+max(1,(max_columns-1)//5)];number=len(shards)+1;name=f'Native Exact {number}'
        shard={'id':f'native_exact_{plan["sourceSha256"][:8]}_{number}','kind':'table','name':name,
               'source':{'kind':'sql','connectionId':plan['targetScope']['connectionId'],'statement':'SELECT 1 AS C0'},
               'columns':[{'id':'native_key','name':'native_key','formula':'1'}]+[c for _,cs in batch for c in cs],
               'sourceFormulaCells':[cell for cell,_ in batch]}
        for cell,cs in batch:formula_outputs[cell]['targetMapping']={'logicalElementId':shard['id'],'logicalColumnId':cs[0]['id'],'logicalLaneColumnIds':{k:plan['formulas'][cell]['columnId']+'_'+k for k in lane_dict(Scalar())}}
        shards.append(shard)
    # Put ordinary aggregate helpers into topological order among scalar shards.
    all_elements=shards+aggregate_elements;by_name={e['name']:e for e in all_elements};done=set();active=set();depths={};ordered_elements=[]
    def visit(e):
        if e['id'] in done:return
        if e['id'] in active:raise UnsupportedExpression('native construction dependency cycle')
        active.add(e['id']);parents=[]
        for c in e['columns']:
            for related in re.findall(r'\[([^\[\]/]+)/[^\[\]]+\]',c['formula']):
                if related in by_name and by_name[related] is not e:
                    visit(by_name[related]);parents.append(depths[by_name[related]['id']])
        depths[e['id']]=max(parents,default=-1)+1
        if depths[e['id']]>256:raise UnsupportedExpression('native construction dependency depth exceeds 256')
        active.remove(e['id']);done.add(e['id']);ordered_elements.append(e)
    for e in all_elements:visit(e)
    if any(len(c['formula'])>6000 for e in ordered_elements for c in e['columns']):raise UnsupportedExpression('assigned native formula exceeds 6000 characters')
    return {'sourceSha256':plan['sourceSha256'],'nativePlanHash':plan['nativePlanHash'],
            'formulas':formula_outputs,'shards':ordered_elements,'helperCount':len(graph.nodes),
            'maxDependencyDepth':max(depths.values(),default=0),'rangeAggregateCount':sum('rangeDomain' in e for e in aggregate_elements),'ordinaryRowTableCount':len(aggregate_elements),'maxFormulaLength':max((len(c['formula']) for e in ordered_elements for c in e['columns']),default=0),
            'unresolved':{c:r['reason'] for c,r in plan['formulas'].items() if r['status']=='unresolved'},
            'status':'CONSTRUCTION_CANDIDATE_PENDING_STAGING','runtimeStatus':'UNVERIFIED_CANDIDATE','formalTemplateObligations':formal_obligations}


def _construction_guard(plan,inputs,manifest,receipt,current,observed_rows,backup):
    try:
        from .native_calculations import _observed_bindings,build_native_calculation_backup
        from .migration_manifest import validate_manifest
    except ImportError:
        from native_calculations import _observed_bindings,build_native_calculation_backup
        from migration_manifest import validate_manifest
    validate_source_input_plan(inputs);validate_manifest(manifest)
    if (plan['sourceSha256']!=inputs['sourceSha256'] or plan['inputPlanHash']!=inputs['inputPlanHash']
        or manifest['sourceHash']!=plan['sourceSha256']
        or manifest.get('planProjection',{}).get('nativeCalculationPlan')!=plan
        or manifest['planProjection'].get('sharedInputArchitecture')!=inputs['sharedInputArchitecture']):raise ValueError('source/input/native/manifest projection is stale')
    target=manifest.get('target')or{}
    if current.get('workbookId')!=target.get('documentId') or current.get('documentVersion')!=target.get('version'):raise ValueError('fresh actual document/version is required')
    if backup!=build_native_calculation_backup(current,observed_rows):raise ValueError('full fresh document/input row backup is required')
    contents=current.get('contents')or{}
    if contents.get('kind')!='workbook' or not isinstance(contents.get('elements'),list) or not isinstance(contents.get('pages'),list):raise ValueError('complete current workbook contents are required')
    assigned=_observed_bindings(inputs,manifest,receipt,contents,observed_rows)
    lowered=lower_exact_native_calculations(plan,assigned)
    records={r['id']:r for r in manifest['formulaCells']}
    for cell,formula in lowered['formulas'].items():
        r=records.get(cell)or{};mapping=formula['targetMapping']
        if (r.get('mappingStatus') not in ('live','verification') or r.get('targetMapping')!=mapping):raise ValueError('reviewed native formula mapping is absent or stale: '+cell)
    return assigned,lowered


def prepare_exact_native_scaffold(plan,inputs,manifest,receipt,current,observed_rows,*,backup,seed_binding,page_id,shard_index=0):
    """One reviewable MCP program using observed input/seed/page identities.

    All final formula text is applied by the guarded REST step after scaffold
    IDs are returned. Placeholder columns are explicitly unverified scaffolds.
    """
    assigned,lowered=_construction_guard(plan,inputs,manifest,receipt,current,observed_rows,backup)
    if not 0<=shard_index<len(lowered['shards']):raise ValueError('native scaffold index is out of bounds')
    if not any(p.get('id')==page_id for p in current['contents']['pages']):raise ValueError('actual scaffold page ID is required')
    seed=next((e for e in current['contents']['elements'] if e.get('id')==seed_binding.get('elementId')),None)
    if (seed is None or seed.get('source',{}).get('kind')!='sql' or seed['source'].get('statement')!='SELECT 1 AS C0'
        or seed['source'].get('connectionId')!=plan['targetScope']['connectionId']
        or seed_binding.get('documentId')!=current['workbookId'] or seed_binding.get('documentVersion')!=current['documentVersion']
        or seed_binding.get('queriedRows')!=[{'C0':1}]):raise ValueError('fresh observed singleton SELECT 1 seed receipt is required')
    shard=lowered['shards'][shard_index]
    if any(e.get('name')==shard['name'] for e in current['contents']['elements']):raise ValueError('native scaffold name already exists; read back assigned IDs before retry')
    source=seed_binding['elementId'] if shard['source']['kind']=='sql' else shard['source']['elementId']
    lines=['# UNVERIFIED structural scaffold; final formulas require guarded REST/readback.',
           f'p = sigma.workbook.get_page({q(page_id)})',f't = p.add_table(sigma.data.source.element({q(source)}))',f't.set_name({q(shard["name"])})',f't.set_frame(1, {1 + 12 * shard_index}, 24, 12)',
           'inherited_columns = t.list_columns()', 'assigned_columns = []']
    for col in shard['columns']:
        lines+=[f'c = t.add_column({q(col["name"])}, sigma.formula.const_num(0))',
                'assigned_columns.append({"logicalColumnId": '+q(col['id'])+', "actualColumnId": c.id(), "name": '+q(col['name'])+'})']
    lines.extend(['for inherited_column in inherited_columns:', '    inherited_column.delete()'])
    lines.append(f'print({{"logicalElementId": {q(shard["id"])}, "actualElementId": t.id(), "name": {q(shard["name"])}, "columns": assigned_columns}})')
    return {'status':'REVIEWABLE_MCP_SCAFFOLD_PENDING_EXECUTION','runtimeStatus':'UNVERIFIED_CANDIDATE','sourceSha256':plan['sourceSha256'],
            'nativePlanHash':plan['nativePlanHash'],'manifestPlanHash':manifest['planHash'],'shardIndex':shard_index,
            'logicalElementId':shard['id'],'name':shard['name'],'sourceElementId':source,'logicalColumns':[{k:c[k] for k in ('id','name')} for c in shard['columns']],
            'documentId':current['workbookId'],'documentVersion':current['documentVersion'],'beforeContents':copy.deepcopy(current['contents']),
            'beforeEnvelope':copy.deepcopy({k:v for k,v in current.items() if k not in ('contents','documentVersion')}),
            'pageId':page_id,'frame':{'gridColumn':'1 / 25','gridRow':f'{1 + 12 * shard_index} / {13 + 12 * shard_index}'},
            'program':'\n'.join(lines)+'\n'}


def _scaffold_layout_conserved(before,after,*,page_id,element_id,frame):
    """Allow one direct placement; normalize only XML syntax/indentation."""
    def parse(value):
        if not isinstance(value,str):raise ValueError('native scaffold requires complete XML layout')
        try:return ET.fromstring('<Layout>'+value+'</Layout>',parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True,insert_pis=True)))
        except ET.ParseError as error:raise ValueError('native scaffold layout XML is invalid') from error
    old,new=parse(before),parse(after)
    pages=[p for p in new.iter('Page') if p.get('id')==page_id]
    placements=[(parent,child) for parent in new.iter() for child in parent if child.get('elementId')==element_id]
    if len(pages)!=1 or len(placements)!=1 or placements[0][0] is not pages[0]:raise ValueError('native scaffold must add exactly one placement on its declared page')
    parent,placement=placements[0]
    if (placement.tag!='Element' or placement.attrib!={'elementId':element_id,**frame} or len(placement)
            or (placement.text or '').strip() or (placement.tail or '').strip()):raise ValueError('native scaffold placement differs from its declared frame')
    parent.remove(placement)
    def canonical(node):
        text=node.text or '';tail=node.tail or ''
        return (node.tag,tuple(sorted(node.attrib.items())),text if text.strip() else '',tail if tail.strip() else '',tuple(canonical(c)for c in node))
    if canonical(old)!=canonical(new):raise ValueError('foreign layout changed during native scaffold')


def confirm_exact_native_scaffold(proposal,readback):
    if (proposal.get('status')!='REVIEWABLE_MCP_SCAFFOLD_PENDING_EXECUTION' or readback.get('workbookId')!=proposal['documentId']
        or not isinstance(readback.get('documentVersion'),int) or readback['documentVersion']<=proposal['documentVersion']):raise ValueError('fresh assigned scaffold readback is required')
    if (not isinstance(proposal.get('beforeEnvelope'),dict)
            or {k:v for k,v in readback.items() if k not in ('contents','documentVersion')}!=proposal['beforeEnvelope']):raise ValueError('foreign document envelope changed during native scaffold')
    contents=readback.get('contents')or{};before=proposal['beforeContents']
    if not isinstance(contents,dict) or {k:v for k,v in contents.items()if k not in ('elements','layout')}!={k:v for k,v in before.items()if k not in ('elements','layout')}:raise ValueError('foreign contents/pages/privateState changed during native scaffold')
    previous=before.get('elements');elements=contents.get('elements')
    if (not isinstance(previous,list) or not isinstance(elements,list) or len(elements)!=len(previous)+1
            or elements[:-1]!=previous):raise ValueError('native scaffold must append exactly one declared element and preserve every foreign element')
    actual=elements[-1];before_ids={e['id']for e in previous}
    if (not isinstance(actual,dict) or set(actual)!={'id','kind','name','source','columns'}
            or actual.get('kind')!='table' or actual.get('name')!=proposal['name']
            or not isinstance(actual.get('id'),str) or not actual['id'] or actual['id']in before_ids):raise ValueError('native scaffold element shape or assigned identity differs')
    if actual.get('source')!={'kind':'table','elementId':proposal['sourceElementId']}:raise ValueError('native scaffold source differs from assigned source')
    columns=actual.get('columns');declared=proposal['logicalColumns']
    if not isinstance(columns,list) or len(columns)!=len(declared):raise ValueError('assigned native scaffold columns are not exactly declared')
    ids=set();prior_column_ids={c.get('id')for e in previous for c in e.get('columns',[])}
    for expected,column in zip(declared,columns):
        if (not isinstance(column,dict) or not {'id','name','formula'}<=set(column) or set(column)-{'id','name','formula','type'}
                or column.get('name')!=expected['name'] or column.get('formula')!='0'
                or ('type'in column and column['type']!='number')
                or not isinstance(column.get('id'),str) or not column['id'] or column['id']in ids or column['id']in prior_column_ids):raise ValueError('assigned native scaffold column differs from declared placeholder')
        ids.add(column['id'])
    if not isinstance(proposal.get('pageId'),str) or not isinstance(proposal.get('frame'),dict):raise ValueError('native scaffold proposal lacks its owned placement contract')
    _scaffold_layout_conserved(before.get('layout'),contents.get('layout'),page_id=proposal['pageId'],element_id=actual['id'],frame=proposal['frame'])
    record={'status':'CONFIRMED_NATIVE_SCAFFOLD','sourceSha256':proposal['sourceSha256'],'nativePlanHash':proposal['nativePlanHash'],
            'manifestPlanHash':proposal['manifestPlanHash'],'logicalElementId':proposal['logicalElementId'],'elementId':actual['id'],'name':actual['name'],
            'source':copy.deepcopy(actual['source']),'columnIds':{c['id']:actual_c['id'] for c,actual_c in zip(declared,columns)},
            'documentId':readback['workbookId'],'documentVersion':readback['documentVersion'],'pageId':proposal['pageId'],'frame':copy.deepcopy(proposal['frame']),
            'beforeEnvelopeHash':digest(proposal['beforeEnvelope']),'beforeContentsHash':digest(before),
            'structureHash':digest(actual),'readbackHash':digest(contents)}
    return {**record,'receiptHash':digest(record)}


def prepare_exact_native_update(plan,inputs,manifest,receipt,current,observed_rows,*,backup,native_bindings,shard_index=0,prior_readbacks=()):
    """One full-contents, version-guarded formula update to an assigned scaffold."""
    _,lowered=_construction_guard(plan,inputs,manifest,receipt,current,observed_rows,backup)
    shards=lowered['shards']
    if not 0<=shard_index<len(shards):raise ValueError('native shard index is out of bounds')
    if len(prior_readbacks)!=shard_index:raise ValueError('confirmed prior native formula readbacks are required')
    # A dependency-ordered prefix permits one scaffold/REST/readback canary
    # before creating the remaining tables. A hole or an unknown receipt is not
    # evidence for a prefix, and all earlier readbacks remain mandatory.
    if (not isinstance(native_bindings,dict) or not shard_index < len(native_bindings) <= len(shards)
            or set(native_bindings)!={s['id']for s in shards[:len(native_bindings)]}):
        raise ValueError('assigned native scaffolds must be a contiguous prefix covering this shard')
    assigned={};actuals={e['id']:e for e in current['contents']['elements']}
    for position,shard in enumerate(shards[:len(native_bindings)]):
        r=native_bindings.get(shard['id'])or{};canonical={k:v for k,v in r.items()if k!='receiptHash'}
        e=actuals.get(r.get('elementId'))or{}
        if (r.get('status')!='CONFIRMED_NATIVE_SCAFFOLD' or r.get('receiptHash')!=digest(canonical) or r.get('nativePlanHash')!=plan['nativePlanHash']
            or r.get('sourceSha256')!=plan['sourceSha256'] or r.get('manifestPlanHash')!=manifest['planHash'] or r.get('logicalElementId')!=shard['id']
            or r.get('documentId')!=current['workbookId'] or r.get('documentVersion',current['documentVersion']+1)>current['documentVersion']
            or r.get('name')!=shard['name'] or e.get('name')!=shard['name'] or r.get('source')!=e.get('source')):raise ValueError('assigned native scaffold receipt is stale')
        cols={c['id']:c for c in e.get('columns',[])}
        if len(cols)!=len(e.get('columns',[])) or set(cols)!=set(r.get('columnIds',{}).values()) or set(r.get('columnIds',{}))!={c['id']for c in shard['columns']} or any(cols.get(r['columnIds'][c['id']],{}).get('name')!=c['name'] for c in shard['columns']):raise ValueError('assigned native column IDs differ from readback')
        if position>=shard_index and digest(e)!=r.get('structureHash'):raise ValueError('pending native scaffold changed since assigned-ID confirmation')
        assigned[shard['id']]=r
    # A prior receipt is evidence only for the exact saved formula document.
    for index,r in enumerate(prior_readbacks):
        previous=shards[index];binding=assigned[previous['id']]
        expected=[{**c,'id':binding['columnIds'][c['id']]}for c in previous['columns']]
        if (r.get('status')!='CONFIRMED_EXACT_NATIVE_READBACK' or r.get('nativePlanHash')!=plan['nativePlanHash'] or r.get('shardIndex')!=index
            or r.get('actualElementId')!=binding['elementId'] or r.get('formulaHash')!=digest(expected)
            or actuals[binding['elementId']].get('columns')!=expected):raise ValueError('prior native formula readback is stale')
    shard=shards[shard_index];binding=assigned[shard['id']];updated=copy.deepcopy(current['contents']);target=next(e for e in updated['elements']if e['id']==binding['elementId'])
    columns=[{**c,'id':binding['columnIds'][c['id']]}for c in shard['columns']]
    target['columns']=columns
    request={'documentVersion':current['documentVersion'],'contents':updated}
    return {'status':'GUARDED_EXACT_REST_CANDIDATE_PENDING_READBACK','runtimeStatus':'UNVERIFIED_CANDIDATE','method':'PUT',
            'endpoint':f'/v2/workbooks/{current["workbookId"]}/contents','sourceSha256':plan['sourceSha256'],'nativePlanHash':plan['nativePlanHash'],
            'manifestPlanHash':manifest['planHash'],'shardIndex':shard_index,'actualElementId':binding['elementId'],'formulaHash':digest(columns),
            'backupHash':backup['backupHash'],'dryRunRequest':request}


def confirm_exact_native_readback(proposal,readback):
    if (proposal.get('status')!='GUARDED_EXACT_REST_CANDIDATE_PENDING_READBACK' or readback.get('workbookId')!=proposal['endpoint'].split('/')[3]
        or not isinstance(readback.get('documentVersion'),int) or readback['documentVersion']<=proposal['dryRunRequest']['documentVersion']
        or readback.get('contents')!=proposal['dryRunRequest']['contents']):raise ValueError('exact saved native formula readback is required')
    return {'status':'CONFIRMED_EXACT_NATIVE_READBACK','runtimeStatus':'UNVERIFIED_CANDIDATE','nativePlanHash':proposal['nativePlanHash'],
            'sourceSha256':proposal['sourceSha256'],'manifestPlanHash':proposal['manifestPlanHash'],'shardIndex':proposal['shardIndex'],
            'actualElementId':proposal['actualElementId'],'formulaHash':proposal['formulaHash'],'documentId':readback['workbookId'],
            'documentVersion':readback['documentVersion'],'readbackHash':digest(readback['contents'])}
