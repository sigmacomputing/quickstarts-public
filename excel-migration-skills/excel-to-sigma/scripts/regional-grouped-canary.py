#!/usr/bin/env python3
"""Emit the source-bound Regional01 B4 grouped canary; no target calls."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from lib.regional_grouped_canary import (build_candidate, reference_b4, source_rows,
    validate_reviewed_candidate)


def _guard_output(args):
    for name in ("source", "input_plan", "native_plan", "excel_oracles"):
        source = getattr(args, name)
        if (args.out.resolve() == source.resolve() or
                (args.out.exists() and source.exists() and os.path.samefile(args.out, source))):
            raise ValueError("regional grouped output aliases input artifact: " + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--input-plan", type=Path, required=True)
    parser.add_argument("--native-plan", type=Path, required=True)
    parser.add_argument("--excel-oracles", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    _guard_output(args)
    inputs = json.loads(args.input_plan.read_text())
    native = json.loads(args.native_plan.read_text())
    oracles = (json.loads(line) for line in args.excel_oracles.read_text().splitlines())
    oracle = next((record for record in oracles if record.get("sourceFile") == native["sourcePath"].rsplit("/", 1)[-1]
                   and record.get("sheet") == "Summary" and record.get("address") == "B4"), None)
    if oracle is None:
        raise ValueError("source-matched Excel B4 oracle is missing")
    candidate = build_candidate(args.source, inputs, native, oracle)
    validate_reviewed_candidate(candidate)
    if str(reference_b4(source_rows(inputs), "West")) != oracle["numericValue"]:
        raise ValueError("independent decimal source-row B4 baseline differs from Excel")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _guard_output(args)
    args.out.write_text(json.dumps(candidate, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": candidate["status"], "sourceCell": "Summary!B4",
                      "budget": candidate["constructionBudget"],
                      "excelOracle": candidate["excelOracle"], "out": str(args.out)}))


if __name__ == "__main__":
    main()
