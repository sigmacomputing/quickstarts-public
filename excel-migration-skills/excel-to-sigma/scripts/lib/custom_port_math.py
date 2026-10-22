"""Standalone standard-library port kernel, embedded verbatim in warehouse programs.

No persistence or Sigma construction calls occur here. Numeric fingerprints use
IEEE double conversion and .17g canonical strings (including a single zero),
matching the Double arithmetic of the controlled VBA source.
"""
import hashlib
import json
import math
from decimal import Decimal

DEPARTMENTS = ('Eng', 'Sales', 'G&A', 'Support')
MONTHS = ('Jul-26', 'Aug-26', 'Sep-26', 'Oct-26', 'Nov-26', 'Dec-26')
SIGNS = {'Revenue': 1, 'Cost of Revenue': -1, 'Operating Expenses': -1, 'Below the Line': -1}
SUBSCRIPTION = 'Subscription Revenue'


class PortError(ValueError):
    pass


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise PortError('INVALID_NUMBER')
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise PortError('INVALID_NUMBER')
    if not math.isfinite(result):
        raise PortError('NON_FINITE')
    return result


def operation(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip() or '|' in value:
        raise PortError('INVALID_OPERATION_ID')
    return value


def canonical(value):
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = finite(value)
        return {'double': '0' if number == 0 else format(number, '.17g')}
    if value is None or isinstance(value, (str, bool)):
        return value
    raise PortError('UNSUPPORTED_CANONICAL_VALUE')


def fingerprint(value):
    return hashlib.sha256(json.dumps(canonical(value), sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def allocate_overhead(headcounts, overhead, operation_id):
    empty = dict(OperationId=operation_id, Status='FAILURE', ErrorCode=None,
                 Department=None, SourceIndex=None, Headcount=None, Overhead=None, Allocation=None)
    try:
        operation(operation_id)
        if len(headcounts) != 4:
            raise PortError('INVALID_HEADCOUNT_ROWS')
        counts = [finite(v) for v in headcounts]
        cost = finite(overhead)
        if min(counts) < 0 or cost < 0:
            raise PortError('NEGATIVE_INPUT')
        total = finite(sum(counts))
        if total <= 0:
            raise PortError('ZERO_HEADCOUNT')
        amounts = [finite((hc/total)*cost*(1 + .5*math.sin(i)))
                   for i, hc in enumerate(counts, 1)]
        return [dict(OperationId=operation_id, Status='SUCCESS', ErrorCode=None,
                     Department=dept, SourceIndex=i, Headcount=hc, Overhead=cost, Allocation=amount)
                for i, (dept, hc, amount) in enumerate(zip(DEPARTMENTS, counts, amounts), 1)]
    except (PortError, TypeError, OverflowError) as error:
        empty['ErrorCode'] = str(error) if isinstance(error, PortError) else 'INVALID_INPUT'
        return [empty]


def keyed(rows, key):
    result = {}
    for row in rows:
        name = row.get(key)
        if not isinstance(name, str) or not name or name in result:
            raise PortError('MISSING_OR_DUPLICATE_KEY')
        result[name] = row
    return result


def prepare_model(actuals, inputs, definitions):
    ins, defs = keyed(inputs, 'Line Item'), keyed(definitions, 'Line Item')
    if not ins or set(ins) != set(defs) or SUBSCRIPTION not in ins:
        raise PortError('INVALID_MODEL_KEYS')
    row_ids = [r.get('Input Row ID') for r in inputs]
    if any(not isinstance(r, str) or not r for r in row_ids) or len(set(row_ids)) != len(row_ids):
        raise PortError('INVALID_ROW_ID')
    bases, coverage, normalized_actuals = {}, set(), []
    actual_income = 0.0
    for row in actuals:
        line, month, section = row.get('Line Item'), row.get('Month'), row.get('Section')
        if line not in defs or section != defs[line].get('Section') or section not in SIGNS:
            raise PortError('INVALID_ACTUAL_LINE')
        if month not in ('Jan-26','Feb-26','Mar-26','Apr-26','May-26','Jun-26'):
            raise PortError('INVALID_ACTUAL_MONTH')
        amount = finite(row.get('Amount'))
        actual_income = finite(actual_income + SIGNS[section]*amount)
        coverage.add((line, month))
        if month == 'Jun-26':
            bases[line] = finite(bases.get(line, 0) + amount)
        normalized_actuals.append({'Line Item': line, 'Month': month, 'Section': section, 'Amount': amount})
    expected = {(line, month) for line in ins for month in
                ('Jan-26','Feb-26','Mar-26','Apr-26','May-26','Jun-26')}
    if coverage != expected:
        raise PortError('MISSING_ACTUAL_PERIOD')
    normalized_inputs = []
    for line, row in sorted(ins.items()):
        if defs[line].get('Section') not in SIGNS or row.get('Method') not in ('manual', 'growth', 'flat'):
            raise PortError('INVALID_METHOD_OR_SECTION')
        method = row['Method']
        if method == 'growth':
            rate = finite(row.get('Monthly Growth'))
            if rate <= -1:
                raise PortError('INVALID_GROWTH')
        elif row.get('Monthly Growth') is not None:
            raise PortError('UNEXPECTED_GROWTH')
        for month in MONTHS:
            if method == 'manual':
                finite(row.get(month))
            elif row.get(month) is not None:
                raise PortError('UNEXPECTED_MANUAL')
        normalized_inputs.append({k: row.get(k) for k in
            ('Line Item', 'Input Row ID', 'Method', 'Monthly Growth', *MONTHS)})
    if ins[SUBSCRIPTION]['Method'] != 'growth' or bases[SUBSCRIPTION] <= 0:
        raise PortError('ZERO_SENSITIVITY')
    normalized_actuals.sort(key=lambda r: json.dumps(canonical(r), sort_keys=True))
    normalized_defs = [{'Line Item': line, 'Section': row['Section']} for line, row in sorted(defs.items())]
    normalized = dict(actuals=normalized_actuals, inputs=normalized_inputs, definitions=normalized_defs)
    return ins, defs, bases, actual_income, normalized


def annual_net_income(model, growth):
    ins, defs, bases, actual, _ = model
    growth = finite(growth)
    amounts = [actual]
    for line, row in sorted(ins.items()):
        for n, month in enumerate(MONTHS, 1):
            if row['Method'] == 'manual':
                amount = finite(row[month])
            elif row['Method'] == 'flat':
                amount = bases[line]
            else:
                rate = growth if line == SUBSCRIPTION else finite(row['Monthly Growth'])
                amount = finite(bases[line] * (1 + rate)**n)
            amounts.append(SIGNS[defs[line]['Section']]*amount)
    return finite(sum(amounts))


def request_contract(request, expected_binding):
    operation(request.get('OperationId'))
    if not expected_binding or request.get('ModelBinding') != expected_binding:
        raise PortError('MODEL_BINDING_MISMATCH')
    if request.get('RequestKey', 'goal-seek') != 'goal-seek' or request.get('State') not in ('PENDING','APPLY_PENDING','APPLIED'):
        raise PortError('INVALID_REQUEST')
    target = finite(request.get('Target'))
    lower, upper = finite(request.get('LowerBound')), finite(request.get('UpperBound'))
    tolerance = finite(request.get('ToleranceCents')) / 100
    maximum = finite(request.get('MaxIterations'))
    if not (0 <= lower < upper <= .25 and tolerance == .01 and maximum.is_integer() and 1 <= maximum <= 64):
        raise PortError('INVALID_REQUEST')
    return target, lower, upper, tolerance, int(maximum)


def model_fingerprint(model, request):
    return fingerprint({'model': model[-1], 'request': {k: request.get(k) for k in
        ('ModelBinding','Target','LowerBound','UpperBound','ToleranceCents','MaxIterations')}})


def solve_forecast(actuals, inputs, definitions, request, *, expected_binding):
    result = dict(OperationId=request.get('OperationId'), Status='FAILURE', ErrorCode=None,
        ModelBinding=request.get('ModelBinding'), InputFingerprint=None, Target=request.get('Target'),
        LowerBound=request.get('LowerBound'), UpperBound=request.get('UpperBound'), LowerNetIncome=None,
        UpperNetIncome=None, SolvedGrowth=None, SolvedNetIncome=None, Residual=None, Iterations=0,
        ToleranceCents=request.get('ToleranceCents'), GrowthPrecisionDigits=12, Converged=False, Endpoint=False,
        SubscriptionRowId=None, PreviousGrowth=None)
    try:
        target, lower, upper, tolerance, maximum = request_contract(request, expected_binding)
        model = prepare_model(actuals, inputs, definitions)
        result.update(InputFingerprint=model_fingerprint(model, request),
                      SubscriptionRowId=model[0][SUBSCRIPTION]['Input Row ID'],
                      PreviousGrowth=finite(model[0][SUBSCRIPTION]['Monthly Growth']))
        lo, hi = annual_net_income(model, lower), annual_net_income(model, upper)
        result.update(LowerNetIncome=lo, UpperNetIncome=hi)
        if lo == hi:
            raise PortError('ZERO_SENSITIVITY')
        if abs(lo-target) <= tolerance:
            candidate = lower; result['Endpoint'] = True
        elif abs(hi-target) <= tolerance:
            candidate = upper; result['Endpoint'] = True
        else:
            if (lo-target)*(hi-target) >= 0:
                raise PortError('INVALID_BRACKET')
            for iteration in range(1, maximum+1):
                candidate = (lower+upper)/2
                value = annual_net_income(model, candidate)
                result['Iterations'] = iteration
                if abs(value-target) <= tolerance:
                    break
                if (value-target)*(lo-target) > 0:
                    lower, lo = candidate, value
                else:
                    upper = candidate
            else:
                raise PortError('ITERATION_LIMIT')
        candidate = round(candidate, 12)
        value = annual_net_income(model, candidate)
        if not request['LowerBound'] <= candidate <= request['UpperBound'] or abs(value-target) > tolerance:
            raise PortError('ROUNDED_SOLUTION_OUT_OF_TOLERANCE')
        result.update(Status='SUCCESS', Converged=True, SolvedGrowth=candidate,
                      SolvedNetIncome=value, Residual=value-target)
    except (PortError, KeyError, TypeError, OverflowError, ValueError) as error:
        result['ErrorCode'] = str(error) if isinstance(error, PortError) else 'INVALID_MODEL'
    return result


def guard_goal_seek(actuals, inputs, definitions, request, result, *, expected_binding):
    guard = dict(OperationId=request.get('OperationId'), ResultOperationId=result.get('OperationId'),
        ModelBinding=request.get('ModelBinding'), ResultFingerprint=result.get('InputFingerprint'),
        CurrentFingerprint=None, SubscriptionRowId=None, PreviousGrowth=result.get('PreviousGrowth'),
        CurrentGrowth=None, SolvedGrowth=None, RecomputedNetIncome=None, Residual=None,
        ReadyToApply=False, ErrorCode=None)
    try:
        target, lower, upper, tolerance, _ = request_contract(request, expected_binding)
        model = prepare_model(actuals, inputs, definitions)
        current = model[0][SUBSCRIPTION]
        current_fp = model_fingerprint(model, request)
        guard.update(CurrentFingerprint=current_fp, SubscriptionRowId=current['Input Row ID'],
                     CurrentGrowth=finite(current['Monthly Growth']))
        if not (request['State'] == 'APPLY_PENDING' and result.get('Status') == 'SUCCESS'
                and result.get('Converged') is True and result.get('OperationId') == request['OperationId']
                and result.get('ModelBinding') == expected_binding and result.get('InputFingerprint') == current_fp
                and result.get('SubscriptionRowId') == current['Input Row ID']
                and finite(result.get('PreviousGrowth')) == finite(current['Monthly Growth'])
                and result.get('GrowthPrecisionDigits') == 12 and result.get('Target') == target):
            raise PortError('STALE_OR_UNCONVERGED_RESULT')
        growth = finite(result.get('SolvedGrowth'))
        value = annual_net_income(model, growth)
        if not lower <= growth <= upper or growth != round(growth,12) or abs(value-target) > tolerance:
            raise PortError('INVALID_SOLUTION')
        guard.update(SolvedGrowth=growth, RecomputedNetIncome=value, Residual=value-target, ReadyToApply=True)
    except (PortError, KeyError, TypeError, OverflowError, ValueError) as error:
        guard['ErrorCode'] = str(error) if isinstance(error, PortError) else 'INVALID_MODEL'
    return guard


def plan_goal_seek_write(actuals, inputs, definitions, request, result, *, expected_binding):
    # A retry is a no-op only after validating the exact post-write input graph:
    # restore the prior candidate in memory and check its original fingerprint.
    if request.get('State') == 'APPLIED':
        operation(request.get('OperationId'))
        model = prepare_model(actuals, inputs, definitions)
        row = model[0][SUBSCRIPTION]
        if not (request.get('OperationId') == request.get('AppliedOperationId') == result.get('OperationId')
                and finite(row['Monthly Growth']) == finite(request.get('AppliedGrowth')) == finite(result.get('SolvedGrowth'))):
            raise PortError('INVALID_RETRY')
        restored = [dict(r) for r in inputs]
        next(r for r in restored if r['Line Item'] == SUBSCRIPTION)['Monthly Growth'] = result.get('PreviousGrowth')
        check = guard_goal_seek(actuals, restored, definitions, {**request, 'State':'APPLY_PENDING'}, result,
                               expected_binding=expected_binding)
        if not check['ReadyToApply']:
            raise PortError('INVALID_RETRY')
        return None
    check = guard_goal_seek(actuals, inputs, definitions, request, result, expected_binding=expected_binding)
    if not check['ReadyToApply']:
        raise PortError(check['ErrorCode'])
    return {'operationId': request['OperationId'], 'rowId': check['SubscriptionRowId'],
            'key': {'Line Item': SUBSCRIPTION}, 'values': {'Monthly Growth': check['SolvedGrowth']}}


def verify_goal_seek_write(before, after, change):
    if set(change.get('values',{})) != {'Monthly Growth'} or change.get('key') != {'Line Item':SUBSCRIPTION}:
        raise PortError('WRITE_CONTRACT_MISMATCH')
    expected = [dict(r) for r in before]
    matches = [r for r in expected if r.get('Input Row ID') == change['rowId']
               and r.get('Line Item') == SUBSCRIPTION]
    if len(matches) != 1:
        raise PortError('WRITE_TARGET_MISMATCH')
    actual = [r for r in after if r.get('Input Row ID') == change['rowId']]
    if len(actual) != 1:
        raise PortError('WRITE_TARGET_MISMATCH')
    planned = finite(change['values']['Monthly Growth'])
    finite(actual[0].get('Monthly Growth'))
    if Decimal(str(actual[0]['Monthly Growth'])) != Decimal(str(change['values']['Monthly Growth'])) or planned != round(planned,12):
        raise PortError('WRITE_READBACK_MISMATCH')
    matches[0]['Monthly Growth'] = actual[0]['Monthly Growth']
    sort = lambda rows: sorted(rows, key=lambda r:r['Input Row ID'])
    if sort(after) != sort(expected):
        raise PortError('WRITE_READBACK_MISMATCH')
    return {'status':'VERIFIED_COMPONENT_WRITE', 'operationId':change['operationId'],
            'beforeHash':fingerprint(sort(before)), 'afterHash':fingerprint(sort(after)), 'productionStatus':'BLOCKED'}
