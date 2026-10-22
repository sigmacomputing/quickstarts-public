"""Guarded, resumable structural and formula phases for Regional outputs.

SDK programs only add documented native tables/groupings. REST packets carry
the complete contents plus an If-Match document version; callers must GET and
confirm each phase before continuing. No transport is performed here.
"""
from __future__ import annotations

import copy
import json

from .native_exact_plan import digest
from .native_frames import validate_native_grid_program
from .regional_grouped_canary import bind_assigned_formula, _canonical_not_call_spacing
from .regional_grouped_model import build_grouped_model, _projection_ddl_columns
from .regional_grouped_output import build_full_output_graph, bind_full_output_formulas
from .source_inputs import validate_source_input_plan


def _require(condition, message):
    if not condition:
        raise ValueError("BLOCKED Regional construction: " + message)


def _element(current, element_id):
    _require(isinstance(current.get("documentVersion"), int) and
             isinstance(current.get("contents", {}).get("elements"), list),
             "fresh full-document readback/version required")
    found = [e for e in current["contents"]["elements"] if e.get("id") == element_id]
    _require(len(found) == 1 and isinstance(found[0].get("name"), str),
             "actual element ID absent or ambiguous")
    return found[0]


def _page(current, page_id):
    _require(any(p.get("id") == page_id for p in current["contents"].get("pages", [])),
             "actual page ID absent")


def _fresh_inputs(graph, current, assigned_rows):
    _require(assigned_rows.get("status") == "FULL_ASSIGNED_ROWS_VERIFIED" and
             assigned_rows.get("documentId") == current.get("workbookId") and
             assigned_rows.get("documentVersion") == current.get("documentVersion") and
             assigned_rows.get("contentsHash") == digest(current.get("contents")) and
             assigned_rows.get("sourceSha256") == graph.get("sourceSha256") and
             assigned_rows.get("inputPlanHash") == graph.get("inputPlanHash") and
             len(assigned_rows.get("features", {})) == 5,
             "fresh five-input query/physical-ID reconciliation required")


def prepare_output_scaffold_program(graph, current, assigned_rows, *, output_element, source_element_id,
                                    page_id, grid_row):
    """One output table scaffold using observed source/page IDs."""
    _require(graph.get("status") == "FULL_REGIONAL_FORMULAS_PENDING_ASSIGNED_BINDINGS" and
             output_element in ("region-summary", "product-summary"),
             "output graph/phase changed")
    _fresh_inputs(graph, current, assigned_rows)
    source = _element(current, source_element_id)
    _page(current, page_id)
    feature = {"region-summary": "summary-regions", "product-summary": "summary-months"}[output_element]
    _require(source_element_id == assigned_rows["features"][feature]["elementId"] and
             source.get("name") == assigned_rows["features"][feature]["name"],
             "output source is not exact reconciled editable role: " + feature)
    _require(source.get("kind") == "input-table" and isinstance(grid_row, int) and grid_row >= 1,
             "ordinary source input and placement required")
    _require(not any(e.get("name") == {"region-summary": "Regional Summary",
                                         "product-summary": "Regional Product Months"}[output_element]
                     for e in current["contents"]["elements"]),
             "output scaffold already exists; reconcile prior phase")
    output_name = {"region-summary": "Regional Summary", "product-summary": "Regional Product Months"}[output_element]
    lines = [
        "# STAGING ONLY. Inspect assigned IDs and input rows before formula patch.",
        f'p = sigma.workbook.get_page({json.dumps(page_id)})',
        f't = p.add_table(sigma.data.source.element({json.dumps(source_element_id)}))',
        f't.set_name({json.dumps(output_name)})',
        f't.set_frame(1, {grid_row}, 24, 12)',
        'inherited = t.list_columns()',
        'assigned = []',
    ]
    for name in graph["formulaColumns"][output_element]:
        lines.append(f'c = t.add_column({json.dumps(name)}, sigma.formula.const_num(0))')
        lines.append(f'assigned.append({{"logicalName": {json.dumps(name)}, "actualId": c.id(), "name": c.name()}})')
    lines.extend(['for c in inherited:', '    c.delete()',
                  f'print({{"logicalElement": {json.dumps(output_element)}, "elementId": t.id(), "columns": assigned}})'])
    program = "\n".join(lines) + "\n"
    validate_native_grid_program(program, current=current, page_id=page_id)
    return {"status": "REGIONAL_OUTPUT_SCAFFOLD_PENDING_EXECUTION", "sourceSha256": graph["sourceSha256"],
            "documentId": current["workbookId"], "documentVersion": current["documentVersion"],
            "contentsHash": digest(current["contents"]), "logicalElement": output_element,
            "sourceElementId": source_element_id, "program": program}


def _observed_namespace_columns(current, actual, receipt):
    """Resolve omitted/aliased names only from complete source-bound native DDL.

    Raw successful describe/SDK envelope admission belongs to the caller; this
    typed receipt binds its full decoded metadata to the current saved source.
    """
    _require(isinstance(receipt, dict) and set(receipt) == {
        "documentId", "documentVersion", "contentsHash", "elementId", "ddl",
        "columns", "reviewedNameDifferences"}, "complete native namespace receipt required")
    _require(actual.get("kind") == "table" and
        receipt["documentId"] == current.get("workbookId") and
        type(receipt["documentVersion"]) is int and
        receipt["documentVersion"] == current.get("documentVersion") and
        receipt["contentsHash"] == digest(current.get("contents")) and
        receipt["elementId"] == actual.get("id"), "native namespace source/version/hash differs")
    observed = _projection_ddl_columns(receipt["ddl"], current, actual)
    _require(receipt["columns"] == observed and
             len({c["name"] for c in observed}) == len(observed),
             "complete native namespace IDs/order/types/formulas/names differ")
    differences = [{"id": native["id"], "restName": rest.get("name"),
                    "nativeName": native["name"]}
                   for rest, native in zip(actual["columns"], observed)
                   if rest.get("name") != native["name"]]
    _require(receipt["reviewedNameDifferences"] == differences,
             "native namespace name differences require exact ordered review")
    return {column["id"]: column for column in observed}


def _validate_namespaces(current, namespaces):
    _require(isinstance(namespaces, dict), "assigned namespace receipt required")
    for alias, binding in namespaces.items():
        _require(isinstance(binding, dict) and isinstance(binding.get("elementId"), str) and
                 isinstance(binding.get("name"), str) and isinstance(binding.get("columns"), dict),
                 "assigned namespace incomplete: " + alias)
        actual = _element(current, binding["elementId"])
        _require(actual["name"] == binding["name"], "assigned namespace name changed: " + alias)
        by_id = {c.get("id"): c for c in actual.get("columns", [])}
        observed = (_observed_namespace_columns(current, actual, binding["nativeColumnReceipt"])
                    if binding.get("nativeColumnReceipt") is not None else None)
        legacy_observed = None
        _require(len(by_id) == len(actual.get("columns", [])), "ambiguous namespace column IDs: " + alias)
        for logical, column in binding["columns"].items():
            _require(isinstance(column, dict) and isinstance(column.get("id"), str) and
                     isinstance(column.get("name"), str), "incomplete column binding: " + alias + "/" + logical)
            actual_column = by_id.get(column["id"])
            _require(actual_column is not None, "assigned column absent: " + alias + "/" + logical)
            if observed is not None:
                _require(column["name"] == observed[column["id"]]["name"],
                         "namespace label differs from complete native metadata: " + alias + "/" + logical)
                continue
            if actual_column.get("name") is None:
                if (column["id"] == "ID" and column["name"] == "ID" and
                        actual.get("kind") == "input-table"):
                    continue
                if legacy_observed is None:
                    describe = binding.get("nativeDescribe")
                    _require(isinstance(describe, dict) and
                             isinstance(describe.get("structuredContent"), dict) and
                             actual.get("source", {}).get("kind") == "table" and
                             actual.get("source", {}).get("groupingId"),
                             "unnamed grouped column needs observed native DDL: " + alias + "/" + logical)
                    # Bind every label to its physical ID using complete ordered
                    # DDL matched to this workbook/element and saved formulas.
                    columns = _projection_ddl_columns(describe["structuredContent"].get("ddl"), current, actual)
                    _require(len({c["name"] for c in columns}) == len(columns) and
                             all(rest.get("name") in (None, native["name"])
                                 for rest, native in zip(actual["columns"], columns)),
                             "legacy native namespace labels ambiguous or differ from REST: " + alias)
                    legacy_observed = {c["id"]: c for c in columns}
                _require(column["name"] == legacy_observed[column["id"]]["name"],
                         "namespace label differs from complete native DDL: " + alias + "/" + logical)
            else:
                _require(actual_column["name"] == column["name"],
                         "assigned column name changed: " + alias + "/" + logical)


def _validate_namespace_roles(current, namespaces, assigned_rows):
    input_aliases = {"Sales": "sales-forecast", "Regions": "regions", "Summary Regions": "summary-regions",
                     "Summary Months": "summary-months", "Summary Products": "summary-products"}
    for alias, feature in input_aliases.items():
        if alias in namespaces:
            binding = namespaces[alias]
            receipt = assigned_rows["features"][feature]
            _require(binding["elementId"] == receipt["elementId"] and
                     binding["name"] == receipt["name"],
                     "output namespace is not reconciled editable input: " + alias)
            actual = _element(current, binding["elementId"])
            for logical, column in binding["columns"].items():
                # A valid physical ID/label pair alone does not establish its
                # logical role: e.g. Source Ordinal must never become a target.
                # The SQL result alias does not identify its physical column.
                # Row IDs used by Lookups must keep the exact queried ID/name.
                if logical == "Row ID":
                    matches = [c for c in actual.get("columns", []) if c.get("id") == column["id"]]
                    _require(len(matches) == 1 and
                             receipt.get("rowIdQueryColumnId") == column["id"] and
                             receipt.get("rowIdColumnName") == column["name"] and
                             (matches[0].get("name") == column["name"] == "Row ID" or
                              (column["id"] == column["name"] == "ID" and
                               matches[0].get("name") in (None, "ID"))),
                             "reconciled input column differs: " + alias + "/" + logical)
                    continue
                matches = [c for c in actual.get("columns", []) if c.get("name") == logical]
                _require(len(matches) == 1 and column["id"] == matches[0].get("id") and
                         column["name"] == logical,
                    "reconciled input column differs: " + alias + "/" + logical)
    if "Rows" in namespaces:
        rows = _element(current, namespaces["Rows"]["elementId"])
        _require(rows.get("kind") == "table" and
                 rows.get("source") == {"kind": "table", "elementId": assigned_rows["features"]["sales-forecast"]["elementId"]},
                 "shared Revenue row source lineage changed")
    if "Grouped" in namespaces:
        grouped = _element(current, namespaces["Grouped"]["elementId"])
        _require("Rows" in namespaces and grouped.get("kind") == "table" and
                 grouped.get("source", {}).get("elementId") == namespaces["Rows"]["elementId"] and
                 grouped.get("source", {}).get("groupingId"),
                 "quarter grouped source lineage changed")
    if "Product Grouped" in namespaces:
        product = _element(current, namespaces["Product Grouped"]["elementId"])
        parent = _element(current, product.get("source", {}).get("elementId"))
        _require("Rows" in namespaces and product.get("kind") == parent.get("kind") == "table" and
                 product.get("source", {}).get("groupingId") and
                 parent.get("source", {}).get("elementId") == namespaces["Rows"]["elementId"],
                 "product/month grouped source lineage changed")
    if "Product Rows" in namespaces:
        product_rows = _element(current, namespaces["Product Rows"]["elementId"])
        _require("Rows" in namespaces and product_rows.get("kind") == "table" and
                 product_rows.get("source") == {"kind": "table", "elementId": namespaces["Rows"]["elementId"]},
                 "product rows source lineage changed")
    if "Region Summary" in namespaces:
        region = _element(current, namespaces["Region Summary"]["elementId"])
        _require(region.get("kind") == "table" and
                 region.get("source") == {"kind": "table", "elementId": assigned_rows["features"]["summary-regions"]["elementId"]},
                 "region total source lineage changed")
    if "Product Summary" in namespaces:
        product_summary = _element(current, namespaces["Product Summary"]["elementId"])
        _require(product_summary.get("kind") == "table" and
                 product_summary.get("source") == {"kind": "table", "elementId": assigned_rows["features"]["summary-months"]["elementId"]},
                 "product summary source lineage changed")
    if "Totals" in namespaces:
        totals = _element(current, namespaces["Totals"]["elementId"])
        _require("Region Summary" in namespaces and totals.get("kind") == "table" and
                 totals.get("source", {}).get("elementId") == namespaces["Region Summary"]["elementId"] and
                 totals.get("source", {}).get("groupingId"),
                 "grand totals grouped source lineage changed")


def prepare_output_contents_patch(graph, current, scaffold, assigned_rows, *, output_element,
                                  output_element_id, source_element_id, assigned_columns,
                                  namespaces):
    """Exact full-document formula patch for all columns in one output table."""
    _require(graph.get("status") == "FULL_REGIONAL_FORMULAS_PENDING_ASSIGNED_BINDINGS" and
             output_element in ("region-summary", "product-summary", "totals") and
             scaffold.get("documentId") == current.get("workbookId") and
             scaffold.get("sourceSha256") == graph["sourceSha256"] and
             scaffold.get("logicalElement") == output_element and
             scaffold.get("sourceElementId") == source_element_id,
             "source/scaffold phase identity differs")
    _fresh_inputs(graph, current, assigned_rows)
    output = _element(current, output_element_id)
    source = _element(current, source_element_id)
    if output_element in ("region-summary", "product-summary"):
        feature = {"region-summary": "summary-regions", "product-summary": "summary-months"}[output_element]
        _require(source_element_id == assigned_rows["features"][feature]["elementId"] and
                 source.get("name") == assigned_rows["features"][feature]["name"] and
                 output.get("source") == {"kind": "table", "elementId": source_element_id},
                 "output source is not exact reconciled editable role: " + feature)
    else:
        _require(scaffold.get("status") == "REGIONAL_TOTALS_GROUPING_PENDING_EXECUTION" and
                 namespaces.get("Region Summary", {}).get("elementId") == source_element_id and
                 output.get("source", {}).get("groupingId") and
                 output.get("source", {}).get("elementId") == source_element_id,
                 "totals source is not confirmed region-summary grouping")
    _require(output.get("kind") == "table" and
             output.get("source", {}).get("elementId") == source_element_id and
             source.get("kind") in ("input-table", "table"),
             "output table/source lineage differs")
    names = graph["formulaColumns"][output_element]
    _require(set(assigned_columns) == set(names), "complete assigned output columns required")
    actual_by_id = {c.get("id"): c for c in output.get("columns", [])}
    for name, col_id in assigned_columns.items():
        _require(isinstance(col_id, str) and actual_by_id.get(col_id, {}).get("name") == name and
                 actual_by_id[col_id].get("formula") == "0", "fresh placeholder/column ID differs: " + name)
    _require(len(set(assigned_columns.values())) == len(assigned_columns),
             "assigned output IDs are not unique")
    _validate_namespaces(current, namespaces)
    _validate_namespace_roles(current, namespaces, assigned_rows)
    bound = bind_full_output_formulas(graph, namespaces, element=output_element)
    updated = copy.deepcopy(current["contents"])
    target = next(e for e in updated["elements"] if e.get("id") == output_element_id)
    for column in target["columns"]:
        if column["id"] in assigned_columns.values():
            column["formula"] = bound[column["name"]]
    return {"status": "REGIONAL_OUTPUT_FORMULAS_PENDING_REST", "sourceSha256": graph["sourceSha256"],
            "documentId": current["workbookId"], "ifMatchDocumentVersion": current["documentVersion"],
            "beforeContentsHash": digest(current["contents"]), "expectedContentsHash": digest(updated),
            "logicalElement": output_element, "outputElementId": output_element_id,
            "assignedColumns": assigned_columns, "contents": updated}


def confirm_output_contents_patch(packet, after):
    _require(packet.get("status") == "REGIONAL_OUTPUT_FORMULAS_PENDING_REST" and
             after.get("workbookId") == packet.get("documentId") and
             after.get("documentVersion") == packet.get("ifMatchDocumentVersion", -1) + 1 and
             digest(after.get("contents")) == packet.get("expectedContentsHash"),
             "saved output formula patch/readback differs")
    return {"status": "REGIONAL_OUTPUT_FORMULAS_CONFIRMED",
            "logicalElement": packet["logicalElement"], "outputElementId": packet["outputElementId"],
            "documentId": after["workbookId"], "documentVersion": after["documentVersion"],
            "contentsHash": digest(after["contents"]), "sourceSha256": packet["sourceSha256"]}


def prepare_totals_grouping_program(graph, current, region_confirmation, assigned_rows, *,
                                    region_element_id, page_id, grid_row):
    """Group four live region records into five source totals and a label row."""
    _require(graph.get("status") == "FULL_REGIONAL_FORMULAS_PENDING_ASSIGNED_BINDINGS" and
             region_confirmation.get("status") == "REGIONAL_OUTPUT_FORMULAS_CONFIRMED" and
             region_confirmation.get("logicalElement") == "region-summary" and
             region_confirmation.get("outputElementId") == region_element_id and
             region_confirmation.get("documentId") == current.get("workbookId") and
             region_confirmation.get("documentVersion") == current.get("documentVersion") and
             region_confirmation.get("contentsHash") == digest(current.get("contents")),
             "confirmed region-summary readback required")
    _fresh_inputs(graph, current, assigned_rows)
    region = _element(current, region_element_id)
    _page(current, page_id)
    _require(region.get("kind") == "table" and
             region.get("source") == {"kind": "table", "elementId": assigned_rows["features"]["summary-regions"]["elementId"]} and
             isinstance(grid_row, int) and grid_row >= 1,
             "actual region table/placement required")
    expected_names = set(graph["formulaColumns"]["region-summary"])
    by_name = {c.get("name"): c for c in region.get("columns", [])}
    _require(expected_names <= set(by_name) and
             all(by_name[name].get("formula") not in (None, "0") for name in expected_names),
             "all saved source region formulas required")
    expected = [{"id": c["id"], "name": c.get("name"), "formula": c.get("formula")}
                for c in region["columns"]]
    lines = [
        "# STAGING ONLY. Read back grouping/flat IDs, query five totals, then patch label/error lanes.",
        "from sigma.levelTable import LevelTable",
        f'p = sigma.workbook.get_page({json.dumps(page_id)})',
        f'region = p.get_element({json.dumps(region_element_id)})',
        'if not isinstance(region, LevelTable): raise RuntimeError("actual region table changed")',
        f'if region.id() != {json.dumps(region_element_id)} or region.name() != {json.dumps(region["name"])}: raise RuntimeError("region identity changed")',
        'actual = []',
        'for c in region.list_columns():',
        '    actual.append({"id": c.id(), "name": c.name(), "formula": c.formula()})',
        f'if actual != {json.dumps(expected)}: raise RuntimeError("region source columns/formulas changed")',
        f'key = region.get_column({json.dumps(by_name["Total Key"]["id"])})',
        'grouping = region.set_groupings([[key]])[0]',
        'calcs = []',
    ]
    for spec in graph["totalGrouping"]["calculations"].values():
        lines.append(f'source = region.get_column({json.dumps(by_name[spec["source"]]["id"])})')
        lines.append(f'calc = grouping.set_calculation({json.dumps(spec["sum"])}, sigma.formula.sum(source))')
        lines.append(f'calcs.append({{"name": {json.dumps(spec["sum"])}, "id": calc.id()}})')
        lines.append(f'error_source = region.get_column({json.dumps(by_name[spec["errorSource"]]["id"])})')
        lines.append(f'calc = grouping.set_calculation({json.dumps(spec["errorOrdinal"])}, sigma.formula.min(error_source))')
        lines.append(f'calcs.append({{"name": {json.dumps(spec["errorOrdinal"])}, "id": calc.id()}})')
    lines.extend(['flat = p.add_table(grouping.to_source())',
                  'flat.set_name("Regional Totals")',
                  f'flat.set_frame(1, {grid_row}, 24, 12)',
                  'assigned = []'])
    for name in graph["formulaColumns"]["totals"]:
        lines.append(f'c = flat.add_column({json.dumps(name)}, sigma.formula.const_num(0))')
        lines.append(f'assigned.append({{"logicalName": {json.dumps(name)}, "actualId": c.id(), "name": c.name()}})')
    lines.append('print({"regionElementId": region.id(), "totalsElementId": flat.id(), "calculations": calcs, "outputColumns": assigned})')
    program = "\n".join(lines) + "\n"
    validate_native_grid_program(program, current=current, page_id=page_id)
    return {"status": "REGIONAL_TOTALS_GROUPING_PENDING_EXECUTION", "sourceSha256": graph["sourceSha256"],
            "documentId": current["workbookId"], "documentVersion": current["documentVersion"],
            "contentsHash": digest(current["contents"]), "logicalElement": "totals",
            "sourceElementId": region_element_id, "program": program}


def _installed_column(current, namespaces, alias, logical):
    binding = namespaces.get(alias, {}).get("columns", {}).get(logical)
    _require(isinstance(binding, dict) and binding.get("id"),
             "installed recipe column unassigned: " + alias + "/" + logical)
    element = _element(current, namespaces[alias]["elementId"])
    matches = [c for c in element.get("columns", []) if c.get("id") == binding["id"]]
    _require(len(matches) == 1, "installed recipe column absent: " + alias + "/" + logical)
    return matches[0]


def _require_formula(current, namespaces, alias, logical, expected):
    actual = _installed_column(current, namespaces, alias, logical)
    _require(actual.get("formula") == expected,
             "installed formula differs: " + alias + "/" + logical)


def _require_grouping(current, namespaces, parent_alias, flat_alias, key_names,
                      calculations):
    parent = _element(current, namespaces[parent_alias]["elementId"])
    flat = _element(current, namespaces[flat_alias]["elementId"])
    groupings = parent.get("groupings")
    _require(isinstance(groupings, list) and len(groupings) == 1 and
             flat.get("source", {}).get("groupingId") == groupings[0].get("id"),
             "installed grouping identity differs: " + flat_alias)
    key_ids = [_installed_column(current, namespaces, parent_alias, name)["id"]
               for name in key_names]
    calc_ids = []
    for formula in calculations:
        matches = [c for c in parent["columns"] if c.get("formula") == formula]
        _require(len(matches) == 1, "installed grouping calculation differs: " + formula)
        calc_ids.append(matches[0]["id"])
    _require(groupings[0].get("groupBy") == key_ids and
             groupings[0].get("calculations") == calc_ids,
             "installed grouping keys/calculation IDs differ: " + flat_alias)


def _verify_installed_recipes(graph, current, namespaces):
    """Compare saved source rows, helpers, aggregates and all output recipes."""
    _require({"Sales", "Rows", "Grouped", "Product Rows", "Product Grouped",
              "Region Summary", "Product Summary", "Totals"} <= set(namespaces),
             "full assigned construction namespaces required")
    record = graph["recordFormulaColumns"]
    local = {c["name"]: namespaces["Rows"]["columns"][c["name"]]["name"] for c in record}
    for column in record:
        expected = bind_assigned_formula(column["formula"], namespaces=namespaces,
                                         local_columns=local)
        if column["name"] in ("h0", "h1", "h2"):
            # The reviewed native readback renders these four Not calls with
            # one ASCII space. Demand that exact rendering, not loose formula
            # whitespace equivalence, for each of these three helpers.
            expected, insertions = _canonical_not_call_spacing(expected)
            _require(len(insertions) == 4,
                     "reviewed record Not-call rendering changed: " + column["name"])
        _require_formula(current, namespaces, "Rows", column["name"], expected)
    for logical, formula in (("Product Key", "Lower([Sales/Product Line])"),
                             ("Month Key", "[Sales/Month]")):
        expected = bind_assigned_formula(formula, namespaces=namespaces, local_columns=local)
        _require_formula(current, namespaces, "Rows", logical, expected)
    rows = _element(current, namespaces["Rows"]["elementId"])
    _require(sum(c.get("formula") == "Sum([Revenue Number])" for c in rows["columns"]) == 1 and
             sum(c.get("formula") == "Min([First Error Ordinal (1)])" for c in rows["columns"]) == 1,
             "region-quarter source grouping recipes differ")
    for logical, source in (("Group Key", "Group Key"), ("Revenue Sum", "Revenue Sum"),
                            ("First Error Ordinal", "First Error Ordinal")):
        _require_formula(current, namespaces, "Grouped", logical,
                         f'[{namespaces["Rows"]["name"]}/{source}]')
    _require_grouping(current, namespaces, "Rows", "Grouped", ["Group Key"],
                      ["Sum([Revenue Number])", "Min([First Error Ordinal (1)])"])
    for logical in ("Product Key", "Month Key", "Revenue Number", "Revenue Error", "Source Ordinal"):
        _require_formula(current, namespaces, "Product Rows", logical,
                         f'[{namespaces["Rows"]["name"]}/{namespaces["Rows"]["columns"][logical]["name"]}]')
    _require_formula(current, namespaces, "Product Rows", "Product Error Ordinal",
                     'If([Revenue Error] != "", [Source Ordinal], Null)')
    product_rows = _element(current, namespaces["Product Rows"]["elementId"])
    _require(sum(c.get("formula") == "Sum([Revenue Number])" for c in product_rows["columns"]) == 1 and
             sum(c.get("formula") == "Min([Product Error Ordinal])" for c in product_rows["columns"]) == 1,
             "product-month source grouping recipes differ")
    for logical in ("Product Key", "Month Key", "Revenue Sum", "First Error Ordinal"):
        _require_formula(current, namespaces, "Product Grouped", logical,
                         f'[{namespaces["Product Rows"]["name"]}/{logical}]')
    _require_grouping(current, namespaces, "Product Rows", "Product Grouped",
                      ["Product Key", "Month Key"],
                      ["Sum([Revenue Number])", "Min([Product Error Ordinal])"])
    for role, alias in (("region-summary", "Region Summary"),
                        ("product-summary", "Product Summary"), ("totals", "Totals")):
        bound = bind_full_output_formulas(graph, namespaces, element=role)
        for logical, expected in bound.items():
            _require_formula(current, namespaces, alias, logical, expected)
    total_specs = graph["totalGrouping"]["calculations"].values()
    region = _element(current, namespaces["Region Summary"]["elementId"])
    for spec in total_specs:
        for logical, expected in ((spec["sum"], f'Sum([{spec["source"]}])'),
                                  (spec["errorOrdinal"], f'Min([{spec["errorSource"]}])')):
            _require(sum(c.get("formula") == expected for c in region["columns"]) == 1,
                     "totals source grouping recipe differs: " + logical)
            _require_formula(current, namespaces, "Totals", logical,
                             f'[{namespaces["Region Summary"]["name"]}/{namespaces["Region Summary"]["columns"][logical]["name"]}]')
    total_formulas = []
    for spec in graph["totalGrouping"]["calculations"].values():
        total_formulas.extend((f'Sum([{spec["source"]}])',
                               f'Min([{spec["errorSource"]}])'))
    _require_grouping(current, namespaces, "Region Summary", "Totals", ["Total Key"],
                      total_formulas)


def bind_full_214_source_manifest(graph, current, assigned_rows, namespaces, *,
                                  source_input_plan, source_native_plan, reviewed_canary,
                                  phase_confirmations):
    """Freeze every source formula against read-back target element/column IDs.

    This is a construction receipt, not formula or runtime qualification. The
    grouped totals row has no source input physical row and is tied to its
    source DAG and the assigned grouped element instead.
    """
    _require(graph.get("status") == "FULL_REGIONAL_FORMULAS_PENDING_ASSIGNED_BINDINGS" and
             graph.get("sourceFormulaCount") == 214, "full source formula graph required")
    validate_source_input_plan(source_input_plan)
    expected = build_full_output_graph(build_grouped_model(source_input_plan, source_native_plan),
                                       reviewed_canary, assigned_rows)
    _require(digest(graph) == digest(expected), "source-bound full graph differs")
    _fresh_inputs(graph, current, assigned_rows)
    _validate_namespaces(current, namespaces)
    _validate_namespace_roles(current, namespaces, assigned_rows)
    required_phases = {"product-key": "PRODUCT_KEY_FORMULAS_CONFIRMED",
                       "product-error": "PRODUCT_ERROR_FORMULA_CONFIRMED",
                       "region-summary": "REGIONAL_OUTPUT_FORMULAS_CONFIRMED",
                       "product-summary": "REGIONAL_OUTPUT_FORMULAS_CONFIRMED",
                       "totals": "REGIONAL_OUTPUT_FORMULAS_CONFIRMED"}
    _require(isinstance(phase_confirmations, dict) and set(phase_confirmations) == set(required_phases),
             "all completed construction phase confirmations required")
    for phase, status in required_phases.items():
        receipt = phase_confirmations[phase]
        _require(receipt.get("status") == status and
                 receipt.get("documentId") == current.get("workbookId") and
                 receipt.get("sourceSha256") == graph["sourceSha256"] and
                 isinstance(receipt.get("documentVersion"), int) and
                 receipt["documentVersion"] <= current["documentVersion"] and
                 isinstance(receipt.get("contentsHash"), str) and len(receipt["contentsHash"]) == 64,
                 "completed phase confirmation differs: " + phase)
    for phase, alias in (("region-summary", "Region Summary"),
                         ("product-summary", "Product Summary"), ("totals", "Totals")):
        _require(phase_confirmations[phase].get("logicalElement") == phase and
                 phase_confirmations[phase].get("outputElementId") == namespaces[alias]["elementId"],
                 "output phase assigned element differs: " + phase)
    _require(phase_confirmations["product-key"].get("rowElementId") == namespaces["Rows"]["elementId"] and
             phase_confirmations["product-error"].get("rowElementId") == namespaces["Rows"]["elementId"] and
             phase_confirmations["product-error"].get("productElementId") == namespaces["Product Rows"]["elementId"] and
             phase_confirmations["product-error"].get("errorColumnId") == namespaces["Product Rows"]["columns"]["Product Error Ordinal"]["id"],
             "product phase assigned IDs differ")
    _verify_installed_recipes(graph, current, namespaces)
    roles = {"sales-rows": "Rows", "region-summary": "Region Summary",
             "product-summary": "Product Summary", "totals": "Totals"}
    for alias in roles.values():
        _require(alias in namespaces, "actual assigned output namespace missing: " + alias)
    expected_counts = {"sales-rows": 144, "region-summary": 28,
                       "product-summary": 36, "totals": 6}
    manifest = {}
    for cell, mapping in graph["sourceMappings"].items():
        role = mapping["targetElement"]
        _require(role in roles, "source target role unknown: " + cell)
        namespace = namespaces[roles[role]]
        lanes = {}
        for lane, column_name in mapping["laneColumnNames"].items():
            column = namespace["columns"].get(column_name)
            _require(isinstance(column, dict) and column.get("id"),
                     "assigned lane column missing: " + cell + "/" + lane)
            lanes[lane] = column["id"]
        _require(set(lanes) == {"number", "text", "logical", "kind", "error"},
                 "five source lanes incomplete: " + cell)
        source_feature = {"sales-rows": "sales-forecast",
                          "region-summary": "summary-regions",
                          "product-summary": "summary-months"}.get(role)
        source_row_id = None
        if source_feature:
            row_index = (mapping["sourceOrdinal"] - 1 if role == "sales-rows"
                         else mapping["targetRowIndex"])
            source_row_id = assigned_rows["features"][source_feature]["rows"].get(str(row_index))
            _require(isinstance(source_row_id, str) and source_row_id,
                     "actual source row ID missing: " + cell)
        manifest[cell] = {"sourceFormulaSha256": mapping["sourceFormulaSha256"],
                          "sourceAstHash": mapping["sourceAstHash"],
                          "targetElementId": namespace["elementId"],
                          "targetElementName": namespace["name"],
                          "targetField": mapping["targetField"],
                          "targetRowIndex": mapping.get("targetRowIndex"),
                          "sourceInputFeature": source_feature,
                          "sourceInputPhysicalRowId": source_row_id,
                          "sourceDependencies": mapping["sourceDependencies"],
                          "laneColumnIds": lanes,
                          "runtimeStatus": "PENDING_QUALIFICATION"}
    counts = {role: sum(m["targetElement"] == role for m in graph["sourceMappings"].values())
              for role in roles}
    _require(counts == expected_counts and len(manifest) == 214,
             "assigned source formula coverage differs")
    return {"status": "FULL_REGIONAL_214_ASSIGNED_PENDING_RUNTIME",
            "documentId": current["workbookId"],
            "documentVersion": current["documentVersion"],
            "contentsHash": digest(current["contents"]),
            "sourceSha256": graph["sourceSha256"],
            "inputPlanHash": graph["inputPlanHash"],
            "nativePlanHash": graph["nativePlanHash"],
            "sourceFormulaCount": 214,
            "roleCounts": counts,
            "sourceMappings": manifest,
            "requiredRuntimeChecks": ["all 214 source values and five lanes",
                "source Excel VLOOKUP capture reconciliation",
                "five editable input change propagation and restoration",
                "appended record and source ordinal behavior",
                "two chart bindings and saved/reopened roles"]}
