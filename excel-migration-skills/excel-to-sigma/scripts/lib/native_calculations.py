"""Source-cell bindings and conservative native formula construction.

Planning is read-only.  A formula remains an obligation whenever a source
reference or Excel operation lacks an exact reviewed live binding.  Lowered
expressions are candidate code-representation material, never runtime proof.
"""
from __future__ import annotations

import hashlib
import json
import re
import copy
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from .excel_expression import (Binary, Boolean, BoundIndirect, BoundRange, ExcelCalcError, Function,
        Group, Number, Percent, Reference, Text, Unary, UnsupportedExpression,
        expand_range, parse_expression)
    from .source_inputs import validate_source_input_plan
    from .workbook_expression import WorkbookContext, _cell_id
    from .input_sync import _approved_feature
    from .input_display import _system_column_contract
    from .migration_manifest import validate_manifest
except ImportError:
    from excel_expression import (Binary, Boolean, BoundIndirect, BoundRange, ExcelCalcError, Function,
        Group, Number, Percent, Reference, Text, Unary, UnsupportedExpression,
        expand_range, parse_expression)
    from source_inputs import validate_source_input_plan
    from workbook_expression import WorkbookContext, _cell_id
    from input_sync import _approved_feature
    from input_display import _system_column_contract
    from migration_manifest import validate_manifest


PLAN_VERSION = 1
_NAME = re.compile(r"[^a-z0-9]+")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def _symbol(source_cell):
    basic = _NAME.sub("_", source_cell.lower()).strip("_")
    return "f_" + basic if len(basic) <= 55 else "f_" + basic[:45] + "_" + _digest(source_cell)[:8]


def _ast(node):
    if isinstance(node, Number): return {"kind": "number", "source": node.source}
    if isinstance(node, Text): return {"kind": "text", "value": node.value}
    if isinstance(node, Boolean): return {"kind": "boolean", "value": node.value}
    if isinstance(node, Reference): return {"kind": "reference", "cell": _cell_id(node.value)}
    if isinstance(node, BoundRange):
        return {"kind": "range", "cells": [_cell_id(ref) for ref in expand_range(node)],
                "sourceKind": node.source_kind, "declaredDomain": node.declared_domain,
                "activeDomain": node.active_domain, "empty": node.empty}
    if isinstance(node, BoundIndirect):
        return {"kind": "indirect", "selector": _ast(node.selector),
                "alternatives": [[name, _ast(target)] for name, target in node.alternatives]}
    if isinstance(node, Group): return {"kind": "group", "expression": _ast(node.expression)}
    if isinstance(node, Unary): return {"kind": "unary", "operator": node.operator, "operand": _ast(node.operand)}
    if isinstance(node, Percent): return {"kind": "percent", "operand": _ast(node.operand)}
    if isinstance(node, Binary):
        return {"kind": "binary", "operator": node.operator, "left": _ast(node.left),
                "right": _ast(node.right)}
    if isinstance(node, Function):
        return {"kind": "function", "name": node.name,
                "arguments": [_ast(argument) for argument in node.arguments]}
    raise UnsupportedExpression(f"unhandled bound AST node {type(node).__name__}")


def _input_bindings(source_plan):
    bindings = {}
    inputs = source_plan["sharedInputArchitecture"]["inputs"]
    for feature, spec in sorted(inputs.items()):
        types = {column["name"]: column["type"] for column in spec["columns"]}
        for index, fields in (spec.get("sourceCells") or {}).items():
            if int(index) >= len(spec["rows"]):
                raise ValueError("source input provenance row is out of bounds")
            for column, cell in fields.items():
                if column not in types:
                    raise ValueError("source input provenance names a foreign column")
                binding = {"kind": "input", "featureId": feature, "rowIndex": int(index),
                           "column": column, "valueType": types[column]}
                if cell in bindings and bindings[cell] != binding:
                    # Reshaped keys/axis headers can occur in many physical rows.
                    # A scalar source cell must never be assigned one arbitrarily.
                    bindings[cell] = {"kind": "ambiguous-input"}
                else:
                    bindings[cell] = binding
    return bindings


def _replacement_external_inputs(source_plan):
    values, provenance = {}, {}
    if source_plan is None:
        return values, provenance
    for feature, spec in source_plan["sharedInputArchitecture"]["inputs"].items():
        entries = spec.get("replacementBindings") or []
        if not entries: continue
        value_column = next(name for name in spec["columns"]
                            if name["name"] not in spec["keyColumns"])["name"]
        for index, entry in enumerate(entries):
            expression = parse_expression(entry["originalFormula"], workbook_mode=True)
            if not isinstance(expression, Reference) or not expression.value.workbook:
                raise ValueError("reviewed replacement must bind one exact external source cell")
            ref = expression.value
            identity = (ref.workbook, ref.sheet, ref.address)
            if identity in values and values[identity] != spec["rows"][index][value_column]:
                raise ValueError("conflicting reviewed external source replacements")
            values[identity] = spec["rows"][index][value_column]
            provenance[f"[{ref.workbook}]{ref.sheet}!{ref.address}"] = {
                "featureId": feature, "rowIndex": index, "column": value_column,
                "sourceCellId": entry["sourceCells"][value_column]}
    return values, provenance


def _render(node, reference, *, arithmetic=False):
    kind = node["kind"]
    if kind == "number": return node["source"]
    if kind == "text":
        if arithmetic: raise UnsupportedExpression("inline text in numeric expression requires Excel coercion")
        return json.dumps(node["value"], ensure_ascii=False)
    if kind == "boolean":
        if arithmetic: raise UnsupportedExpression("Boolean in numeric expression requires Excel coercion")
        return "True" if node["value"] else "False"
    if kind == "reference": return reference(node["cell"], arithmetic)
    if kind == "group": return "(" + _render(node["expression"], reference, arithmetic=arithmetic) + ")"
    if kind == "unary":
        if node["operator"] not in {"+", "-"}: raise UnsupportedExpression("unqualified unary operator")
        return "(" + node["operator"] + _render(node["operand"], reference, arithmetic=True) + ")"
    if kind == "percent": return "(" + _render(node["operand"], reference, arithmetic=True) + " * 0.01)"
    if kind == "binary":
        op = node["operator"]
        if op not in {"+", "-", "*", "/", "^", "=", "<>", "<", ">", "<=", ">=", "&"}:
            raise UnsupportedExpression(f"unqualified binary operator {op}")
        numeric = op in {"+", "-", "*", "/", "^"}
        left = _render(node["left"], reference, arithmetic=numeric)
        right = _render(node["right"], reference, arithmetic=numeric)
        if op == "^": return f"Power({left}, {right})"
        return f"({left} {'!=' if op == '<>' else op} {right})"
    if kind == "indirect":
        # The finite alternatives remain in the bound AST and dependency DAG.
        # Excel returns an error for an invalid selector, whereas a Switch
        # default of Null would silently change that business result.
        raise UnsupportedExpression("finite INDIRECT invalid-selector/error semantics require qualification")
    if kind == "function":
        name, args = node["name"], node["arguments"]
        simple = {"IF": ("If", 3), "ROUND": ("Round", 2), "ABS": ("Abs", 1),
                  "INT": ("Floor", 1)}
        if name in {"MIN", "MAX"}:
            # Sigma Min/Max aggregate a field; Excel also accepts scalar and
            # mixed arguments with different coercion and error semantics.
            # v1 has no exact range aggregation lowering either.
            raise UnsupportedExpression(f"function {name} requires exact native qualification; use exact=True")
        if name == "SUM":
            terms = []
            for arg in args:
                if arg["kind"] == "range":
                    terms.extend(reference(cell, True) for cell in arg["cells"])
                else:
                    terms.append(_render(arg, reference, arithmetic=True))
            return "(" + " + ".join(terms or ["0"]) + ")"
        if name not in simple:
            raise UnsupportedExpression(f"function {name} requires exact native qualification")
        native, count = simple[name]
        if count is not None and len(args) != count:
            raise UnsupportedExpression(f"function {name} argument count")
        if count is None and not args:
            raise UnsupportedExpression(f"function {name} argument count")
        return native + "(" + ", ".join(_render(arg, reference, arithmetic=name != "IF") for arg in args) + ")"
    if kind == "range":
        if len(node["cells"]) == 1:
            return reference(node["cells"][0], arithmetic)
        raise UnsupportedExpression("range requires an exact aggregate or lookup lowering")
    raise UnsupportedExpression(f"AST node {kind} requires exact native qualification")


def build_native_calculation_plan(source_path, source_input_plan=None, *, exact=False):
    """Account for every source formula without cached results or guessed inputs."""
    if exact:
        try: from .native_exact_plan import build_exact_native_calculation_plan
        except ImportError: from native_exact_plan import build_exact_native_calculation_plan
        return build_exact_native_calculation_plan(source_path, source_input_plan)
    path = Path(source_path)
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if source_input_plan is not None:
        validate_source_input_plan(source_input_plan, path)
        if source_input_plan["sourceSha256"] != source_hash:
            raise ValueError("source hash disagrees with reviewed inputs")
    external_inputs, external_provenance = _replacement_external_inputs(source_input_plan)
    context = WorkbookContext.from_path(path, external_inputs=external_inputs)
    bindings = _input_bindings(source_input_plan) if source_input_plan else {}
    formulas = {}
    source_formulas = {f"{sheet}!{address}": formula for (sheet, address), formula in context.formulas.items()}
    for cell, original in sorted(source_formulas.items()):
        sheet, address = cell.rsplit("!", 1)
        record = {"sourceCellId": cell, "originalFormula": str(original),
                  "status": "unresolved", "reason": None, "dependencies": [],
                  "layer": None, "columnId": _symbol(cell), "ast": None}
        if bindings.get(cell, {}).get("kind") == "input":
            record["status"] = "reviewed-replacement-input"
            record["reason"] = "reviewed editable replacement; original source formula retained"
        else:
            try:
                bound = context.bind_formula(original, sheet=sheet, address=address)
                record["ast"] = _ast(bound)
                deps, domains, complete = context._bound_evidence(bound)
                record["dependencies"] = deps
                record["bindingEvidence"] = domains
                if not complete:
                    raise UnsupportedExpression("incomplete dynamic or whole-column dependency domain")
                def check(reference_cell, arithmetic):
                    if reference_cell in source_formulas:
                        return "[pending-formula]"
                    binding = bindings.get(reference_cell)
                    if binding is None:
                        target_sheet, target_address = reference_cell.rsplit("!", 1)
                        source_cell = context.workbook[target_sheet][target_address] if target_sheet in context.workbook else None
                        if source_cell is not None and source_cell.data_type == "e":
                            raise UnsupportedExpression(f"Excel error source cell {reference_cell}")
                        raise UnsupportedExpression(f"unmapped source literal {reference_cell}")
                    if binding["kind"] != "input":
                        raise UnsupportedExpression(f"ambiguous source input {reference_cell}")
                    if arithmetic and binding["valueType"] != "number":
                        raise UnsupportedExpression(f"numeric expression references {binding['valueType']} source {reference_cell}")
                    return "[pending-input]"
                _render(record["ast"], check)
                expected = context.evaluate_cell(sheet, address)
                if expected is not None and type(expected) not in {str, int, float, bool}:
                    raise UnsupportedExpression("non-scalar source result requires native qualification")
                record["localExpected"] = expected
                record["status"] = "ready-to-bind"
            except (ExcelCalcError, UnsupportedExpression, ValueError, TypeError) as error:
                record["reason"] = str(error)
        formulas[cell] = record
    # A ready formula can only depend on ready formulas or reviewed replacement inputs.
    visiting = set()
    def layer(cell):
        record = formulas[cell]
        if record["status"] != "ready-to-bind": return None
        if record["layer"] is not None: return record["layer"]
        if cell in visiting:
            record["status"], record["reason"] = "unresolved", "formula dependency cycle"
            return None
        visiting.add(cell)
        depths = []
        for dep in record["dependencies"]:
            if dep not in formulas: continue
            if formulas[dep]["status"] == "reviewed-replacement-input": continue
            depth = layer(dep)
            if depth is None:
                record["status"] = "unresolved"
                record["reason"] = f"unresolved formula dependency {dep}"
                break
            depths.append(depth)
        visiting.remove(cell)
        if record["status"] == "ready-to-bind":
            record["layer"] = max(depths, default=-1) + 1
        return record["layer"]
    for cell in formulas: layer(cell)
    logical = {"nativePlanVersion": PLAN_VERSION, "sourceSha256": source_hash,
               "inputPlanHash": source_input_plan["inputPlanHash"] if source_input_plan else None,
               "targetScope": source_input_plan["sharedInputArchitecture"]["targetScope"] if source_input_plan else None,
               "formulaCount": len(formulas), "bindings": bindings,
               "replacementExternalBindings": external_provenance, "formulas": formulas,
               "status": "SOURCE_BOUND_PENDING_STAGING"}
    return {**logical, "nativePlanHash": _digest(logical)}


def lower_native_calculations(plan, assigned_rows, *, max_columns=64):
    """Lower a dependency-ordered scalar layer using actual observed row IDs.

    The returned code-representation shards are construction candidates only.
    The caller must pass them through the approved staging and document gates.
    """
    if isinstance(plan, dict) and plan.get("nativePlanVersion") == 2:
        try: from .native_exact_plan import lower_exact_native_calculations
        except ImportError: from native_exact_plan import lower_exact_native_calculations
        return lower_exact_native_calculations(plan, assigned_rows, max_columns=max_columns)
    if not isinstance(plan, dict) or plan.get("nativePlanVersion") != PLAN_VERSION:
        raise ValueError("unsupported native plan")
    logical = {key: value for key, value in plan.items() if key != "nativePlanHash"}
    if _digest(logical) != plan.get("nativePlanHash"):
        raise ValueError("native plan hash is stale")
    if not isinstance(plan.get("targetScope"), dict) or not plan["targetScope"].get("connectionId"):
        raise ValueError("reviewed input target scope is required for native construction")
    if not 1 <= max_columns <= 64:
        raise ValueError("native shard column limit must be between 1 and 64")
    bindings = plan["bindings"]
    for binding in bindings.values():
        if binding["kind"] != "input": continue
        feature, index = binding["featureId"], str(binding["rowIndex"])
        assigned = assigned_rows.get(feature) or {}
        if (not assigned.get("elementId") or not assigned.get("name") or not assigned.get("rowIdColumn")
                or not isinstance(assigned.get("rows"), dict) or not assigned["rows"].get(index)):
            raise ValueError(f"actual assigned row ID is required for {feature}/{index}")
    ready = sorted((cell for cell, record in plan["formulas"].items()
                    if record["status"] == "ready-to-bind"),
                   key=lambda cell: (plan["formulas"][cell]["layer"], cell))
    shards = []
    handles = {}
    formulas = {}
    pending = []
    def flush():
        if not pending: return
        number = len(shards) + 1
        name = f"Native Calculations {number}"
        element_id = "native_calc_" + plan["sourceSha256"][:8] + f"_{number}"
        source = ({"kind": "sql", "connectionId": plan["targetScope"]["connectionId"],
                   "statement": "SELECT 1 AS C0"} if not shards else
                  {"kind": "table", "elementId": shards[-1]["id"]})
        columns = []
        for cell, formula in pending:
            record = plan["formulas"][cell]
            columns.append({"id": record["columnId"], "name": record["columnId"], "formula": formula})
            handles[cell] = f"[{name}/{record['columnId']}]"
            formulas[cell] = formula
        shards.append({"id": element_id, "kind": "table", "name": name,
                       "source": source, "columns": columns,
                       "sourceFormulaCells": [cell for cell, _ in pending]})
        pending.clear()
    active_layer = None
    for cell in ready:
        record = plan["formulas"][cell]
        if active_layer is not None and (record["layer"] != active_layer or len(pending) >= max_columns):
            flush()
        active_layer = record["layer"]
        def resolve(reference_cell, arithmetic):
            if reference_cell in handles:
                return handles[reference_cell]
            binding = bindings.get(reference_cell)
            if binding is None or binding["kind"] != "input":
                raise ValueError(f"unbound native source reference {reference_cell}")
            assigned = assigned_rows[binding["featureId"]]
            name = assigned["name"]
            field = binding["column"]
            row_id = assigned["rows"][str(binding["rowIndex"])]
            lookup = f"Lookup([{name}/{field}], {json.dumps(row_id)}, [{name}/{assigned['rowIdColumn']}])"
            return f"Coalesce({lookup}, 0)" if arithmetic and binding["valueType"] == "number" else lookup
        formula = _render(record["ast"], resolve)
        pending.append((cell, formula))
    flush()
    return {"sourceSha256": plan["sourceSha256"], "nativePlanHash": plan["nativePlanHash"],
            "formulas": formulas, "shards": shards,
            "unresolved": {cell: record["reason"] for cell, record in plan["formulas"].items()
                           if record["status"] == "unresolved"},
            "status": "CONSTRUCTION_CANDIDATE_PENDING_STAGING"}


def _observed_bindings(source_plan, manifest, receipt, contents, observed_rows, *, input_binding_only=False):
    inputs = source_plan["sharedInputArchitecture"]["inputs"]
    elements = contents["elements"]
    result = {}
    for feature, spec in sorted(inputs.items()):
        _approved, target, _artifact = _approved_feature(manifest, receipt, feature,
                                                         require_assigned=True, allow_input_only=input_binding_only)
        matches = [element for element in elements if element.get("id") == target["elementId"]]
        if len(matches) != 1 or matches[0].get("kind") != "input-table" or matches[0].get("name") != spec["name"]:
            raise ValueError(f"actual assigned input element is stale: {feature}")
        if sum(element.get("name") == spec["name"] for element in elements) != 1:
            raise ValueError(f"input lookup name is ambiguous: {feature}")
        observed_columns = {column.get("id"): column for column in matches[0].get("columns") or []}
        for column in spec["columns"]:
            actual = observed_columns.get(target["columnIds"][column["name"]]) or {}
            if actual.get("name") != column["name"] or actual.get("type") != column["type"]:
                raise ValueError(f"actual assigned input column is stale: {feature}/{column['name']}")
        system = _system_column_contract(target)
        system_id = system.get("id") or target.get("rowIdColumnId")
        actual_system = observed_columns.get(system_id) or {}
        if actual_system.get("name") != system["name"]:
            raise ValueError(f"actual assigned row ID alias is stale: {feature}")
        queried = observed_rows.get(feature)
        if not isinstance(queried, list):
            raise ValueError(f"fresh queried physical rows are required: {feature}")
        keys = spec["keyColumns"]
        def token(row):
            if not isinstance(row, dict) or any(name not in row or row[name] is None for name in keys):
                raise ValueError(f"observed source key is incomplete: {feature}")
            return _digest([[type(row[name]).__name__, row[name]] for name in keys])
        by_key = {}
        all_ids = set()
        for row in queried:
            if any(column["name"] not in row for column in spec["columns"]):
                raise ValueError(f"full input row backup is required: {feature}")
            key = token(row)
            row_id = row.get(system["name"])
            if key in by_key or not isinstance(row_id, str) or not row_id or row_id in all_ids:
                raise ValueError(f"observed physical rows lack unique keys and row IDs: {feature}")
            by_key[key] = row_id
            all_ids.add(row_id)
        assigned = {}
        for index, row in enumerate(spec["rows"]):
            key = token(row)
            if key not in by_key:
                raise ValueError(f"source row lacks an observed physical row ID: {feature}/{index}")
            assigned[str(index)] = by_key[key]
        result[feature] = {"elementId": target["elementId"], "name": spec["name"],
                           "rowIdColumn": system["name"], "rows": assigned}
    return result


def _native_page_id(plan):
    return "native_calculations_" + plan["sourceSha256"][:8]


def build_native_calculation_backup(current, observed_rows):
    """Return the complete document and input-row restoration material."""
    if (not isinstance(current, dict) or not isinstance(current.get("contents"), dict)
            or not isinstance(observed_rows, dict)):
        raise ValueError("complete document and queried input rows are required for backup")
    data = {"documentId": current.get("workbookId"),
            "documentVersion": current.get("documentVersion"),
            "contents": copy.deepcopy(current["contents"]),
            "inputRows": copy.deepcopy(observed_rows)}
    if not data["documentId"] or not isinstance(data["documentVersion"], int):
        raise ValueError("backup requires observed document identity and version")
    return {**data, "backupHash": _digest(data)}


def prepare_native_calculation_update(plan, source_input_plan, manifest, receipt,
                                      current, observed_rows, *, backup=None, shard_index=0,
                                      max_columns=64, prior_readbacks=()):
    """Prepare one version-guarded REST contents PUT after fresh assigned input reads.

    It never sends a request.  Each shard needs a fresh GET and confirmed prior
    shard readback, so a later write cannot consume guessed assigned IDs.
    """
    if plan.get("nativePlanVersion") == 2:
        raise ValueError("exact native updates require assigned scaffold receipts; use prepare_exact_native_update")
    validate_source_input_plan(source_input_plan)
    validate_manifest(manifest)
    if (manifest.get("sourceHash") != plan.get("sourceSha256")
            or source_input_plan["sourceSha256"] != plan.get("sourceSha256")
            or source_input_plan["inputPlanHash"] != plan.get("inputPlanHash")
            or manifest.get("planProjection", {}).get("inputPlanHash") != plan.get("inputPlanHash")
            or manifest.get("planProjection", {}).get("sharedInputArchitecture") !=
            source_input_plan["sharedInputArchitecture"]):
        raise ValueError("source/input/native/manifest hash or architecture is stale")
    scope = manifest.get("target") or {}
    if (current.get("workbookId") != scope.get("documentId")
            or current.get("documentVersion") != scope.get("version")):
        raise ValueError("current target/version is stale")
    contents = current.get("contents")
    if (not isinstance(contents, dict) or contents.get("kind") != "workbook"
            or not isinstance(contents.get("elements"), list)
            or not isinstance(contents.get("pages"), list)
            or not isinstance(contents.get("layout"), str)):
        raise ValueError("complete fresh workbook contents are required")
    if backup != build_native_calculation_backup(current, observed_rows):
        raise ValueError("complete persisted document and input row backup is required")
    assigned = _observed_bindings(source_input_plan, manifest, receipt, contents, observed_rows)
    lowered = lower_native_calculations(plan, assigned, max_columns=max_columns)
    shards = lowered["shards"]
    if not 0 <= shard_index < len(shards):
        raise ValueError("native shard index is out of bounds")
    cell_manifest = {item["id"]: item for item in manifest["formulaCells"]}
    for cell, formula in lowered["formulas"].items():
        native = plan["formulas"][cell]
        manifest_record = cell_manifest.get(cell) or {}
        intended = manifest_record.get("targetMapping") or {}
        target_shard = next(shard for shard in shards if cell in shard["sourceFormulaCells"])
        if (manifest_record.get("mappingStatus") != "live"
                or manifest_record.get("originalFormula") != native["originalFormula"]
                or intended.get("logicalElementId") != target_shard["id"]
                or intended.get("logicalColumnId") != native["columnId"]):
            raise ValueError(f"reviewed live formula mapping is absent or stale: {cell}")
    marker = "excel-to-sigma:native-calculations:" + plan["nativePlanHash"]
    expected_existing = shards[:shard_index]
    if len(prior_readbacks) != shard_index:
        raise ValueError("confirmed prior shard readback is required")
    for index, previous in enumerate(expected_existing):
        record = prior_readbacks[index]
        if (record.get("status") != "CONFIRMED_NATIVE_SHARD_READBACK"
                or record.get("nativePlanHash") != plan["nativePlanHash"]
                or record.get("shardIndex") != index
                or record.get("documentId") != scope["documentId"]
                or not isinstance(record.get("documentVersion"), int)
                or record["documentVersion"] > scope["version"]
                or record.get("actualElementId") != previous["id"]
                or record.get("formulaHash") != _digest(previous["columns"])):
            raise ValueError("prior shard readback is stale")
        actual = [item for item in contents["elements"] if item.get("id") == previous["id"]]
        if (len(actual) != 1 or actual[0].get("description", {}).get("text") != marker
                or actual[0].get("columns") != previous["columns"]
                or actual[0].get("source") != previous["source"]
                or (index == shard_index - 1 and record.get("readbackHash") != _digest(contents))):
            raise ValueError("saved prior shard expression structure changed")
    shard = shards[shard_index]
    if any(item.get("id") == shard["id"] for item in contents["elements"]):
        raise ValueError("native shard target collides with current contents")
    updated = copy.deepcopy(contents)
    inserted = {key: copy.deepcopy(value) for key, value in shard.items()
                if key != "sourceFormulaCells"}
    inserted["description"] = {"text": marker, "visibility": "hidden"}
    updated["elements"].append(inserted)
    page_id = _native_page_id(plan)
    xml = ET.fromstring("<Layout>" + updated["layout"] + "</Layout>")
    pages = [page for page in updated["pages"] if page.get("id") == page_id]
    layout_pages = [page for page in xml.iter("Page") if page.get("id") == page_id]
    placement = (f'<Element elementId="{shard["id"]}" gridColumn="1 / 25" '
                 f'gridRow="{shard_index * 12 + 1} / {shard_index * 12 + 13}" />')
    if shard_index == 0:
        if pages or layout_pages:
            raise ValueError("native calculation page collides with current contents")
        updated["pages"].append({"id": page_id, "name": "Native Calculations", "visibility": "hidden"})
        updated["layout"] += (f'<Page id="{page_id}" type="grid" gridTemplateColumns="repeat(24, 1fr)" '
                              f'gridTemplateRows="auto">{placement}</Page>')
    else:
        if len(pages) != 1 or len(layout_pages) != 1:
            raise ValueError("native calculation page is absent or ambiguous")
        old = ET.tostring(layout_pages[0], encoding="unicode")
        # ElementTree may normalize whitespace; use the actual layout substring
        # only to locate the unique owned closing tag, leaving foreign bytes intact.
        del old
        pattern = re.compile(r"(<Page\b[^>]*\bid=[\"']" + re.escape(page_id) +
                             r"[\"'][^>]*>)(.*?)(</Page>)", re.S)
        matches = list(pattern.finditer(updated["layout"]))
        if len(matches) != 1:
            raise ValueError("native calculation layout ownership is ambiguous")
        match = matches[0]
        updated["layout"] = (updated["layout"][:match.start()] + match.group(1) + match.group(2)
                             + placement + match.group(3) + updated["layout"][match.end():])
    request = {"documentVersion": scope["version"], "contents": updated}
    return {"status": "GUARDED_REST_CANDIDATE_PENDING_READBACK", "method": "PUT",
            "endpoint": f"/v2/workbooks/{scope['documentId']}/contents",
            "sourceSha256": plan["sourceSha256"], "nativePlanHash": plan["nativePlanHash"],
            "manifestPlanHash": manifest["planHash"], "inputPlanHash": plan["inputPlanHash"],
            "shardIndex": shard_index, "shardCount": len(shards),
            "expectedElementId": shard["id"], "expectedFormulaColumns": {
                cell: lowered["formulas"][cell] for cell in shard["sourceFormulaCells"]},
            "formulaHash": _digest(shard["columns"]), "assignedRowsHash": _digest(assigned),
            "backupHash": backup["backupHash"],
            "dryRunRequest": request}


def confirm_native_calculation_readback(proposal, readback):
    """Confirm exact saved structure before another shard may be prepared."""
    if (proposal.get("status") != "GUARDED_REST_CANDIDATE_PENDING_READBACK"
            or readback.get("workbookId") != proposal["endpoint"].split("/")[3]
            or not isinstance(readback.get("documentVersion"), int)
            or readback["documentVersion"] <= proposal["dryRunRequest"]["documentVersion"]
            or readback.get("contents") != proposal["dryRunRequest"]["contents"]):
        raise ValueError("exact fresh REST readback is required")
    elements = readback["contents"].get("elements") or []
    actual = [item for item in elements if item.get("id") == proposal["expectedElementId"]]
    if len(actual) != 1:
        raise ValueError("native shard actual assigned ID is absent from readback")
    return {"status": "CONFIRMED_NATIVE_SHARD_READBACK", "sourceSha256": proposal["sourceSha256"],
            "nativePlanHash": proposal["nativePlanHash"], "manifestPlanHash": proposal["manifestPlanHash"],
            "shardIndex": proposal["shardIndex"], "actualElementId": actual[0]["id"],
            "formulaHash": proposal["formulaHash"], "documentId": readback["workbookId"],
            "documentVersion": readback["documentVersion"], "readbackHash": _digest(readback["contents"])}
