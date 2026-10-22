#!/usr/bin/env python3
"""Extract and emit source-bound Sigma presentation fragments.

With ``--contents`` this is an actual full-contents builder: it fails if runtime
IDs are absent, merges pages/elements/layout and column/rule patches, and emits a
version-guarded PUT body. It performs no network calls.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(LIB))

import code_rep  # noqa: E402
from presentation import (  # noqa: E402
    audit_presentation_openapi,
    emit_presentation,
    extract_presentation,
    fixture_bindings,
    integrate_presentation,
)


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="source .xlsx")
    parser.add_argument("--bindings", help="runtime element/column binding JSON")
    parser.add_argument("--fixture-bindings", action="store_true",
                        help="use logical bindings for the five synthetic fixtures")
    parser.add_argument("--contents", help="GET-back workbook response or contents JSON")
    parser.add_argument("--manifest", help="immutable source/plan/target migration manifest")
    parser.add_argument("--staging-receipt", help="APPROVED_STAGING receipt bound to the manifest")
    parser.add_argument("--document-version", type=int, help="required with --contents")
    parser.add_argument("--plan-out", help="write extraction plan JSON")
    parser.add_argument("--openapi", help="current Sigma OpenAPI JSON to audit before emission")
    parser.add_argument("--out", required=True, help="write artifact or PUT body JSON")
    args = parser.parse_args(argv)

    plan = extract_presentation(args.source)
    if args.openapi:
        audit = audit_presentation_openapi(_read(args.openapi))
        if audit["status"] != "PASS":
            raise SystemExit("presentation OpenAPI drift: " + ", ".join(audit["missing"]))
    if args.plan_out:
        Path(args.plan_out).write_text(json.dumps(plan, indent=2, default=str) + "\n", encoding="utf-8")
    if args.bindings:
        bindings = _read(args.bindings)
    elif args.fixture_bindings:
        bindings = fixture_bindings(plan)
    else:
        parser.error("--bindings or --fixture-bindings is required")
    if not args.fixture_bindings and (not args.manifest or not args.staging_receipt):
        parser.error("actual bindings require --manifest and --staging-receipt")
    artifact = emit_presentation(
        plan, bindings,
        _read(args.manifest) if args.manifest else None,
        _read(args.staging_receipt) if args.staging_receipt else None,
        logical_fixture=args.fixture_bindings,
    )

    output = artifact
    if args.contents:
        if args.fixture_bindings:
            parser.error("--fixture-bindings produces logical IDs and cannot be used with --contents")
        if args.document_version is None:
            parser.error("--document-version is required with --contents")
        current = _read(args.contents)
        contents = code_rep.document(current)
        if not contents:
            parser.error("--contents does not contain workbook contents")
        output = {
            "documentVersion": args.document_version,
            "contents": integrate_presentation(contents, artifact),
            "presentationArtifactHash": artifact["artifactHash"],
            "sourceHash": artifact["sourceHash"],
        }
    Path(args.out).write_text(json.dumps(output, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({
        "workflow": plan["workflow"], "charts": len(plan["charts"]),
        "validations": len(plan["validations"]),
        "conditionalFormats": len(plan["conditionalFormats"]),
        "formulas": len(plan["formulaProvenance"]),
        "unresolved": len(artifact["unresolved"]), "artifactHash": artifact["artifactHash"],
        "output": str(Path(args.out).resolve()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
