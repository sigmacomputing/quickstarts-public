#!/usr/bin/env python3
"""Offline, resumable source-key reconciliation for the three statistical inputs.

This command never queries or writes Sigma. It emits one bounded SDK write chunk
from a fresh actual source and query receipt. Re-query after that chunk, then
run again with the prior plan. Never replay an emitted write program.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import hashlib
import json
import math
import re
from pathlib import Path
import runpy
import sys

LIB = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(LIB))
from input_sync import _row_expression, plan_seed  # noqa: E402
from statistical_forecast import SOURCE_SHA256  # noqa: E402

OPERATOR = runpy.run_path(str(Path(__file__).with_name("statistical-operator.py")))
TABLES = OPERATOR["TABLES"]


def query_requests(workbook_id, element_id, column_ids, key_columns, row_id_key):
    """Exact unrestricted workbook queries to capture for this source role."""
    del key_columns  # Natural keys are reconciled in Python; no SQL ordering is required.
    select = ", ".join(f'"{column_id}"' for column_id in (*column_ids.values(), row_id_key))
    table = f'"workbook"."{element_id}"'
    return {"rows": {"type": "workbook", "workbookId": workbook_id,
                     "sql": f"SELECT {select} FROM {table}"},
            "count": {"type": "workbook", "workbookId": workbook_id,
                      "sql": f'SELECT COUNT(*) AS "__COUNT__" FROM {table}'}}


def _rows_from_receipt(receipt, *, requests, role, element_id, column_ids, row_id_key):
    """Validate the saved executed-query request and raw result, including count."""
    if not isinstance(receipt, list) or not receipt or any(
            not isinstance(entry, dict) or entry.get("status") != "fulfilled"
            for entry in receipt):
        raise ValueError("BOUND_QUERY_RECEIPT_REQUIRED")
    matches = [entry["value"] for entry in receipt if isinstance(entry.get("value"), dict)
               and entry["value"].get("role") == role]
    if len(matches) != 1:
        raise ValueError("BOUND_QUERY_RECEIPT_REQUIRED")
    observed = matches[0]
    if (observed.get("elementId") != element_id
            or observed.get("selectedColumnIds") != [*column_ids.values(), row_id_key]
            or observed.get("rowIdAlias") != row_id_key):
        raise ValueError("BOUND_QUERY_RECEIPT_REQUIRED")
    observed_times = []
    payloads = {}
    for purpose in ("rows", "count"):
        entry = observed if purpose == "rows" else observed.get("count")
        if (not isinstance(entry, dict) or entry.get("request") != {"query": requests[purpose]}
                or not isinstance(entry.get("result"), dict)
                or entry["result"].get("isError") is True
                or not isinstance(entry["result"].get("structuredContent"), dict)):
            raise ValueError("EXECUTED_QUERY_TARGET_OR_STATUS_MISMATCH:" + purpose)
        try:
            started = datetime.fromisoformat(entry["startedAt"].replace("Z", "+00:00"))
            completed = datetime.fromisoformat(entry["completedAt"].replace("Z", "+00:00"))
            if started.tzinfo is None or completed.tzinfo is None or started > completed:
                raise ValueError
        except (KeyError, AttributeError, ValueError):
            raise ValueError("EXECUTED_QUERY_TIMING_REQUIRED:" + purpose) from None
        observed_times.append((started, completed))
        payloads[purpose] = entry["result"]["structuredContent"]
    if observed_times[1][0] < observed_times[0][1]:
        raise ValueError("EXECUTED_QUERY_ORDER_MISMATCH")
    row_payload, count_payload = payloads["rows"], payloads["count"]
    count_columns, count_rows = count_payload.get("columns"), count_payload.get("rows")
    if (count_columns != ["__COUNT__"] or not isinstance(count_rows, list)
            or len(count_rows) != 1 or not isinstance(count_rows[0], list)
            or len(count_rows[0]) != 1 or type(count_rows[0][0]) is not int
            or count_rows[0][0] < 0):
        raise ValueError("INVALID_COUNT_QUERY_RESULT")
    expected_columns = [*column_ids, row_id_key]
    columns, matrix = row_payload.get("columns"), row_payload.get("rows")
    if (not isinstance(matrix, list) or len(matrix) != count_rows[0][0]
            or columns != (list(column_ids.values()) + [row_id_key] if matrix else [])):
        raise ValueError("QUERY_COUNT_OR_SCHEMA_MISMATCH")
    rows = []
    for values in matrix:
        if not isinstance(values, list) or len(values) != len(expected_columns):
            raise ValueError("INVALID_QUERY_ROW_SHAPE")
        row = dict(zip(column_ids, values))
        row[row_id_key] = values[-1]
        rows.append(row)
    return rows


def _normalize(value, kind):
    if value is None:
        return None
    if kind == "datetime":
        if isinstance(value, datetime):
            if (value.utcoffset() not in (None, timedelta(0))
                    or value.minute or value.second or value.microsecond
                    or value.hour not in (0, 12)):
                raise ValueError("AMBIGUOUS_DATE_VALUE")
            value = value.date()
        if isinstance(value, date):
            if value.day != 1:
                raise ValueError("INVALID_MONTH_DATE")
            return value.isoformat()
        if isinstance(value, str):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                parsed = date.fromisoformat(value)
            elif re.fullmatch(r"\d{4}-\d{2}-\d{2}T(?:00|12):00:00(?:\.0{1,9})?(?:Z|\+00:00)?", value):
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            else:
                raise ValueError("AMBIGUOUS_DATE_VALUE")
            if parsed.day != 1:
                raise ValueError("INVALID_MONTH_DATE")
            return parsed.isoformat()
        raise ValueError("INVALID_DATE_VALUE")
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("INVALID_NUMERIC_VALUE")
        return float(value)
    if kind == "text":
        if not isinstance(value, str):
            raise ValueError("INVALID_TEXT_VALUE")
        return value
    raise ValueError("UNSUPPORTED_COLUMN_TYPE")


def seed_plan(*, source_packet_path, source_original, actual_source, actual_source_after, query_receipt,
              describe_receipt, role, row_id_key, prior_seed=None, max_rows=25):
    packet_hash = OPERATOR["source_packet"](source_packet_path, source_original)
    packet = json.loads(Path(source_packet_path).read_text())
    if role not in TABLES or not isinstance(row_id_key, str) or not row_id_key:
        raise ValueError("ACTUAL_ROLE_AND_ROW_ID_REQUIRED")
    if not 1 <= max_rows <= 2000:
        raise ValueError("INVALID_BATCH_SIZE")
    source = json.loads(Path(actual_source).read_text())
    if Path(actual_source).read_bytes() != Path(actual_source_after).read_bytes():
        raise ValueError("SOURCE_CHANGED_DURING_QUERY")
    if type(source.get("documentVersion")) is not int or not source.get("workbookId"):
        raise ValueError("ACTUAL_WORKBOOK_SOURCE_REQUIRED")
    elements = source.get("contents", {}).get("elements", [])
    title, names, types, _frame = TABLES[role]
    matches = [item for item in elements if item.get("name") == title]
    if len(matches) != 1:
        raise ValueError("ACTUAL_INPUT_TABLE_MISSING_OR_AMBIGUOUS")
    element = matches[0]
    if element.get("kind") != "input-table" or element.get("source", {}).get("kind") != "empty":
        raise ValueError("ACTUAL_INPUT_TABLE_KIND_MISMATCH")
    actual_columns = [c for c in element.get("columns", []) if c.get("name") is not None]
    if [(c.get("name"), c.get("type")) for c in actual_columns] != list(zip(names, types)):
        raise ValueError("ACTUAL_INPUT_TABLE_COLUMNS_MISMATCH")
    column_ids = {c["name"]: c["id"] for c in actual_columns}
    describes = json.loads(Path(describe_receipt).read_text())
    matches = [item["value"] for item in describes if item.get("status") == "fulfilled"
               and isinstance(item.get("value"), dict)
               and item["value"].get("role") == role
               and item["value"].get("elementId") == element["id"]]
    if len(matches) != 1:
        raise ValueError("ACTUAL_DDL_DESCRIBE_REQUIRED")
    if matches[0].get("request") != {"object": {"type": "workbook-element",
            "workbookId": source["workbookId"], "elementId": element["id"]}}:
        raise ValueError("ACTUAL_DDL_DESCRIBE_REQUIRED")
    ddl = matches[0]["result"]["structuredContent"]["ddl"]
    if (f'-- Workbook ID: "{source["workbookId"]}"' not in ddl
            or f'-- Element ID: "{element["id"]}"' not in ddl
            or any(f'"{column_ids[name]}" {kind}' not in ddl for name, kind in zip(names, types))):
        raise ValueError("ACTUAL_DDL_IDENTITY_MISMATCH")
    row_ids = re.findall(r'^\s+"([^"]+)" text -- "ID" \|', ddl, re.MULTILINE)
    if row_ids != [row_id_key]:
        raise ValueError("ACTUAL_ROW_ID_ALIAS_MISMATCH")
    role_spec = packet["roles"][role]
    source_rows = [{name: _normalize(row[name], kind) for name, kind in role_spec["columns"].items()}
                   for row in role_spec["rows"]]
    receipt_bytes = Path(query_receipt).read_bytes()
    receipt_hash = hashlib.sha256(receipt_bytes).hexdigest()
    requests = query_requests(source["workbookId"], element["id"], column_ids,
                              role_spec["naturalKey"], row_id_key)
    raw_rows = _rows_from_receipt(
        json.loads(receipt_bytes), requests=requests, role=role,
        element_id=element["id"], column_ids=column_ids, row_id_key=row_id_key)
    current_rows = []
    for raw in raw_rows:
        if row_id_key not in raw:
            raise ValueError("ACTUAL_QUERY_ROW_ID_MISSING")
        record = {row_id_key: raw[row_id_key]}
        for name, kind in role_spec["columns"].items():
            found = [key for key in (name, column_ids[name]) if key in raw]
            if len(found) != 1:
                raise ValueError("ACTUAL_QUERY_COLUMN_KEY_MISSING_OR_AMBIGUOUS:" + name)
            record[name] = _normalize(raw[found[0]], kind)
        current_rows.append(record)
    if prior_seed is not None and prior_seed.get("snapshot", {}).get("queryReceiptHash") == receipt_hash:
        raise ValueError("REQUERY_REQUIRED_AFTER_PRIOR_BATCH")
    # This fixed-source port permits inserts of missing keys only. Prior
    # seedRecords are untrusted assertions and must never authorize updates.
    plan = plan_seed(source_rows, current_rows, role_spec["naturalKey"], row_id_key,
                     prior_seed=None,
                     snapshot={"queryReceiptHash": receipt_hash,
                               "workbookId": source["workbookId"],
                               "workbookVersion": source["documentVersion"],
                               "elementId": element["id"], "sourcePacketHash": packet_hash},
                     column_types=role_spec["columns"])
    if prior_seed is not None and prior_seed.get("sourceHash") != plan["sourceHash"]:
        raise ValueError("PRIOR_SEED_SOURCE_CHANGED")
    if plan["updates"]:
        raise ValueError("FIXED_SOURCE_UPDATES_DISABLED")
    actions = [("insert", item) for item in plan["inserts"]]
    if plan["conflicts"] or plan["orphans"]:
        return plan, None
    if not actions:
        return plan, None
    chunk = actions[:max_rows]
    checkpoint = hashlib.sha256(json.dumps({"planHash": plan["planHash"],
                                             "snapshot": plan["snapshot"],
                                             "actions": chunk}, sort_keys=True).encode()).hexdigest()
    page_id = next((p["id"] for p in source["contents"].get("pages", [])
                    if p.get("name") == "Statistical Demand Forecast — candidate preview"), None)
    if not page_id:
        raise ValueError("ACTUAL_INPUT_PAGE_MISSING")
    lines = ["from datetime import datetime", f"# sourceHash={SOURCE_SHA256}",
             f"# sourcePacketHash={packet_hash}", f"# queryReceiptHash={receipt_hash}",
             f"# expectedWorkbookId={source['workbookId']}",
             f"# expectedWorkbookVersion={source['documentVersion']}",
             f"# checkpointId={checkpoint}",
             "# Repeat full source/version and query before execution; SDK has no row CAS.",
             f"page = sigma.workbook.get_page({page_id!r})",
             "if not isinstance(page, Page): raise RuntimeError('expected input page')",
             f"table = page.get_element({element['id']!r})",
             "if not isinstance(table, InputTable): raise RuntimeError('expected observed input table')"]
    variables = {}
    for index, name in enumerate(names):
        var = f"c{index}"; variables[name] = var
        lines += [f"{var} = table.get_column({column_ids[name]!r})",
                  f"if not isinstance({var}, LiteralEditableColumn): raise RuntimeError('expected editable {name}')"]
    inserts = [item for kind, item in chunk if kind == "insert"]
    if inserts:
        lines.append("row_ids = table.upsert_rows([")
        lines.extend(f"    {_row_expression(item['source'], variables, role_spec['columns'])},"
                     for item in inserts)
        lines.append("])")
        lines.append("print(row_ids)")
    lines.append(f"print('checkpointId={checkpoint}')")
    return plan, {"program": "\n".join(lines) + "\n", "checkpointId": checkpoint,
                  "actionCount": len(chunk), "remainingCount": len(actions) - len(chunk),
                  "snapshot": plan["snapshot"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-packet", "source-original", "actual-source", "actual-source-after", "query-receipt", "describe-receipt", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--role", choices=tuple(TABLES), required=True)
    parser.add_argument("--row-id-key", required=True)
    parser.add_argument("--prior-seed", type=Path)
    parser.add_argument("--max-rows", type=int, default=25)
    args = parser.parse_args()
    prior = json.loads(args.prior_seed.read_text()) if args.prior_seed else None
    plan, chunk = seed_plan(source_packet_path=args.source_packet,
                            source_original=args.source_original,
                            actual_source=args.actual_source,
                            actual_source_after=args.actual_source_after,
                            query_receipt=args.query_receipt,
                            describe_receipt=args.describe_receipt, role=args.role,
                            row_id_key=args.row_id_key, prior_seed=prior,
                            max_rows=args.max_rows)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"seed-plan-{args.role}.json").write_text(json.dumps(plan, indent=2) + "\n")
    if chunk:
        (args.out / f"seed-next-{args.role}.py").write_text(chunk["program"])
        (args.out / f"seed-next-{args.role}-metadata.json").write_text(
            json.dumps({key: value for key, value in chunk.items() if key != "program"}, indent=2) + "\n")
    print(json.dumps({"role": args.role, "inserts": len(plan["inserts"]),
                      "updates": len(plan["updates"]), "conflicts": len(plan["conflicts"]),
                      "orphans": len(plan["orphans"]), "nextActionCount": chunk["actionCount"] if chunk else 0}))


if __name__ == "__main__":
    main()
