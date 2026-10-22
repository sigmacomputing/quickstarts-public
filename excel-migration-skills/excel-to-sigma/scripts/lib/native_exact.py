"""Source-bound scalar semantics and typed native formula candidates.

A value has five independent lanes: number, text, logical, kind, Excel error.
SQL NULL is never used as an Excel error. Unsupported binding is a compiler
exception and cannot be caught by IFERROR. Expressions may be materialized by
``emit`` into a bounded, deduplicated dependency graph; no cache is consulted.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
import calendar
import json
import math
import re
try:
    from .excel_expression import ExcelCalcError, UnsupportedExpression, NUMERIC_TEXT, _parse_criterion
except ImportError:
    from excel_expression import ExcelCalcError, UnsupportedExpression, NUMERIC_TEXT, _parse_criterion

EMPTY='""'
SCALAR_LANES=('number','text','logical','kind','error')

def q(value): return json.dumps(value,ensure_ascii=False)
def iff(condition,yes,no):
    if condition=='True': return yes
    if condition=='False': return no
    if yes==no:return yes
    return f'If({condition}, {yes}, {no})'
def both(*terms):
    terms=[t for t in terms if t!='True']
    if 'False' in terms:return 'False'
    return '('+' and '.join(terms)+')' if len(terms)>1 else next(iter(terms),'True')
def either(*terms):
    terms=[t for t in terms if t!='False']
    if 'True' in terms:return 'True'
    return '('+' or '.join(terms)+')' if len(terms)>1 else next(iter(terms),'False')
def eq(a,b):
    if a==b:return 'True'
    if a.startswith(chr(34)) and b.startswith(chr(34)) and a.endswith(chr(34)) and b.endswith(chr(34)):return 'False'
    if a in ('0','1','True','False',EMPTY,'"n"','"t"','"b"','"z"') and b in ('0','1','True','False',EMPTY,'"n"','"t"','"b"','"z"'):return 'False'
    return f'({a} = {b})'
def ne(a,b):
    e=eq(a,b)
    return {'True':'False','False':'True'}.get(e,f'({a} != {b})')

def first_error(*errors):
    result=EMPTY
    for error in reversed(errors):result=iff(ne(error,EMPTY),error,result)
    return result

@dataclass(frozen=True)
class Scalar:
    number: str='0'
    text: str=EMPTY
    logical: str='False'
    kind: str='"n"'              # n numeric, t text (including ""), b Boolean, z blank
    error: str=EMPTY
    may_be_boolean: bool=False   # compile-time type-domain evidence, never an emitted lane

def can_be_boolean(value):return value.may_be_boolean or '"b"' in value.kind

def lane_dict(value):return {key:getattr(value,key)for key in SCALAR_LANES}

class Literal:
    @staticmethod
    def number(value):return Scalar(number=str(value))
    @staticmethod
    def text(value):return Scalar(text=q(value),kind='"t"')
    @staticmethod
    def boolean(value):return Scalar(logical='True' if value else 'False',kind='"b"',may_be_boolean=True)
    @staticmethod
    def blank():return Scalar(kind='"z"')
    @staticmethod
    def error(code):return Scalar(kind='"z"',error=q(code))
    @staticmethod
    def value(value):
        if value is None:return Literal.blank()
        if type(value) is bool:return Literal.boolean(value)
        if isinstance(value,(int,float)):return Literal.number(value)
        if isinstance(value,str):return Literal.text(value)
        raise UnsupportedExpression('unqualified literal type')

@dataclass(frozen=True)
class Vector:
    values: tuple
    width: int=1
    source: dict|None=None


def _width(node):
    if node.get('width'):return node['width']
    cells=node.get('cells',[])
    if not cells:return 1
    # Row-major binding; count cells sharing the first row.
    first=re.search(r'\d+$',cells[0]).group()
    return sum(re.search(r'\d+$',c).group()==first for c in cells)

def flatten(values):
    for value in values:
        if isinstance(value,Vector):yield from value.values
        else:yield value

def scalar(value):
    if isinstance(value,Vector):
        if len(value.values)!=1:raise UnsupportedExpression('multi-cell array used as scalar')
        return value.values[0]
    return value

def select(condition,yes,no):
    if isinstance(yes,Vector) or isinstance(no,Vector):
        if not isinstance(yes,Vector) or not isinstance(no,Vector) or len(yes.values)!=len(no.values):
            raise UnsupportedExpression('conditional array shapes differ')
        return Vector(tuple(select(condition,a,b) for a,b in zip(yes.values,no.values)),yes.width)
    return Scalar(*(iff(condition,getattr(yes,k),getattr(no,k)) for k in SCALAR_LANES),may_be_boolean=can_be_boolean(yes)or can_be_boolean(no))

def numeric(value):
    value=scalar(value)
    text_number=f'RegexpMatch(Trim({value.text}), {q(NUMERIC_TEXT)})'
    number=iff(eq(value.kind,'"n"'),value.number,
               iff(eq(value.kind,'"b"'),iff(value.logical,'1','0'),
                   iff(both(eq(value.kind,'"t"'),text_number),f'Number({value.text})','0')))
    error=first_error(value.error,iff(both(eq(value.kind,'"t"'),f'Not({text_number})'),q('#VALUE!'),EMPTY))
    return number,error

def logical(value,*,reference=False):
    value=scalar(value)
    truth=iff(eq(value.kind,'"b"'),value.logical,ne(value.number,'0'))
    if reference:return truth,value.error
    textok=either(eq(f'Lower({value.text})','"true"'),eq(f'Lower({value.text})','"false"'))
    truth=iff(eq(value.kind,'"t"'),eq(f'Lower({value.text})','"true"'),truth)
    return truth,first_error(value.error,iff(both(eq(value.kind,'"t"'),f'Not({textok})'),q('#VALUE!'),EMPTY))

def text_value(value):
    return iff(eq(value.kind,'"t"'),value.text,iff(eq(value.kind,'"b"'),iff(value.logical,'"TRUE"','"FALSE"'),iff(eq(value.kind,'"n"'),f'Text({value.number})',EMPTY)))

def compare(a,b,op='=',*,lookup=False):
    # Excel comparison order: number < text < logical. Blanks adopt the other
    # operand's comparison type; lookup preserves number/text distinction.
    ka=iff(eq(a.kind,'"z"'),iff(eq(b.kind,'"z"'),'"n"',b.kind),a.kind)
    kb=iff(eq(b.kind,'"z"'),ka,b.kind)
    def rank(k):return iff(eq(k,'"n"'),'0',iff(eq(k,'"t"'),'1','2'))
    same=eq(ka,kb)
    n=f'({a.number} {op} {b.number})'
    t=f'(Lower({a.text}) {op} Lower({b.text}))'
    l=f'({iff(a.logical,"1","0")} {op} {iff(b.logical,"1","0")})'
    within=iff(eq(ka,'"n"'),n,iff(eq(ka,'"t"'),t,l))
    across='False' if op=='=' else 'True' if op=='!=' else f'({rank(ka)} {op} {rank(kb)})'
    return iff(same,within,across)


def wildcard_pattern(text):
    parts=[];i=0
    while i<len(text):
        c=text[i]
        if c=='~' and i+1<len(text):i+=1;parts.append(re.escape(text[i]))
        elif c=='*':parts.append('.*')
        elif c=='?':parts.append('.')
        else:parts.append(re.escape(c))
        i+=1
    return '^'+''.join(parts)+'$'


def criterion_spec(node,compile):
    """Compile criteria without guessing editable string contents.

    Literal wildcard syntax is exact. Dynamic numeric/date operator templates
    and dynamic text equality are supported; arbitrary dynamic wildcard or
    operator syntax requires a guarded error obligation (never silent equality).
    """
    if node['kind']=='text':
        op,target=_parse_criterion(node['value'])
        if target is None:return op,Literal.blank(),None
        if isinstance(target,str):return op,Literal.text(target),wildcard_pattern(target) if any(c in target for c in '*?~') else None
        return op,Literal.number(target),None
    if node['kind']=='binary' and node['operator']=='&' and node['left']['kind']=='text' and node['left']['value'] in ('<=','>=','<>','=','<','>'):
        op=node['left']['value'];target=scalar(compile(node['right']))
        if target.kind in ('"n"','"z"') or can_be_boolean(target):return op,target,None
        # Concatenation makes a criterion string: a text operand such as "1"
        # must be parsed just like ">1", rather than compared as typed text.
        return '=',Scalar(text=f'Concat({q(op)}, {text_value(target)})',kind='"t"',error=target.error),'dynamic'
    target=scalar(compile(node))
    # A typed blank criterion is numeric zero. Empty text is parsed separately
    # below and keeps its empty-cell matcher, including operator concatenation.
    target=select(eq(target.kind,'"z"'),Scalar(error=target.error),target)
    return '=',target,'dynamic'


def ordered_criterion(value,target,op):
    # Criteria ordering does not use Excel's ordinary cross-type rank. Empty
    # operands compare as numeric zero; blank range cells never match ordering.
    target_kind=iff(eq(target.kind,'"z"'),'"n"',target.kind)
    return both(ne(value.kind,'"z"'),eq(value.kind,target_kind),compare(value,target,op))


def criterion_equal(value,target):
    # COUNTIFS/SUMIFS numeric equality also accepts numbers stored as text.
    # This coercion belongs to criteria, not ordinary comparisons or lookups.
    isnum=f'RegexpMatch(Trim({value.text}), {q(NUMERIC_TEXT)})'
    converted=iff(isnum,f'Number({value.text})','0')
    return iff(both(eq(target.kind,'"n"'),eq(value.kind,'"t"'),isnum),
               eq(converted,target.number),compare(value,target))


def criteria(value,spec,emit=lambda f:f,*,numeric_text=True):
    op,target,pattern=spec
    if can_be_boolean(value) or can_be_boolean(target):raise UnsupportedExpression('Boolean criteria semantics await actual Excel oracle')
    nativeop='!=' if op=='<>' else op
    equal=criterion_equal if numeric_text else compare
    if pattern and pattern!='dynamic' and op in ('=','<>'):
        matched=both(eq(value.kind,'"t"'),f'RegexpMatch(Lower({value.text}), {q(pattern.lower())})')
        return (f'Not({matched})' if op=='<>' else matched),first_error(value.error,target.error)
    matched=ordered_criterion(value,target,nativeop) if op in ('<','>','<=','>=') else equal(value,target)
    if op=='<>':matched=f'Not({matched})'
    if target.kind=='"z"' and op in ('=','<>'):
        matched=either(eq(value.kind,'"z"'),both(eq(value.kind,'"t"'),eq(value.text,EMPTY)))
        if op=='<>':matched=f'Not({matched})'
    error=first_error(value.error,target.error)
    if pattern=='dynamic':
        # Parse arbitrary editable criteria at runtime, including wildcard/tilde
        # escaping. Non-text typed criteria retain their native type.
        target=Scalar(*(emit(getattr(target,k)) for k in SCALAR_LANES))
        raw=target.text
        operator=f'Coalesce(RegexpExtract({raw}, "^(<=|>=|<>|=|<|>)"), "=")'
        operator=emit(operator)
        operand=f'RegexpReplace({raw}, "^(<=|>=|<>|=|<|>)", "")'
        operand=emit(operand)
        # Exact lookups reuse wildcard parsing, but their textual sought value
        # must retain its type instead of becoming a numeric criterion.
        isnum=f'RegexpMatch(Trim({operand}), {q(NUMERIC_TEXT)})' if numeric_text else 'False'
        isnum=emit(isnum)
        dynamic=Scalar(number=iff(isnum,f'Number({operand})','0'),text=operand,
                       kind=iff(eq(operand,EMPTY),'"z"',iff(isnum,'"n"','"t"')))
        dynamic=select(eq(target.kind,'"t"'),dynamic,target)
        dynamic=Scalar(*(emit(getattr(dynamic,k)) for k in SCALAR_LANES))
        # First escape regex metacharacters other than Excel wildcards. Expand
        # wildcards, restore odd tilde escapes, then halve literal tilde pairs.
        pattern_expr=f'RegexpReplace({operand}, {q(r"([\\.^$|()\[\]{}+])")}, {q(r"\\\1")})'
        pattern_expr=emit(pattern_expr)
        pattern_expr=emit(f'Replace({pattern_expr}, "*", ".*")')
        for _ in range(2):pattern_expr=emit(f'RegexpReplace({pattern_expr}, {q(r"(^|[^~])((~~)*)~[.][*]")}, {q(r"\1\2\\*")})')
        pattern_expr=emit(f'Replace({pattern_expr}, "?", ".")')
        for _ in range(2):pattern_expr=emit(f'RegexpReplace({pattern_expr}, {q(r"(^|[^~])((~~)*)~[.]")}, {q(r"\1\2\\?")})')
        pattern_expr=f'Concat("^", Replace({pattern_expr}, "~~", "~"), "$")'
        pattern_expr=emit(pattern_expr)
        wild=both(eq(value.kind,'"t"'),f'RegexpMatch(Lower({value.text}), Lower({pattern_expr}))')
        wild=emit(wild)
        equality=emit(equal(value,dynamic))
        equality=iff(eq(dynamic.kind,'"z"'),either(eq(value.kind,'"z"'),both(eq(value.kind,'"t"'),eq(value.text,EMPTY))),equality)
        equality=iff(both(eq(dynamic.kind,'"t"'),f'RegexpMatch({operand}, "[*?~]")'),wild,equality)
        equality=emit(equality)
        result=equality
        for excel,native in (('<>','!='),('<','<'),('>','>'),('<=','<='),('>=','>=')):
            cond=f'Not({equality})' if excel=='<>' else ordered_criterion(value,dynamic,native)
            cond=emit(cond)
            result=emit(iff(eq(operator,q(excel)),cond,result))
        fallback=equal(value,target)
        if op=='<>':fallback=f'Not({fallback})'
        matched=iff(eq(target.kind,'"t"'),result,fallback)
    return matched,error


def compile_expression(node,reference,*,emit=lambda formula:formula,aggregate=None,epoch='1900',expression_cache=None):
    """Return a Scalar/Vector; emit sees only parenthesized native strings.

    aggregate may replace a complete aligned range operation with a native
    aggregate over an ordinary table; returning None uses bounded helper terms.
    """
    def merge_errors(*values):
        result=EMPTY
        for value in reversed(values):
            result=first_error(value,result)
            if len(result)>1200:result=emit(result)
        return result
    def sum_terms(values):
        layer=list(values) or ['0']
        while len(layer)>8:
            layer=[emit('('+' + '.join(layer[i:i+8])+')') for i in range(0,len(layer),8)]
        return '('+' + '.join(layer)+')'
    def save(value):
        if isinstance(value,Vector):return value
        return Scalar(*(emit(getattr(value,k)) if getattr(value,k) not in ('0','1','True','False','"n"','"t"','"b"','"z"',EMPTY) and not re.fullmatch(r'-?[0-9]+([.][0-9]+)?',getattr(value,k)) and not getattr(value,k).startswith('"') else getattr(value,k) for k in SCALAR_LANES),may_be_boolean=can_be_boolean(value))
    cache={} if expression_cache is None else expression_cache
    def run(n):
        key=json.dumps(n,sort_keys=True,separators=(',',':'))
        if key not in cache:cache[key]=uncached(n)
        return cache[key]
    def uncached(n):
        k=n['kind']
        if k=='number':return Literal.number(n['source'])
        if k=='text':return Literal.text(n['value'])
        if k=='boolean':return Literal.boolean(n['value'])
        if k=='reference':return reference(n['cell'])
        if k=='range':return Vector(tuple(reference(c) for c in n['cells']),_width(n),n)
        if k=='group':return run(n['expression'])
        if k=='indirect':
            selector=scalar(run(n['selector']));result=Literal.error('#REF!')
            for name,target in reversed(n['alternatives']):result=select(eq(f'Lower({text_value(selector)})',q(name.lower())),run(target),result)
            if isinstance(result,Vector):raise UnsupportedExpression('INDIRECT array result needs review')
            return save(Scalar(result.number,result.text,result.logical,result.kind,merge_errors(selector.error,result.error),may_be_boolean=can_be_boolean(result)))
        if k in ('unary','percent'):
            value=scalar(run(n['operand']));v,e=numeric(value)
            return save(Scalar(number=f'({v} * 0.01)' if k=='percent' else f'({n["operator"]}{v})',error=e))
        if k=='binary':
            a,b=scalar(run(n['left'])),scalar(run(n['right']));op=n['operator'];e=merge_errors(a.error,b.error)
            if op=='&':return save(Scalar(text=f'Concat({text_value(a)}, {text_value(b)})',kind='"t"',error=e))
            if op in ('=','<>','<','>','<=','>='):return save(Scalar(logical=compare(a,b,'!=' if op=='<>' else op),kind='"b"',error=e))
            x,xe=numeric(a);y,ye=numeric(b);e=merge_errors(xe,ye)
            if op=='/':e=merge_errors(e,iff(eq(y,'0'),q('#DIV/0!'),EMPTY));v=f'({x} / {iff(eq(y,"0"),"1",y)})'
            elif op=='^':
                e=merge_errors(e,iff(either(both(f'({x} < 0)',ne(y,f'Floor({y})')),both(eq(x,'0'),f'({y} < 0)')),q('#NUM!'),EMPTY))
                v=f'Power({iff(ne(e,EMPTY),"1",x)}, {iff(ne(e,EMPTY),"1",y)})'
            else:v=f'({x} {op} {y})'
            return save(Scalar(number=v,error=e))
        if k!='function':raise UnsupportedExpression(f'unsupported AST {k}')
        name,args=n['name'],n['arguments']
        if name in ('FORECAST.LINEAR','FORECAST.ETS','NORM.S.INV','STDEV.S','TREND','OFFSET'):
            raise UnsupportedExpression(f'custom-port obligation {name}; no numeric replacement')
        if name in ('IF','IFERROR'):
            if len(args) not in ((2,3) if name=='IF' else (2,)):raise UnsupportedExpression(f'{name} arity')
            if name=='IFERROR':
                a,b=run(args[0]),run(args[1]);a=scalar(a)
                return save(select(ne(a.error,EMPTY),b,a))
            a=scalar(run(args[0]));condition,e=logical(a)
            b=run(args[1]);c=run(args[2]) if len(args)==3 else Literal.boolean(False)
            result=select(condition,b,c)
            def condition_error(value):return save(replace(value,error=merge_errors(e,value.error)))
            if isinstance(result,Vector):return Vector(tuple(condition_error(v) for v in result.values),result.width,result.source)
            return condition_error(result)
        if aggregate and name in ('SUMIFS','COUNTIFS','SUM','COUNT','COUNTA'):
            result=aggregate(n,run)
            if result is not None:return result
        values=[run(a) for a in args]
        flat=list(flatten(values));error=merge_errors(*(v.error for v in flat))
        if name in ('SUM','MIN','MAX','AVERAGE','COUNT','COUNTA','AND','OR'):
            if not values:raise UnsupportedExpression(f'{name} arity')
            if name=='COUNTA':return save(Scalar(number='('+' + '.join(iff(either(ne(v.kind,'"z"'),ne(v.error,EMPTY)),'1','0') for v in flat)+')'))
            if name=='COUNT':
                terms=[];errors=[]
                for ast,value in zip(args,values):
                    referenced=isinstance(value,Vector) or ast['kind']=='reference'
                    for v in flatten([value]):
                        eligible=eq(v.kind,'"n"')
                        if not referenced:
                            eligible=either(eligible,eq(v.kind,'"b"'),both(eq(v.kind,'"t"'),f'RegexpMatch(Trim({v.text}), {q(NUMERIC_TEXT)})'))
                            errors.append(v.error)
                        terms.append(iff(both(eligible,eq(v.error,EMPTY)),'1','0'))
                return save(Scalar(number=sum_terms(terms),error=merge_errors(*errors)))
            if name in ('AND','OR'):
                bools=[];errors=[];eligibilities=[]
                for ast,value in zip(args,values):
                    referenced=isinstance(value,Vector) or ast['kind']=='reference'
                    for v in flatten([value]):
                        b,e=logical(v,reference=referenced);errors.append(e)
                        eligible=either(eq(v.kind,'"n"'),eq(v.kind,'"b"')) if referenced else 'True'
                        eligibilities.append(eligible)
                        bools.append(iff(eligible,b,'True' if name=='AND' else 'False'))
                e=merge_errors(*errors,iff(either(*eligibilities),EMPTY,q('#VALUE!')))
                return save(Scalar(logical=both(*bools) if name=='AND' else either(*bools),kind='"b"',error=e))
            numbers=[];present=[];errors=[]
            for ast,value in zip(args,values):
                referenced=isinstance(value,Vector) or ast['kind']=='reference'
                for v in flatten([value]):
                    if referenced:
                        numbers.append(iff(eq(v.kind,'"n"'),v.number,'0'));present.append(eq(v.kind,'"n"'));errors.append(v.error)
                    else:
                        x,e=numeric(v);numbers.append(x);present.append('True');errors.append(e)
            count='('+' + '.join(iff(p,'1','0') for p in present)+')' if present else '0'
            total=sum_terms(numbers);e=merge_errors(*errors)
            if name in ('MIN','MAX'):
                result='0';seen='False'
                for x,p in zip(numbers,present):result=iff(p,iff(seen,f'If({x} {"<" if name=="MIN" else ">"} {result}, {x}, {result})',x),result);seen=either(seen,p);result=emit(result)
                total=result
            if name=='AVERAGE':e=merge_errors(e,iff(eq(count,'0'),q('#DIV/0!'),EMPTY));total=f'({total} / {iff(eq(count,"0"),"1",count)})'
            return save(Scalar(number=total,error=e))
        if name in ('SUMIFS','COUNTIFS'):
            offset=1 if name=='SUMIFS' else 0
            if (len(args)-offset)%2 or len(args)-offset<2:raise UnsupportedExpression(f'{name} arity')
            ranges=values[offset::2]
            if any(not isinstance(v,Vector) for v in ranges):raise UnsupportedExpression(f'{name} criteria must be ranges')
            size=len(ranges[0].values)
            if any(len(v.values)!=size or v.width!=ranges[0].width for v in ranges):return Literal.error('#VALUE!')
            sums=values[0] if offset else Vector(tuple(Literal.number(1) for _ in range(size)))
            if not isinstance(sums,Vector) or len(sums.values)!=size:return Literal.error('#VALUE!')
            specs=[criterion_spec(a,run) for a in args[offset+1::2]];terms=[];errors=[]
            for i in range(size):
                conditions=[]
                for vector,spec in zip(ranges,specs):
                    c,e=criteria(vector.values[i],spec,emit=emit);conditions.append(c);errors.append(e)
                item=sums.values[i];match=emit(both(*conditions));terms.append(emit(iff(both(match,eq(item.kind,'"n"')),item.number,'0')))
                errors.append(iff(match,item.error,EMPTY))
            return save(Scalar(number=sum_terms(terms),error=merge_errors(*errors)))
        if name in ('INDEX','MATCH','VLOOKUP','XLOOKUP'):
            if name=='INDEX':
                if len(values) not in (2,3):raise UnsupportedExpression('INDEX arity')
                vector=values[0] if isinstance(values[0],Vector) else Vector((values[0],));row,re=numeric(values[1]);col,ce=numeric(values[2]) if len(values)==3 else ('1',EMPTY)
                if col=='0':
                    selected=[]
                    for j in range(vector.width):
                        item=Literal.error('#REF!')
                        for i in reversed(range(len(vector.values)//vector.width)):
                            item=select(eq(f'Trunc({row}, 0)',str(i+1)),vector.values[i*vector.width+j],item)
                        selected.append(save(Scalar(item.number,item.text,item.logical,item.kind,merge_errors(re,ce,item.error),may_be_boolean=can_be_boolean(item))))
                    return Vector(tuple(selected),vector.width)
                if row=='0':
                    selected=[]
                    for i in range(len(vector.values)//vector.width):
                        item=Literal.error('#REF!')
                        for j in reversed(range(vector.width)):item=select(eq(f'Trunc({col}, 0)',str(j+1)),vector.values[i*vector.width+j],item)
                        selected.append(save(Scalar(item.number,item.text,item.logical,item.kind,merge_errors(re,ce,item.error),may_be_boolean=can_be_boolean(item))))
                    return Vector(tuple(selected))
                result=Literal.error('#REF!')
                for i,v in reversed(list(enumerate(vector.values))):result=save(select(both(eq(f'Trunc({row}, 0)',str(i//vector.width+1)),eq(f'Trunc({col}, 0)',str(i%vector.width+1))),v,result))
                result=select(ne(merge_errors(re,ce),EMPTY),Scalar(error=merge_errors(re,ce)),result)
                # Excel scalar INDEX of an empty cell returns numeric zero.
                return save(select(eq(result.kind,'"z"'),Scalar(error=result.error),result))
            sought=scalar(values[0]);fallback=Literal.error('#N/A')
            if name=='MATCH':
                if len(args)!=3 or args[2].get('source')!='0':raise UnsupportedExpression('MATCH approximate mode requires review')
                vector=values[1] if isinstance(values[1],Vector) else Vector((values[1],));keys=vector.values;returns=[Literal.number(i+1) for i in range(len(keys))]
            elif name=='VLOOKUP':
                if len(args)!=4 or not (args[3].get('value') is False or args[3].get('source')=='0'):raise UnsupportedExpression('VLOOKUP approximate mode requires review')
                vector=values[1]
                if not isinstance(vector,Vector):raise UnsupportedExpression('VLOOKUP requires table range')
                col,ce=numeric(values[2]);keys=vector.values[::vector.width];returns=[]
                for row_index in range(len(keys)):
                    result=Literal.error('#REF!')
                    for j in reversed(range(vector.width)):result=select(eq(f'Floor({col})',str(j+1)),vector.values[row_index*vector.width+j],result)
                    returns.append(result)
                sought=Scalar(sought.number,sought.text,sought.logical,sought.kind,merge_errors(sought.error,ce),may_be_boolean=can_be_boolean(sought))
            else:
                if not 3<=len(values)<=6:raise UnsupportedExpression('XLOOKUP arity')
                if len(args)>=5 and args[4].get('source')!='0':raise UnsupportedExpression('XLOOKUP approximate mode requires review')
                if len(args)>=6 and args[5].get('source') not in ('1','-1'):raise UnsupportedExpression('XLOOKUP binary search mode requires review')
                keys=list(flatten([values[1]]));returns=list(flatten([values[2]]))
                if len(keys)!=len(returns):return Literal.error('#VALUE!')
                if len(values)>=4:fallback=scalar(values[3])
                if len(args)>=6 and args[5].get('source')=='-1':keys=list(reversed(keys));returns=list(reversed(returns))
            result=fallback
            for key,value in reversed(list(zip(keys,returns))):
                condition=compare(key,sought)
                if name in ('MATCH','VLOOKUP'):
                    escaped=select(eq(sought.kind,'"t"'),Scalar(text=f'Concat("=", {sought.text})',kind='"t"',error=sought.error),sought)
                    condition,_lookup_error=criteria(key,('=',escaped,'dynamic'),emit=emit,numeric_text=False)
                result=select(condition,select(eq(value.kind,'"z"'),Scalar(error=value.error),value),result)
                result=select(ne(key.error,EMPTY),Scalar(error=key.error),result)
                result=save(result)
            if name=='VLOOKUP':result=select(either(f'({col} < 1)',f'({col} >= {vector.width+1})'),Literal.error('#REF!'),result)
            return save(select(ne(sought.error,EMPTY),Scalar(error=sought.error),result))
        numbers=[numeric(v) for v in values];ns=[x for x,_ in numbers];e=merge_errors(*(er for _,er in numbers))
        if name in ('ABS','INT','ROUND','ROUNDUP','MOD','CEILING','SQRT'):
            arity=1 if name in ('ABS','INT','SQRT') else 2
            if len(values)!=arity:raise UnsupportedExpression(f'{name} arity')
            x=ns[0]
            if name=='ABS':v=f'Abs({x})'
            elif name=='INT':v=f'Floor({x})'
            elif name=='SQRT':e=merge_errors(e,iff(f'({x} < 0)',q('#NUM!'),EMPTY));v=f'Sqrt(If({x} < 0, 0, {x}))'
            elif name=='ROUND':v=f'Round({x}, Trunc({ns[1]}, 0))'
            elif name=='ROUNDUP':
                # Sigma RoundUp is ceiling even for negatives. Excel ROUNDUP
                # rounds away from zero, so round a positive magnitude first.
                v=f'(If({x} < 0, -1, 1) * RoundUp(Abs({x}), Trunc({ns[1]}, 0)))'
            elif name=='MOD':
                y=ns[1];e=merge_errors(e,iff(eq(y,'0'),q('#DIV/0!'),EMPTY));safe=iff(eq(y,'0'),'1',y);v=f'({x} - ({safe} * Floor(({x} / {safe}))))'
            else:
                y=ns[1];e=merge_errors(e,iff(both(f'({x} > 0)',f'({y} < 0)'),q('#NUM!'),EMPTY))
                safe=iff(eq(y,'0'),'1',y);v=iff(eq(y,'0'),'0',f'(Ceiling(({x} / {safe})) * {y})')
            return save(Scalar(number=v,error=e))
        if name in ('DATE','EDATE','EOMONTH','MONTH'):
            if len(values)!=({'DATE':3,'MONTH':1}.get(name,2)):raise UnsupportedExpression(f'{name} arity')
            # Serial arithmetic explicitly preserves epoch and the 1900 leap bug.
            origin='1904-01-01' if epoch=='1904' else '1899-12-31'
            def serial(date):
                d=f'DateDiff("day", Date({q(origin)}), {date})'
                return d if epoch=='1904' else f'({d} + If({date} >= Date("1900-03-01"), 1, 0))'
            if name=='DATE':
                year=emit(f'Trunc({ns[0]}, 0)');month=emit(f'Trunc({ns[1]}, 0)');day=f'Trunc({ns[2]}, 0)'
                year=emit(iff(both(f'({year} >= 0)',f'({year} < 1900)'),f'({year} + 1900)',year))
                y=emit(f'({year} + Floor((({month} - 1) / 12)))');m=emit(f'({month} - (12 * Floor((({month} - 1) / 12))))')
                invalid=either(f'({y} < 1)',f'({y} > 9999)');e=merge_errors(e,iff(invalid,q('#NUM!'),EMPTY))
                start=emit(f'MakeDate(If({invalid}, 2000, {y}), {m}, 1)');v=f'({serial(start)} + {day} - 1)'
                # Moving across Feb 1900 must use serial arithmetic, intentionally.
            else:
                start=emit(f'Trunc({ns[0]}, 0)');phantom=eq(start,'60') if epoch=='1900' else 'False'
                e=merge_errors(e,iff(either(f'({start} < 0)',f'({start} > {2957003 if epoch=="1904" else 2958465})'),q('#NUM!'),EMPTY))
                date=emit(f'DateAdd("day", If({ne(e,EMPTY)}, 0, {start})'+(' - If('+start+' >= 60, 1, 0)' if epoch=='1900' else '')+f', Date({q(origin)}))')
                if name=='MONTH':v=iff(eq(start,'0'),'1',iff(phantom,'2',f'DatePart("month", {date})'))
                else:
                    months=emit(f'Trunc({ns[1]}, 0)')
                    targetyear=emit(f'(DatePart("year", {date}) + Floor(((DatePart("month", {date}) - 1 + {months}) / 12)))')
                    invalid=either(f'({targetyear} < 1)',f'({targetyear} > 9999)')
                    e=merge_errors(e,iff(invalid,q('#NUM!'),EMPTY))
                    shift=emit(f'DateAdd("month", If({invalid}, 0, {months}), {date})')
                    sy=emit(f'DatePart("year", {shift})');sm=emit(f'DatePart("month", {shift})')
                    leap=both(eq(f'Mod({sy}, 4)','0'),either(ne(f'Mod({sy}, 100)','0'),eq(f'Mod({sy}, 400)','0')))
                    monthdays=emit(iff(eq(sm,'2'),iff(leap,'29','28'),iff(either(*(eq(sm,str(m))for m in(4,6,9,11))),'30','31')))
                    if name=='EOMONTH':shift=emit(f'DateAdd("day", ({monthdays} - DatePart("day", {shift})), {shift})')
                    v=serial(shift)
                    if name=='EDATE' and epoch=='1900':
                        monthstart=emit(f'DateTrunc("month", {shift})')
                        monthend=emit(f'DateAdd("day", ({monthdays} - 1), {monthstart})')
                        phantomshift=emit(f'DateAdd("day", If(DatePart("day", {monthend}) < 29, DatePart("day", {monthend}), 29) - 1, {monthstart})')
                        v=iff(phantom,iff(eq(months,'0'),'60',serial(phantomshift)),v)
            e=merge_errors(e,iff(either(f'({v} < 0)',f'({v} > {2957003 if epoch=="1904" else 2958465})'),q('#NUM!'),EMPTY)) if name!='MONTH' else e
            return save(Scalar(number=v,error=e))
        raise UnsupportedExpression(f'function {name} requires exact native qualification')
    return run(node)


@dataclass(frozen=True)
class Fault:
    code: str

def evaluate_bound(node,reference,*,epoch='1900'):
    """Independent source evaluator. Range errors remain values until consumed."""
    def checked(v):
        if isinstance(v,Fault):raise ExcelCalcError(v.code)
        return v
    def number(v):
        v=checked(v)
        if v is None:return 0
        if isinstance(v,(int,float,bool)):return float(v) if isinstance(v,float) else int(v)
        if isinstance(v,str):
            try:return float(v.strip())
            except ValueError:raise ExcelCalcError('#VALUE!')
        raise ExcelCalcError('#VALUE!')
    def txt(v):
        v=checked(v)
        return '' if v is None else 'TRUE' if v is True else 'FALSE' if v is False else str(v)
    def equal(a,b):
        a,b=checked(a),checked(b)
        if a is None:a='' if isinstance(b,str) else 0
        if b is None:b='' if isinstance(a,str) else 0
        if isinstance(a,str) and isinstance(b,str):return a.lower()==b.lower()
        if type(a) is bool or type(b) is bool:return type(a) is type(b) and a==b
        return type(a) is not str and type(b) is not str and a==b
    def ordered(a,b,op):
        a,b=checked(a),checked(b)
        if a is None:a='' if isinstance(b,str) else False if type(b)is bool else 0
        if b is None:b='' if isinstance(a,str) else False if type(a)is bool else 0
        rank=lambda v:2 if type(v)is bool else 1 if isinstance(v,str) else 0
        if rank(a)!=rank(b):a,b=rank(a),rank(b)
        elif isinstance(a,str):a,b=a.lower(),b.lower()
        return {'<':lambda:a<b,'>':lambda:a>b,'<=':lambda:a<=b,'>=':lambda:a>=b}[op]()
    def match(v,c):
        v,c=checked(v),checked(c)
        op,target=_parse_criterion(c)
        if isinstance(target,str) and any(z in target for z in '*?~') and op in ('=','<>'):
            matched=isinstance(v,str) and re.fullmatch(wildcard_pattern(target),v,re.I) is not None
        elif target is None:matched=v is None or v==''
        elif isinstance(target,(int,float)) and not isinstance(target,bool) and isinstance(v,str) and re.fullmatch(NUMERIC_TEXT,v.strip()):matched=float(v)==target
        else:matched=equal(v,target)
        if op in ('=','<>'):return matched if op=='=' else not matched
        if v is None:return False
        if isinstance(v,str)!=isinstance(target,str):return False
        return ordered(v,target,op)
    def aslist(v):return v if isinstance(v,list) else [v]
    def flat(vs):
        for v in vs:yield from v if isinstance(v,list) else [v]
    def run(n):
        k=n['kind']
        if k=='number':return float(n['source']) if any(c in n['source'].lower() for c in '.e') else int(n['source'])
        if k in ('text','boolean'):return n['value']
        if k=='reference':return checked(reference(n['cell']))
        if k=='range':
            result=[]
            for c in n['cells']:
                try:result.append(reference(c))
                except ExcelCalcError as e:result.append(Fault(e.code))
            return result[0] if len(result)==1 and n.get('sourceKind','').endswith(':#this row') else result
        if k=='group':return run(n['expression'])
        if k=='indirect':
            s=txt(run(n['selector'])).lower()
            for name,target in n['alternatives']:
                if name.lower()==s:return run(target)
            raise ExcelCalcError('#REF!')
        if k in ('percent','unary'):
            v=number(run(n['operand']));return v*.01 if k=='percent' else v if n['operator']=='+' else -v
        if k=='binary':
            a,b=run(n['left']),run(n['right']);op=n['operator']
            if op=='&':return txt(a)+txt(b)
            if op in ('=','<>'):return equal(a,b) if op=='=' else not equal(a,b)
            if op in ('<','>','<=','>='):return ordered(a,b,op)
            a,b=number(a),number(b)
            if op=='/' and b==0:raise ExcelCalcError('#DIV/0!')
            return {'+':lambda:a+b,'-':lambda:a-b,'*':lambda:a*b,'/':lambda:a/b,'^':lambda:a**b}[op]()
        if k!='function':raise UnsupportedExpression(f'unsupported AST {k}')
        name,args=n['name'],n['arguments']
        if name=='IF':
            condition=run(args[0])
            if isinstance(condition,str):
                if condition.lower()not in('true','false'):raise ExcelCalcError('#VALUE!')
                condition=condition.lower()=='true'
            return run(args[1]) if condition else run(args[2]) if len(args)>2 else False
        if name=='IFERROR':
            try:return run(args[0])
            except ExcelCalcError:return run(args[1])
        vals=[]
        for ast in args:
            try:vals.append(run(ast))
            except ExcelCalcError as error:
                if name in ('COUNT','COUNTA') and ast['kind'] in ('reference','range') or name=='XLOOKUP' and len(vals)==3:vals.append(Fault(error.code))
                else:raise
        items=list(flat(vals))
        if name=='COUNTA':return sum(v is not None for v in items)
        if name=='COUNT':
            count=0
            for a,v in zip(args,vals):
                for x in aslist(v):
                    if type(x)in(int,float):count+=1
                    elif not isinstance(v,list) and a['kind']!='reference':
                        if type(x)is bool:count+=1
                        elif isinstance(x,str) and re.fullmatch(NUMERIC_TEXT,x.strip()):count+=1
            return count
        if name in ('SUM','MIN','MAX','AVERAGE'):
            nums=[]
            for a,v in zip(args,vals):
                referenced=isinstance(v,list) or a['kind']=='reference'
                for x in aslist(v):
                    checked(x)
                    if not referenced:nums.append(number(x))
                    elif type(x)in(int,float):nums.append(x)
            if name=='SUM':return sum(nums)
            if name=='MIN':return min(nums,default=0)
            if name=='MAX':return max(nums,default=0)
            if not nums:raise ExcelCalcError('#DIV/0!')
            return sum(nums)/len(nums)
        if name in ('AND','OR'):
            bools=[]
            for a,v in zip(args,vals):
                referenced=isinstance(v,list) or a['kind']=='reference'
                for x in aslist(v):
                    checked(x)
                    if referenced and (x is None or isinstance(x,str)):continue
                    if isinstance(x,str):
                        if x.lower()not in('true','false'):raise ExcelCalcError('#VALUE!')
                        x=x.lower()=='true'
                    bools.append(bool(x))
            if not bools:raise ExcelCalcError('#VALUE!')
            return all(bools) if name=='AND' else any(bools)
        if name in ('SUMIFS','COUNTIFS'):
            offset=int(name=='SUMIFS');ranges=vals[offset::2];criteria_values=vals[offset+1::2]
            if any(type(v)is bool for r in ranges for v in r) or any(type(v)is bool for v in criteria_values):raise UnsupportedExpression('Boolean criteria semantics await actual Excel oracle')
            if any(len(r)!=len(ranges[0]) for r in ranges):raise ExcelCalcError('#VALUE!')
            indices=[i for i in range(len(ranges[0])) if all(match(r[i],c) for r,c in zip(ranges,criteria_values))]
            if name=='COUNTIFS':return len(indices)
            if len(vals[0])!=len(ranges[0]):raise ExcelCalcError('#VALUE!')
            return sum(checked(vals[0][i]) for i in indices if type(checked(vals[0][i]))in(int,float))
        if name=='INDEX':
            vs=aslist(vals[0]);w=_width(args[0]) if args[0]['kind']=='range' else 1;r=int(number(vals[1]));c=int(number(vals[2])) if len(vals)>2 else 1
            if r>0 and c==0:
                if r>len(vs)//w:raise ExcelCalcError('#REF!')
                return vs[(r-1)*w:r*w]
            if r==0 and c>0:
                if c>w:raise ExcelCalcError('#REF!')
                return vs[c-1::w]
            i=(r-1)*w+c-1
            if r<1 or c<1 or c>w or i>=len(vs):raise ExcelCalcError('#REF!')
            value=checked(vs[i]);return 0 if value is None else value
        if name in ('MATCH','VLOOKUP','XLOOKUP'):
            if name=='MATCH':
                if len(vals)!=3 or vals[2]!=0:raise UnsupportedExpression('MATCH approximate mode requires review')
                keys=aslist(vals[1]);returns=list(range(1,len(keys)+1))
            elif name=='VLOOKUP':
                if len(vals)!=4 or vals[3]not in(False,0):raise UnsupportedExpression('VLOOKUP approximate mode requires review')
                w=_width(args[1]);c=int(number(vals[2]));vs=aslist(vals[1])
                if c<1 or c>w:raise ExcelCalcError('#REF!')
                keys=vs[::w];returns=vs[c-1::w]
            else:
                if len(vals)>=5 and vals[4]!=0:raise UnsupportedExpression('XLOOKUP approximate mode requires review')
                if len(vals)>=6 and vals[5]not in(1,-1):raise UnsupportedExpression('XLOOKUP binary search mode requires review')
                keys=aslist(vals[1]);returns=aslist(vals[2])
                if len(keys)!=len(returns):raise ExcelCalcError('#VALUE!')
                if len(vals)>=6 and vals[5]==-1:keys=keys[::-1];returns=returns[::-1]
            for key,value in zip(keys,returns):
                matches=equal(key,vals[0])
                if name in ('MATCH','VLOOKUP') and isinstance(vals[0],str) and isinstance(key,str):matches=re.fullmatch(wildcard_pattern(vals[0]),key,re.I)is not None
                if matches:return 0 if value is None else checked(value)
            if name=='XLOOKUP' and len(vals)>=4:return checked(vals[3])
            raise ExcelCalcError('#N/A')
        ns=[number(v) for v in vals]
        if name=='ABS':return abs(ns[0])
        if name=='INT':return math.floor(ns[0])
        if name in ('ROUND','ROUNDUP'):return float(Decimal(str(ns[0])).quantize(Decimal(1).scaleb(-int(ns[1])),rounding=ROUND_UP if name=='ROUNDUP' else ROUND_HALF_UP))
        if name=='MOD':
            if ns[1]==0:raise ExcelCalcError('#DIV/0!')
            return ns[0]%ns[1]
        if name=='CEILING':
            if ns[1]==0:return 0
            if ns[0]>0 and ns[1]<0:raise ExcelCalcError('#NUM!')
            return math.ceil(ns[0]/ns[1])*ns[1]
        if name=='SQRT':
            if ns[0]<0:raise ExcelCalcError('#NUM!')
            return math.sqrt(ns[0])
        if name in ('DATE','EDATE','EOMONTH','MONTH'):
            origin=datetime(1904,1,1) if epoch=='1904' else datetime(1899,12,31)
            def serial(d):return (d-origin).days+(1 if epoch=='1900' and d>=datetime(1900,3,1) else 0)
            if name=='DATE':
                y,m,d=map(int,ns)
                if 0<=y<1900:y+=1900
                y+=(m-1)//12;m=(m-1)%12+1
                try:return serial(datetime(y,m,1))+d-1
                except ValueError:raise ExcelCalcError('#NUM!')
            s=int(ns[0])
            if s<0:raise ExcelCalcError('#NUM!')
            start=origin+timedelta(days=s-(1 if epoch=='1900' and s>=60 else 0))
            if name=='MONTH':return 1 if s==0 else 2 if epoch=='1900' and s==60 else start.month
            m=start.month+int(ns[1]);y=start.year+(m-1)//12;m=(m-1)%12+1
            if not 1<=y<=9999:raise ExcelCalcError('#NUM!')
            d=calendar.monthrange(y,m)[1] if name=='EOMONTH' else min(29 if epoch=='1900' and s==60 else start.day,calendar.monthrange(y,m)[1])
            if name=='EDATE' and epoch=='1900' and s==60 and int(ns[1])==0:return 60
            return serial(datetime(y,m,d))
        raise UnsupportedExpression(f'custom-port obligation {name}; no numeric replacement')
    return run(node)
