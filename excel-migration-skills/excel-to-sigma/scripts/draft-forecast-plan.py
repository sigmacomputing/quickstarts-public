#!/usr/bin/env python3
"""Draft a build-forecast-model.py plan from a cell-drawn actuals + driver P&L workbook.

Reads the P&L (formulas + Excel's cached values), the GL actuals tab, and the drivers
tab; classifies each line's forecast as growth / flat / manual; re-derives every
line-month from the drafted plan and compares it with the workbook's cached values;
and writes a source-bound plan JSON. Any shape it does not recognise fails with the
offending cell instead of being coerced.

usage: draft-forecast-plan.py <xlsx> --intent what-if --connection <id> --folder <id> --out plan.json
Next:  build-forecast-model.py plan.json  (dry run), then  ... --post --review-dispositions review.json
"""
import argparse
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
from lib.forecast_plan import INTENTS, PlanDraftError, draft_plan  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("workbook")
    parser.add_argument("--intent", default="what-if", choices=INTENTS)
    parser.add_argument("--connection", required=True, help="write-enabled Sigma connectionId")
    parser.add_argument("--folder", required=True, help="target Sigma folderId")
    parser.add_argument("--name", help="workbook name (default: workbook title, else file stem)")
    parser.add_argument("--sheet", help="report sheet (default: most SUMIFS/driver-growth cells)")
    parser.add_argument("--currency-format", default="$,.0f")
    parser.add_argument("--pct-format", default=".1%")
    parser.add_argument("--tolerance", type=float, default=0.01,
                        help="absolute tolerance when re-deriving cached values (default: 0.01)")
    parser.add_argument("--out", required=True, help="plan JSON to write")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        plan, info = draft_plan(
            args.workbook, intent=args.intent, connection=args.connection, folder=args.folder,
            name=args.name, sheet=args.sheet, currency_format=args.currency_format,
            pct_format=args.pct_format, tolerance=args.tolerance)
    except PlanDraftError as error:
        print(f"DRAFT FAILED: {error}", file=sys.stderr)
        return 1
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    kinds = ", ".join(f"{k} {v}" for k, v in sorted(info["kinds"].items()))
    print(f"plan -> {out}")
    print(f"  {info['lines']} lines ({kinds}) | {info['glRows']} GL rows ({info['glSheet']}) "
          f"| {info['drivers']} drivers | intent={plan['intent']}")
    print(f"  months: {info['actualRange'][0]}-{info['actualRange'][1]} actual, "
          f"{info['forecastRange'][0]}-{info['forecastRange'][1]} forecast "
          f"(report sheet {info['reportSheet']!r})")
    print("  parity targets (" + (f"FY column {info['fyColumn']}" if info["fyColumn"] else "summed months")
          + "): " + ("  ".join(f"{k}={v:,.2f}" for k, v in info["parityTargets"].items()) or "none"))
    if info["missingTargets"]:
        print("  no target found for: " + ", ".join(info["missingTargets"]))
    print("  verified: every line-month and GL month sum matches the workbook's cached values")
    for chart in info["charts"]:
        print(f"  source chart mapped + values verified: {chart}")
    for chart in info["unmappedCharts"]:
        print(f"  source chart NOT mapped (rebuild by hand): {chart}")
    print("  review issues: " + (", ".join(info["reviewIssues"]) or "none from the drafter")
          + " (plus any workbook-audit issues; see migrate.py plan)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
