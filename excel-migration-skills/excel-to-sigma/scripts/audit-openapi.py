#!/usr/bin/env python3
"""Verify that Sigma's live workbook OpenAPI still supports this converter."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(LIB))

from openapi_audit import DEFAULT_OPENAPI_URL, audit_openapi, fetch_openapi  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="local compiled OpenAPI JSON; default fetches live")
    parser.add_argument("--url", default=DEFAULT_OPENAPI_URL)
    parser.add_argument("--out", help="write JSON audit result")
    args = parser.parse_args(argv)

    if args.source:
        document = json.loads(Path(args.source).read_text(encoding="utf-8"))
    else:
        document = fetch_openapi(args.url)
    report = audit_openapi(document)
    rendered = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    print(
        f"{report['status']}: Sigma OpenAPI {report['openapiVersion']} "
        f"({len(report['missing'])} missing contract(s))",
        file=sys.stderr,
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
