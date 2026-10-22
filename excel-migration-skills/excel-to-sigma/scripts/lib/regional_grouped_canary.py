"""Source-bound, offline Regional01 B4 grouped construction candidate.

This module emits logical columns and a staged execution contract. It never
creates Sigma objects or treats authored names as server-assigned identities.
The formal 144-row Revenue template is proved from the saved source ASTs.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import copy
import hashlib
import json
from pathlib import Path
import re

from .native_exact import compile_expression, lane_dict
from .native_exact_plan import HelperGraph, input_scalar, digest, _map_helpers
from .source_inputs import validate_source_input_plan

SOURCE_SHA = "4b46bfa6190d1ef12ea35713e3932aa77f19fb964730b4b3bbb0851294219e2c"
# Independently reviewed complete candidate at f45b3a0. This constant is
# outside candidate.json and covers every emitted formula, mapping, budget,
# obligation, and qualification. A candidate-supplied digest is never trusted.
REVIEWED_CANDIDATE_DIGEST = "371046eb9c4826ae85dd8682bd6d7dd7f527869ffcf9fe5b1392a073709e4077"
CELL = "Summary!B4"
SALES_ROWS = tuple(range(2, 146))
MAX_TABLES = 8
MAX_FORMULA_COLUMNS = 128


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_reviewed_candidate(candidate):
    _require(isinstance(candidate, dict) and digest(candidate) == REVIEWED_CANDIDATE_DIGEST,
             "complete Regional B4 candidate differs from independently reviewed graph")
    return candidate


def _relative_ast(ast, row):
    """Replace only same-row source addresses; all other edges remain visible."""
    if isinstance(ast, list):
        return [_relative_ast(value, row) for value in ast]
    if not isinstance(ast, dict):
        return ast
    result = {}
    for key, value in ast.items():
        if key == "cells":
            result[key] = [re.sub(rf"(?<=!)([A-Z]+){row}$", r"\1@ROW", c)
                           for c in value]
        elif key == "activeDomain":
            result[key] = "@ROW:@ROW"
        else:
            result[key] = _relative_ast(value, row)
    return result


def build_candidate(source_path, input_plan, native_plan, oracle):
    source_path = Path(source_path)
    _require(hashlib.sha256(source_path.read_bytes()).hexdigest() == SOURCE_SHA,
             "Regional01 source bytes changed")
    validate_source_input_plan(input_plan, source_path)
    _require(input_plan["sourceSha256"] == native_plan["sourceSha256"] == SOURCE_SHA,
             "source plans do not match source bytes")
    _require(native_plan["inputPlanHash"] == input_plan["inputPlanHash"],
             "native/input plan binding mismatch")
    _require(digest({k: v for k, v in native_plan.items() if k != "nativePlanHash"}) == native_plan["nativePlanHash"],
             "native plan hash is stale")
    sales = input_plan["sharedInputArchitecture"]["inputs"]["sales-forecast"]
    _require(len(sales["rows"]) == len(SALES_ROWS) == 144, "sales row domain changed")
    _require(sales["sourceRowNumbers"] == list(SALES_ROWS), "sales source ordinal changed")
    _require(native_plan["bindings"]["Summary!A4"] == {
        "kind": "input", "featureId": "summary-regions", "rowIndex": 0,
        "column": "Region", "valueType": "text"}, "B4 region criterion lost source input")
    b4 = native_plan["formulas"][CELL]
    _require(b4["status"] == "ready-to-bind" and b4["ast"]["name"] == "SUMIFS",
             "B4 is no longer a bound SUMIFS")
    args = b4["ast"]["arguments"]
    expected_ranges = (("F", "table:tblSalesForecast:#data"),
                       ("A", "table:tblSalesForecast:#data"),
                       ("C", "table:tblSalesForecast:#data"),
                       ("C", "table:tblSalesForecast:#data"))
    for node, (col, kind) in zip((args[0], args[1], args[3], args[5]), expected_ranges):
        _require(node["kind"] == "range" and node["sourceKind"] == kind and
                 node["cells"] == [f"Forecast Input!{col}{row}" for row in SALES_ROWS],
                 "B4 formal table range changed; append semantics must be reviewed")
    _require(args[2] == {"kind": "reference", "cell": "Summary!A4"},
             "B4 region criterion is not live A4")
    _require(b4["originalFormula"] ==
             '=SUMIFS(tblSalesForecast[Revenue],tblSalesForecast[Region],$A4,tblSalesForecast[Month],">="&DATE(2026,1,1),tblSalesForecast[Month],"<"&EDATE(DATE(2026,1,1),3))',
             "B4 date criteria changed")
    formulas = native_plan["formulas"]
    revenue_ids = [f"Forecast Input!F{row}" for row in SALES_ROWS]
    first = formulas[revenue_ids[0]]
    signature = _relative_ast(first["ast"], 2)
    for row, cell in zip(SALES_ROWS, revenue_ids):
        record = formulas[cell]
        _require(record["status"] == "ready-to-bind" and
                 _relative_ast(record["ast"], row) == signature and
                 record["dependencies"] == [f"Forecast Input!D{row}", f"Forecast Input!E{row}"],
                 f"Revenue row template breaks at {cell}")
    _require(oracle["sourceSha256"] == SOURCE_SHA and oracle["sheet"] == "Summary" and
             oracle["address"] == "B4" and oracle["numericValue"] == "1544984.02" and
             oracle["excel"]["valueClass"] == "real", "independent Excel B4 oracle missing")

    # Existing typed compiler provides the five public lanes, including Excel
    # blank/text/logical/error coercion. It is applied once after proving every
    # source Revenue cell has the same row-relative expression.
    graph = HelperGraph(prefix="__regional_r")
    value = compile_expression(first["ast"],
        lambda cell: input_scalar(cell, native_plan["bindings"],
            lambda binding: f'[Sales/{binding["column"]}]'),
        emit=graph.emit, epoch=native_plan["dateEpoch"])
    columns = []
    for index, helper in enumerate(graph.nodes):
        formula = _map_helpers(helper["formula"], graph.prefix,
            lambda match: f'[h{int(match.group()[len(graph.prefix):-2])}]')
        columns.append({"id": f"h{index}", "name": f"h{index}", "formula": formula})
    for lane, formula in lane_dict(value).items():
        formula = _map_helpers(formula, graph.prefix,
            lambda match: f'[h{int(match.group()[len(graph.prefix):-2])}]')
        columns.append({"id": f"revenue_{lane}", "name": f"Revenue {lane.title()}",
                        "formula": formula})
    columns += [
        {"id": "region_key", "name": "Region Key", "formula": "Lower([Sales/Region])"},
        {"id": "year_key", "name": "Year Key", "formula": 'DatePart("year", [Sales/Month])'},
        {"id": "quarter_key", "name": "Quarter Key", "formula": 'DatePart("quarter", [Sales/Month])'},
        {"id": "group_key", "name": "Group Key",
         "formula": 'Concat([Region Key], "|", Text([Year Key]), "|", Text([Quarter Key]))'},
        {"id": "source_ordinal", "name": "Source Ordinal",
         "formula": "[Sales/Source Ordinal]"},
        {"id": "source_key", "name": "Source Key",
         "formula": "[Sales/Source Key]"},
        {"id": "source_row_id", "name": "Source Row ID",
         "formula": "[Sales/Row ID]"},
        {"id": "first_error_ordinal", "name": "First Error Ordinal",
         "formula": 'If([Revenue Error] != "", [Source Ordinal], Null)'},
    ]
    _require(all("__regional_r" not in c["formula"] and len(c["formula"]) <= 6000
                 for c in columns), "row helper did not resolve or formula exceeds limit")
    # Grouped result is a flat source derived from the live calculated row
    # table. B4's exact date interval is represented by 2026/Q1. This date
    # equivalence is valid only for non-null civil dates and needs live TZ proof.
    elements = [
        {"id": "regional_sales_rows", "kind": "calculated-table",
         "sourceFeature": "sales-forecast", "columns": columns},
        {"id": "regional_sales_region_quarter", "kind": "grouped-source",
         "sourceElement": "regional_sales_rows",
         "keys": ["Group Key"],
         "calculations": [
             {"id": "revenue_sum", "name": "Revenue Sum", "aggregate": "Sum",
              "column": "Revenue Number"},
             {"id": "first_error_ordinal", "name": "First Error Ordinal", "aggregate": "Min",
              "column": "First Error Ordinal"}],
         "sourceMethod": "Grouping.to_source",
         "keyComponents": ["Region Key", "Year Key", "Quarter Key"]},
        {"id": "regional_summary_b4", "kind": "summary-table",
         "sourceFeature": "summary-regions",
         "columns": [
             {"id": "source_key", "name": "Source Key",
              "formula": "[Summary Regions/Source Key]"},
             {"id": "source_row_id", "name": "Source Row ID",
              "formula": "[Summary Regions/Row ID]"},
             {"id": "group_key", "name": "Group Key",
              "formula": 'Concat(Lower([Summary Regions/Region]), "|2026|1")'},
             {"id": "matched_revenue", "name": "Matched Revenue",
              "formula": 'Lookup([Grouped/Revenue Sum], [Group Key], [Grouped/Group Key])'},
             {"id": "matched_error_ordinal", "name": "Matched Error Ordinal",
              "formula": 'Lookup([Grouped/First Error Ordinal], [Group Key], [Grouped/Group Key])'},
             {"id": "b4_number", "name": "B4 Number", "formula": "Coalesce([Matched Revenue], 0)"},
             {"id": "b4_text", "name": "B4 Text", "formula": '""'},
             {"id": "b4_logical", "name": "B4 Logical", "formula": "False"},
             {"id": "b4_kind", "name": "B4 Kind", "formula": '"n"'},
             {"id": "b4_error", "name": "B4 Error",
              "formula": 'If(IsNull([Matched Error Ordinal]), "", Lookup([Rows/Revenue Error], [Matched Error Ordinal], [Rows/Source Ordinal]))'}]}]
    formula_columns = sum(len(e.get("columns", [])) + len(e.get("calculations", []))
                          for e in elements)
    _require(len(elements) <= MAX_TABLES and formula_columns <= MAX_FORMULA_COLUMNS,
             "grouped canary construction budget exceeded")
    source_mapping = {cell: {"targetElement": "regional_sales_rows",
                             "laneColumnIds": {lane: f"revenue_{lane}" for lane in
                                               ("number", "text", "logical", "kind", "error")},
                             "sourceOrdinal": row - 1,
                             "sourceKey": f"Forecast Input!row:{row}"}
                      for row, cell in zip(SALES_ROWS, revenue_ids)}
    source_mapping[CELL] = {"targetElement": "regional_summary_b4", "sourceRow": 0,
                            "laneColumnIds": {lane: f"b4_{lane}" for lane in
                                              ("number", "text", "logical", "kind", "error")}}
    return {"status": "OFFLINE_GROUPED_CANARY_PENDING_STAGING", "runtimeStatus": "UNVERIFIED_CANDIDATE",
            "sourceSha256": SOURCE_SHA, "inputPlanHash": input_plan["inputPlanHash"],
            "nativePlanHash": native_plan["nativePlanHash"], "sourceFormulaSha256": b4["formulaSha256"],
            "sourceCell": CELL, "excelOracle": {"kind": "number", "number": "1544984.02"},
            "sourceRangeAppendPolicy": "formal-table-data-body; includes appended sales rows",
            "sourceRowCount": 144, "sourceMappings": source_mapping,
            "sourceDependencies": b4["dependencies"], "sourceLayer": b4["layer"],
            "elements": elements, "constructionBudget": {"tables": len(elements),
                                                    "formulaColumns": formula_columns,
                                                    "maxTables": MAX_TABLES,
                                                    "maxFormulaColumns": MAX_FORMULA_COLUMNS},
            "qualificationsRequired": [
                "Persist Source Ordinal and Source Key with all 144 ordinary sales rows; observe actual row IDs.",
                "Prove deterministic Source Ordinal assignment and first-error order for appended rows.",
                "Prove grouped DatePart year/quarter matches Excel >=2026-01-01 and <2026-04-01 under date and timezone edits.",
                "Prove Sigma grouped Sum/Min, flat grouping source, three-key join/lookup, and zero for no match.",
                "Qualify Excel case-insensitive/wildcard/blank/error SUMIFS criteria before accepting arbitrary A4 edits.",
                "Use assigned IDs and strict full-contents REST formula patch/readback if SDK nested math serialization changes text.",
                "Query final five B4 lanes after baseline, edits, reopen and restore; source B4 must remain mapped."],
            "unsupported": ["full Regional01 migration", "other 51 SUMIFS cells",
                            "four source VLOOKUP NAME errors", "charts", "production promotion"]}


def source_rows(input_plan):
    """Independent decimal fixture for comparing an emitted candidate baseline."""
    rows = input_plan["sharedInputArchitecture"]["inputs"]["sales-forecast"]["rows"]
    return [{**row, "Source Ordinal": i + 1,
             "Source Key": f"Forecast Input!row:{i+2}"} for i, row in enumerate(rows)]


def reference_b4(rows, region):
    total = Decimal(0)
    for row in rows:
        month = date.fromisoformat(row["Month"][:10]) if row["Month"] is not None else None
        if (isinstance(row["Region"], str) and row["Region"].casefold() == region.casefold()
                and month is not None and date(2026, 1, 1) <= month < date(2026, 4, 1)):
            units = Decimal(str(row["Units"] or 0))
            price = Decimal(str(row["Avg Price"] or 0))
            total += units * price
    return total


def bind_assigned_formula(formula, *, namespaces, local_columns):
    """Bind logical bracket references only after IDs/names come from readback.

    `namespaces` maps Sales/Rows/Grouped/Summary Regions to readback element
    name and exact logical-to-actual column names. Literal quoted text, such as
    a regex character class, is never scanned as a reference.
    """
    result = []
    index = 0
    while index < len(formula):
        if formula[index] == '"':
            end = index + 1
            while end < len(formula):
                if formula[end] == '\\':
                    end += 2
                elif formula[end] == '"':
                    end += 1
                    break
                else:
                    end += 1
            _require(end <= len(formula) and formula[end - 1] == '"', "unterminated formula text")
            result.append(formula[index:end]); index = end
        elif formula[index] == '[':
            end = formula.find(']', index + 1)
            _require(end != -1, "unterminated formula reference")
            key = formula[index + 1:end]
            if '/' in key:
                namespace, column = key.split('/', 1)
                binding = namespaces.get(namespace)
                _require(binding is not None and column in binding.get("columns", {}),
                         f"unassigned native reference [{key}]")
                result.append(f'[{binding["name"]}/{binding["columns"][column]["name"]}]')
            else:
                _require(key in local_columns, f"unassigned local column [{key}]")
                result.append(f'[{local_columns[key]}]')
            index = end + 1
        else:
            result.append(formula[index]); index += 1
    bound = ''.join(result)
    _require(len(bound) <= 6000, "assigned formula exceeds 6000 characters")
    return bound


def prepare_scaffold_program(candidate, *, element_kind, page_id, source_element_id,
                             grid_row, current, source_path, base_input_plan,
                             canary_input_plan, observed_inputs):
    """One documented SDK table scaffold; print assigned IDs for readback.

    The caller supplies observed page/source IDs. Grouping and the flat grouped
    table require their own qualification phase after the row formulas patch.
    """
    validate_reviewed_candidate(candidate)
    from .regional_canary_inputs import validate_phase_inputs
    validated = validate_phase_inputs(canary_input_plan, source_path, base_input_plan,
                                      candidate, current, observed_inputs)
    _require(element_kind in ("calculated-table", "summary-table"), "unsupported scaffold phase")
    feature = "sales-forecast" if element_kind == "calculated-table" else "summary-regions"
    _require(any(p.get("id") == page_id for p in current["contents"].get("pages", [])) and
             source_element_id == validated[feature]["elementId"],
             "observed page/reconciled source input IDs required")
    _require(isinstance(grid_row, int) and grid_row >= 1, "positive placement row required")
    logical = next(e for e in candidate["elements"] if e["kind"] == element_kind)
    name = "Regional Sales Rows" if element_kind == "calculated-table" else "Regional Summary B4"
    lines = [
        "# Structural placeholder only. Read back all assigned IDs before REST formulas.",
        f'p = sigma.workbook.get_page({json_quote(page_id)})',
        f't = p.add_table(sigma.data.source.element({json_quote(source_element_id)}))',
        f't.set_name({json_quote(name)})',
        f't.set_frame(1, {grid_row}, 24, 12)',
        "inherited = t.list_columns()", "assigned = []",
    ]
    for column in logical["columns"]:
        lines += [f'c = t.add_column({json_quote(column["name"])}, sigma.formula.const_num(0))',
                  'assigned.append({"logicalColumnId": ' + json_quote(column["id"])
                  + ', "actualColumnId": c.id(), "name": ' + json_quote(column["name"]) + '})']
    lines += ["for c in inherited:", "    c.delete()",
              f'print({{"logicalElementId": {json_quote(logical["id"])}, "actualElementId": t.id(), "name": {json_quote(name)}, "columns": assigned}})']
    return "\n".join(lines) + "\n"


def json_quote(value):
    return json.dumps(value, ensure_ascii=False)


def prepare_grouping_program(candidate, current, row_patch_confirmation, *,
                             row_element_id, page_id, grid_row, source_path,
                             base_input_plan, canary_input_plan, observed_inputs):
    """Emit the documented SDK grouping phase from a saved row-formula readback."""
    validate_reviewed_candidate(candidate)
    from .regional_canary_inputs import validate_phase_inputs
    validated = validate_phase_inputs(canary_input_plan, source_path, base_input_plan,
                                      candidate, current, observed_inputs)
    _require(candidate.get("status") == "OFFLINE_GROUPED_CANARY_PENDING_STAGING" and
             row_patch_confirmation.get("status") == "CONFIRMED_FORMULA_PATCH_STRUCTURE_ONLY" and
             row_patch_confirmation.get("sourceSha256") == candidate.get("sourceSha256") and
             row_patch_confirmation.get("documentId") == current.get("workbookId") and
             row_patch_confirmation.get("documentVersion") == current.get("documentVersion") and
             row_patch_confirmation.get("contentsHash") == digest(current.get("contents")),
             "saved calculated-row patch readback required before grouping")
    _require(isinstance(grid_row, int) and grid_row >= 1 and
             any(p.get("id") == page_id for p in current["contents"].get("pages", [])),
             "observed page and placement required")
    elements = current["contents"]["elements"]
    rows = [e for e in elements if e.get("id") == row_element_id]
    _require(len(rows) == 1 and rows[0].get("kind") == "table" and
             rows[0].get("name") == "Regional Sales Rows" and
             rows[0].get("source") == {"kind": "table", "elementId": validated["sales-forecast"]["elementId"]},
             "observed calculated rows/source lineage missing")
    needed = {"Group Key", "Revenue Number", "First Error Ordinal"}
    columns = rows[0].get("columns", [])
    _require(needed <= {c.get("name") for c in columns} and
             len({c.get("name") for c in columns}) == len(columns) and
             all(isinstance(c.get("id"), str) and c["id"] and
                 isinstance(c.get("formula"), str) for c in columns) and
             len({c["id"] for c in columns}) == len(columns) and
             all(c.get("formula") != "0" for c in columns if c.get("name") in needed),
             "saved group-key and aggregate source formulas required")
    _require(all(e.get("name") != "Regional Sales Region Quarter" for e in elements),
             "grouped flat table already exists")
    expected_columns = [{key: column[key] for key in ("id", "name", "formula")}
                        for column in columns]
    column_ids = {column["name"]: column["id"] for column in columns}
    lines = [
        "# CANARY_QUALIFICATION_ONLY. Re-read the full document and assigned IDs after this mutation.",
        'from sigma.levelTable import LevelTable',
        'from sigma.data.source import QueryableSource',
        f'p = sigma.workbook.get_page({json_quote(page_id)})',
        f'rows = p.get_element({json_quote(row_element_id)})',
        'if not isinstance(rows, LevelTable): raise RuntimeError("expected actual calculated-row LevelTable")',
        f'if rows.id() != {json_quote(row_element_id)} or rows.name() != "Regional Sales Rows": raise RuntimeError("calculated-row identity changed")',
        'source = rows.data_source()',
        'if not isinstance(source, QueryableSource): raise RuntimeError("expected calculated-row element source")',
        f'if source.ref() != sigma.data.source.element({json_quote(validated["sales-forecast"]["elementId"])}).ref(): raise RuntimeError("calculated-row source changed")',
        'actual_columns = [{"id": c.id(), "name": c.name(), "formula": c.formula()} for c in rows.list_columns()]',
        f'if actual_columns != {json_quote(expected_columns)}: raise RuntimeError("calculated-row columns or formulas changed")',
        f'key = rows.get_column({json_quote(column_ids["Group Key"])})',
        f'revenue = rows.get_column({json_quote(column_ids["Revenue Number"])})',
        f'error_ordinal = rows.get_column({json_quote(column_ids["First Error Ordinal"])})',
        'grouping = rows.set_groupings([[key]])[0]',
        'sum_column = grouping.set_calculation("Revenue Sum", sigma.formula.sum(revenue))',
        'min_column = grouping.set_calculation("First Error Ordinal", sigma.formula.min(error_ordinal))',
        'flat = p.add_table(grouping.to_source())',
        'flat.set_name("Regional Sales Region Quarter")',
        f'flat.set_frame(1, {grid_row}, 24, 12)',
        'print({"rowElementId": rows.id(), '
        '"sumColumnId": sum_column.id(), "minColumnId": min_column.id(), '
        '"flatElementId": flat.id(), "flatColumns": '
        '[{"id": c.id(), "name": c.name()} for c in flat.list_columns()]})',
    ]
    return {"status": "CANARY_GROUPING_PENDING_EXECUTION", "sourceSha256": candidate["sourceSha256"],
            "documentId": current["workbookId"], "documentVersion": current["documentVersion"],
            "contentsHash": digest(current["contents"]), "rowElementId": row_element_id,
            "pageId": page_id, "program": "\n".join(lines) + "\n"}


def _verified_unnamed_grouped_columns(current, namespaces, candidate):
    """Resolve SDK-omitted flat names only from the actual grouping and DDL."""
    elements = current["contents"]["elements"]
    rows_binding, flat_binding = namespaces["Rows"], namespaces["Grouped"]
    rows = next((e for e in elements if e.get("id") == rows_binding["elementId"]), None)
    flat = next((e for e in elements if e.get("id") == flat_binding["elementId"]), None)
    _require(rows is not None and flat is not None and
             rows.get("kind") == flat.get("kind") == "table" and
             rows.get("name") == rows_binding["name"] and
             flat.get("name") == flat_binding["name"] and
             rows.get("source") == {"kind": "table",
                                    "elementId": namespaces["Sales"]["elementId"]},
             "grouped row/source identity differs")
    logical_rows = next(e for e in candidate["elements"] if e["kind"] == "calculated-table")
    logical_group = next(e for e in candidate["elements"] if e["kind"] == "grouped-source")
    logical_names = {c["name"] for c in logical_rows["columns"]}
    _require(set(rows_binding["columns"]) == logical_names and
             logical_group["sourceElement"] == logical_rows["id"] and
             logical_group["keys"] == ["Group Key"] and
             [(c["name"], c["aggregate"], c["column"]) for c in logical_group["calculations"]] ==
             [("Revenue Sum", "Sum", "Revenue Number"),
              ("First Error Ordinal", "Min", "First Error Ordinal")],
             "reviewed grouped roles or row namespace incomplete")
    row_columns = rows.get("columns", [])
    row_by_id = {c.get("id"): c for c in row_columns}
    _require(len(row_by_id) == len(row_columns) == len(logical_names) + 2 and
             all(isinstance(c.get("id"), str) and c["id"] and
                 isinstance(c.get("name"), str) and c["name"] and
                 isinstance(c.get("formula"), str) and c["formula"]
                 for c in row_columns), "grouped row columns incomplete or ambiguous")
    for name, assigned in rows_binding["columns"].items():
        _require(isinstance(assigned, dict) and
                 row_by_id.get(assigned.get("id"), {}).get("name") == name and
                 assigned.get("name") == name,
                 f"grouped original row lineage differs: {name}")
    original_error = rows_binding["columns"]["First Error Ordinal"]["id"]
    _require(row_by_id[original_error]["formula"] ==
             'If([Revenue Error] != "", [Source Ordinal], Null)' and
             row_by_id[rows_binding["columns"]["Group Key"]["id"]]["formula"] ==
             'Concat([Region Key], "|", Text([Year Key]), "|", Text([Quarter Key]))',
             "grouped source key/error source formula differs")
    groupings = rows.get("groupings", [])
    _require(len(groupings) == 1 and isinstance(groupings[0].get("id"), str) and
             groupings[0]["id"] and
             groupings[0].get("groupBy") == [rows_binding["columns"]["Group Key"]["id"]] and
             len(groupings[0].get("calculations", [])) == 2,
             "actual row grouping IDs differ")
    grouping = groupings[0]
    sum_id, min_id = grouping["calculations"]
    _require(sum_id != min_id and sum_id not in
             {v["id"] for v in rows_binding["columns"].values()} and
             min_id not in {v["id"] for v in rows_binding["columns"].values()} and
             row_by_id.get(sum_id) == {"id": sum_id, "name": "Revenue Sum",
                                       "formula": "Sum([Revenue Number])"} and
             row_by_id.get(min_id) == {"id": min_id, "name": "First Error Ordinal",
                                       "formula": "Min([First Error Ordinal (1)])"},
             "actual grouped aggregate IDs/formulas differ")
    _require({c["name"] for c in row_columns} == logical_names | {"Revenue Sum"} and
             sum(c["name"] == "First Error Ordinal" for c in row_columns) == 2 and
             all(sum(c["name"] == name for c in row_columns) == 1
                 for name in logical_names - {"First Error Ordinal"}),
             "foreign or conflicting grouped row names")
    roles = [("Group Key", grouping["groupBy"][0], "text"),
             ("Revenue Sum", sum_id, "number"),
             ("First Error Ordinal", min_id, "number")]
    flat_columns = flat.get("columns", [])
    _require(flat.get("source") == {"kind": "table", "elementId": rows["id"],
                                    "groupingId": grouping["id"]} and
             len(flat_columns) == len(roles) and
             flat.get("order") == [c.get("id") for c in flat_columns] and
             all(set(c) == {"id", "formula"} for c in flat_columns) and
             len({c.get("id") for c in flat_columns}) == len(flat_columns),
             "unnamed flat grouping shape/source differs")
    _require(set(flat_binding["columns"]) == {r[0] for r in roles},
             "grouped namespace roles incomplete")
    ddl_columns = []
    for index, ((name, parent_id, kind), column) in enumerate(zip(roles, flat_columns, strict=True)):
        _require(row_by_id[parent_id]["name"] == name and
                 column["formula"] == f'[{rows["name"]}/{name}]' and
                 flat_binding["columns"][name] == {"id": column["id"], "name": name},
                 f"unnamed grouped column lineage differs: {name}")
        punctuation = "," if index < len(roles) - 1 else ""
        ddl_columns.append(f'  "{column["id"]}" {kind}{punctuation} -- '
                           f'"{name}" | Formula: [{rows["name"]}/{name}]')
    expected_ddl = "\n".join([
        '-- Type: "level table"',
        f'-- Workbook ID: "{current["workbookId"]}"',
        f'-- Element ID: "{flat["id"]}"',
        f'CREATE TABLE "workbook"."{flat["id"]}" (', *ddl_columns, ');',
    ])
    native = flat_binding.get("nativeDescribe")
    _require(isinstance(native, dict) and
             native.get("structuredContent", {}).get("ddl") == expected_ddl and
             len(native.get("content", [])) == 1 and
             isinstance(native["content"][0].get("text"), str),
             "exact native grouped DDL evidence required")
    try:
        response = json.loads(native["content"][0]["text"])
    except (ValueError, TypeError):
        response = {}
    _require(response.get("ddl") == expected_ddl,
             "native grouped DDL response representations conflict")
    return {"rows": rows, "flat": flat}


def _verified_namespaces(current, namespaces, observed_inputs, *, element_kind, candidate=None):
    elements = current["contents"]["elements"]
    required = ({"Sales", "Summary Regions", "Rows"} if element_kind == "calculated-table"
                else {"Sales", "Summary Regions", "Rows", "Grouped"})
    _require(set(namespaces) == required, "exact assigned namespaces required")
    unnamed_grouped = False
    if element_kind == "summary-table":
        flat_matches = [e for e in elements if e.get("id") == namespaces["Grouped"].get("elementId")]
        _require(len(flat_matches) == 1, "grouped namespace element absent/ambiguous")
        unnamed_grouped = any("name" not in c for c in flat_matches[0].get("columns", []))
        if unnamed_grouped:
            _require(candidate is not None, "reviewed candidate required for unnamed grouped columns")
            _verified_unnamed_grouped_columns(current, namespaces, candidate)
    result = {}
    for alias, binding in namespaces.items():
        _require(isinstance(binding.get("elementId"), str) and binding["elementId"] and
                 isinstance(binding.get("name"), str) and binding["name"] and
                 isinstance(binding.get("columns"), dict) and binding["columns"],
                 f"assigned namespace identity missing: {alias}")
        matches = [e for e in elements if e.get("id") == binding["elementId"]]
        _require(len(matches) == 1 and matches[0].get("name") == binding["name"] and
                 sum(e.get("name") == binding["name"] for e in elements) == 1,
                 f"assigned namespace absent or ambiguous: {alias}")
        element = matches[0]
        columns = element.get("columns", [])
        allow_native_grouping = unnamed_grouped and alias in ("Rows", "Grouped")
        _require(len({c.get("id") for c in columns}) == len(columns) and
                 (allow_native_grouping or len({c.get("name") for c in columns}) == len(columns)),
                 f"actual namespace column IDs/names ambiguous: {alias}")
        by_id = {c.get("id"): c for c in columns}
        for logical, assigned in binding["columns"].items():
            if logical == "Row ID" and by_id.get("ID") == {"id": "ID"}:
                _require(assigned == {"id": "ID", "name": "ID"},
                         f"actual implicit system ID lineage differs: {alias}")
                continue
            _require(isinstance(assigned, dict) and
                     isinstance(assigned.get("id"), str) and assigned["id"] and
                     isinstance(assigned.get("name"), str) and assigned["name"] and
                     (alias == "Grouped" and unnamed_grouped or
                      by_id.get(assigned["id"], {}).get("name") == assigned["name"]),
                     f"actual source column lineage differs: {alias}/{logical}")
        result[alias] = element
    _require(len({e["id"] for e in result.values()}) == len(result),
             "native namespace elements must be distinct")
    for alias, feature in (("Sales", "sales-forecast"), ("Summary Regions", "summary-regions")):
        observed = observed_inputs[feature]["receipt"]
        binding = namespaces[alias]
        _require(result[alias].get("kind") == "input-table" and
                 binding["elementId"] == observed["elementId"] and
                 binding["name"] == observed["name"] and
                 all(binding["columns"].get(name) == {"id": column_id, "name": name}
                     for name, column_id in observed["columnIds"].items()) and
                 binding["columns"].get("Row ID") == {
                     "id": observed["rowIdColumnId"], "name": observed["rowIdColumn"]},
                 f"source namespace does not match reconciled input: {alias}")
    _require(result["Rows"].get("kind") == "table" and
             result["Rows"].get("source") == {"kind": "table", "elementId": result["Sales"]["id"]},
             "calculated rows are not sourced from reconciled sales input")
    # The Grouping.to_source() representation is SDK-owned. Require the saved
    # grouped source to carry the exact observed row element ID; a new SDK
    # representation must be reviewed rather than guessed by this binder.
    if element_kind == "summary-table":
        _require(result["Grouped"].get("kind") == "table" and
                 result["Rows"]["id"] in json.dumps(result["Grouped"].get("source", {}), sort_keys=True),
                 "grouped source does not carry the observed calculated-row lineage")
    return result


def prepare_contents_patch(candidate, current, receipt, *, element_kind,
                           source_path, base_input_plan, canary_input_plan,
                           observed_inputs):
    """Prepare an exact, one-element formula patch against fresh scaffold IDs.

    The caller owns REST transport and must use the returned document version as
    an If-Match guard. Grouping creation/calculations are a separate SDK phase.
    """
    validate_reviewed_candidate(candidate)
    _require(candidate["status"] == "OFFLINE_GROUPED_CANARY_PENDING_STAGING", "candidate status changed")
    _require(element_kind in ("calculated-table", "summary-table"), "unsupported patch phase")
    _require(receipt.get("sourceSha256") == candidate["sourceSha256"] and
             receipt.get("documentId") == current.get("workbookId") and
             receipt.get("documentVersion") == current.get("documentVersion"),
             "stale source/document scaffold receipt")
    _require(isinstance(current.get("documentVersion"), int) and
             isinstance(current.get("contents", {}).get("elements"), list),
             "fresh full document readback required")
    from .regional_canary_inputs import validate_phase_inputs
    validate_phase_inputs(canary_input_plan, source_path, base_input_plan, candidate,
                          current, observed_inputs)
    _require(receipt.get("canaryInputPlanHash") == canary_input_plan["canaryInputPlanHash"],
             "canary input extension receipt is stale")
    namespace_elements = _verified_namespaces(current, receipt.get("namespaces") or {},
                                               observed_inputs, element_kind=element_kind,
                                               candidate=candidate)
    logical = next(e for e in candidate["elements"] if e["kind"] == element_kind)
    binding = receipt.get("elements", {}).get(logical["id"], {})
    _require(binding.get("elementId") and binding.get("name") and
             set(binding.get("columns", {})) == {c["id"] for c in logical["columns"]},
             "exact assigned element/column receipt required")
    original = current["contents"]
    updated = copy.deepcopy(original)
    matches = [e for e in updated["elements"] if e.get("id") == binding["elementId"]]
    _require(len(matches) == 1 and matches[0].get("name") == binding["name"],
             "assigned scaffold element changed")
    target = matches[0]
    expected_source = namespace_elements["Sales"] if element_kind == "calculated-table" else namespace_elements["Summary Regions"]
    _require(target.get("source") == {"kind": "table", "elementId": expected_source["id"]},
             "scaffold source does not match reconciled input element")
    actual = {c.get("id"): c for c in target.get("columns", [])}
    _require(set(actual) == set(binding["columns"].values()),
             "assigned scaffold columns changed")
    namespaces = receipt["namespaces"]
    local = {c["name"]: actual[binding["columns"][c["id"]]]["name"]
             for c in logical["columns"]}
    changes = []
    for column in logical["columns"]:
        actual_column = actual[binding["columns"][column["id"]]]
        _require(actual_column.get("name") == column["name"] and
                 actual_column.get("formula") == "0", "scaffold placeholder changed")
        bound = bind_assigned_formula(column["formula"], namespaces=namespaces,
                                      local_columns=local)
        actual_column["formula"] = bound
        changes.append({"logicalColumnId": column["id"], "actualColumnId": actual_column["id"],
                        "formula": bound})
    packet = {"status": "REST_FORMULA_PATCH_PENDING_EXECUTION", "sourceSha256": candidate["sourceSha256"],
              "reviewedCandidateDigest": REVIEWED_CANDIDATE_DIGEST,
              "canaryInputPlanHash": canary_input_plan["canaryInputPlanHash"],
              "documentId": current["workbookId"], "ifMatchDocumentVersion": current["documentVersion"],
              "elementId": binding["elementId"], "beforeContentsHash": digest(original),
              "afterContentsHash": digest(updated), "contents": updated, "changes": changes}
    if element_kind == "summary-table":
        a4 = observed_inputs["summary-regions"]["receipt"]["rows"]["0"]
        _require(a4["sourceCells"] == {"Region": "Summary!A4"} and
                 a4["sourceKey"] == "Summary!row:4" and a4["rowId"],
                 "B4 source A4 physical row identity is missing")
        packet["b4Source"] = {"cell": "Summary!A4", "sourceKey": a4["sourceKey"],
                              "sourceRowId": a4["rowId"],
                              "region": canary_input_plan["features"]["summary-regions"]["rows"][0]["Region"]}
    return packet


def _canonical_not_call_spacing(formula):
    """The observed Sigma formatter rule, outside text and column references.

    This deliberately is not general whitespace or expression equivalence.
    Every byte other than the single space added after a `Not` call token is
    retained, including whitespace, escaped text, regexes, and reference names.
    """
    _require(isinstance(formula, str), "formula text required")
    result, insertions = [], []
    index = 0
    while index < len(formula):
        start = index
        if formula[index] in ('"', "'"):
            quote = formula[index]
            index += 1
            while index < len(formula):
                if formula[index] == '\\':
                    index += 2
                elif formula[index] == quote:
                    index += 1
                    break
                else:
                    index += 1
            _require(index <= len(formula) and formula[index - 1] == quote,
                     "unterminated formula text")
        elif formula[index] == '[':
            end = formula.find(']', index + 1)
            _require(end != -1, "unterminated formula reference")
            index = end + 1
        elif formula[index].isalpha() or formula[index] == '_':
            index += 1
            while index < len(formula) and (formula[index].isalnum() or formula[index] == '_'):
                index += 1
            if formula[start:index] == "Not" and formula[index:index + 1] == '(':
                result.append("Not ")
                insertions.append(index)
                continue
        else:
            index += 1
        result.append(formula[start:index])
    return ''.join(result), insertions


def confirm_contents_patch(packet, readback):
    _require(packet.get("reviewedCandidateDigest") == REVIEWED_CANDIDATE_DIGEST and
             packet.get("status") == "REST_FORMULA_PATCH_PENDING_EXECUTION" and
             readback.get("workbookId") == packet.get("documentId") and
             isinstance(readback.get("documentVersion"), int) and
             readback["documentVersion"] > packet["ifMatchDocumentVersion"],
             "fresh saved document readback required")
    expected = packet.get("contents")
    expected_hash = packet["afterContentsHash"]
    _require(isinstance(expected, dict) and digest(expected) == expected_hash,
             "prepared full contents hash is stale")
    actual = readback.get("contents")
    actual_hash = digest(actual)
    normalizations = []
    comparable = copy.deepcopy(actual)
    if actual_hash != expected_hash:
        _require(isinstance(actual, dict), "saved full contents required")
        expected_targets = [e for e in expected.get("elements", [])
                            if e.get("id") == packet.get("elementId")]
        actual_targets = [e for e in comparable.get("elements", [])
                          if e.get("id") == packet.get("elementId")]
        _require(len(expected_targets) == len(actual_targets) == 1,
                 "exact owned formula element required")
        changes = packet.get("changes", [])
        ids = [change["actualColumnId"] for change in changes]
        _require(len(set(ids)) == len(ids), "ambiguous owned formula columns")
        for change in changes:
            column_id = change["actualColumnId"]
            expected_columns = [c for c in expected_targets[0].get("columns", [])
                                if c.get("id") == column_id]
            actual_columns = [c for c in actual_targets[0].get("columns", [])
                              if c.get("id") == column_id]
            _require(len(expected_columns) == len(actual_columns) == 1 and
                     expected_columns[0].get("formula") == change["formula"],
                     "prepared owned formula identity changed")
            authored, saved = change["formula"], actual_columns[0].get("formula")
            if authored == saved:
                continue
            canonical, insertions = _canonical_not_call_spacing(authored)
            _require(insertions and canonical == saved,
                     "saved owned formula differs beyond observed Not call spacing")
            normalizations.append({"logicalColumnId": change["logicalColumnId"],
                "actualColumnId": column_id,
                "rule": "not-call-single-ascii-space-before-open-paren",
                "expectedFormula": authored, "actualFormula": saved,
                "expectedFormulaSha256": hashlib.sha256(authored.encode()).hexdigest(),
                "actualFormulaSha256": hashlib.sha256(saved.encode()).hexdigest(),
                "expectedInsertionOffsets": insertions})
            actual_columns[0]["formula"] = authored
    _require(digest(comparable) == expected_hash,
             "saved full contents differ from exact candidate patch")
    return {"status": "CONFIRMED_FORMULA_PATCH_STRUCTURE_ONLY",
            "sourceSha256": packet["sourceSha256"], "documentId": packet["documentId"],
            "documentVersion": readback["documentVersion"], "contentsHash": actual_hash,
            "expectedContentsHash": expected_hash, "actualContentsHash": actual_hash,
            "formulaNormalizations": normalizations,
            "runtimeStatus": "UNVERIFIED_CANDIDATE"}


def observe_b4_query(candidate, packet, readback, query, *, source_path,
                     base_input_plan, canary_input_plan, observed_inputs):
    """Tie a runtime query row to physical Summary!A4; parity is a later check."""
    validate_reviewed_candidate(candidate)
    from .regional_canary_inputs import validate_phase_inputs
    validate_phase_inputs(canary_input_plan, source_path, base_input_plan,
                          candidate, readback, observed_inputs)
    _require(packet.get("reviewedCandidateDigest") == REVIEWED_CANDIDATE_DIGEST and
             packet.get("b4Source", {}).get("cell") == "Summary!A4" and
             packet.get("status") == "REST_FORMULA_PATCH_PENDING_EXECUTION",
             "summary B4 patch and A4 source row required")
    confirmed = confirm_contents_patch(packet, readback)
    _require(query.get("elementId") == packet["elementId"] and
             query.get("documentVersion") == confirmed["documentVersion"] and
             isinstance(query.get("snapshotId"), str) and query["snapshotId"] and
             isinstance(query.get("rows"), list),
             "fresh B4 output query required")
    a4 = packet["b4Source"]
    matches = [r for r in query["rows"] if r.get("Source Key") == a4["sourceKey"]]
    _require(len(matches) == 1 and matches[0].get("Source Row ID") == a4["sourceRowId"],
             "B4 output does not resolve the observed Summary A4 physical row")
    row = matches[0]
    lanes = {}
    for lane in ("Number", "Text", "Logical", "Kind", "Error"):
        _require(f"B4 {lane}" in row, f"B4 {lane} lane absent from query")
        lanes[lane.lower()] = row[f"B4 {lane}"]
    return {"status": "B4_QUERY_OBSERVED_UNVERIFIED", "runtimeStatus": "UNVERIFIED_CANDIDATE",
            "sourceSha256": packet["sourceSha256"], "documentId": packet["documentId"],
            "documentVersion": confirmed["documentVersion"], "querySnapshotId": query["snapshotId"],
            "sourceCell": "Summary!B4", "sourceA4RowId": a4["sourceRowId"],
            "outputElementId": packet["elementId"], "lanes": lanes}
