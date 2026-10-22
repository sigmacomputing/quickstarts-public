#!/usr/bin/env python3
"""Inventory an .xlsx/.xlsm and fail loudly on features needing disposition."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(LIB))

from xlsx_audit import audit_workbook, dumps  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook")
    parser.add_argument("--out", help="write the complete JSON routing manifest")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 for REVIEW_REQUIRED (production gate); default exits 0 so review "
             "issues are reported, not fatal",
    )
    # Kept for CI and older docs; REVIEW_REQUIRED already exits 0 unless --strict.
    parser.add_argument("--allow-review", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    report = audit_workbook(args.workbook)
    rendered = dumps(report)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    print(
        f"{report['status']}: {args.workbook} "
        f"({len(report['issues'])} routed issue(s))",
        file=sys.stderr,
    )
    if report["status"] == "BLOCKED":
        return 2
    if report["status"] == "REVIEW_REQUIRED" and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
