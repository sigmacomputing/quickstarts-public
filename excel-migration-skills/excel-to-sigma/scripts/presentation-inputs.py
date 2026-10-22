#!/usr/bin/env python3
"""Prepare and emit approved editable inputs used by presentation migration.

This command performs no Sigma calls. Construction and extension output is
derived only from an immutable manifest plus an APPROVED_STAGING receipt.
Extension seeding additionally requires a checkpoint made from assigned column
IDs and an immediate readback of those exact columns.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import tempfile
import json
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(LIB))

from input_sync import (  # noqa: E402
    checkpoint_input_extension,
    emit_write_programs,
    emit_workbook_wiring,
    normalize_seed_plan,
    plan_extension_seed,
)
from migration_manifest import build_manifest, validate_manifest  # noqa: E402
from presentation import (  # noqa: E402
    build_business_input_architecture,
    build_business_input_plan,
    approved_business_bindings,
    emit_approved_business_input_program,
    extract_presentation,
)


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="build the source-bound plan and manifest")
    prepare.add_argument("source")
    prepare.add_argument("--connection", required=True)
    prepare.add_argument("--folder", required=True)
    prepare.add_argument("--research-plan")
    prepare.add_argument("--reviewed-formulas",
                         help="approved replacement records for parser-unsupported source formulas")
    prepare.add_argument("--out-plan", required=True)
    prepare.add_argument("--out-manifest", required=True)

    target = commands.add_parser(
        "bind-target", help="bind a reviewed manifest to the current document version")
    target.add_argument("--manifest", required=True)
    target.add_argument("--document-id", required=True)
    target.add_argument("--document-version", required=True, type=int)
    target.add_argument("--out", required=True)

    emit = commands.add_parser("emit", help="emit approved construction or missing-column extension")
    emit.add_argument("--manifest", required=True)
    emit.add_argument("--receipt", required=True)
    emit.add_argument("--feature", required=True)
    emit.add_argument("--current-columns")
    emit.add_argument("--out", required=True)

    wiring = commands.add_parser("wiring", help="emit assigned native calculations or a guarded contents PUT")
    wiring.add_argument("--manifest", required=True)
    wiring.add_argument("--receipt", required=True)
    wiring.add_argument("--contents", help="current GET-back response including workbookId and documentVersion")
    wiring.add_argument("--out", required=True)

    bindings = commands.add_parser("bindings", help="resolve business presentation bindings from assigned inputs")
    bindings.add_argument("source")
    bindings.add_argument("--manifest", required=True)
    bindings.add_argument("--receipt", required=True)
    bindings.add_argument("--out", required=True)

    for name in ("display", "checkpoint-display", "verify-display"):
        display = commands.add_parser(name, help="emit approved SDK input display programs or verify fresh SDK observations")
        display.add_argument("source")
        display.add_argument("--manifest", required=True)
        display.add_argument("--receipt", required=True)
        display.add_argument("--feature")
        if name != "display":
            display.add_argument("--state", required=True, help="authoritative durable one-use controller ledger")
            display.add_argument("--current-version", required=True, help="fresh controller-recorded workbook version capture")
        if name == "checkpoint-display":
            display.add_argument("--execution", required=True, help="raw SDK request context and execution result")
            display.add_argument("--readback", required=True, help="raw read-only SDK request context and result")
        display.add_argument("--out", required=True)

    checkpoint = commands.add_parser(
        "checkpoint-extension", help="bind created IDs to the exact post-extension readback")
    checkpoint.add_argument("--extension-plan", required=True)
    checkpoint.add_argument("--created-columns", required=True)
    checkpoint.add_argument("--result-version", required=True, type=int)
    checkpoint.add_argument("--readback", required=True)
    checkpoint.add_argument("--out", required=True)

    seed = commands.add_parser(
        "seed-extension", help="plan first writes for checkpointed, still-null extension fields")
    seed.add_argument("--manifest", required=True)
    seed.add_argument("--receipt", required=True)
    seed.add_argument("--feature", required=True)
    seed.add_argument("--current-rows", required=True)
    seed.add_argument("--row-id", required=True)
    seed.add_argument("--prior-seed", required=True)
    seed.add_argument("--extension-proof", required=True)
    seed.add_argument("--snapshot-id", required=True)
    seed.add_argument("--snapshot-age-seconds", required=True, type=int)
    seed.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "prepare":
        extracted = extract_presentation(args.source)
        architecture = build_business_input_architecture(
            extracted, connection_id=args.connection, folder_id=args.folder,
            research_plan=_read(args.research_plan) if args.research_plan else None)
        reviewed_payload = _read(args.reviewed_formulas) if args.reviewed_formulas else {}
        if (isinstance(reviewed_payload, dict) and "sourceHash" in reviewed_payload
                and reviewed_payload["sourceHash"] != extracted["source"]["sha256"]):
            raise ValueError("reviewed formula payload source hash is stale")
        reviewed = (reviewed_payload if isinstance(reviewed_payload, list)
                    else reviewed_payload.get("formulaCells", []))
        plan = build_business_input_plan(extracted, architecture, reviewed)
        manifest = build_manifest(args.source, plan)
        _write(args.out_plan, plan)
        _write(args.out_manifest, manifest)
    elif args.command == "bind-target":
        manifest = _read(args.manifest)
        validate_manifest(manifest)
        manifest["target"] = {"documentId": args.document_id,
                              "version": args.document_version}
        _write(args.out, manifest)
    elif args.command == "emit":
        manifest = _read(args.manifest)
        validate_manifest(manifest)
        result = emit_approved_business_input_program(
            manifest, _read(args.receipt), args.feature,
            current_columns=_read(args.current_columns) if args.current_columns else None)
        _write(args.out, result)
    elif args.command == "wiring":
        manifest, receipt = _read(args.manifest), _read(args.receipt)
        validate_manifest(manifest)
        result = emit_workbook_wiring(manifest, receipt)
        if args.contents:
            from native_input_wiring import integrate_native_wiring
            result = integrate_native_wiring(_read(args.contents), manifest, receipt, result)
        _write(args.out, result)
    elif args.command == "bindings":
        manifest = _read(args.manifest)
        validate_manifest(manifest)
        result = approved_business_bindings(
            extract_presentation(args.source), manifest, _read(args.receipt))
        _write(args.out, result)
    elif args.command in {"display", "checkpoint-display", "verify-display"}:
        from input_display import build_input_display, checkpoint_input_display, verify_input_display
        manifest = _read(args.manifest)
        validate_manifest(manifest)
        result = build_input_display(extract_presentation(args.source), manifest, _read(args.receipt), args.feature)
        if args.command != "display":
            state_path=Path(args.state)
            if state_path.resolve()==Path(args.out).resolve():
                raise ValueError("display output must not overwrite the authoritative ledger")
            # Lock a separate inode so atomic replacement cannot allow concurrent replay.
            with state_path.with_name(state_path.name+".lock").open("a+") as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                state=_read(state_path) if state_path.exists() else None
                if args.command=="checkpoint-display":
                    state=checkpoint_input_display(result,_read(args.execution),_read(args.readback),
                                                   _read(args.current_version),state)
                    result={"status":"PENDING_SDK_VERIFICATION","proofHash":state['attempts'][-1]['proofHash']}
                else:
                    result=verify_input_display(result,state,_read(args.current_version))
                with tempfile.NamedTemporaryFile(mode="w",dir=state_path.parent,delete=False,encoding="utf-8") as saved:
                    json.dump(state,saved,indent=2)
                    saved.write("\n")
                    saved.flush()
                    os.fsync(saved.fileno())
                os.replace(saved.name,state_path)
                directory_fd=os.open(state_path.parent,os.O_RDONLY)
                try:os.fsync(directory_fd)
                finally:os.close(directory_fd)
        _write(args.out, result)
        if result.get("status") == "FAILED":
            return 1
    elif args.command == "checkpoint-extension":
        proof = checkpoint_input_extension(
            _read(args.extension_plan), _read(args.created_columns),
            result_version=args.result_version, readback=_read(args.readback))
        _write(args.out, proof)
    elif args.command == "seed-extension":
        manifest, receipt = _read(args.manifest), _read(args.receipt)
        feature = args.feature
        spec = manifest["planProjection"]["sharedInputArchitecture"]["inputs"][feature]
        result = plan_extension_seed(
            spec["rows"], _read(args.current_rows), spec["keyColumns"], args.row_id,
            prior_seed=normalize_seed_plan(_read(args.prior_seed)), manifest=manifest,
            staging_receipt=receipt, feature=feature,
            extension_proof=_read(args.extension_proof),
            snapshot={"id": args.snapshot_id, "ageSeconds": args.snapshot_age_seconds},
            column_types={column["name"]: column["type"] for column in spec["columns"]})
        _write(args.out, {"plan": result,
                          "programs": emit_write_programs(result, manifest, receipt, feature)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
