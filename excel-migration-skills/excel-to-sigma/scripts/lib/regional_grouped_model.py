"""Source-profiled Regional grouped IR and independent local SUMIFS oracle.

This is an offline construction plan. Every source formula retains its own
provenance and qualification state; only identical record calculations and
reviewed aggregation shapes are interned. No target calls occur here.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
import calendar
import copy
import hashlib
import json
import re

from .native_exact_plan import digest
from .native_frames import validate_native_grid_program


def _blocked(message):
    raise ValueError("BLOCKED Regional grouped profile: " + message)


def _cell(node):
    if not isinstance(node, dict) or node.get("kind") != "reference":
        _blocked("selector is not a source cell reference")
    return node["cell"]


def _number(node):
    if node.get("kind") != "number":
        _blocked("date or lookup argument is not a constant number")
    return int(node["source"])


def _date(node):
    if node.get("kind") != "function" or node.get("name") != "DATE":
        _blocked("quarter boundary is not DATE")
    y, m, d = map(_number, node["arguments"])
    return date(y, m, d)


def _edate(node):
    if node.get("kind") != "function" or node.get("name") != "EDATE":
        _blocked("upper quarter boundary is not EDATE")
    start = _date(node["arguments"][0])
    months = _number(node["arguments"][1])
    index = start.year * 12 + start.month - 1 + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def _range_column(node, source_sheet, first_row, last_row, expected_source_kind):
    if node.get("kind") != "range" or node.get("sourceKind") != expected_source_kind:
        _blocked("SUMIFS range is not a formal table data body")
    cells = node.get("cells", [])
    match = re.fullmatch(r"(.+)!([A-Z]+)(\d+)", cells[0]) if cells else None
    if not match or match.group(1) != source_sheet or int(match.group(3)) != first_row or cells != [
            f"{source_sheet}!{match.group(2)}{r}" for r in range(first_row, last_row + 1)]:
        _blocked("SUMIFS range/provenance changed")
    return match.group(2)


def _binding(bindings, source_cell, feature, column=None):
    binding = bindings.get(source_cell)
    if not binding or binding.get("kind") != "input" or binding.get("featureId") != feature or (
            column is not None and binding.get("column") != column):
        _blocked(f"missing reviewed physical input binding for {source_cell}")
    return {"featureId": feature, "column": binding["column"],
            "rowIndex": binding["rowIndex"], "sourceCell": source_cell}


def _relative_revenue(ast, row, sheet):
    if ast.get("kind") != "binary" or ast.get("operator") != "*":
        _blocked("Revenue is not a multiply expression")
    refs = [ast.get("left"), ast.get("right")]
    if any(x.get("kind") != "range" or x.get("sourceKind", "").split(":")[-1] != "#this row" or len(x.get("cells", [])) != 1 for x in refs):
        _blocked("Revenue has non-record operands")
    return [re.sub(rf"^{re.escape(sheet)}!([A-Z]+){row}$", r"\1@ROW", x["cells"][0]) for x in refs]


def build_grouped_model(input_plan, native_plan):
    """Recognize only the reviewed finite graph, with all formula cells mapped."""
    if native_plan.get("nativePlanVersion") != 2 or digest({k: v for k, v in native_plan.items()
                                                              if k != "nativePlanHash"}) != native_plan.get("nativePlanHash"):
        _blocked("native plan hash is stale")
    if input_plan.get("sourceSha256") != native_plan.get("sourceSha256") or input_plan.get("inputPlanHash") != native_plan.get("inputPlanHash"):
        _blocked("input/source identity changed")
    inputs = input_plan["sharedInputArchitecture"]["inputs"]
    if set(inputs) != {"sales-forecast", "regions", "summary-regions", "summary-months", "summary-products"}:
        _blocked("five editable source roles changed")
    formulas = native_plan["formulas"]
    bindings = native_plan["bindings"]
    for cell, record in formulas.items():
        if record.get("status") != "ready-to-bind" or record.get("astHash") != digest(record.get("ast")) or record.get("formulaSha256") != hashlib.sha256(record.get("originalFormula", "").encode()).hexdigest():
            _blocked(f"source AST/formula provenance changed at {cell}")
    counts = Counter((f.get("ast") or {}).get("name", (f.get("ast") or {}).get("kind")) for f in formulas.values())
    if counts != Counter({"binary": 144, "SUMIFS": 52, "VLOOKUP": 4, "IFERROR": 4, "SUM": 9, "text": 1}):
        _blocked("formula profile changed")
    sales_bindings = [(cell, b) for cell, b in bindings.items() if b.get("featureId") == "sales-forecast"]
    sales_sheets = {cell.rsplit("!", 1)[0] for cell, _ in sales_bindings}
    if len(sales_sheets) != 1:
        _blocked("sales source sheet ambiguous")
    sales_sheet = next(iter(sales_sheets))
    source_rows = input_plan["sharedInputArchitecture"]["inputs"]["sales-forecast"]["sourceRowNumbers"]
    if len(source_rows) != 144 or source_rows != list(range(source_rows[0], source_rows[0] + 144)):
        _blocked("Revenue source row domain changed")
    first_row, last_row = source_rows[0], source_rows[-1]
    revenue = []
    signature = None
    revenue_row_kind = None
    for cell, record in formulas.items():
        ast = record.get("ast") or {}
        if ast.get("kind") != "binary":
            continue
        sheet, address = cell.rsplit("!", 1)
        match = re.fullmatch(r"([A-Z]+)(\d+)", address)
        if sheet != sales_sheet or not match:
            _blocked("foreign multiply formula")
        row = int(match.group(2))
        relative = _relative_revenue(ast, row, sheet)
        if signature is None:
            signature = relative
            revenue_row_kind = ast["left"]["sourceKind"]
        if ast["left"]["sourceKind"] != revenue_row_kind or ast["right"]["sourceKind"] != revenue_row_kind:
            _blocked(f"Revenue formal table provenance changed at {cell}")
        if relative != signature or record.get("status") != "ready-to-bind":
            _blocked(f"Revenue row template breaks at {cell}")
        dependencies = [ast["left"]["cells"][0], ast["right"]["cells"][0]]
        if set(dependencies) != set(record["dependencies"]):
            _blocked(f"Revenue dependencies changed at {cell}")
        for dep in dependencies:
            _binding(bindings, dep, "sales-forecast")
        revenue.append((row, cell, record))
    if [r for r, _, _ in sorted(revenue)] != source_rows:
        _blocked("Revenue does not cover every sales record")
    revenue_column = re.fullmatch(r"([A-Z]+)\d+", revenue[0][1].rsplit("!", 1)[1]).group(1)
    revenue_source_kind = revenue_row_kind
    if not revenue_source_kind.endswith(":#this row"):
        _blocked("Revenue formal-row provenance changed")
    data_source_kind = revenue_source_kind[:-len("#this row")] + "#data"
    mappings = {}
    for row, cell, record in revenue:
        mappings[cell] = {"kind": "record-revenue", "sourceCell": cell,
                          "sourceFormulaSha256": record["formulaSha256"],
                          "sourceAstHash": record["astHash"], "sourceDependencies": record["dependencies"],
                          "sourceOrdinal": row - first_row + 1, "sourceKey": f"{sales_sheet}!row:{row}",
                          "targetElement": "sales-rows", "targetField": "Revenue",
                          "runtimeStatus": "PENDING_QUALIFICATION"}
    periods = {"region-quarter": {}, "product-month": {}}
    for cell, record in formulas.items():
        ast = record.get("ast") or {}
        if ast.get("name") != "SUMIFS":
            continue
        args = ast["arguments"]
        if len(args) not in (5, 7):
            _blocked(f"SUMIFS criteria shape changed at {cell}")
        if _range_column(args[0], sales_sheet, first_row, last_row, data_source_kind) != revenue_column:
            _blocked(f"SUMIFS sum range changed at {cell}")
        selector_cell = _cell(args[2])
        if len(args) == 7:
            kind, feature, selector_column = "region-quarter", "summary-regions", "Region"
            if _range_column(args[1], sales_sheet, first_row, last_row, data_source_kind) != _source_col(bindings, sales_sheet, first_row, "Region"):
                _blocked(f"region criteria range changed at {cell}")
            month_col = _source_col(bindings, sales_sheet, first_row, "Month")
            if _range_column(args[3], sales_sheet, first_row, last_row, data_source_kind) != month_col or _range_column(args[5], sales_sheet, first_row, last_row, data_source_kind) != month_col:
                _blocked(f"quarter month ranges changed at {cell}")
            lower, upper = args[4], args[6]
            if lower.get("kind") != "binary" or upper.get("kind") != "binary" or lower.get("operator") != upper.get("operator") != "&" or lower["left"] != {"kind": "text", "value": ">="} or upper["left"] != {"kind": "text", "value": "<"}:
                _blocked(f"quarter bound operators changed at {cell}")
            start = _date(lower["right"])
            end = _edate(upper["right"])
            if _date(upper["right"]["arguments"][0]) != start or (end.year * 12 + end.month) - (start.year * 12 + start.month) != 3:
                _blocked(f"quarter bounds changed at {cell}")
            period = {"start": start.isoformat(), "endExclusive": end.isoformat()}
            selector = _binding(bindings, selector_cell, feature, selector_column)
            month_selector = None
        else:
            kind, feature, selector_column = "product-month", "summary-products", "Product Line"
            if _range_column(args[1], sales_sheet, first_row, last_row, data_source_kind) != _source_col(bindings, sales_sheet, first_row, "Product Line") or _range_column(args[3], sales_sheet, first_row, last_row, data_source_kind) != _source_col(bindings, sales_sheet, first_row, "Month"):
                _blocked(f"product/month criteria ranges changed at {cell}")
            selector = _binding(bindings, selector_cell, feature, selector_column)
            month_selector = _binding(bindings, _cell(args[4]), "summary-months", "Month")
            period = {"exactMonthSelector": month_selector}
        descriptor = {"kind": kind, "sourceCell": cell,
                      "sourceFormulaSha256": record["formulaSha256"],
                      "sourceAstHash": record["astHash"], "sourceDependencies": record["dependencies"],
                      "selector": selector, "period": period,
                      "targetElement": "region-summary" if kind == "region-quarter" else "product-summary",
                      "runtimeStatus": "PENDING_QUALIFICATION"}
        if kind == "region-quarter":
            descriptor["targetRowIndex"] = selector["rowIndex"]
            descriptor["targetField"] = f'Quarter {(start.month - 1) // 3 + 1}'
        else:
            descriptor["targetRowIndex"] = month_selector["rowIndex"]
            descriptor["targetField"] = f'Product {selector["rowIndex"] + 1}'
        mappings[cell] = descriptor
        periods[kind][cell] = descriptor
    if len(periods["region-quarter"]) != 16 or len(periods["product-month"]) != 36:
        _blocked("period matrix incomplete")
    region_slots = {(m["targetRowIndex"], m["targetField"]) for m in periods["region-quarter"].values()}
    product_slots = {(m["targetRowIndex"], m["targetField"]) for m in periods["product-month"].values()}
    if len(region_slots) != 16 or len(product_slots) != 36:
        _blocked("grouped output slots collide")
    for cell, record in formulas.items():
        if cell in mappings:
            continue
        ast = record.get("ast") or {}
        name = ast.get("name")
        kind = {"VLOOKUP": "lookup", "IFERROR": "ratio", "SUM": "total"}.get(name)
        if ast.get("kind") == "text":
            kind = "text"
        if kind is None:
            _blocked(f"unrecognized source vertex {cell}")
        secondary = _verify_secondary(kind, ast, bindings, formulas, cell, inputs)
        mappings[cell] = {"kind": kind, "sourceCell": cell,
                          "sourceFormulaSha256": record["formulaSha256"],
                          "sourceAstHash": record["astHash"], "sourceDependencies": record["dependencies"],
                          "sourceAst": ast, "targetElement": "region-summary" if kind in ("lookup", "ratio") else "totals",
                          "runtimeStatus": "PENDING_QUALIFICATION", **secondary}
    if set(mappings) != set(formulas):
        _blocked("source formula mappings are incomplete")
    elements = [
        {"id": "sales-rows", "kind": "calculated-table", "sourceFeature": "sales-forecast",
         "columns": ["Revenue Number", "Revenue Text", "Revenue Logical", "Revenue Kind", "Revenue Error",
                     "Source Ordinal", "Source Key", "Region Key", "Year Key", "Quarter Key",
                     "Product Key", "Month Key", "Group Key", "First Error Ordinal"]},
        {"id": "region-quarter", "kind": "grouped-source", "sourceElement": "sales-rows",
         "keys": ["Group Key"], "aggregates": ["Revenue Sum", "First Error Ordinal"]},
        {"id": "product-rows", "kind": "calculated-table", "sourceElement": "sales-rows",
         "columns": ["Product Key", "Month Key", "Revenue Number", "Revenue Error", "Source Ordinal"]},
        {"id": "product-month", "kind": "grouped-source", "sourceElement": "product-rows",
         "keys": ["Product Key", "Month Key"], "aggregates": ["Revenue Sum", "First Error Ordinal"]},
        {"id": "region-summary", "kind": "calculated-table", "sourceFeature": "summary-regions",
         "columns": [f"{field} {lane}" for field in ("Quarter 1", "Quarter 2", "Quarter 3", "Quarter 4", "Annual", "Target", "Ratio") for lane in ("Number", "Text", "Logical", "Kind", "Error")]},
        {"id": "product-summary", "kind": "calculated-table", "sourceFeature": "summary-months",
         "columns": [f"{field} {lane}" for field in ("Product 1", "Product 2", "Product 3") for lane in ("Number", "Text", "Logical", "Kind", "Error")]},
        {"id": "totals", "kind": "calculated-table", "sourceFeature": "summary-regions",
         "columns": [f"{field} {lane}" for field in ("Quarter Total 1", "Quarter Total 2", "Quarter Total 3", "Quarter Total 4", "Grand Total", "Total Label") for lane in ("Number", "Text", "Logical", "Kind", "Error")]},
    ]
    return {"status": "OFFLINE_GROUPED_MODEL_PENDING_STAGING", "runtimeStatus": "UNVERIFIED_CANDIDATE",
            "sourceSha256": native_plan["sourceSha256"], "inputPlanHash": native_plan["inputPlanHash"],
            "nativePlanHash": native_plan["nativePlanHash"], "formulaCount": len(mappings),
            "editableInputs": list(inputs), "recordProfile": {"sheet": sales_sheet,
                "firstRow": first_row, "lastRow": last_row, "revenueColumn": revenue_column,
                "revenueOperandColumns": signature, "formalDataSourceKind": data_source_kind}, "sourceMappings": mappings,
            "elements": elements, "constructionBudget": {"tables": len(elements),
                "logicalRoleColumns": sum(len(e.get("columns", [])) + len(e.get("aggregates", [])) for e in elements)},
            "qualificationsRequired": ["Actual typed SDK row/grouped/join formulas and assigned alias readbacks",
                "All 214 five-lane formula outputs, edits, reopen, and restoration",
                "SUMIFS wildcard/case/blank/error criteria and first included error order",
                "Exact month date equality and quarter civil-date/timezone boundaries",
                "VLOOKUP exact first duplicate, missing key, error and source capture reconciliation",
                "Appended sales records and stable source ordinal", "Two source charts, layout, and five editable inputs"]}


def _source_col(bindings, sheet, row, column):
    found = []
    for cell, binding in bindings.items():
        match = re.fullmatch(r"([A-Z]+)(\d+)", cell.rsplit("!", 1)[1]) if cell.startswith(sheet + "!") else None
        if match and int(match.group(2)) == row and binding.get("featureId") == "sales-forecast" and binding.get("column") == column:
            found.append(match.group(1))
    if len(found) != 1:
        _blocked(f"source column {column} ambiguous")
    return found[0]


def _verify_secondary(kind, ast, bindings, formulas, cell, inputs):
    args = ast.get("arguments", [])
    if kind == "lookup":
        if len(args) != 4 or _number(args[2]) != 3 or args[3] != {"kind": "boolean", "value": False}:
            _blocked(f"VLOOKUP shape changed at {cell}")
        selector = _binding(bindings, _cell(args[0]), "summary-regions", "Region")
        if args[1].get("kind") != "range" or not args[1].get("sourceKind", "").startswith("table:"):
            _blocked(f"VLOOKUP table changed at {cell}")
        ordered = []
        for row_index in range(len(inputs["regions"]["rows"])):
            row = []
            for column in ("Region", "Region Manager", "FY26 Target"):
                candidates = [source for source, binding in bindings.items()
                              if binding.get("kind") == "input" and binding.get("featureId") == "regions"
                              and binding.get("rowIndex") == row_index and binding.get("column") == column]
                if len(candidates) != 1:
                    _blocked(f"VLOOKUP physical source order ambiguous at {cell}")
                row.append(candidates[0])
            ordered.extend(row)
        if args[1]["cells"] != ordered:
            _blocked(f"VLOOKUP first-duplicate source order changed at {cell}")
        return {"selector": selector, "lookupSourceOrder": ordered,
                "targetRowIndex": selector["rowIndex"], "targetField": "Target"}
    elif kind == "ratio":
        if len(args) != 2 or args[1] != {"kind": "number", "source": "0"} or args[0].get("kind") != "binary" or args[0].get("operator") != "/":
            _blocked(f"IFERROR ratio changed at {cell}")
        for node in (args[0]["left"], args[0]["right"]):
            if _cell(node) not in formulas:
                _blocked(f"IFERROR edge changed at {cell}")
        return {"numeratorSourceCell": _cell(args[0]["left"]),
                "denominatorSourceCell": _cell(args[0]["right"]),
                "targetField": "Ratio"}
    elif kind == "total":
        if len(args) != 1 or args[0].get("kind") != "range" or args[0].get("sourceKind") != "cell_range" or not all(x in formulas for x in args[0]["cells"]):
            _blocked(f"SUM total edges changed at {cell}")
        return {"summedSourceCells": args[0]["cells"]}
    elif kind == "text" and ast.get("value") != "Total":
        _blocked(f"source text changed at {cell}")
    return {}


def evaluate_sumifs(mapping, sales_rows, input_plan, *, errors=None):
    """Independent finite-profile oracle; returns first included source error."""
    if mapping["kind"] not in ("region-quarter", "product-month"):
        raise ValueError("SUMIFS mapping required")
    inputs = input_plan["sharedInputArchitecture"]["inputs"]
    selector = mapping["selector"]
    criterion = inputs[selector["featureId"]]["rows"][selector["rowIndex"]][selector["column"]]
    if not isinstance(criterion, str):
        _blocked("non-text selector needs separate Excel criteria qualification")
    month_value = None
    if mapping["kind"] == "product-month":
        month = mapping["period"]["exactMonthSelector"]
        month_value = inputs[month["featureId"]]["rows"][month["rowIndex"]][month["column"]]
    result = Decimal(0)
    for ordinal, row in enumerate(sales_rows, 1):
        value = row["Region"] if mapping["kind"] == "region-quarter" else row["Product Line"]
        if not isinstance(value, str) or value.casefold() != criterion.casefold():
            continue
        month = row["Month"]
        if mapping["kind"] == "region-quarter":
            if month is None or not mapping["period"]["start"] <= str(month)[:10] < mapping["period"]["endExclusive"]:
                continue
        elif month != month_value:
            continue
        if errors and ordinal in errors:
            return errors[ordinal]
        units = Decimal(str(row["Units"] or 0))
        price = Decimal(str(row["Avg Price"] or 0))
        result += units * price
    return result


def evaluate_lookup(mapping, input_plan, *, region_rows=None, selector_value=None):
    """Local exact-match first-row reference, independent of native output."""
    if mapping["kind"] != "lookup":
        raise ValueError("VLOOKUP mapping required")
    inputs = input_plan["sharedInputArchitecture"]["inputs"]
    source_rows = region_rows if region_rows is not None else inputs["regions"]["rows"]
    selector = mapping["selector"]
    wanted = selector_value if selector_value is not None else inputs[selector["featureId"]]["rows"][selector["rowIndex"]][selector["column"]]
    for row in source_rows:
        key = row["Region"]
        if isinstance(key, str) and isinstance(wanted, str) and key.casefold() == wanted.casefold():
            return row["FY26 Target"] if row["FY26 Target"] is not None else 0
    return "#N/A"


def _observed_rows(current, row_element_id, sales_element_id):
    if not isinstance(current.get("documentVersion"), int) or not isinstance(current.get("contents", {}).get("elements"), list):
        _blocked("fresh full document/version readback required")
    elements = current["contents"]["elements"]
    rows = [x for x in elements if x.get("id") == row_element_id]
    sales = [x for x in elements if x.get("id") == sales_element_id]
    if len(rows) != 1 or len(sales) != 1 or rows[0].get("kind") != "table" or sales[0].get("kind") != "input-table" or rows[0].get("source") != {"kind": "table", "elementId": sales_element_id}:
        _blocked("actual sales-row/source lineage changed")
    columns = rows[0].get("columns", [])
    by_name = {}
    for column in columns:
        if column.get("name") and column["name"] in by_name:
            # Grouping adds a second First Error Ordinal, but the original
            # source column remains identified by its formula.
            if column["name"] != "First Error Ordinal":
                _blocked("ambiguous saved row column names")
        by_name[column.get("name")] = column
    for name in ("Revenue Number", "Revenue Error", "Source Ordinal", "Group Key"):
        if name not in by_name or not by_name[name].get("id") or by_name[name].get("formula") in (None, "0"):
            _blocked("proven shared Revenue/group source column absent")
    return rows[0], sales[0]


def _row_sdk_metadata_guard(current, rows, sdk_metadata_receipt):
    """Bind an explicitly reviewed SDK display projection to exact saved REST rows.

    The default stays the strict REST projection. The optional receipt must be a
    complete ordered SDK observation for this workbook/version/contents and
    declare every display-name difference by physical column ID. It changes
    only the generated read guard, never the saved source or formula bindings.
    """
    expected = [{"id": c["id"], "name": c.get("name"), "formula": c.get("formula")}
                for c in rows["columns"]]
    if sdk_metadata_receipt is None:
        return expected
    receipt = sdk_metadata_receipt
    if not isinstance(receipt, dict) or set(receipt) != {
            "documentId", "documentVersion", "contentsHash", "elementId",
            "columns", "reviewedNameDifferences"}:
        _blocked("complete explicit SDK metadata receipt required")
    if (receipt["documentId"] != current.get("workbookId") or
            type(receipt["documentVersion"]) is not int or
            receipt["documentVersion"] != current.get("documentVersion") or
            receipt["contentsHash"] != digest(current.get("contents")) or
            receipt["elementId"] != rows.get("id")):
        _blocked("SDK metadata receipt source/version/content binding differs")
    columns = receipt["columns"]
    differences = receipt["reviewedNameDifferences"]
    if (not isinstance(columns, list) or len(columns) != len(expected) or
            not isinstance(differences, list) or
            any(not isinstance(c, dict) or set(c) != {"id", "name", "formula"} or
                not isinstance(c["id"], str) or not c["id"] or
                not isinstance(c["name"], str)
                for c in columns) or
            any(not isinstance(d, dict) or set(d) != {"id", "restName", "sdkName"} or
                not all(isinstance(d[key], str) for key in ("id", "restName", "sdkName"))
                for d in differences)):
        _blocked("SDK metadata receipt columns/review incomplete")
    if len({c["id"] for c in columns}) != len(columns):
        _blocked("SDK metadata receipt column IDs duplicate")
    observed_differences = []
    for rest, sdk in zip(expected, columns):
        if (sdk["id"] != rest["id"] or sdk["formula"] != rest["formula"] or
                not isinstance(sdk["name"], str)):
            _blocked("SDK metadata receipt ID/order/formula differs")
        if sdk["name"] != rest["name"]:
            observed_differences.append({"id": rest["id"], "restName": rest["name"],
                                         "sdkName": sdk["name"]})
    if differences != observed_differences:
        _blocked("SDK display differences require exact ordered caller review")
    return columns


def prepare_product_key_scaffold(model, current, *, row_element_id, sales_element_id,
                                 page_id, sdk_metadata_receipt=None):
    """SDK structural extension; caller must read back IDs before formulas."""
    if model.get("status") != "OFFLINE_GROUPED_MODEL_PENDING_STAGING":
        _blocked("unreviewed grouped model")
    rows, sales = _observed_rows(current, row_element_id, sales_element_id)
    if any(c.get("name") in ("Product Key", "Month Key") for c in rows["columns"]):
        _blocked("product/month key already exists; reconcile previous phase")
    if not any(p.get("id") == page_id for p in current["contents"].get("pages", [])):
        _blocked("observed page ID required")
    expected = _row_sdk_metadata_guard(current, rows, sdk_metadata_receipt)
    lines = [
        "# STAGING ONLY: structural add; read back IDs, then exact versioned formula patch.",
        "from sigma.levelTable import LevelTable",
        "from sigma.data.source import QueryableSource",
        f'p = sigma.workbook.get_page({json.dumps(page_id)})',
        f'rows = p.get_element({json.dumps(row_element_id)})',
        'if not isinstance(rows, LevelTable): raise RuntimeError("actual row table changed")',
        f'if rows.id() != {json.dumps(row_element_id)} or rows.name() != {json.dumps(rows["name"])}: raise RuntimeError("row identity changed")',
        'source = rows.data_source()',
        'if not isinstance(source, QueryableSource): raise RuntimeError("row source changed")',
        f'if source.ref() != sigma.data.source.element({json.dumps(sales_element_id)}).ref(): raise RuntimeError("sales source changed")',
        'actual = []',
        'for c in rows.list_columns():',
        '    actual.append({"id": c.id(), "name": c.name(), "formula": c.formula()})',
        f'if actual != {json.dumps(expected)}: raise RuntimeError("row columns/formulas changed")',
        'product = rows.add_column("Product Key", sigma.formula.const_num(0))',
        'month = rows.add_column("Month Key", sigma.formula.const_num(0))',
        'print({"rowElementId": rows.id(), "productKeyColumnId": product.id(), "monthKeyColumnId": month.id()})',
    ]
    return {"status": "PRODUCT_KEY_SCAFFOLD_PENDING_EXECUTION", "sourceSha256": model["sourceSha256"],
            "documentId": current["workbookId"], "documentVersion": current["documentVersion"],
            "contentsHash": digest(current["contents"]), "rowElementId": row_element_id,
            "salesElementId": sales["id"], "program": "\n".join(lines) + "\n"}


def prepare_product_key_patch(model, current, scaffold, *, row_element_id,
                              sales_element_id, product_column_id, month_column_id):
    """Full-content CAS packet using only observed IDs and actual input alias."""
    if model.get("status") != "OFFLINE_GROUPED_MODEL_PENDING_STAGING":
        _blocked("unreviewed grouped model")
    if scaffold.get("status") != "PRODUCT_KEY_SCAFFOLD_PENDING_EXECUTION" or scaffold.get("sourceSha256") != model["sourceSha256"] or scaffold.get("documentId") != current.get("workbookId") or scaffold.get("rowElementId") != row_element_id or scaffold.get("salesElementId") != sales_element_id:
        _blocked("key scaffold provenance differs")
    rows, sales = _observed_rows(current, row_element_id, sales_element_id)
    columns = {c.get("id"): c for c in rows["columns"]}
    if product_column_id == month_column_id or columns.get(product_column_id, {}).get("name") != "Product Key" or columns.get(month_column_id, {}).get("name") != "Month Key" or columns[product_column_id].get("formula") != "0" or columns[month_column_id].get("formula") != "0":
        _blocked("fresh assigned key-column placeholders required")
    sales_names = {c.get("name") for c in sales.get("columns", [])}
    if not {"Product Line", "Month"} <= sales_names:
        _blocked("source input columns changed")
    updated = copy.deepcopy(current["contents"])
    target = next(e for e in updated["elements"] if e.get("id") == row_element_id)
    for column in target["columns"]:
        if column["id"] == product_column_id:
            column["formula"] = f'Lower([{sales["name"]}/Product Line])'
        elif column["id"] == month_column_id:
            column["formula"] = f'[{sales["name"]}/Month]'
    return {"status": "PRODUCT_KEY_FORMULA_PATCH_PENDING_REST", "sourceSha256": model["sourceSha256"],
            "documentId": current["workbookId"], "ifMatchDocumentVersion": current["documentVersion"],
            "beforeContentsHash": digest(current["contents"]), "expectedContentsHash": digest(updated),
            "contents": updated, "rowElementId": row_element_id,
            "keyColumnIds": {"Product Key": product_column_id, "Month Key": month_column_id}}


def confirm_product_key_patch(packet, after):
    """A saved readback, not a submitted PUT body, advances the phase."""
    if packet.get("status") != "PRODUCT_KEY_FORMULA_PATCH_PENDING_REST" or after.get("workbookId") != packet.get("documentId") or after.get("documentVersion") != packet.get("ifMatchDocumentVersion", -1) + 1 or digest(after.get("contents")) != packet.get("expectedContentsHash"):
        _blocked("saved product-key patch/readback differs")
    return {"status": "PRODUCT_KEY_FORMULAS_CONFIRMED", "documentId": after["workbookId"],
            "documentVersion": after["documentVersion"], "contentsHash": digest(after["contents"]),
            "rowElementId": packet["rowElementId"], "sourceSha256": packet["sourceSha256"]}


def prepare_product_rows_scaffold_program(model, current, confirmation, *, row_element_id,
                                          sales_element_id, page_id, grid_row,
                                          sdk_metadata_receipt=None):
    """Project shared rows and add a distinct error ordinal for read-back patching."""
    if model.get("status") != "OFFLINE_GROUPED_MODEL_PENDING_STAGING" or confirmation.get("status") != "PRODUCT_KEY_FORMULAS_CONFIRMED" or confirmation.get("documentId") != current.get("workbookId") or confirmation.get("documentVersion") != current.get("documentVersion") or confirmation.get("contentsHash") != digest(current.get("contents")) or confirmation.get("rowElementId") != row_element_id:
        _blocked("confirmed fresh product-key readback required")
    rows, _ = _observed_rows(current, row_element_id, sales_element_id)
    if not isinstance(grid_row, int) or grid_row < 1 or not any(p.get("id") == page_id for p in current["contents"].get("pages", [])):
        _blocked("observed placement/page required")
    names = {c.get("name"): c for c in rows["columns"] if c.get("name") in ("Product Key", "Month Key", "Revenue Number", "Source Ordinal")}
    if set(names) != {"Product Key", "Month Key", "Revenue Number", "Source Ordinal"} or names["Product Key"].get("formula") != f'Lower([{next(e for e in current["contents"]["elements"] if e.get("id") == sales_element_id)["name"]}/Product Line])' or not names["Month Key"].get("formula", "").endswith('/Month]'):
        _blocked("saved product key/date and source error-order formulas differ")
    expected = _row_sdk_metadata_guard(current, rows, sdk_metadata_receipt)
    lines = [
        "# STAGING ONLY: read back projected columns before patching error ordinal.",
        "from sigma.levelTable import LevelTable",
        "from sigma.data.source import QueryableSource",
        f'p = sigma.workbook.get_page({json.dumps(page_id)})',
        f'rows = p.get_element({json.dumps(row_element_id)})',
        'if not isinstance(rows, LevelTable): raise RuntimeError("actual row table changed")',
        f'if rows.id() != {json.dumps(row_element_id)} or rows.name() != {json.dumps(rows["name"])}: raise RuntimeError("row identity changed")',
        'source = rows.data_source()',
        'if not isinstance(source, QueryableSource): raise RuntimeError("row source changed")',
        f'if source.ref() != sigma.data.source.element({json.dumps(sales_element_id)}).ref(): raise RuntimeError("sales source changed")',
        'actual = []',
        'for c in rows.list_columns():',
        '    actual.append({"id": c.id(), "name": c.name(), "formula": c.formula()})',
        f'if actual != {json.dumps(expected)}: raise RuntimeError("row columns/formulas changed")',
        'product_rows = p.add_table(sigma.data.source.element(rows.id()))',
        'product_rows.set_name("Regional Product Rows")',
        f'product_rows.set_frame(1, {grid_row}, 24, 12)',
        'error_order = product_rows.add_column("Product Error Ordinal", sigma.formula.const_num(0))',
        'print({"productRowsElementId": product_rows.id(), "errorOrdinalColumnId": error_order.id(), "columns": [{"id": c.id(), "name": c.name(), "formula": c.formula()} for c in product_rows.list_columns()]})',
    ]
    program = "\n".join(lines) + "\n"
    validate_native_grid_program(program, current=current, page_id=page_id)
    return {"status": "PRODUCT_ROWS_SCAFFOLD_PENDING_EXECUTION", "sourceSha256": model["sourceSha256"],
            "documentId": current["workbookId"], "documentVersion": current["documentVersion"],
            "contentsHash": digest(current["contents"]), "rowElementId": row_element_id,
            "program": program}


def _projection_ddl_columns(ddl, current, element):
    if not isinstance(ddl, str):
        _blocked("projection DDL text required")
    lines = ddl.strip().splitlines()
    opening = f'CREATE TABLE "workbook"."{element["id"]}" ('
    positions = [i for i, line in enumerate(lines) if line.strip() == opening]
    if len(positions) != 1:
        _blocked("projection DDL workbook/element target differs")
    start = positions[0]
    headers = [line.strip() for line in lines[:start] if line.strip()]
    if (any(not line.startswith("-- ") for line in headers) or
            [line for line in headers if line.startswith("-- Workbook ID:")] !=
            [f'-- Workbook ID: "{current["workbookId"]}"'] or
            [line for line in headers if line.startswith("-- Element ID:")] !=
            [f'-- Element ID: "{element["id"]}"'] or lines[-1].strip() != ");"):
        _blocked("projection DDL workbook/element target differs")
    body = lines[start + 1:-1]
    matches = [re.fullmatch(
        r'\s*"([A-Za-z0-9_-]+)" (text|number|datetime|boolean)(,?) -- "([^"]+)" \| Formula: (.*)',
        line) for line in body]
    columns = element.get("columns", [])
    if (len(matches) != len(columns) or any(match is None for match in matches) or
            len({match[1] for match in matches}) != len(matches)):
        _blocked("complete ordered projection DDL columns required")
    result = []
    for index, (column, match) in enumerate(zip(columns, matches)):
        column_id, kind, comma, name, formula = match.groups()
        if (column.get("id") != column_id or column.get("formula") != formula or
                not name or bool(comma) != (index < len(columns) - 1)):
            _blocked("projection DDL physical ID/order/formula differs")
        result.append({"id": column_id, "name": name, "formula": formula, "type": kind})
    return result


def _unnamed_product_projection(current, rows, product, receipt, *, error_formula="0"):
    """Use full observed native DDL only for omitted inherited REST names."""
    if not isinstance(receipt, dict) or set(receipt) != {
            "documentId", "documentVersion", "contentsHash", "rowElementId",
            "productElementId", "parentDdl", "productDdl",
            "reviewedParentNameDifferences"}:
        _blocked("complete actual inherited-column receipt required")
    if (receipt["documentId"] != current.get("workbookId") or
            type(receipt["documentVersion"]) is not int or
            receipt["documentVersion"] != current.get("documentVersion") or
            receipt["contentsHash"] != digest(current.get("contents")) or
            receipt["rowElementId"] != rows.get("id") or
            receipt["productElementId"] != product.get("id")):
        _blocked("inherited-column receipt source/version/element binding differs")
    parent = _projection_ddl_columns(receipt["parentDdl"], current, rows)
    child = _projection_ddl_columns(receipt["productDdl"], current, product)
    if len(child) != len(parent) + 1 or not any(
            c.get("name") is None for c in product["columns"][:-1]):
        _blocked("receipt is only for omitted inherited REST names")
    differences = []
    for source, observed in zip(rows["columns"], parent):
        if source.get("name") != observed["name"]:
            differences.append({"id": observed["id"], "restName": source.get("name"),
                                "sdkName": observed["name"]})
    if (not isinstance(receipt["reviewedParentNameDifferences"], list) or
            receipt["reviewedParentNameDifferences"] != differences):
        _blocked("parent SDK display differences require exact ordered review")
    if len({c["name"] for c in parent}) != len(parent) or len({c["name"] for c in child}) != len(child):
        _blocked("observed projection DDL names ambiguous")
    for rest, observed, source in zip(product["columns"][:-1], child[:-1], parent):
        if (rest.get("name") not in (None, observed["name"]) or
                observed["name"] != source["name"] or
                observed["type"] != source["type"] or
                observed["formula"] != f'[{rows["name"]}/{source["name"]}]'):
            _blocked("inherited projection DDL/REST source lineage differs")
    last_rest, last_observed = product["columns"][-1], child[-1]
    if (last_rest.get("name") != last_observed["name"] or
            last_observed["name"] != "Product Error Ordinal" or
            last_observed["type"] != "number" or
            last_observed["formula"] != error_formula):
        _blocked("projected error ordinal formula differs")
    return {column["name"]: column for column in child}


def prepare_product_error_patch(model, current, scaffold, *, row_element_id,
                                product_element_id, error_column_id,
                                inherited_column_receipt=None):
    """Patch the observed error placeholder, retaining strict named-REST defaults.

    For omitted inherited REST names, the optional source-bound receipt carries
    complete successful parent/product native DDL and explicitly reviewed
    parent display differences. The caller admits raw describe envelopes;
    this function validates decoded metadata, not live capture provenance.
    """
    if model.get("status") != "OFFLINE_GROUPED_MODEL_PENDING_STAGING" or scaffold.get("status") != "PRODUCT_ROWS_SCAFFOLD_PENDING_EXECUTION" or scaffold.get("sourceSha256") != model["sourceSha256"] or scaffold.get("documentId") != current.get("workbookId") or scaffold.get("rowElementId") != row_element_id:
        _blocked("product-row scaffold provenance differs")
    elements = current.get("contents", {}).get("elements", [])
    products = [e for e in elements if e.get("id") == product_element_id]
    rows = [e for e in elements if e.get("id") == row_element_id]
    if len(products) != 1 or len(rows) != 1 or products[0].get("kind") != "table" or products[0].get("source") != {"kind": "table", "elementId": row_element_id}:
        _blocked("saved product projection/source differs")
    observed_names = (_unnamed_product_projection(current, rows[0], products[0],
                      inherited_column_receipt) if inherited_column_receipt is not None else None)
    names = ("Revenue Error", "Source Ordinal", "Product Key", "Month Key", "Revenue Number")
    for name in names:
        original = [c for c in rows[0]["columns"] if c.get("name") == name]
        inherited = ([observed_names[name]] if observed_names is not None and name in observed_names else
                     [c for c in products[0]["columns"] if c.get("name") == name])
        if len(original) != 1 or len(inherited) != 1 or inherited[0].get("formula") != f'[{rows[0]["name"]}/{name}]':
            _blocked("projected source column lineage differs: " + name)
    matches = [c for c in products[0]["columns"] if c.get("id") == error_column_id]
    if len(matches) != 1 or matches[0].get("name") != "Product Error Ordinal" or matches[0].get("formula") != "0":
        _blocked("assigned product error placeholder differs")
    updated = copy.deepcopy(current["contents"])
    target = next(e for e in updated["elements"] if e.get("id") == product_element_id)
    next(c for c in target["columns"] if c.get("id") == error_column_id)["formula"] = 'If([Revenue Error] != "", [Source Ordinal], Null)'
    return {"status": "PRODUCT_ERROR_FORMULA_PENDING_REST", "sourceSha256": model["sourceSha256"],
            "documentId": current["workbookId"], "ifMatchDocumentVersion": current["documentVersion"],
            "beforeContentsHash": digest(current["contents"]), "expectedContentsHash": digest(updated),
            "contents": updated, "rowElementId": row_element_id, "productElementId": product_element_id,
            "errorColumnId": error_column_id}


def confirm_product_error_patch(packet, after):
    if packet.get("status") != "PRODUCT_ERROR_FORMULA_PENDING_REST" or after.get("workbookId") != packet.get("documentId") or after.get("documentVersion") != packet.get("ifMatchDocumentVersion", -1) + 1 or digest(after.get("contents")) != packet.get("expectedContentsHash"):
        _blocked("saved product error patch/readback differs")
    return {"status": "PRODUCT_ERROR_FORMULA_CONFIRMED", "documentId": after["workbookId"],
            "documentVersion": after["documentVersion"], "contentsHash": digest(after["contents"]),
            "rowElementId": packet["rowElementId"], "productElementId": packet["productElementId"],
            "errorColumnId": packet["errorColumnId"], "sourceSha256": packet["sourceSha256"]}


def prepare_product_grouping_program(model, current, confirmation, *, product_element_id,
                                     page_id, grid_row, inherited_column_receipt=None,
                                     sdk_metadata_receipt=None):
    """Group with exact IDs, requiring DDL plus SDK evidence for omitted names.

    The inherited receipt carries the confirmed error formula. Its full DDL
    name projection is the reference for the complete SDK receipt, so no
    further SDK name differences are permitted in this optional path.
    """
    if model.get("status") != "OFFLINE_GROUPED_MODEL_PENDING_STAGING" or confirmation.get("status") != "PRODUCT_ERROR_FORMULA_CONFIRMED" or confirmation.get("documentId") != current.get("workbookId") or confirmation.get("documentVersion") != current.get("documentVersion") or confirmation.get("contentsHash") != digest(current.get("contents")) or confirmation.get("productElementId") != product_element_id:
        _blocked("confirmed fresh product error readback required")
    elements = current.get("contents", {}).get("elements", [])
    products = [e for e in elements if e.get("id") == product_element_id]
    if len(products) != 1 or products[0].get("kind") != "table" or products[0].get("source") != {"kind": "table", "elementId": confirmation["rowElementId"]}:
        _blocked("saved product projection/source differs")
    if not isinstance(grid_row, int) or grid_row < 1 or not any(p.get("id") == page_id for p in current["contents"].get("pages", [])):
        _blocked("observed placement/page required")
    observed_names = None
    guard_source = products[0]
    if inherited_column_receipt is not None:
        parents = [e for e in elements if e.get("id") == confirmation["rowElementId"]]
        if len(parents) != 1 or sdk_metadata_receipt is None:
            _blocked("complete parent DDL and actual SDK grouping metadata required")
        observed_names = _unnamed_product_projection(current, parents[0], products[0],
            inherited_column_receipt,
            error_formula='If([Revenue Error] != "", [Source Ordinal], Null)')
        if not isinstance(sdk_metadata_receipt, dict) or sdk_metadata_receipt.get("reviewedNameDifferences") != []:
            _blocked("SDK grouping names must exactly match the reviewed complete DDL")
        by_id = {c["id"]: c for c in observed_names.values()}
        guard_source = dict(products[0], columns=[dict(c, name=by_id[c["id"]]["name"])
                                                for c in products[0]["columns"]])
    names = {}
    for name in ("Product Key", "Month Key", "Revenue Number", "Product Error Ordinal"):
        matches = ([observed_names[name]] if observed_names is not None and name in observed_names else
                   [c for c in products[0]["columns"] if c.get("name") == name])
        if len(matches) != 1 or not matches[0].get("id"):
            _blocked("saved product grouping input ambiguous: " + name)
        names[name] = matches[0]
    if names["Product Error Ordinal"].get("id") != confirmation["errorColumnId"] or names["Product Error Ordinal"].get("formula") != 'If([Revenue Error] != "", [Source Ordinal], Null)':
        _blocked("saved product error-order formula differs")
    expected = _row_sdk_metadata_guard(current, guard_source, sdk_metadata_receipt)
    lines = [
        "# STAGING ONLY: read back assigned grouping/flat IDs after this mutation.",
        "from sigma.levelTable import LevelTable",
        f'p = sigma.workbook.get_page({json.dumps(page_id)})',
        f'product_rows = p.get_element({json.dumps(product_element_id)})',
        'if not isinstance(product_rows, LevelTable): raise RuntimeError("actual product projection changed")',
        f'if product_rows.id() != {json.dumps(product_element_id)} or product_rows.name() != {json.dumps(products[0]["name"])}: raise RuntimeError("product identity changed")',
        'actual = []',
        'for c in product_rows.list_columns():',
        '    actual.append({"id": c.id(), "name": c.name(), "formula": c.formula()})',
        f'if actual != {json.dumps(expected)}: raise RuntimeError("product columns/formulas changed")',
        f'product = product_rows.get_column({json.dumps(names["Product Key"]["id"])})',
        f'month = product_rows.get_column({json.dumps(names["Month Key"]["id"])})',
        f'revenue = product_rows.get_column({json.dumps(names["Revenue Number"]["id"])})',
        f'error_order = product_rows.get_column({json.dumps(names["Product Error Ordinal"]["id"])})',
        'grouping = product_rows.set_groupings([[product, month]])[0]',
        'sum_column = grouping.set_calculation("Revenue Sum", sigma.formula.sum(revenue))',
        'min_column = grouping.set_calculation("First Error Ordinal", sigma.formula.min(error_order))',
        'flat = p.add_table(grouping.to_source())',
        'flat.set_name("Regional Sales Product Month")',
        f'flat.set_frame(1, {grid_row}, 24, 12)',
        'print({"productRowsElementId": product_rows.id(), "groupedElementId": flat.id(), "sumColumnId": sum_column.id(), "minColumnId": min_column.id(), "flatColumns": [{"id": c.id(), "name": c.name()} for c in flat.list_columns()]})',
    ]
    program = "\n".join(lines) + "\n"
    validate_native_grid_program(program, current=current, page_id=page_id)
    return {"status": "PRODUCT_MONTH_GROUPING_PENDING_EXECUTION", "sourceSha256": model["sourceSha256"],
            "documentId": current["workbookId"], "documentVersion": current["documentVersion"],
            "contentsHash": digest(current["contents"]), "productElementId": product_element_id,
            "program": program}
