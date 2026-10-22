"""Two-input disposable Regional B4 fixture; never a migration staging gate."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .input_sync import _row_expression
from .native_exact_plan import digest
from .source_inputs import validate_source_input_plan

SOURCE_SHA = "4b46bfa6190d1ef12ea35713e3932aa77f19fb964730b4b3bbb0851294219e2c"
# Independent pinned review of the complete two-input projection. This
# protects create/seed even if a plan's own hash is recomputed after editing.
REVIEWED_INPUT_PLAN_DIGEST = "9d0c292bb4df1b9d67aad8d4c7dd2e628d6ec4db1c7a021893301fac244c417c"
FEATURES = ("sales-forecast", "summary-regions")
METADATA = (("Source Key", "text"), ("Source Ordinal", "number"))


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _canonical(plan):
    return {key: value for key, value in plan.items() if key != "canaryInputPlanHash"}


def validate_reviewed_input_plan(plan):
    _require(isinstance(plan, dict) and digest(plan) == REVIEWED_INPUT_PLAN_DIGEST,
             "complete Regional canary input fixture differs from independently reviewed projection")
    return plan


def build_canary_input_plan(source_path, base_input_plan, candidate):
    from .regional_grouped_canary import validate_reviewed_candidate
    validate_reviewed_candidate(candidate)
    source_path = Path(source_path)
    _require(hashlib.sha256(source_path.read_bytes()).hexdigest() == SOURCE_SHA,
             "Regional source bytes changed")
    validate_source_input_plan(base_input_plan, source_path)
    _require(base_input_plan["sourceSha256"] == candidate["sourceSha256"] == SOURCE_SHA and
             base_input_plan["inputPlanHash"] == candidate["inputPlanHash"],
             "source/input/canary identity differs")
    base = base_input_plan["sharedInputArchitecture"]["inputs"]
    _require(set(base) == {"sales-forecast", "summary-regions", "regions",
                           "summary-months", "summary-products"},
             "Regional source input feature denominator changed")
    features = {}
    for feature in FEATURES:
        source = base[feature]
        cells = source["sourceCells"]
        rows = []
        for index, original in enumerate(source["rows"]):
            row_number = source["sourceRowNumbers"][index]
            expected_cells = ({"Region": f"Summary!A{row_number}"} if feature == "summary-regions" else
                              {"Region": f"Forecast Input!A{row_number}",
                               "Product Line": f"Forecast Input!B{row_number}",
                               "Month": f"Forecast Input!C{row_number}",
                               "Units": f"Forecast Input!D{row_number}",
                               "Avg Price": f"Forecast Input!E{row_number}"})
            _require(cells[str(index)] == expected_cells, f"source field provenance differs: {feature}/{index}")
            key = f"{('Summary' if feature == 'summary-regions' else 'Forecast Input')}!row:{row_number}"
            rows.append({**original, "Source Key": key, "Source Ordinal": index + 1})
        expected_count = 144 if feature == "sales-forecast" else 4
        expected_numbers = list(range(2, 146)) if feature == "sales-forecast" else list(range(4, 8))
        _require(len(rows) == expected_count and source["sourceRowNumbers"] == expected_numbers,
                 f"source row domain differs: {feature}")
        columns = [{"name": c["name"], "type": c["type"], "lineage": "source-literal"}
                   for c in source["columns"]]
        columns += [{"name": name, "type": kind, "lineage": "migration-metadata"}
                    for name, kind in METADATA]
        features[feature] = {"name": "Regional B4 Sales Inputs" if feature == "sales-forecast" else
                             "Regional B4 Region Labels", "kind": "input-table",
                             "editMode": "published-explore", "keyColumns": ["Source Key"],
                             "columns": columns, "rows": rows, "sourceCells": cells,
                             "sourceRowNumbers": source["sourceRowNumbers"],
                             "metadataLineage": {
                                 "Source Key": "source sheet + physical original row, stable under field edits",
                                 "Source Ordinal": "original source row order 1..N; appended-row policy unresolved"}}
    formula_ids = sorted(item["sourceCellId"] for item in base_input_plan["formulaObligations"])
    _require(len(formula_ids) == 214 and len(set(formula_ids)) == 214,
             "Regional formula denominator changed")
    logical = {"status": "CANARY_QUALIFICATION_ONLY", "sourceSha256": SOURCE_SHA,
               "baseInputPlanHash": base_input_plan["inputPlanHash"],
               "nativePlanHash": candidate["nativePlanHash"],
               "sourceCell": "Summary!B4", "features": features,
               "omittedSourceInputFeatures": sorted(set(base) - set(FEATURES)),
               "pendingFormulaCellIds": formula_ids,
               "limits": {"inputTables": 2, "salesRows": 144, "summaryRows": 4},
               "scope": "disposable isolated SDK/runtime qualification; no full migration approval"}
    return {**logical, "canaryInputPlanHash": digest(logical)}


def validate_canary_input_plan(plan, source_path, base_input_plan, candidate):
    validate_reviewed_input_plan(plan)
    _require(plan.get("status") == "CANARY_QUALIFICATION_ONLY" and
             digest(_canonical(plan)) == plan.get("canaryInputPlanHash"),
             "canary input plan hash/status is stale")
    rebuilt = build_canary_input_plan(source_path, base_input_plan, candidate)
    _require(plan == rebuilt, "canary input projection differs from source")
    return plan


def _feature(plan, feature):
    _require(feature in FEATURES and feature in plan.get("features", {}),
             "canary feature is out of scope")
    return plan["features"][feature]


def prepare_input_create_program(plan, current, *, feature, page_id,
                                 connection_id, grid_row):
    validate_reviewed_input_plan(plan)
    _require(plan.get("status") == "CANARY_QUALIFICATION_ONLY" and
             digest(_canonical(plan)) == plan.get("canaryInputPlanHash"),
             "reviewed canary input plan required")
    spec = _feature(plan, feature)
    _require(isinstance(current.get("workbookId"), str) and
             type(current.get("documentVersion")) is int and
             any(p.get("id") == page_id for p in current.get("contents", {}).get("pages", [])),
             "fresh actual document/page required")
    _require(isinstance(connection_id, str) and connection_id and not connection_id.startswith("@")
             and isinstance(grid_row, int) and grid_row >= 1,
             "observed connection and placement required")
    _require(all(e.get("name") != spec["name"] for e in current["contents"].get("elements", [])),
             "canary input name already exists")
    lines = [f"# CANARY_QUALIFICATION_ONLY source={plan['sourceSha256']} plan={plan['canaryInputPlanHash']}",
             f"page = sigma.workbook.get_page({page_id!r})",
             "if not isinstance(page, Page): raise RuntimeError('expected actual page')",
             f"table = page.add_input_table({connection_id!r})",
             f"table.set_name({spec['name']!r})",
             "table.set_edit_mode('published-explore')",
             f"table.set_frame(1, {grid_row}, 24, 12)",
             "assigned = {}"]
    for column in spec["columns"]:
        lines += [f"col = table.add_editable_column({column['name']!r}, {column['type']!r})",
                  f"assigned[{column['name']!r}] = col.id()"]
    lines += ["system_columns = table.add_system_columns(['row_id'])",
              f"print({{'feature': {feature!r}, 'elementId': table.id(), 'columnIds': assigned}})"]
    return {"status": "CANARY_INPUT_CREATE_PENDING_EXECUTION", "sourceSha256": plan["sourceSha256"],
            "canaryInputPlanHash": plan["canaryInputPlanHash"], "feature": feature,
            "documentId": current["workbookId"], "documentVersion": current["documentVersion"],
            "pageId": page_id, "connectionId": connection_id, "program": "\n".join(lines) + "\n"}


def _validate_input_query_lineage(plan, feature, current, binding, query=None):
    """Bind a current query-facing ID to observed DDL and the exact row query.

    Previously saved distinct-ID receipts remain readable. Equality with the
    physical ID, or any subsequent alias transition, requires this explicit
    evidence; neither an invented alias nor equality alone establishes lineage.
    """
    lineage = binding.get("rowIdQueryLineage")
    if lineage is None:
        _require(binding["rowIdQueryColumnId"] != binding["rowIdColumnId"],
                 "physical-ID query requires fresh DDL/query lineage")
        return None
    _require(isinstance(lineage, dict) and
             lineage.get("documentId") == current["workbookId"] and
             lineage.get("documentVersion") == current["documentVersion"] and
             lineage.get("elementId") == binding["elementId"] and
             isinstance(lineage.get("snapshotId"), str) and lineage["snapshotId"],
             "fresh input DDL/query lineage scope required")
    spec = _feature(plan, feature)
    columns = [{"id": binding["columnIds"][c["name"]], "name": c["name"]}
               for c in spec["columns"]]
    columns.append({"id": binding["rowIdQueryColumnId"], "name": binding["rowIdColumn"]})
    _require(len({c["id"] for c in columns}) == len(columns),
             "query row ID overlaps a source field")
    ddl_columns = [f'  "{binding["columnIds"][c["name"]]}" {c["type"]}, -- '
        f'"{c["name"]}" | Formula: [New Input Table/{binding["columnIds"][c["name"]]}]'
        for c in spec["columns"]]
    ddl_columns.append(f'  "{binding["rowIdQueryColumnId"]}" text -- '
        f'"{binding["rowIdColumn"]}" | Formula: [New Input Table/{binding["rowIdColumnId"]}]')
    expected_ddl = '\n'.join(['-- Type: "input-table"',
        f'-- Workbook ID: "{current["workbookId"]}"',
        f'-- Element ID: "{binding["elementId"]}"',
        f'CREATE TABLE "workbook"."{binding["elementId"]}" (', *ddl_columns, ');'])
    select = ', '.join(f'"{c["id"]}" AS "{c["name"]}"' for c in columns)
    expected_request = {"query": {"type": "workbook", "workbookId": current["workbookId"],
        "sql": f'SELECT {select} FROM "workbook"."{binding["elementId"]}"'}}
    _require(lineage.get("ddl") == expected_ddl and lineage.get("columns") == columns and
             lineage.get("queryRequest") == expected_request and
             lineage.get("count") == len(spec["rows"]),
             "input query IDs are not documented by exact DDL/request/count")
    if query is not None:
        labels = [c["name"] for c in columns]
        rows = query.get("rows")
        _require(query.get("snapshotId") == lineage["snapshotId"] and
                 query.get("queryRequest") == expected_request and query.get("columns") == columns and
                 isinstance(rows, list) and len(rows) == lineage["count"] and
                 all(isinstance(row, dict) and set(row) == set(labels) for row in rows),
                 "fresh input query projection differs from documented lineage")
        _require(lineage.get("resultHash") == digest({"columns": labels,
            "rows": [[row[name] for name in labels] for row in rows]}),
            "input query values differ from observed result")
    return lineage


def _observed_schema(plan, feature, current, binding):
    validate_reviewed_input_plan(plan)
    spec = _feature(plan, feature)
    _require(binding.get("documentId") == current.get("workbookId") and
             binding.get("canaryInputPlanHash") == plan["canaryInputPlanHash"],
             "canary input receipt scope differs")
    elements = current.get("contents", {}).get("elements", [])
    matches = [e for e in elements if e.get("id") == binding.get("elementId")]
    _require(len(matches) == 1 and matches[0].get("kind") == "input-table" and
             matches[0].get("name") == spec["name"] and
             sum(e.get("name") == spec["name"] for e in elements) == 1,
             "actual canary input element is missing/ambiguous")
    element = matches[0]
    _require(element.get("source", {}).get("kind") == "empty" and
             element["source"].get("connectionId") == binding.get("connectionId"),
             "canary input connection/source differs")
    columns = element.get("columns", [])
    _require(len({c.get("id") for c in columns}) == len(columns) and
             len({c.get("name") for c in columns}) == len(columns),
             "actual canary input columns are ambiguous")
    by_id = {c.get("id"): c for c in columns}
    expected_names = {c["name"] for c in spec["columns"]}
    _require(set(binding.get("columnIds", {})) == expected_names,
             "assigned canary input column IDs incomplete")
    _require(len(columns) == len(spec["columns"]) + 1 and
             {c.get("id") for c in columns} ==
             set(binding["columnIds"].values()) | {binding.get("rowIdColumnId")} and
             binding.get("rowIdColumnId") not in set(binding["columnIds"].values()),
             "actual canary input contains foreign or overlapping columns")
    for column in spec["columns"]:
        actual = by_id.get(binding["columnIds"][column["name"]], {})
        _require(actual.get("name") == column["name"] and actual.get("type") == column["type"],
                 f"assigned canary input column differs: {feature}/{column['name']}")
    system_id = binding.get("rowIdColumnId")
    system = by_id.get(system_id, {})
    implicit_id = system == {"id": "ID"} and system_id == "ID"
    explicit_id = (system.get("name") == binding.get("rowIdColumn") and
                   binding.get("rowIdColumn") in ("ID", "Row ID") and
                   system.get("type") == "text")
    _require((implicit_id and binding.get("rowIdColumn") == "ID") or explicit_id,
             "actual input row ID physical column differs")
    _require(isinstance(binding.get("rowIdQueryColumnId"), str) and
             binding["rowIdQueryColumnId"], "explicit observed row ID query field required")
    _validate_input_query_lineage(plan, feature, current, binding)
    return element


def prepare_input_seed_program(plan, current, *, feature, binding, empty_query):
    _observed_schema(plan, feature, current, binding)
    _require(empty_query.get("elementId") == binding["elementId"] and
             empty_query.get("documentVersion") == current["documentVersion"] and
             empty_query.get("rowIdQueryColumnId") == binding["rowIdQueryColumnId"] and
             empty_query.get("snapshotId") and empty_query.get("rows") == [],
             "fresh empty input query required before first seed")
    spec = _feature(plan, feature)
    lines = ["from datetime import datetime",
             f"# CANARY_QUALIFICATION_ONLY source={plan['sourceSha256']} plan={plan['canaryInputPlanHash']}",
             f"page = sigma.workbook.get_page({binding['pageId']!r})",
             f"table = page.get_element({binding['elementId']!r})",
             "if not isinstance(table, InputTable): raise RuntimeError('expected actual input table')"]
    variables = {}
    for index, column in enumerate(spec["columns"]):
        variable = f"c{index}"; variables[column["name"]] = variable
        lines += [f"{variable} = table.get_column({binding['columnIds'][column['name']]!r})",
                  f"if not isinstance({variable}, LiteralEditableColumn): raise RuntimeError('expected editable column')"]
    types = {c["name"]: c["type"] for c in spec["columns"]}
    lines += ["row_ids = table.upsert_rows(["]
    lines += [f"    {_row_expression(row, variables, types)}," for row in spec["rows"]]
    lines += ["])", "print({'feature': " + repr(feature) + ", 'returnedRowIds': row_ids})"]
    return {"status": "CANARY_INPUT_SEED_PENDING_EXECUTION", "sourceSha256": plan["sourceSha256"],
            "canaryInputPlanHash": plan["canaryInputPlanHash"], "feature": feature,
            "documentId": current["workbookId"], "documentVersion": current["documentVersion"],
            "elementId": binding["elementId"], "emptySnapshotId": empty_query["snapshotId"],
            "expectedRows": len(spec["rows"]), "program": "\n".join(lines) + "\n"}


def _same_value(expected, observed, kind):
    if expected is None:
        return observed is None
    if kind == "datetime":
        if isinstance(observed, datetime):
            return observed.date().isoformat() == expected
        if isinstance(observed, date):
            return observed.isoformat() == expected
        if isinstance(observed, str):
            return observed[:10] == expected
        return False
    if kind == "number":
        try:
            return type(observed) is not bool and Decimal(str(expected)) == Decimal(str(observed))
        except Exception:
            return False
    return type(observed) is type(expected) and observed == expected


def reconcile_input_rows(plan, current, *, feature, binding, query):
    element = _observed_schema(plan, feature, current, binding)
    _require(query.get("elementId") == element["id"] and
             query.get("documentVersion") == current["documentVersion"] and
             query.get("rowIdQueryColumnId") == binding["rowIdQueryColumnId"] and
             isinstance(query.get("snapshotId"), str) and query["snapshotId"] and
             isinstance(query.get("rows"), list),
             "fresh physical input query required")
    lineage = _validate_input_query_lineage(plan, feature, current, binding, query)
    spec = _feature(plan, feature)
    observed = query["rows"]
    _require(len(observed) == len(spec["rows"]), "canary input row count differs")
    by_key = {}
    row_ids = set()
    for row in observed:
        key = row.get("Source Key")
        row_id = row.get(binding["rowIdColumn"])
        _require(isinstance(key, str) and key and isinstance(row_id, str) and row_id and
                 key not in by_key and row_id not in row_ids,
                 "actual source key/physical row ID is missing or duplicated")
        by_key[key] = row; row_ids.add(row_id)
    types = {c["name"]: c["type"] for c in spec["columns"]}
    mappings = {}
    for index, wanted in enumerate(spec["rows"]):
        actual = by_key.get(wanted["Source Key"])
        _require(actual is not None, "actual source key was not seeded")
        for name, expected in wanted.items():
            _require(_same_value(expected, actual.get(name), types[name]),
                     f"actual seeded source/metadata value differs: {feature}/{index}/{name}")
        mappings[str(index)] = {"sourceKey": wanted["Source Key"],
                                "sourceOrdinal": wanted["Source Ordinal"],
                                "rowId": actual[binding["rowIdColumn"]],
                                "sourceCells": spec["sourceCells"][str(index)]}
    record = {"status": "CONFIRMED_CANARY_INPUT_ROWS", "sourceSha256": plan["sourceSha256"],
              "canaryInputPlanHash": plan["canaryInputPlanHash"], "feature": feature,
              "documentId": current["workbookId"], "documentVersion": current["documentVersion"],
              "elementId": element["id"], "name": element["name"],
              "columnIds": binding["columnIds"], "rowIdColumn": binding["rowIdColumn"],
              "rowIdColumnId": binding["rowIdColumnId"], "querySnapshotId": query["snapshotId"],
              "rowIdQueryColumnId": binding["rowIdQueryColumnId"],
              "connectionId": element["source"]["connectionId"],
              "rows": mappings}
    if lineage is not None:
        record["rowIdQueryLineageHash"] = digest(lineage)
    return {**record, "receiptHash": digest(record)}


def validate_reconciled_receipt(plan, current, *, feature, binding, query, receipt):
    expected = reconcile_input_rows(plan, current, feature=feature, binding=binding, query=query)
    _require(receipt == expected, "canary row reconciliation receipt is stale")
    return expected


def validate_phase_inputs(plan, source_path, base_input_plan, candidate,
                          current, observed_inputs):
    """Require fresh, exact physical-row evidence before a native phase."""
    validate_canary_input_plan(plan, source_path, base_input_plan, candidate)
    _require(set(observed_inputs) == set(FEATURES),
             "both actual canary input queries are required")
    return {feature: validate_reconciled_receipt(plan, current, feature=feature,
            binding=observed_inputs[feature]["binding"],
            query=observed_inputs[feature]["query"],
            receipt=observed_inputs[feature]["receipt"])
            for feature in FEATURES}


def confirm_phase_input_stability(plan, source_path, base_input_plan, candidate,
                                  before_current, before_inputs,
                                  after_current, after_inputs):
    """Post-mutation check: every original physical row and metadata stays put."""
    before = validate_phase_inputs(plan, source_path, base_input_plan, candidate,
                                   before_current, before_inputs)
    after = validate_phase_inputs(plan, source_path, base_input_plan, candidate,
                                  after_current, after_inputs)
    _require(before_current["workbookId"] == after_current["workbookId"] and
             after_current["documentVersion"] > before_current["documentVersion"],
             "post-mutation document version did not advance")
    aliases = {}
    for feature in FEATURES:
        for field in ("elementId", "name", "columnIds", "rowIdColumn", "rowIdColumnId",
                      "connectionId", "rows"):
            _require(before[feature][field] == after[feature][field],
                     f"canary physical source or metadata drifted after native edit: {feature}/{field}")
        _require(before[feature]["querySnapshotId"] != after[feature]["querySnapshotId"],
                 "post-mutation source query reused an earlier snapshot")
        if before[feature]["rowIdQueryColumnId"] != after[feature]["rowIdQueryColumnId"]:
            _require(after[feature].get("rowIdQueryLineageHash"),
                     "changed input query alias requires fresh DDL/query lineage")
        aliases[feature] = {"physicalColumnId": after[feature]["rowIdColumnId"],
            "beforeQueryColumnId": before[feature]["rowIdQueryColumnId"],
            "afterQueryColumnId": after[feature]["rowIdQueryColumnId"],
            "beforeReceiptHash": before[feature]["receiptHash"],
            "afterReceiptHash": after[feature]["receiptHash"],
            "afterLineageHash": after[feature].get("rowIdQueryLineageHash")}
    return {"status": "CONFIRMED_CANARY_INPUTS_STABLE_AFTER_EDIT",
            "sourceSha256": plan["sourceSha256"],
            "canaryInputPlanHash": plan["canaryInputPlanHash"],
            "documentId": after_current["workbookId"],
            "beforeDocumentVersion": before_current["documentVersion"],
            "afterDocumentVersion": after_current["documentVersion"],
            "queryAliasLineage": aliases,
            "beforeQuerySnapshotIds": {f: before[f]["querySnapshotId"] for f in FEATURES},
            "afterQuerySnapshotIds": {f: after[f]["querySnapshotId"] for f in FEATURES}}
