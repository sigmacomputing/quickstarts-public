#!/usr/bin/env python3
"""Inventory any OOXML workbook and emit reviewed native presentation specs."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(LIB))

import code_rep  # noqa: E402
import presentation  # noqa: E402
from source_presentation import build_source_plan, emit_approved, emit_preview  # noqa: E402


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n",
                          encoding="utf-8")


def _aliases(first, second):
    first, second = Path(first), Path(second)
    return (first.resolve() == second.resolve() or
            (first.exists() and second.exists() and os.path.samefile(first, second)))


def _guard_outputs(args):
    for name in ("source", "bindings", "manifest", "approval", "staging_receipt",
                 "openapi", "contents"):
        source = getattr(args, name)
        if source and (_aliases(source, args.out) or
                       (args.plan_out and _aliases(source, args.plan_out))):
            raise ValueError("presentation output aliases input artifact: " + name)
    if args.plan_out and _aliases(args.out, args.plan_out):
        raise ValueError("plan and result output paths alias")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="source .xlsx or .xlsm")
    parser.add_argument("--bindings", help="reviewed source-point to live-target facts")
    parser.add_argument("--preview", action="store_true", help="logical preview only; never a PUT")
    parser.add_argument("--manifest", help="source/plan-bound migration manifest")
    parser.add_argument("--approval", help="named staging approval")
    parser.add_argument("--staging-receipt", help="shared-gate APPROVED_STAGING receipt")
    parser.add_argument("--openapi", help="current OpenAPI document for chart spec audit")
    parser.add_argument("--contents", help="complete current GET/readback document")
    parser.add_argument("--plan-out", help="also save the source presentation plan")
    parser.add_argument("--out", required=True, help="save plan, preview, artifact, or PUT body")
    args = parser.parse_args(argv)
    if args.preview and args.contents:
        parser.error("logical preview cannot be integrated into a PUT body")
    if args.contents and not args.bindings:
        parser.error("--contents requires --bindings")
    _guard_outputs(args)
    plan = build_source_plan(args.source)
    if not args.bindings:
        result = plan
    else:
        bindings = _read(args.bindings)
        if args.preview:
            result = emit_preview(plan, bindings)
        else:
            required = {"--manifest": args.manifest, "--approval": args.approval,
                        "--staging-receipt": args.staging_receipt, "--openapi": args.openapi}
            missing = [name for name, value in required.items() if not value]
            if missing:
                parser.error("approved emission requires " + ", ".join(missing))
            result = emit_approved(plan, bindings, _read(args.manifest), _read(args.approval),
                                   _read(args.staging_receipt), _read(args.openapi))
            if args.contents:
                current = _read(args.contents)
                contents = code_rep.document(current)
                if not contents:
                    parser.error("--contents requires complete workbook contents")
                if (current.get("workbookId") != bindings["documentId"]
                        or current.get("documentVersion") != bindings["documentVersion"]):
                    parser.error("current workbook identity/version differs from approved bindings")
                result = {"documentVersion": bindings["documentVersion"],
                          "contents": presentation.integrate_presentation(contents, result),
                          "sourceHash": plan["sourceHash"],
                          "presentationPlanHash": plan["planHash"],
                          "presentationArtifactHash": result["artifactHash"]}
    _guard_outputs(args)
    if args.plan_out:
        _write(args.plan_out, plan)
    _guard_outputs(args)
    _write(args.out, result)
    print(json.dumps({"source": plan["source"]["name"], "charts": len(plan["charts"]),
                      "presentationPlanHash": plan["planHash"],
                      "output": str(Path(args.out).resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
