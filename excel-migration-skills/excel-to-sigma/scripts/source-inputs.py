#!/usr/bin/env python3
"""Build a reviewed ordinary-input plan or inspect an explicit source unpivot."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from source_inputs import build_source_input_plan  # noqa: E402
from source_reshape import unpivot_source_table  # noqa: E402


def _guard_output(args):
    output = Path(args.out)
    for name in ("source", "decisions", "axis_values"):
        value = getattr(args, name, None)
        if value:
            source = Path(value)
            if (output.resolve() == source.resolve() or
                    (output.exists() and source.exists() and os.path.samefile(output, source))):
                raise ValueError("source input output aliases input artifact: " + name)


def _write(args, payload):
    _guard_output(args)
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--source", required=True); plan.add_argument("--decisions", required=True)
    plan.add_argument("--connection", required=True); plan.add_argument("--folder", required=True)
    plan.add_argument("--out", required=True)
    reshape = commands.add_parser("unpivot")
    reshape.add_argument("--source", required=True); reshape.add_argument("--sheet", required=True)
    reshape.add_argument("--table", required=True); reshape.add_argument("--key-column", action="append", required=True)
    reshape.add_argument("--value-column", action="append", required=True)
    reshape.add_argument("--axis-name", required=True); reshape.add_argument("--value-name", required=True)
    reshape.add_argument("--axis-values"); reshape.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    _guard_output(args)
    if args.command == "plan":
        payload = build_source_input_plan(args.source, args.decisions,
                                          connection_id=args.connection, folder_id=args.folder)
    else:
        axis = json.loads(Path(args.axis_values).read_text(encoding="utf-8")) if args.axis_values else None
        payload = unpivot_source_table(args.source, sheet=args.sheet, table=args.table,
                                       key_columns=args.key_column, value_columns=args.value_column,
                                       axis_name=args.axis_name, value_name=args.value_name,
                                       axis_values=axis)
    _write(args, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
