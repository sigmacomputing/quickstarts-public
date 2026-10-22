#!/usr/bin/env python3
"""Plan resumable input-table writes and emit reviewable Sigma MCP programs.

This CLI performs no MCP query or mutation.  Query current rows with the Sigma
MCP companion tools, run ``plan``, review the JSON/program bundle, execute the
program through Code Mode, then query again and retain the checkpoint evidence.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from input_orchestration import gate_input_completion, gate_input_staging, gate_input_only_staging  # noqa: E402
from input_sync import (  # noqa: E402
    build_shared_input_architecture,
    emit_construction_program,
    emit_workbook_wiring,
    emit_write_programs,
    plan_seed,
)
from migration_gate import gate_plan_source, gate_plan_staging_source  # noqa: E402
from migration_manifest import build_manifest  # noqa: E402


def _load(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def _default(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, default=_default) + "\n", encoding="utf-8")


def _apply_reviewed_replacements(plan, path):
    if not path:
        return
    payload = _load(path)
    records = payload.get("formulaCells") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        raise ValueError("reviewed replacements must contain a nonempty formulaCells array")
    by_id = {item.get("id"): dict(item) for item in plan.get("formulaCells", [])
             if isinstance(item, dict) and item.get("id")}
    for record in records:
        if not isinstance(record, dict) or not record.get("id"):
            raise ValueError("each reviewed replacement requires a formula cell id")
        replacement = record.get("reviewedReplacement") or {}
        if (record.get("mappingStatus") != "live" or not record.get("targetMapping")
                or replacement.get("reviewStatus") != "approved"
                or not str(replacement.get("reviewer") or "").strip()
                or not str(replacement.get("originalFormula") or "").strip()
                or not str(replacement.get("replacementFormula") or "").strip()):
            raise ValueError(f"reviewed replacement is incomplete for {record['id']}")
        by_id[record["id"]] = record
    plan["formulaCells"] = [by_id[key] for key in sorted(by_id)]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan", help="reconcile queried current rows and emit write programs")
    plan.add_argument("--current-rows", required=True)
    plan.add_argument("--manifest", required=True)
    plan.add_argument("--receipt", required=True)
    plan.add_argument("--feature", required=True)
    plan.add_argument("--row-id", required=True, help="queried Sigma system row-ID column")
    plan.add_argument("--prior-seed")
    plan.add_argument("--snapshot-id", required=True)
    plan.add_argument("--snapshot-age-seconds", required=True, type=int)
    plan.add_argument("--out", required=True)

    create = commands.add_parser("emit-create", help="emit an independent ordinary input-table program")
    create.add_argument("--manifest", required=True)
    create.add_argument("--receipt", required=True)
    create.add_argument("--feature", required=True)
    create.add_argument("--out", required=True)

    wiring = commands.add_parser("emit-wiring", help="emit approved native join fragments")
    wiring.add_argument("--manifest", required=True)
    wiring.add_argument("--receipt", required=True)
    wiring.add_argument("--out", required=True)

    architecture = commands.add_parser("architecture", help="add shared-input scope before manifest hashing")
    architecture.add_argument("--plan", required=True)
    architecture.add_argument("--source", required=True)
    architecture.add_argument("--connection", required=True)
    architecture.add_argument("--folder", required=True)
    architecture.add_argument("--workflow", action="append", required=True,
                              choices=("sales", "expense", "research"))
    architecture.add_argument("--reviewed-replacements")
    architecture.add_argument("--out-plan", required=True)
    architecture.add_argument("--out-manifest", required=True)

    stage = commands.add_parser("stage", help="run the source/plan staging gate")
    stage.add_argument("--manifest", required=True)
    stage.add_argument("--plan", required=True)
    stage.add_argument("--source")
    stage.add_argument("--review-dispositions")
    stage.add_argument("--approval", required=True)
    stage.add_argument("--out", required=True)
    stage.add_argument("--inputs-only", action="store_true", help="explicit literal input staging; does not approve formulas")
    stage.add_argument("--input-plan", help="source-validated input plan required with --inputs-only")

    complete = commands.add_parser("complete", help="run completion gate from recorded runtime evidence")
    complete.add_argument("--manifest", required=True)
    complete.add_argument("--receipt", required=True)
    complete.add_argument("--runtime-evidence", required=True)
    complete.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "plan":
        manifest = _load(args.manifest)
        receipt = _load(args.receipt)
        architecture = manifest["planProjection"]["sharedInputArchitecture"]
        spec = architecture["inputs"][args.feature]
        result = plan_seed(
            spec["rows"], _load(args.current_rows), spec["keyColumns"], args.row_id,
            prior_seed=_load(args.prior_seed) if args.prior_seed else None,
            snapshot={"id": args.snapshot_id, "ageSeconds": args.snapshot_age_seconds},
            column_types={column["name"]: column["type"] for column in spec["columns"]},
        )
        bundle = {"plan": result,
                  "programs": emit_write_programs(
                      result, manifest, receipt, args.feature)}
        _write(args.out, bundle)
    elif args.command == "emit-create":
        program = emit_construction_program(
            _load(args.manifest), _load(args.receipt), args.feature)
        Path(args.out).write_text(program, encoding="utf-8")
    elif args.command == "emit-wiring":
        _write(args.out, emit_workbook_wiring(
            _load(args.manifest), _load(args.receipt)))
    elif args.command == "architecture":
        plan = _load(args.plan)
        _apply_reviewed_replacements(plan, args.reviewed_replacements)
        shared = build_shared_input_architecture(
            plan, connection_id=args.connection, folder_id=args.folder,
            workflows=args.workflow)
        plan["targetScope"] = shared["targetScope"]
        plan["sharedInputArchitecture"] = shared
        plan.pop("migrationManifest", None)
        manifest = build_manifest(args.source, plan)
        plan["migrationManifest"] = manifest
        _write(args.out_plan, plan)
        _write(args.out_manifest, manifest)
    elif args.command == "stage":
        plan = _load(args.plan)
        # An optional legacy dispositions file must still pass the strict gate;
        # it cannot substitute for sourceReviewApproval or runtime evidence.
        if args.review_dispositions:
            gate_plan_source(plan, source_arg=args.source,
                             dispositions_path=args.review_dispositions, plan_path=args.plan)
        _source, source_gate = gate_plan_staging_source(
            plan, source_arg=args.source, plan_path=args.plan)
        manifest = _load(args.manifest)
        if build_manifest(_source, plan)["planHash"] != manifest.get("planHash"):
            raise ValueError("staging plan does not match the approved manifest planHash")
        if args.inputs_only:
            if not args.input_plan:
                raise ValueError("--inputs-only requires --input-plan")
            receipt = gate_input_only_staging(manifest, _load(args.approval),
                _load(args.input_plan), source_gate, source_path=_source)
        else:
            if args.input_plan:
                raise ValueError("--input-plan requires explicit --inputs-only")
            receipt = gate_input_staging(manifest, _load(args.approval), plan, source_gate)
        _write(args.out, receipt)
    elif args.command == "complete":
        receipt = gate_input_completion(
            _load(args.manifest), _load(args.receipt), _load(args.runtime_evidence))
        _write(args.out, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
