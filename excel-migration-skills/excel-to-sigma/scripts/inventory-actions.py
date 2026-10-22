#!/usr/bin/env python3
"""Offline Inventory plan/readback CLI. It never executes SQL or Sigma writes."""
import argparse
import json
from pathlib import Path

from lib.inventory_controller import (InventoryControllerError, plan_demand_update,
    plan_refresh, plan_snapshot, plan_purchase_orders, verify_update,
    verify_append, verify_po_stage)


def _read(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('plan-adjust','plan-smooth','plan-refresh',
        'plan-snapshot','plan-po','verify-update','verify-append','verify-po'))
    parser.add_argument('--capture', required=True, help='complete current input capture or fresh post-write capture')
    parser.add_argument('--log', help='current independent Snapshots or PO_STAGE capture')
    parser.add_argument('--erp', help='isolated test-schema ERP query capture')
    parser.add_argument('--plan', help='previous plan for verify modes')
    parser.add_argument('--operation')
    parser.add_argument('--percent')
    parser.add_argument('--time')
    parser.add_argument('--invoker')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    current = _read(args.capture)
    try:
        if args.mode == 'plan-adjust':
            result = plan_demand_update(current, 'adjust', args.operation, percentage=args.percent)
        elif args.mode == 'plan-smooth':
            result = plan_demand_update(current, 'smooth', args.operation)
        elif args.mode == 'plan-refresh':
            result = plan_refresh(current, _read(args.erp), args.operation)
        elif args.mode == 'plan-snapshot':
            result = plan_snapshot(current, _read(args.log), args.operation, args.time, args.invoker)
        elif args.mode == 'plan-po':
            result = plan_purchase_orders(current, _read(args.log), args.operation)
        elif args.mode == 'verify-update':
            result = verify_update(_read(args.plan), current)
        elif args.mode == 'verify-append':
            result = verify_append(_read(args.plan), current)
        else:
            result = verify_po_stage(_read(args.plan), current)
    except (InventoryControllerError, ValueError, TypeError, OSError) as error:
        parser.error(str(error))
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
