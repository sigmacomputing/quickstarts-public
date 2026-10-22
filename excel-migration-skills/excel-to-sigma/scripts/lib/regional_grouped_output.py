"""Native formula recipes for every Regional source result.

The row Revenue expression is supplied by the independently reviewed B4
canary. This module emits the 70 remaining source results as shared fields
over 4 region rows, 12 month rows, and one grouped totals row. Actual input
row IDs are mandatory for the three product selectors and ordered targets.
"""
from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal
import json
import re

from .native_exact_plan import digest

from .regional_grouped_canary import validate_reviewed_candidate, bind_assigned_formula


LANES = ("Number", "Text", "Logical", "Kind", "Error")


def _require(condition, message):
    if not condition:
        raise ValueError("BLOCKED Regional output emitter: " + message)


def _add(columns, name, formula):
    _require(name not in columns, "duplicate output column " + name)
    columns[name] = formula


def _sum_lanes(columns, field, matched_number, matched_error_ordinal):
    _add(columns, field + " Matched Revenue", matched_number)
    _add(columns, field + " Matched Error Ordinal", matched_error_ordinal)
    _add(columns, field + " Number", f"Coalesce([{field} Matched Revenue], 0)")
    _add(columns, field + " Text", '""')
    _add(columns, field + " Logical", "False")
    _add(columns, field + " Kind", '"n"')
    _add(columns, field + " Error", f'If(IsNull([{field} Matched Error Ordinal]), "", Lookup([Rows/Revenue Error], [{field} Matched Error Ordinal], [Rows/Source Ordinal]))')


def _numeric_lanes(columns, field, number, error='""'):
    _add(columns, field + " Number", number)
    _add(columns, field + " Text", '""')
    _add(columns, field + " Logical", "False")
    _add(columns, field + " Kind", '"n"')
    _add(columns, field + " Error", error)


def _ids(assigned_rows, feature, expected):
    binding = assigned_rows.get(feature)
    _require(isinstance(binding, dict) and isinstance(binding.get("rows"), dict) and
             isinstance(binding.get("rowIdColumn"), str) and binding["rowIdColumn"],
             "observed physical row-ID binding missing for " + feature)
    result = []
    for index in range(expected):
        row_id = binding["rows"].get(str(index))
        _require(isinstance(row_id, str) and row_id, f"physical row ID missing: {feature}/{index}")
        result.append(row_id)
    _require(len(set(result)) == len(result), "duplicate physical row IDs for " + feature)
    return result


def _source_key(spec, index, feature):
    cells = list(spec["sourceCells"][str(index)].values())
    _require(cells and len({c.rsplit("!", 1)[0] for c in cells}) == 1,
             "source row cell lineage ambiguous")
    # The qualified B4 staging inputs use stable physical source-row keys for
    # both reused tables, including the one-column Summary Region labels.
    if feature in ("sales-forecast", "summary-regions") or len(cells) != 1:
        return cells[0].rsplit("!", 1)[0] + "!row:" + str(spec["sourceRowNumbers"][index])
    return cells[0]


def _same_input(actual, expected, source_type):
    if expected is None:
        return actual is None
    if isinstance(expected, (int, float)) and type(expected) is not bool:
        try:
            return Decimal(str(actual)) == Decimal(str(expected))
        except (ValueError, TypeError):
            return False
    if source_type == "datetime":
        try:
            source_day = date.fromisoformat(expected)
        except (TypeError, ValueError):
            return False
        # The observed Sigma datetime wire format for these source date-only
        # cells is civil noon UTC. Accept only that exact serialization (or
        # the source's canonical date form), never a changed time or offset.
        canonical = source_day.isoformat()
        return actual in (canonical, canonical + "T12:00:00.000Z")
    return type(actual) is type(expected) and actual == expected


def validate_full_assigned_rows(input_plan, current, observed):
    """Reconcile all five editable rowsets, source keys, and physical IDs."""
    inputs = input_plan["sharedInputArchitecture"]["inputs"]
    _require(isinstance(current.get("workbookId"), str) and current["workbookId"] and
             type(current.get("documentVersion")) is int and
             isinstance(current.get("contents", {}).get("elements"), list) and
             set(observed) == set(inputs), "fresh full document and five query snapshots required")
    result = {"status": "FULL_ASSIGNED_ROWS_VERIFIED", "documentId": current["workbookId"],
              "documentVersion": current["documentVersion"],
              "contentsHash": digest(current["contents"]),
              "sourceSha256": input_plan["sourceSha256"],
              "inputPlanHash": input_plan["inputPlanHash"], "features": {}}
    for feature, spec in inputs.items():
        source_types = {column["name"]: column["type"] for column in spec["columns"]}
        receipt = observed[feature]
        _require(isinstance(receipt, dict) and
                 receipt.get("documentId") == current["workbookId"] and
                 type(receipt.get("documentVersion")) is int and
                 receipt["documentVersion"] == current["documentVersion"] and
                 isinstance(receipt.get("snapshotId"), str) and receipt["snapshotId"].strip(),
                 "fresh full input query required (documentId, documentVersion, snapshotId): " + feature)
        matches = [e for e in current["contents"]["elements"] if e.get("id") == receipt.get("elementId")]
        _require(len(matches) == 1 and matches[0].get("kind") == "input-table" and
                 matches[0].get("name") == receipt.get("name"),
                 "actual editable input identity differs: " + feature)
        actual_columns = matches[0].get("columns", [])
        columns = {c.get("name"): c.get("id") for c in actual_columns}
        required_columns = set(spec["rows"][0]) | {"Source Key", "Source Ordinal"}
        _require(len(columns) == len(actual_columns) and
                 len({c.get("id") for c in actual_columns}) == len(actual_columns) and
                 required_columns <= set(columns) and
                 receipt.get("rowIdColumn") in ("ID", columns.get("Row ID")) and
                 any(c.get("id") == "ID" for c in matches[0].get("columns", [])),
                 "editable source/metadata/system-ID columns missing: " + feature)
        _require(receipt.get("columnIds") == {name: columns[name] for name in required_columns} and
                 receipt.get("rowIdQueryColumnId") in ("ID", columns.get("Row ID")) and
                 isinstance(receipt.get("rowIdQueryColumnId"), str) and
                 receipt["rowIdQueryColumnId"] and
                 receipt["rowIdQueryColumnId"] not in {columns[name] for name in required_columns},
                 "bound input query columnIds/rowIdQueryColumnId required: " + feature)
        row_id_column = next(c for c in actual_columns if c.get("id") == receipt["rowIdQueryColumnId"])
        row_id_name = row_id_column.get("name")
        if row_id_column["id"] == "ID" and row_id_name is None:
            row_id_name = "ID"
        _require(row_id_name == "Row ID" or
                 (row_id_column["id"] == "ID" and row_id_name == "ID"),
                 "selected physical row-ID column identity is ambiguous: " + feature)
        projection = [(column["name"], columns[column["name"]]) for column in spec["columns"]]
        projection += [(name, columns[name]) for name in ("Source Key", "Source Ordinal")]
        projection.append((receipt["rowIdColumn"], receipt["rowIdQueryColumnId"]))
        select = ", ".join(f'"{column_id}" AS "{name}"' for name, column_id in projection)
        expected_request = {"query": {"type": "workbook", "workbookId": current["workbookId"],
            "sql": f'SELECT {select} FROM "workbook"."{receipt["elementId"]}"'}}
        _require(receipt.get("queryRequest") == expected_request,
                 "fresh input queryRequest does not match current workbook/element/column projection: " + feature)
        rows = receipt.get("queryRows")
        _require(isinstance(rows, list) and len(rows) == len(spec["rows"]),
                 "full queried source rowset missing: " + feature)
        by_key = {}
        for row in rows:
            key = row.get("Source Key")
            _require(isinstance(key, str) and key not in by_key,
                     "duplicate or missing queried Source Key: " + feature)
            by_key[key] = row
        ids = {}
        for index, expected in enumerate(spec["rows"]):
            key = _source_key(spec, index, feature)
            row = by_key.get(key)
            _require(row is not None and row.get("Source Ordinal") == index + 1,
                     "source key/ordinal lineage differs: " + feature + "/" + str(index))
            for column, value in expected.items():
                _require(_same_input(row.get(column), value, source_types.get(column)),
                         "queried business input differs: " + feature + "/" + str(index) + "/" + column)
            row_id = row.get(receipt["rowIdColumn"])
            _require(isinstance(row_id, str) and row_id,
                     "actual physical row ID missing: " + feature + "/" + str(index))
            ids[str(index)] = row_id
        _require(len(set(ids.values())) == len(ids), "duplicate physical row ID: " + feature)
        labels = [name for name, _ in projection]
        _require(all(isinstance(row, dict) and set(row) == set(labels) for row in rows) and
                 receipt.get("resultHash") == digest({"columns": labels,
                    "rows": [[row[name] for name in labels] for row in rows]}),
                 "input query resultHash/row projection differs from captured result: " + feature)
        result["features"][feature] = {"elementId": receipt["elementId"],
                                       "name": receipt["name"], "rowIdColumn": receipt["rowIdColumn"],
                                       "rowIdQueryColumnId": row_id_column["id"],
                                       "rowIdColumnName": row_id_name,
                                       "rows": ids}
    return result


def _source_fields(model, kind):
    return [(cell, mapping) for cell, mapping in model["sourceMappings"].items()
            if mapping["kind"] == kind]


def build_full_output_graph(model, canary, assigned_rows):
    """Return formula columns and a complete source-cell/row/lane manifest."""
    validate_reviewed_candidate(canary)
    _require(model.get("status") == "OFFLINE_GROUPED_MODEL_PENDING_STAGING" and
             canary["sourceSha256"] == model["sourceSha256"] and
             canary["inputPlanHash"] == model["inputPlanHash"] and
             canary["nativePlanHash"] == model["nativePlanHash"],
             "source-bound canary/full plan identity differs")
    _require(assigned_rows.get("status") == "FULL_ASSIGNED_ROWS_VERIFIED" and
             assigned_rows.get("documentId") and isinstance(assigned_rows.get("documentVersion"), int) and
             assigned_rows.get("sourceSha256") == model["sourceSha256"] and
             assigned_rows.get("inputPlanHash") == model["inputPlanHash"],
             "reconciled five-input/physical-ID receipt required")
    features = assigned_rows["features"]
    product_ids = _ids(features, "summary-products", 3)
    target_ids = _ids(features, "regions", 4)
    _ids(features, "summary-regions", 4)
    _ids(features, "summary-months", 12)
    _ids(features, "sales-forecast", 144)
    region = {}
    product = {}
    totals = {}
    mappings = copy.deepcopy(model["sourceMappings"])
    row_lanes = {lane.lower(): "Revenue " + lane for lane in LANES}
    for cell, mapping in _source_fields(model, "record-revenue"):
        _require(cell in canary["sourceMappings"] and
                 canary["sourceMappings"][cell]["sourceOrdinal"] == mapping["sourceOrdinal"],
                 "Revenue physical row/source mapping differs")
        mappings[cell]["laneColumnNames"] = row_lanes
    region_periods = {}
    for cell, mapping in _source_fields(model, "region-quarter"):
        region_periods.setdefault(mapping["targetField"], []).append(mapping)
        mappings[cell]["laneColumnNames"] = {lane.lower(): mapping["targetField"] + " " + lane for lane in LANES}
    _require(set(region_periods) == {f"Quarter {q}" for q in range(1, 5)}, "quarter field set changed")
    for quarter in range(1, 5):
        field = f"Quarter {quarter}"
        batch = region_periods[field]
        _require(len(batch) == 4 and {m["targetRowIndex"] for m in batch} == set(range(4)) and
                 len({json.dumps(m["period"], sort_keys=True) for m in batch}) == 1,
                 "quarter source selectors/periods diverge")
        start = batch[0]["period"]["start"]
        year = int(start[:4])
        _require((int(start[5:7]) - 1) // 3 + 1 == quarter,
                 "quarter bound is not aligned with grouped key")
        _add(region, field + " Group Key", f'Concat(Lower([Summary Regions/Region]), "|{year}|{quarter}")')
        _sum_lanes(region, field,
                   f'Lookup([Grouped/Revenue Sum], [{field} Group Key], [Grouped/Group Key])',
                   f'Lookup([Grouped/First Error Ordinal], [{field} Group Key], [Grouped/Group Key])')
    _add(region, "Source Ordinal", "[Summary Regions/Source Ordinal]")
    _add(region, "Source Key", "[Summary Regions/Source Key]")
    _add(region, "Total Key", '"all"')
    for quarter in range(1, 5):
        field = f"Quarter {quarter}"
        _add(region, field + " Error Ordinal", f'If([{field} Error] != "", [Source Ordinal], Null)')
    for cell, mapping in _source_fields(model, "total"):
        edges = mapping["summedSourceCells"]
        rows = {mappings[x]["targetRowIndex"] for x in edges}
        if all(mappings[x]["kind"] == "region-quarter" for x in edges) and len(rows) == 1:
            fields = {mappings[x]["targetField"] for x in edges}
            _require(len(rows) == 1 and fields == set(region_periods), "annual total DAG changed")
            mappings[cell]["targetElement"] = "region-summary"
            mappings[cell]["targetRowIndex"] = next(iter(rows))
            mappings[cell]["targetField"] = "Annual"
            mappings[cell]["laneColumnNames"] = {lane.lower(): "Annual " + lane for lane in LANES}
    _require(sum(m["kind"] == "total" and m["targetElement"] == "region-summary" for m in mappings.values()) == 4,
             "four source annual totals missing")
    _numeric_lanes(region, "Annual", " + ".join(f"[Quarter {q} Number]" for q in range(1, 5)),
                   _first_error([f"Quarter {q} Error" for q in range(1, 5)]))
    _add(region, "Annual Error Ordinal", 'If([Annual Error] != "", [Source Ordinal], Null)')
    # Every exact VLOOKUP reads the four reviewed Regions rows in physical
    # source order. Later edits may duplicate keys; the first row wins.
    target_selector = "[Summary Regions/Region]"
    first_row = "Null"
    for row_id in reversed(target_ids):
        value = json.dumps(row_id)
        first_row = (f'If(Lower({target_selector}) = '
                     f'Lower(Lookup([Regions/Region], {value}, [Regions/Row ID])), '
                     f'{value}, {first_row})')
    _add(region, "Target Matched Row ID", first_row)
    _numeric_lanes(region, "Target",
                   'If(IsNull([Target Matched Row ID]), 0, Coalesce(Lookup([Regions/FY26 Target], [Target Matched Row ID], [Regions/Row ID]), 0))',
                   'If(IsNull([Target Matched Row ID]), "#N/A", "")')
    for cell, mapping in _source_fields(model, "lookup"):
        mappings[cell]["laneColumnNames"] = {lane.lower(): "Target " + lane for lane in LANES}
    _numeric_lanes(region, "Ratio",
        'If(([Annual Error] != "") or ([Target Error] != "") or ([Target Number] = 0), 0, [Annual Number] / [Target Number])')
    for cell, mapping in _source_fields(model, "ratio"):
        numerator = mappings.get(mapping["numeratorSourceCell"])
        denominator = mappings.get(mapping["denominatorSourceCell"])
        _require(numerator and denominator and numerator.get("targetField") == "Annual" and
                 denominator.get("targetField") == "Target" and
                 numerator.get("targetRowIndex") == denominator.get("targetRowIndex"),
                 "ratio source DAG no longer shares region row")
        mappings[cell]["targetRowIndex"] = numerator["targetRowIndex"]
        mappings[cell]["laneColumnNames"] = {lane.lower(): "Ratio " + lane for lane in LANES}
    for product_index, product_id in enumerate(product_ids, 1):
        field = f"Product {product_index}"
        batch = [m for _, m in _source_fields(model, "product-month") if m["targetField"] == field]
        _require(len(batch) == 12 and {m["targetRowIndex"] for m in batch} == set(range(12)),
                 "product/month selector matrix changed")
        _add(product, field + " Key", f'Lower(Lookup([Summary Products/Product Line], {json.dumps(product_id)}, [Summary Products/Row ID]))')
        _sum_lanes(product, field,
            f'Lookup([Product Grouped/Revenue Sum], [{field} Key], [Product Grouped/Product Key], [Summary Months/Month], [Product Grouped/Month Key])',
            f'Lookup([Product Grouped/First Error Ordinal], [{field} Key], [Product Grouped/Product Key], [Summary Months/Month], [Product Grouped/Month Key])')
    _add(product, "Source Key", "[Summary Months/Source Key]")
    for cell, mapping in _source_fields(model, "product-month"):
        mappings[cell]["laneColumnNames"] = {lane.lower(): mapping["targetField"] + " " + lane for lane in LANES}
    for quarter in range(1, 5):
        field = f"Quarter Total {quarter}"
        totals[field] = {"source": f"Quarter {quarter} Number", "errorSource": f"Quarter {quarter} Error Ordinal",
                         "sum": field + " Sum", "errorOrdinal": field + " First Error Ordinal"}
    totals["Grand Total"] = {"source": "Annual Number", "errorSource": "Annual Error Ordinal", "sum": "Grand Total Sum",
                             "errorOrdinal": "Grand Total First Error Ordinal"}
    for cell, mapping in _source_fields(model, "total"):
        if mappings[cell]["targetElement"] == "region-summary":
            continue
        edges = mapping["summedSourceCells"]
        edge_kinds = {mappings[x]["kind"] for x in edges}
        if edge_kinds == {"region-quarter"}:
            fields = {mappings[x]["targetField"] for x in edges}
            rows = {mappings[x]["targetRowIndex"] for x in edges}
            _require(len(fields) == 1 and rows == set(range(4)), "quarter total DAG changed")
            q = int(next(iter(fields)).split()[-1])
            field = f"Quarter Total {q}"
        else:
            _require(edge_kinds == {"total"} and {mappings[x].get("targetField") for x in edges} == {"Annual"} and
                     {mappings[x].get("targetRowIndex") for x in edges} == set(range(4)),
                     "grand total DAG changed")
            field = "Grand Total"
        mappings[cell]["targetField"] = field
        mappings[cell]["targetRowIndex"] = 0
        mappings[cell]["laneColumnNames"] = {lane.lower(): field + " " + lane for lane in LANES}
    _require(sum(m["kind"] == "total" and m["targetElement"] == "totals" for m in mappings.values()) == 5,
             "five grouped total source cells missing")
    for cell, mapping in _source_fields(model, "text"):
        mappings[cell]["targetField"] = "Total Label"
        mappings[cell]["targetRowIndex"] = 0
        mappings[cell]["laneColumnNames"] = {lane.lower(): "Total Label " + lane for lane in LANES}
    _require(len(_source_fields(model, "text")) == 1, "source label vertex missing")
    record_columns = next(e["columns"] for e in canary["elements"] if e["id"] == "regional_sales_rows")
    row_formulas = {c["name"]: c["formula"] for c in record_columns}
    row_error_tokens = set(re.findall(r"#[A-Z0-9/!?]+", " ".join(
        row_formulas.get(name, "") for name in ("h0", "h1", "h2"))))
    _require(row_formulas.get("Revenue Error") == "[h4]" and
             row_formulas.get("h4") == "[h2]" and row_error_tokens == {"#VALUE!"},
             "grouped Totals error domain is not limited to #VALUE!")
    totals_columns = {}
    for field, spec in totals.items():
        # Grouping collapses Region Summary row columns. The grouped minimum
        # ordinal still says whether an included source Revenue error exists;
        # this pinned Units×Avg Price source emits only #VALUE! in that lane.
        _numeric_lanes(totals_columns, field, f'[{spec["sum"]}]',
                       f'If(IsNull([{field} First Error Ordinal]), "", "#VALUE!")')
    _add(totals_columns, "Total Label Number", "0")
    _add(totals_columns, "Total Label Text", '"Total"')
    _add(totals_columns, "Total Label Logical", "False")
    _add(totals_columns, "Total Label Kind", '"t"')
    _add(totals_columns, "Total Label Error", '""')
    _require(set(mappings) == set(model["sourceMappings"]) and
             all(set(m.get("laneColumnNames", {})) == {x.lower() for x in LANES} for m in mappings.values()),
             "one or more source outputs lack five lane bindings")
    formula_count = (len(record_columns) + 2 + 2 + 2 + len(region) + len(product) +
                     2 * len(totals) + len(totals_columns))
    return {"status": "FULL_REGIONAL_FORMULAS_PENDING_ASSIGNED_BINDINGS",
            "sourceSha256": model["sourceSha256"], "inputPlanHash": model["inputPlanHash"],
            "nativePlanHash": model["nativePlanHash"],
            "sourceMappings": mappings,
            "formulaColumns": {"region-summary": region, "product-summary": product, "totals": totals_columns},
            "totalGrouping": {"sourceElement": "region-summary", "groupBy": ["Total Key"],
                "calculations": totals},
            "recordFormulaColumns": record_columns,
            "constructionBudget": {"tables": 7, "formulaAndAggregateColumns": formula_count},
            "sourceFormulaCount": len(mappings)}


def _first_error(names):
    formula = '""'
    for name in reversed(names):
        formula = f'If([{name}] != "", [{name}], {formula})'
    return formula


def bind_full_output_formulas(graph, namespaces, *, element):
    """Bind bracket names from actual element/column readbacks after scaffold."""
    _require(graph.get("status") == "FULL_REGIONAL_FORMULAS_PENDING_ASSIGNED_BINDINGS" and
             element in graph["formulaColumns"], "full formula graph/element required")
    columns = graph["formulaColumns"][element]
    local = {name: name for name in columns}
    if element == "totals":
        for spec in graph["totalGrouping"]["calculations"].values():
            for aggregate in (spec["sum"], spec["errorOrdinal"]):
                binding = namespaces.get("Totals", {}).get("columns", {}).get(aggregate)
                _require(isinstance(binding, dict) and isinstance(binding.get("name"), str),
                         "observed totals aggregate binding missing: " + aggregate)
                local[aggregate] = binding["name"]
    return {name: bind_assigned_formula(formula, namespaces=namespaces, local_columns=local)
            for name, formula in columns.items()}
