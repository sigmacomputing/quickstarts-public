#!/usr/bin/env python3
"""Emit the isolated Regional B4 two-input fixture plan; no Sigma calls."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from lib.regional_canary_inputs import build_canary_input_plan, validate_reviewed_input_plan


def _guard_output(args):
    for name in ("source", "base_input_plan", "candidate"):
        source = getattr(args, name)
        if (args.out.resolve() == source.resolve() or
                (args.out.exists() and source.exists() and os.path.samefile(args.out, source))):
            raise ValueError("regional canary output aliases input artifact: " + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--base-input-plan", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    _guard_output(args)
    plan = build_canary_input_plan(args.source,
        json.loads(args.base_input_plan.read_text()), json.loads(args.candidate.read_text()))
    validate_reviewed_input_plan(plan)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _guard_output(args)
    args.out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": plan["status"], "features": {name: len(spec["rows"])
            for name, spec in plan["features"].items()},
            "pendingFormulaCells": len(plan["pendingFormulaCellIds"]), "out": str(args.out)}))


if __name__ == "__main__":
    main()
