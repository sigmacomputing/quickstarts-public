"""Pure ports of the reviewed Inventory BAS. No VBA, Sigma, SQL, or I/O.

The source is the 72-row Demand table and six-row SKUs/Projection tables in
Inventory Replenishment Plan.xlsm (SHA256 461bee7b...). Rows retain worksheet
ordinals so a controller can bind them to current physical input-table IDs.
"""
from __future__ import annotations

import copy
import math
from datetime import datetime
from decimal import Decimal


class InventoryBehaviorError(ValueError):
    pass


def _number(value, *, blank_zero=True):
    if value is None and blank_zero:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise InventoryBehaviorError('INVALID_NUMERIC_CELL')
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise InventoryBehaviorError('INVALID_NUMERIC_CELL') from None
    if not math.isfinite(number):
        raise InventoryBehaviorError('NONFINITE_OR_OVERFLOW')
    return number


def _rounded(number):
    if not math.isfinite(number):
        raise InventoryBehaviorError('NONFINITE_OR_OVERFLOW')
    # VBA.Round(x, 0) is ties-to-even on a Double; Python's round(float)
    # implements the same tie rule. Avoid Excel/Sigma ROUND assumptions.
    return round(number)


def _source_rows(rows, start, count):
    if not isinstance(rows, list) or len(rows) != count:
        raise InventoryBehaviorError('SOURCE_ROW_COUNT_MISMATCH')
    for ordinal, row in enumerate(rows, start):
        if not isinstance(row, dict) or row.get('Source Row') != ordinal:
            raise InventoryBehaviorError('SOURCE_ORDINAL_MISMATCH')
        if not isinstance(row.get('SKU'), str) or not row['SKU']:
            raise InventoryBehaviorError('INVALID_SKU')
    return rows


def _demand(rows):
    _source_rows(rows, 2, 72)
    for row in rows:
        if not isinstance(row.get('Week Start'), str) or not row['Week Start']:
            raise InventoryBehaviorError('INVALID_WEEK_START')
        _number(row.get('Forecast Units'))
    return rows


def _percentage(value):
    if isinstance(value, bool) or value is None:
        raise InventoryBehaviorError('INVALID_PERCENTAGE')
    if isinstance(value, str):
        if not value.strip():
            raise InventoryBehaviorError('INVALID_PERCENTAGE')
        try:
            value = float(value)
        except ValueError:
            raise InventoryBehaviorError('INVALID_PERCENTAGE') from None
    return _number(value, blank_zero=False)


def adjust_demand(rows, percentage):
    """Apply one CDbl(InputBox) value to every Forecast Units cell in row order."""
    _demand(rows)
    pct = _percentage(percentage)
    factor = 1 + pct / 100
    if not math.isfinite(factor):
        raise InventoryBehaviorError('NONFINITE_OR_OVERFLOW')
    changed = copy.deepcopy(rows)
    for row in changed:
        row['Forecast Units'] = _rounded(_number(row.get('Forecast Units')) * factor)
    return changed


def smooth_demand(rows):
    """Port i=3..73, comparing adjacent SKUs and reading prior UPDATED units."""
    _demand(rows)
    changed = copy.deepcopy(rows)
    for i in range(1, len(changed)):
        if changed[i]['SKU'] == changed[i-1]['SKU']:
            current = _number(changed[i].get('Forecast Units'))
            previous = _number(changed[i-1].get('Forecast Units'))
            changed[i]['Forecast Units'] = _rounded(.3 * current + (1 - .3) * previous)
    return changed


def snapshot_forecast(rows, operation_id, committed_at, invoker):
    """One immutable append payload per intent, including all 72 current rows."""
    _demand(rows)
    if not isinstance(operation_id, str) or not operation_id.strip() or operation_id != operation_id.strip():
        raise InventoryBehaviorError('INVALID_OPERATION_ID')
    if not isinstance(invoker, str) or not invoker.strip():
        raise InventoryBehaviorError('AUTHENTICATED_INVOKER_REQUIRED')
    if not isinstance(committed_at, str) or not committed_at.endswith('Z'):
        raise InventoryBehaviorError('INVALID_OPERATION_TIME')
    try:
        datetime.fromisoformat(committed_at.replace('Z', '+00:00'))
    except ValueError:
        raise InventoryBehaviorError('INVALID_OPERATION_TIME') from None
    return [{'Operation ID': operation_id, 'Source Row': row['Source Row'],
             'Committed At': committed_at, 'SKU': row['SKU'],
             'Week Start': row['Week Start'], 'Forecast Units': row['Forecast Units'],
             'Committed By': invoker} for row in rows]


def refresh_on_hand(skus, erp_rows):
    """Approved repair: update only On Hand by exact SKU, preserving Description."""
    _source_rows(skus, 2, 6)
    if not isinstance(erp_rows, list) or len(erp_rows) != len(skus):
        raise InventoryBehaviorError('ERP_KEYSET_MISMATCH')
    keys = [r['SKU'] for r in skus]
    if len(set(keys)) != len(keys):
        raise InventoryBehaviorError('DUPLICATE_SKU')
    erp = {}
    for row in erp_rows:
        if not isinstance(row, dict) or not isinstance(row.get('SKU'), str) or row['SKU'] in erp:
            raise InventoryBehaviorError('ERP_DUPLICATE_OR_MISSING_SKU')
        _number(row.get('On Hand'), blank_zero=False)
        erp[row['SKU']] = row['On Hand']
    if set(erp) != set(keys):
        raise InventoryBehaviorError('ERP_KEYSET_MISMATCH')
    changed = copy.deepcopy(skus)
    for row in changed:
        row['On Hand'] = erp[row['SKU']]
    return changed


def select_purchase_orders(projection_rows):
    """Exactly Projection rows 4..9; VBA uses literal case-sensitive ORDER."""
    _source_rows(projection_rows, 4, 6)
    if len({r['SKU'] for r in projection_rows}) != 6:
        raise InventoryBehaviorError('DUPLICATE_PROJECTION_SKU')
    selected = []
    for row in projection_rows:
        if row.get('Reorder?') == 'ORDER':
            quantity = _number(row.get('Suggested Qty'), blank_zero=False)
            if not quantity.is_integer() or abs(quantity) > 2**53 - 1:
                raise InventoryBehaviorError('NON_WHOLE_PO_QUANTITY')
            selected.append({'Source Row': row['Source Row'], 'SKU': row['SKU'],
                             'Quantity': int(quantity)})
    return selected
