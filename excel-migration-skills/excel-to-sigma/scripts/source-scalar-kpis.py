#!/usr/bin/env python3
"""Prepare source scalar contracts, native append programs and assigned-ID bindings.

Offline only: this command has no credentials, network calls or Sigma mutation.
See refs/source-scalar-kpis.md for observation/identity schemas and runtime gates.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'lib'))
from source_scalar_kpis import (extract_sales_overview_scalars,
                                plan_native_scalar_append, bind_native_scalar_owners)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('source')
    prepare.add_argument('--out', required=True)
    plan = commands.add_parser('plan')
    for field in ('contract', 'identity', 'snapshot', 'out'):
        plan.add_argument('--' + field, required=True)
    plan.add_argument('--ownership')
    bind = commands.add_parser('bind')
    for field in ('plan', 'snapshot', 'assignments', 'out'):
        bind.add_argument('--' + field, required=True)
    args = parser.parse_args(argv)
    read = lambda path: json.loads(Path(path).read_text(encoding='utf-8'))
    if args.command == 'prepare':
        result = extract_sales_overview_scalars(args.source)
    elif args.command == 'plan':
        result = plan_native_scalar_append(read(args.contract), read(args.identity), read(args.snapshot),
                                           ownership=read(args.ownership) if args.ownership else None)
    else:
        result = bind_native_scalar_owners(read(args.plan), read(args.snapshot), read(args.assignments))
    Path(args.out).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
