#!/usr/bin/env python3
"""Parse a Hex ".hex.yaml" project export into a plain-dict intermediate form.

Hex has no REST endpoint that returns cell content (SQL text, chart config) —
confirmed against the public API docs (learn.hex.tech/docs/api/api-overview):
it covers projects/runs/users/collections/data-connections only. The actual
source of truth for full project logic is the ".hex.yaml" file, obtained via
a one-click manual `Export` (any plan) or continuous Git Sync (Team/
Enterprise) — same format either way. There is a public JSON Schema for it
at https://static.hex.site/hex-file-schema.json (registered on SchemaStore),
vendored locally at refs/hex-file-schema.json for reference — this module
does a lightweight structural check against the known shape rather than full
draft-07 validation, matching this repo's stdlib-only / no-pip-install
convention (see shared/lib/sigma_rest.py's docstring).

Confirmed cell types (from a real export, `Commerce Dashboard.yaml` —
corpus/hex/commerce/): SQL, METRIC, EXPLORE. Every other cellType
(CODE/Python, INPUT, MARKDOWN, TABLE_DISPLAY, TEXT, MAP, WRITEBACK, PIVOT,
FILTER, DBT_METRIC, COMPONENT_IMPORT, BLOCK, COLLAPSIBLE) is parsed as a
skipped cell and surfaced as a warning by the converters — never silently
dropped.
"""

from __future__ import annotations

import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

SUPPORTED_CELL_TYPES = {"SQL", "METRIC", "EXPLORE"}

# Hex's own synthetic pseudo-column, added to every SQL cell's preview grid —
# not a real data column, never carry it into the Sigma data model.
_SYNTHETIC_COLUMN_PREFIXES = ("row-index-",)


class HexParseError(Exception):
    pass


def load_project(path: str) -> dict:
    """Load and lightly validate a .hex.yaml export. Returns the raw parsed
    dict (top-level keys: schemaVersion, meta, projectAssets, sharedAssets,
    cells, appLayout, sharedFilters)."""
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    if not isinstance(doc, dict):
        raise HexParseError(f"{path}: expected a YAML mapping at the top level")
    for required in ("meta", "cells"):
        if required not in doc:
            raise HexParseError(f"{path}: missing required top-level key '{required}' — "
                                 "not a Hex project export? (see refs/hex-file-schema.json)")
    if not isinstance(doc["cells"], list):
        raise HexParseError(f"{path}: 'cells' must be a list")
    return doc


def project_title(doc: dict) -> str:
    return (doc.get("meta") or {}).get("title") or "Untitled Hex Project"


def data_connection_ids(doc: dict) -> list[str]:
    """Every data-connection id referenced anywhere in the project. Hex
    references connections by uuid only — the human-readable name (e.g.
    "Snowflake-PB (snowflake)") is a YAML *comment*, not a parseable field,
    so it never survives yaml.safe_load. The kickoff prompt supplies the
    target SIGMA_CONNECTION_ID directly, same as every sibling skill."""
    ids = []
    for c in (doc.get("sharedAssets") or {}).get("dataConnections") or []:
        if c.get("dataConnectionId"):
            ids.append(c["dataConnectionId"])
    return ids


def _clean_columns(column_properties: list[dict]) -> list[str]:
    """A SQL cell's config.tableDisplayConfig.columnProperties[] enumerates
    every resolved output column (Hex's stand-in for Metabase's
    result_metadata, since the YAML export never separately lists a SQL
    cell's output schema) — originalName is the exact column alias as it
    appears in the SELECT. Drop Hex's synthetic row-index pseudo-column."""
    names = []
    for c in column_properties or []:
        name = c.get("originalName")
        if not name or name.startswith(_SYNTHETIC_COLUMN_PREFIXES):
            continue
        names.append(name)
    return names


def parse_sql_cell(cell: dict) -> dict:
    cfg = cell.get("config") or {}
    return {
        "cell_id": cell["cellId"],
        "label": cell.get("cellLabel"),
        "result_variable": cfg.get("resultVariableName") or "query_result",
        "source": cfg.get("source") or "",
        "data_connection_id": cfg.get("dataConnectionId"),
        "is_dataframe_cell": bool(cfg.get("dataFrameCell")),
        "columns": _clean_columns((cfg.get("tableDisplayConfig") or {}).get("columnProperties")),
    }


def parse_metric_cell(cell: dict) -> dict:
    cfg = cell.get("config") or {}
    return {
        "cell_id": cell["cellId"],
        "label": cell.get("cellLabel"),
        "title": cfg.get("title") or cell.get("cellLabel") or "Metric",
        "value_variable_name": cfg.get("valueVariableName"),
        "value_column": cfg.get("valueColumn"),
        "value_aggregate": cfg.get("valueAggregate"),
        "display_format": cfg.get("displayFormat"),
    }


def parse_explore_cell(cell: dict) -> dict:
    cfg = cell.get("config") or {}
    spec = cfg.get("spec") or {}
    chart = spec.get("chartConfig") or {}
    return {
        "cell_id": cell["cellId"],
        "label": cell.get("cellLabel"),
        "dataframe": cfg.get("dataframe"),
        "fields": spec.get("fields") or [],
        "series": chart.get("series") or [],
        "series_groups": chart.get("seriesGroups") or [],
        "orientation": chart.get("orientation"),
        "view_type": spec.get("viewType"),
        "visualization_type": spec.get("visualizationType"),
    }


def parse_cells(doc: dict) -> tuple[list[dict], list[str]]:
    """Returns (parsed_cells, warnings). Each parsed cell dict carries a
    'kind' key ('sql' | 'metric' | 'explore') for supported types; anything
    else is omitted from the returned list and reported as a warning —
    flagged, never silently dropped."""
    parsed = []
    warnings = []
    for cell in doc.get("cells") or []:
        ctype = cell.get("cellType")
        label = cell.get("cellLabel") or cell.get("cellId")
        if ctype == "SQL":
            parsed.append({"kind": "sql", **parse_sql_cell(cell)})
        elif ctype == "METRIC":
            parsed.append({"kind": "metric", **parse_metric_cell(cell)})
        elif ctype == "EXPLORE":
            parsed.append({"kind": "explore", **parse_explore_cell(cell)})
        else:
            warnings.append(
                f"cell '{label}' (cellType={ctype!r}) has no Sigma equivalent in this "
                "skill yet — skipped, not converted. Python (CODE) cells in particular "
                "need hand-review: their transform logic has no automatic Sigma translation."
            )
    return parsed, warnings


def parse_app_layout(doc: dict) -> list[dict]:
    """appLayout.tabs[].rows[].columns[].{start,end,elements[]} on a 0-120
    scale (confirmed from a real export — NOT Metabase's 24-col grid).
    Returns a list of tabs: [{name, rows: [{columns: [{start,end,cell_ids:[...]}]}]}]."""
    layout = doc.get("appLayout") or {}
    tabs = []
    for tab in layout.get("tabs") or []:
        rows = []
        for row in tab.get("rows") or []:
            cols = []
            for col in row.get("columns") or []:
                cell_ids = [
                    el["cellId"] for el in (col.get("elements") or [])
                    if el.get("type") == "CELL" and el.get("cellId")
                ]
                cols.append({
                    "start": col.get("start", 0),
                    "end": col.get("end", 120),
                    "cell_ids": cell_ids,
                })
            rows.append({"columns": cols})
        tabs.append({"name": tab.get("name") or "Page 1", "rows": rows})
    return tabs
