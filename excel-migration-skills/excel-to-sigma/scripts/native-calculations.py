#!/usr/bin/env python3
"""Read-only source binding and guarded native calculation artifact emission."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from native_calculations import (build_native_calculation_plan,
    lower_native_calculations, prepare_native_calculation_update,
    confirm_native_calculation_readback, build_native_calculation_backup)


from native_exact_plan import (prepare_exact_native_scaffold, confirm_exact_native_scaffold,
    prepare_exact_native_update, confirm_exact_native_readback)


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _guard_output(args):
    destination = Path(args.out)
    for name in ("source", "input_plan", "native_plan", "assigned_rows", "manifest",
                 "staging_receipt", "current", "observed_rows", "backup",
                 "prior_readbacks", "native_bindings", "seed_binding", "proposal", "readback"):
        value = getattr(args, name, None)
        if value:
            source = Path(value)
            if (destination.resolve() == source.resolve() or
                    (destination.exists() and source.exists() and
                     os.path.samefile(destination, source))):
                raise ValueError("native calculation output aliases input artifact: " + name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="account for exact source formulas")
    plan.add_argument("--source", required=True)
    plan.add_argument("--input-plan")
    plan.add_argument("--exact", action="store_true", help="typed error-preserving native v2 compiler")
    lower = commands.add_parser("lower-candidate", help="lower using observed assigned row IDs")
    lower.add_argument("--native-plan", required=True)
    lower.add_argument("--assigned-rows", required=True)
    lower.add_argument("--max-columns", type=int, default=64)
    bind = commands.add_parser("bind-input-rows", help="validate actual input schema/physical rows; never authorize formulas")
    for name in ("input-plan", "manifest", "staging-receipt", "current", "observed-rows"):
        bind.add_argument("--" + name, required=True)
    backup = commands.add_parser("backup", help="persist complete document and queried rows")
    backup.add_argument("--current", required=True)
    backup.add_argument("--observed-rows", required=True)
    update = commands.add_parser("prepare-update", help="prepare one guarded REST contents candidate")
    for name in ("native-plan", "input-plan", "manifest", "staging-receipt", "current", "observed-rows"):
        update.add_argument("--" + name, required=True)
    update.add_argument("--shard-index", type=int, default=0)
    update.add_argument("--max-columns", type=int, default=64)
    update.add_argument("--prior-readbacks")
    update.add_argument("--backup", required=True)
    update.add_argument("--native-bindings", help="all actual assigned v2 scaffold receipts")
    scaffold = commands.add_parser("prepare-scaffold", help="prepare one receipt-bound MCP structural program")
    for name in ("native-plan", "input-plan", "manifest", "staging-receipt", "current", "observed-rows", "backup", "seed-binding", "page-id"):
        scaffold.add_argument("--" + name, required=True)
    scaffold.add_argument("--shard-index", type=int, default=0)
    scaffold_confirm = commands.add_parser("confirm-scaffold", help="record actual MCP scaffold element and column IDs")
    scaffold_confirm.add_argument("--proposal", required=True)
    scaffold_confirm.add_argument("--readback", required=True)
    confirm = commands.add_parser("confirm-readback", help="check saved native formula structure")
    confirm.add_argument("--proposal", required=True)
    confirm.add_argument("--readback", required=True)
    for command in (plan, lower, bind, backup, update, confirm, scaffold, scaffold_confirm):
        command.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    _guard_output(args)
    if args.command == "plan":
        result = build_native_calculation_plan(args.source, _read(args.input_plan) if args.input_plan else None, exact=args.exact)
    elif args.command == "lower-candidate":
        result = lower_native_calculations(_read(args.native_plan), _read(args.assigned_rows),
                                           max_columns=args.max_columns)
    elif args.command == "bind-input-rows":
        from source_inputs import validate_source_input_plan
        from migration_manifest import validate_manifest
        from native_calculations import _observed_bindings
        inputs, manifest, current = _read(args.input_plan), _read(args.manifest), _read(args.current)
        validate_source_input_plan(inputs)
        validate_manifest(manifest, allow_input_only=True)
        if (manifest.get("sourceHash") != inputs["sourceSha256"]
                or manifest.get("planProjection", {}).get("inputPlanHash") != inputs["inputPlanHash"]
                or manifest.get("planProjection", {}).get("sharedInputArchitecture") != inputs["sharedInputArchitecture"]
                or current.get("workbookId") != (manifest.get("target") or {}).get("documentId")
                or current.get("documentVersion") != (manifest.get("target") or {}).get("version")):
            raise ValueError("actual input manifest/document/version is stale")
        result = _observed_bindings(inputs, manifest, _read(args.staging_receipt),
            current["contents"], _read(args.observed_rows), input_binding_only=True)
    elif args.command == "backup":
        result = build_native_calculation_backup(_read(args.current), _read(args.observed_rows))
    elif args.command == "prepare-scaffold":
        result = prepare_exact_native_scaffold(_read(args.native_plan), _read(args.input_plan), _read(args.manifest),
            _read(args.staging_receipt), _read(args.current), _read(args.observed_rows), backup=_read(args.backup),
            seed_binding=_read(args.seed_binding), page_id=args.page_id, shard_index=args.shard_index)
    elif args.command == "confirm-scaffold":
        result = confirm_exact_native_scaffold(_read(args.proposal), _read(args.readback))
    elif args.command == "prepare-update" and _read(args.native_plan).get("nativePlanVersion") == 2:
        if not args.native_bindings:
            raise ValueError("exact native update requires --native-bindings from confirmed MCP scaffold readback")
        result = prepare_exact_native_update(_read(args.native_plan), _read(args.input_plan), _read(args.manifest),
            _read(args.staging_receipt), _read(args.current), _read(args.observed_rows), backup=_read(args.backup),
            native_bindings=_read(args.native_bindings), shard_index=args.shard_index,
            prior_readbacks=_read(args.prior_readbacks) if args.prior_readbacks else ())
    elif args.command == "prepare-update":
        result = prepare_native_calculation_update(
            _read(args.native_plan), _read(args.input_plan), _read(args.manifest),
            _read(args.staging_receipt), _read(args.current), _read(args.observed_rows),
            backup=_read(args.backup),
            shard_index=args.shard_index, max_columns=args.max_columns,
            prior_readbacks=_read(args.prior_readbacks) if args.prior_readbacks else ())
    else:
        proposal = _read(args.proposal)
        confirmer = confirm_exact_native_readback if proposal.get("status") == "GUARDED_EXACT_REST_CANDIDATE_PENDING_READBACK" else confirm_native_calculation_readback
        result = confirmer(proposal, _read(args.readback))
    destination = Path(args.out)
    _guard_output(args)
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
