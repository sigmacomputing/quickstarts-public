#!/usr/bin/env python3
"""Offline, phased operator code for the Statistical Demand Forecast preview.

Generation performs no Sigma call. Execute each phase-1 program separately in
Sigma MCP Code Mode, then capture actual readback before generating phase 2.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from statistical_forecast import SOURCE_SHA256  # noqa: E402
from statistical_runtime import CANDIDATE_REQUIRED, emit_preview_program  # noqa: E402

COUNTS = {"history": 108, "parameters": 1, "targets": 12}
TABLES = {
    "history": ("Statistical History (editable)", ("Month", "SKU", "Demand"),
                ("datetime", "text", "number"), (1, 1, 24, 12)),
    "parameters": ("Statistical Parameters (editable)",
                   ("Scope", "SelectedSKU", "Seasonality", "ServiceLevel", "LeadTime"),
                   ("text", "text", "number", "number", "number"), (1, 15, 24, 8)),
    "targets": ("Statistical Target Months (editable)", ("Period", "Month"),
                ("number", "datetime"), (1, 25, 24, 10)),
}


def source_packet(path, source_original):
    """Authenticate every proposed row and CSV against fresh hashed-source extraction."""
    path = Path(path)
    packet = json.loads(path.read_text())
    if packet.get("sourceHash") != SOURCE_SHA256 or set(packet.get("roles", {})) != set(COUNTS):
        raise ValueError("SOURCE_PACKET_MISMATCH")
    for role, expected in COUNTS.items():
        spec = packet["roles"][role]
        if (len(spec.get("rows", [])) != expected
                or list(spec.get("columns", {})) != list(TABLES[role][1])
                or list(spec.get("naturalKey", [])) != (["Month", "SKU"] if role == "history" else ["Scope"] if role == "parameters" else ["Period"])):
            raise ValueError("SOURCE_PACKET_ROLE_MISMATCH")
    extract = runpy.run_path(str(Path(__file__).with_name("statistical-source-packet.py")))["extract"]
    expected = extract(source_original)
    if packet != expected:
        raise ValueError("SOURCE_PACKET_CONTENT_MISMATCH")
    for role, spec in expected["roles"].items():
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(spec["columns"]))
        writer.writeheader()
        writer.writerows({name: row[name] for name in spec["columns"]} for row in spec["rows"])
        if (path.parent / f"{role}.csv").read_bytes() != stream.getvalue().encode():
            raise ValueError("SOURCE_CSV_CONTENT_MISMATCH:" + role)
    return hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def phase1_snapshot(source, *, page_id, connection_id, role, existing_id=None):
    """Gate a single create/continuation against captured full workbook contents.

    The caller must repeat this GET and compare workbook version immediately
    before the MCP mutation; the SDK has no documented source-version CAS.
    """
    if not isinstance(source, dict) or not source.get("workbookId") or type(source.get("documentVersion")) is not int:
        raise ValueError("ACTUAL_WORKBOOK_SOURCE_REQUIRED")
    contents = source.get("contents") or {}
    pages, elements = contents.get("pages"), contents.get("elements")
    if not isinstance(pages, list) or not isinstance(elements, list) or sum(
            p.get("id") == page_id for p in pages if isinstance(p, dict)) != 1:
        raise ValueError("ACTUAL_PAGE_MISMATCH")
    names = [e.get("name") for e in elements if isinstance(e, dict)]
    if len(names) != len(set(names)):
        raise ValueError("AMBIGUOUS_ELEMENT_TITLES")
    name, columns, types, _ = TABLES[role]
    matches = [e for e in elements if isinstance(e, dict) and e.get("name") == name]
    if existing_id is None:
        if matches:
            raise ValueError("ROLE_ALREADY_EXISTS:" + role)
    elif (len(matches) != 1 or matches[0].get("id") != existing_id
          or matches[0].get("kind") != "input-table"
          or matches[0].get("source") != {"kind": "empty", "connectionId": connection_id}
          or matches[0].get("inputMode") != "edit"
          or matches[0].get("columns", []) != []):
        raise ValueError("PARTIAL_PARAMETER_STATE_CHANGED")
    return {"workbookId": source["workbookId"], "documentVersion": source["documentVersion"],
            "pageId": page_id, "role": role,
            "sourceSnapshotHash": hashlib.sha256(json.dumps(source, sort_keys=True,
                                                        separators=(",", ":")).encode()).hexdigest()}


def phase1_program(role, page_id, connection_id):
    if role not in TABLES or not page_id or not connection_id:
        raise ValueError("OBSERVED_PAGE_AND_WRITE_CONNECTION_REQUIRED")
    name, columns, types, frame = TABLES[role]
    lines = [f"# sourceHash={SOURCE_SHA256}", f"# role={role}",
             "# CREATE ONLY: query first and skip if this role already exists.",
             f"page = sigma.workbook.get_page({page_id!r})",
             "if not isinstance(page, Page): raise RuntimeError('expected current page')",
             f"created = page.add_input_table({connection_id!r})",
             f"created.set_name({name!r})", "created.set_edit_mode('draft')",
             f"created.set_frame({', '.join(map(str, frame))})"]
    for index, (column, kind) in enumerate(zip(columns, types)):
        lines.append(f"created_c{index} = created.add_editable_column({column!r}, {kind!r})")
    lines += ["created.add_system_columns(['row_id'])",
              "print('role=' + " + repr(role) + ")",
              "print('title=' + " + repr(name) + ")",
              "print('inputTableId=' + created.id())",
              *[f"print('column:{column}=' + created_c{index}.id())"
                for index, column in enumerate(columns)],
              "print('Read back Snowpark identifiers and Row.as_dict keys before phase 2')"]
    return "\n".join(lines) + "\n"


def phase1_continue_parameters(page_id, element_id):
    """Continue a readback-proven partial parameters table without creating one."""
    if not page_id or not element_id:
        raise ValueError("OBSERVED_PARTIAL_PARAMETERS_REQUIRED")
    name, columns, types, frame = TABLES["parameters"]
    lines = [f"# sourceHash={SOURCE_SHA256}",
             "# CONTINUATION ONLY: operator must confirm this element has zero editable columns.",
             f"page = sigma.workbook.get_page({page_id!r})",
             "if not isinstance(page, Page): raise RuntimeError('expected current page')",
             f"created = page.get_element({element_id!r})",
             "if not isinstance(created, InputTable): raise RuntimeError('expected existing parameters input table')",
             f"created.set_frame({', '.join(map(str, frame))})"]
    for index, (column, kind) in enumerate(zip(columns, types)):
        lines.append(f"created_c{index} = created.add_editable_column({column!r}, {kind!r})")
    lines += ["created.add_system_columns(['row_id'])",
              "print('role=parameters')", f"print('title={name}')",
              "print('inputTableId=' + created.id())",
              *[f"print('column:{column}=' + created_c{index}.id())"
                for index, column in enumerate(columns)]]
    return "\n".join(lines) + "\n"


def phase2_program(readback, *, actual_source, source_packet_hash, candidate_ets=False):
    if (readback.get("sourceHash") != SOURCE_SHA256 or not readback.get("workbookId")
            or not readback.get("workbookVersion") or not readback.get("pageId")
            or not readback.get("sourceSnapshotId")):
        raise ValueError("OBSERVED_WORKBOOK_READBACK_REQUIRED")
    roles = readback.get("roles")
    if not isinstance(roles, dict) or set(roles) != set(CANDIDATE_REQUIRED):
        raise ValueError("THREE_OBSERVED_ROLES_REQUIRED")
    binding = {}
    if (actual_source.get("workbookId") != readback["workbookId"]
            or actual_source.get("documentVersion") != readback["workbookVersion"]
            or sum(p.get("id") == readback["pageId"] for p in actual_source.get("contents", {}).get("pages", [])) != 1):
        raise ValueError("ACTUAL_SOURCE_VERSION_OR_PAGE_MISMATCH")
    source_elements = actual_source.get("contents", {}).get("elements", [])
    # Native code-output tables have no title in workbook source. Only actual
    # titles can make sigma.get_element(title) ambiguous.
    titled = [e.get("name") for e in source_elements if e.get("name") is not None]
    if len(titled) != len(set(titled)):
        raise ValueError("AMBIGUOUS_ACTUAL_SOURCE_TITLES")
    element_ids = []
    titles = []
    identity_roles = {}
    for role, names in CANDIDATE_REQUIRED.items():
        item = roles[role]
        if (not item.get("elementId") or item.get("rowCount") != COUNTS[role]
                or item.get("naturalKeysVerified") is not True
                or not item.get("readbackSnapshotId")):
            raise ValueError("OBSERVED_ROLE_READBACK_INCOMPLETE:" + role)
        element_ids.append(item["elementId"])
        observed_elements = [e for e in source_elements if e.get("id") == item["elementId"]]
        if len(observed_elements) != 1 or observed_elements[0].get("name") != item.get("title"):
            raise ValueError("ACTUAL_SOURCE_ELEMENT_MISMATCH:" + role)
        source_columns = {c.get("name"): c.get("id") for c in observed_elements[0].get("columns", [])
                          if c.get("name") is not None}
        if (set(source_columns) != set(names)
                or item.get("columnIds") != source_columns):
            raise ValueError("ACTUAL_SOURCE_COLUMN_IDS_MISMATCH:" + role)
        binding[role] = {"title": item["title"], "columns": item["columns"]}
        titles.append(item["title"])
        identity_roles[role] = {"elementId": item["elementId"],
                                "title": item["title"], "columns": item["columns"],
                                "columnIds": item["columnIds"],
                                "readbackSnapshotId": item["readbackSnapshotId"]}
        if set(binding[role]["columns"]) != set(names):
            raise ValueError("OBSERVED_COLUMNS_MISMATCH:" + role)
    if len(set(element_ids)) != 3 or len(set(titles)) != 3:
        raise ValueError("AMBIGUOUS_OBSERVED_ELEMENTS")
    if not candidate_ets:
        raise ValueError("TYPED_PARAMETER_TABLE_REQUIRES_CANDIDATE_PREVIEW")
    identity = {"workbookId": readback["workbookId"],
                "workbookVersion": readback["workbookVersion"],
                "pageId": readback["pageId"],
                "sourceSnapshotId": readback["sourceSnapshotId"],
                "sourceSnapshotHash": hashlib.sha256(json.dumps(actual_source, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest(),
                "sourcePacketHash": source_packet_hash,
                "roles": identity_roles}
    return emit_preview_program(binding, candidate_ets=True, source_identity=identity)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-packet", type=Path, required=True)
    parser.add_argument("--source-original", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    commands = parser.add_subparsers(dest="phase", required=True)
    create = commands.add_parser("phase1")
    create.add_argument("--page-id", required=True)
    create.add_argument("--write-connection-id", required=True)
    create.add_argument("--role", choices=tuple(COUNTS), required=True)
    create.add_argument("--source-snapshot", type=Path, required=True)
    continue_params = commands.add_parser("phase1-continue-parameters")
    continue_params.add_argument("--page-id", required=True)
    continue_params.add_argument("--write-connection-id", required=True)
    continue_params.add_argument("--element-id", required=True)
    continue_params.add_argument("--source-snapshot", type=Path, required=True)
    bind = commands.add_parser("phase2")
    bind.add_argument("--readback", type=Path, required=True)
    bind.add_argument("--actual-source", type=Path, required=True)
    bind.add_argument("--candidate-ets", action="store_true")
    args = parser.parse_args()
    packet_hash = source_packet(args.source_packet, args.source_original)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.phase == "phase1":
        snapshot = phase1_snapshot(json.loads(args.source_snapshot.read_text()),
                                   page_id=args.page_id, connection_id=args.write_connection_id,
                                   role=args.role)
        (args.out / f"phase1-create-{args.role}.py").write_text(
            f"# sourcePacketHash={packet_hash}\n# observedSnapshot={snapshot!r}\n" +
            phase1_program(args.role, args.page_id, args.write_connection_id))
        print("Generated one source-gated create-only program; recheck version before MCP execution.")
    elif args.phase == "phase1-continue-parameters":
        snapshot = phase1_snapshot(json.loads(args.source_snapshot.read_text()),
                                   page_id=args.page_id, connection_id=args.write_connection_id,
                                   role="parameters", existing_id=args.element_id)
        (args.out / "phase1-continue-parameters.py").write_text(
            f"# sourcePacketHash={packet_hash}\n# observedSnapshot={snapshot!r}\n" +
            phase1_continue_parameters(args.page_id, args.element_id))
        print("Generated source-gated existing-table continuation; recheck version before MCP execution.")
    else:
        program = phase2_program(json.loads(args.readback.read_text()),
                                 actual_source=json.loads(args.actual_source.read_text()),
                                 source_packet_hash=packet_hash, candidate_ets=args.candidate_ets)
        (args.out / "phase2-python-preview.py").write_text(program["code"])
        (args.out / "phase2-program-metadata.json").write_text(json.dumps(
            {key: value for key, value in program.items() if key != "code"}, indent=2) + "\n")
        print("Generated bound Python preview; no Sigma call was made.")


if __name__ == "__main__":
    main()
