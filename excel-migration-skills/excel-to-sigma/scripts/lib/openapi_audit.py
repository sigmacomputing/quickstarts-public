"""Operation-scoped drift audit for Sigma workbook code representation."""
from __future__ import annotations

import json
import urllib.request

DEFAULT_OPENAPI_URL = (
    "https://assets.sigmacomputing.com/openapi/public-rest-api/"
    "sigma-computing-public-rest-api.json"
)


def _decode_pointer_token(token):
    return token.replace("~1", "/").replace("~0", "~")


def resolve_ref(document, ref):
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise ValueError(f"only local OpenAPI refs are supported: {ref!r}")
    value = document
    for token in ref[2:].split("/"):
        value = value[_decode_pointer_token(token)]
    return value


def walk_resolved(document, root, active_refs=()):
    """Yield dict/list/scalar nodes reachable from one operation root.

    `$ref` siblings are traversed (OpenAPI 3.1), while the active reference
    stack prevents cycles without dropping a shared schema used in another
    logical context.
    """
    yield root
    if isinstance(root, dict):
        ref = root.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/") and ref not in active_refs:
            yield from walk_resolved(
                document, resolve_ref(document, ref), active_refs + (ref,))
        for key, value in root.items():
            if key != "$ref":
                yield from walk_resolved(document, value, active_refs)
    elif isinstance(root, list):
        for value in root:
            yield from walk_resolved(document, value, active_refs)


def _property_names(document, root):
    names = set()
    for node in walk_resolved(document, root):
        if isinstance(node, dict) and isinstance(node.get("properties"), dict):
            names.update(node["properties"])
    return names


def _required_names(document, root):
    names = set()
    for node in walk_resolved(document, root):
        if isinstance(node, dict) and isinstance(node.get("required"), list):
            names.update(str(name) for name in node["required"])
    return names


def _literal_values(document, root):
    values = set()
    for node in walk_resolved(document, root):
        if not isinstance(node, dict):
            continue
        if "const" in node and isinstance(node["const"], (str, int, float, bool)):
            values.add(node["const"])
        enum = node.get("enum")
        if isinstance(enum, list):
            values.update(
                value for value in enum
                if isinstance(value, (str, int, float, bool))
            )
    return values


def _request_schema(operation):
    content = (operation.get("requestBody") or {}).get("content") or {}
    return (content.get("application/json") or {}).get("schema") or {}


def _response_schema(operation, status):
    response = (operation.get("responses") or {}).get(str(status)) or {}
    content = response.get("content") or {}
    return (content.get("application/json") or {}).get("schema") or {}


def _parameter_names(operation):
    return {
        item.get("name")
        for item in operation.get("parameters") or []
        if isinstance(item, dict)
    }


def _contents_schema(document, create_schema):
    """Return the schema located beneath the create request's contents field."""
    for node in walk_resolved(document, create_schema):
        if not isinstance(node, dict):
            continue
        properties = node.get("properties")
        if isinstance(properties, dict) and isinstance(properties.get("contents"), dict):
            return properties["contents"]
    return {}


def _property_schema(document, root, name):
    for node in walk_resolved(document, root):
        if not isinstance(node, dict):
            continue
        properties = node.get("properties")
        if isinstance(properties, dict) and isinstance(properties.get(name), dict):
            return properties[name]
    return {}


def _pivot_axes_supported(document, contents_schema):
    for node in walk_resolved(document, contents_schema):
        if not isinstance(node, dict):
            continue
        properties = node.get("properties")
        if not isinstance(properties, dict) or not {"rowsBy", "columnsBy"}.issubset(properties):
            continue
        axes_ok = True
        for axis_name in ("rowsBy", "columnsBy"):
            axis = properties[axis_name]
            items = axis.get("items") if isinstance(axis, dict) else None
            if not isinstance(items, dict):
                axes_ok = False
                break
            item_properties = _property_names(document, items)
            item_required = _required_names(document, items)
            sort = _property_schema(document, items, "sort")
            sort_properties = _property_names(document, sort)
            sort_required = _required_names(document, sort)
            if not (
                "columnId" in item_properties
                and "columnId" in item_required
                and {"direction", "by", "aggregation"}.issubset(sort_properties)
                and "direction" in sort_required
            ):
                axes_ok = False
                break
        if axes_ok:
            return True
    return False


def audit_openapi(document):
    paths = document.get("paths") or {}
    create = (paths.get("/v2/workbooks") or {}).get("post") or {}
    read = (paths.get("/v2/workbooks/{workbookId}") or {}).get("get") or {}
    update = (paths.get("/v2/workbooks/{workbookId}/contents") or {}).get("put") or {}

    create_schema = _request_schema(create)
    contents_schema = _contents_schema(document, create_schema)
    create_props = _property_names(document, create_schema)
    create_required = _required_names(document, create_schema)
    contents_props = _property_names(document, contents_schema)
    contents_required = _required_names(document, contents_schema)
    contents_literals = _literal_values(document, contents_schema)

    success_schema = _response_schema(create, "200")
    bad_schema = _response_schema(create, "400")
    success_props = _property_names(document, success_schema)
    bad_props = _property_names(document, bad_schema)

    read_schema = _response_schema(read, "200")
    read_props = _property_names(document, read_schema)
    update_schema = _request_schema(update)
    update_props = _property_names(document, update_schema)

    capabilities = {
        "currentCreateEndpoint": bool(create),
        "contentsEnvelope": (
            {"folderId", "name", "contents"}.issubset(create_props)
            and {"folderId", "name"}.issubset(create_required)
        ),
        "dryRunValidation": (
            "dryRun" in create_props
            and {"dryRun", "warnings"}.issubset(success_props)
            and {"dryRun", "valid", "errors", "warnings"}.issubset(bad_props)
        ),
        "workbookContents": (
            {"schemaVersion", "kind", "pages", "elements", "layout"}.issubset(contents_props)
            and {"schemaVersion", "kind", "pages", "elements", "layout"}.issubset(contents_required)
            and "workbook" in contents_literals
        ),
        "readContents": (
            "includeContents" in _parameter_names(read)
            and {"contents", "documentVersion"}.issubset(read_props)
        ),
        "updateContents": (
            bool(update)
            and "contents" in update_props
            and "documentVersion" in update_props
        ),
        "inputTables": (
            "input-table" in contents_literals
            and {"inputMode", "source", "columns"}.issubset(contents_props)
            and {"edit", "explore", "view"}.issubset(contents_literals)
        ),
        "inputValidation": (
            {"values", "valuesFrom", "range", "maxFileNum", "maxFileSizeMb",
             "acceptedFileTypes"}.issubset(contents_props)
        ),
        "actions": (
            {"trigger", "effects"}.issubset(contents_props)
            and {"insert-rows", "update-rows", "delete-rows", "call-api",
                 "call-stored-procedure", "run-python-element"}.issubset(contents_literals)
        ),
        "automatedActions": (
            "automatedActions" in contents_props
            and {"schedule", "webhook"}.issubset(contents_literals)
            and "call-agent" in contents_literals
        ),
        "python": (
            {"code", "code-output"}.issubset(contents_literals)
            and {"code", "connectionId", "output"}.issubset(contents_props)
        ),
        "visuals": (
            {"pivot-table", "bar-chart", "line-chart", "scatter-chart", "control"}
            .issubset(contents_literals)
        ),
        "pivotAxes": _pivot_axes_supported(document, contents_schema),
    }
    missing = [name for name, present in capabilities.items() if not present]
    return {
        "openapiVersion": (document.get("info") or {}).get("version"),
        "status": "PASS" if not missing else "DRIFT",
        "capabilities": capabilities,
        "missing": missing,
    }


def fetch_openapi(url=DEFAULT_OPENAPI_URL, timeout=30):
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "excel-to-sigma-openapi-audit/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)
