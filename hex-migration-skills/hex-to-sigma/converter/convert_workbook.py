#!/usr/bin/env python3
"""Convert a Hex project's METRIC/EXPLORE cells into a Sigma workbook spec,
wired to the data model built by convert_dm.py, plus a page `layout` built
from Hex's appLayout.

Shapes below are taken directly from the sigma-workbooks skill's
reference/specification/{kpis,charts,layout,sources}.md — not guessed:

- KPI: `kind: kpi-chart`, `value: {columnId}` (singular id, on the element's
  OWN columns[]).
- Bar/line/area/scatter (cartesian): `xAxis: {columnId}`, `yAxis:
  {columnIds: [...]}`, optional `orientation: horizontal` (omit for the
  default vertical).
- Pie/donut: `value: {id}`, `color: {id}` — NOTE the singular `id` key, not
  `columnId` — different from the cartesian axis shape.
- Top-N filter is a NATIVE Sigma feature (`filters: [{kind: top-n, columnId,
  rankingFunction, rowCount, ...}]`) — Hex's `lump` on an EXPLORE field maps
  onto it directly. This is NOT a flagged/unsupported construct.
- Cross-document DM reference: `source: {kind: 'data-model', dataModelId,
  elementId}`.

One assumption, flagged for verification on the first live POST+readback
(same "flag it, verify at POST" discipline used throughout this skill
family): the formula prefix for columns on an element sourced from a DM's
*native-SQL* element. metabase-to-sigma's design-notes.md confirms "Sigma
does NOT honor sql-element names (all read back 'Custom SQL')" for
SQL-sourced elements — so every column formula below is qualified
`[Custom SQL/<column>]`, matching that confirmed behavior, not the DM
element's own (deliberately absent) `name`.
"""

from __future__ import annotations

import argparse
import json
import sys

import hex_yaml
import sigma_ids

SOURCE_PREFIX = "Custom SQL"  # see module docstring — flagged assumption

AGG_FORMULA = {
    "Sum": "Sum([{ref}])",
    "Avg": "Avg([{ref}])",
    "Min": "Min([{ref}])",
    "Max": "Max([{ref}])",
    "Count": "CountIf(IsNotNull([{ref}]))",
    "CountDistinct": "CountDistinct([{ref}])",
    "Median": "Median([{ref}])",
    "StdDev": "StdDev([{ref}])",
    "StdDevPop": "StdDevPop([{ref}])",
    "Variance": "Variance([{ref}])",
    "VariancePop": "VariancePop([{ref}])",
}

# Hex EXPLORE series `type` -> Sigma chart `kind`. Histogram has no confirmed
# direct Sigma chart kind — flagged, never faked (falls back to a table).
CHART_KIND = {
    "bar": "bar-chart",
    "line": "line-chart",
    "area": "area-chart",
    "scatter": "scatter-chart",
    "pie": "pie-chart",
}


def _qualified(colname: str) -> str:
    return f"[{SOURCE_PREFIX}/{colname}]"


def _agg_formula(agg: str | None, colname: str) -> str:
    template = AGG_FORMULA.get(agg or "Sum", AGG_FORMULA["Sum"])
    return template.format(ref=f"{SOURCE_PREFIX}/{colname}")


def _axis_sort(field: dict, axis_col_id: str, measure_col_id: str) -> dict | None:
    """Hex's field-level `sort.mode` (e.g. `cross-axis-descending`,
    `value-ascending`) -> Sigma's `{by: <colId>, direction: ascending|
    descending}` sort object. Without this, Sigma's default is an alphabetical
    dimension sort (live-verified 2026-07-30: our "Revenue by Country - Top
    10" chart rendered Australia/Canada/France/... instead of sorted by
    revenue, because no explicit xAxis.sort was emitted). `cross-axis*` sorts
    by the paired measure; `value*` sorts by the axis field's own value
    (e.g. a Year axis sorted chronologically)."""
    sort = field.get("sort") or {}
    mode = sort.get("mode", "")
    if mode.startswith("cross-axis"):
        by = measure_col_id
    elif mode.startswith("value"):
        by = axis_col_id
    else:
        return None
    direction = "descending" if mode.endswith("descending") else "ascending"
    return {"by": by, "direction": direction}


def _dm_source(dm_id: str, element_id: str) -> dict:
    return {"kind": "data-model", "dataModelId": dm_id, "elementId": element_id}


def _resolve_col_id(dataframe: str, colname: str, columns_by_variable: dict) -> str | None:
    return (columns_by_variable.get(dataframe) or {}).get(colname)


def build_metric_element(cell: dict, dm_id: str, element_id: str,
                          columns_by_variable: dict, warnings: list[str]) -> dict | None:
    dataframe = cell["value_variable_name"]
    col = cell["value_column"]
    if not dataframe or not col:
        warnings.append(f"METRIC cell '{cell['label'] or cell['cell_id']}' has no value "
                         "column configured — skipped.")
        return None
    if not _resolve_col_id(dataframe, col, columns_by_variable):
        warnings.append(f"METRIC cell '{cell['title']}': column '{col}' not found on "
                         f"dataframe '{dataframe}' — skipped.")
        return None

    value_col_id = sigma_ids.sigma_short_id()
    fmt = sigma_ids.infer_sigma_format(cell["value_aggregate"], cell["display_format"])
    column = {
        "id": value_col_id,
        "formula": _agg_formula(cell["value_aggregate"], col),
    }
    if fmt:
        column["format"] = fmt

    return {
        "id": sigma_ids.sigma_short_id(),
        "kind": "kpi-chart",
        "name": cell["title"],
        "source": _dm_source(dm_id, element_id),
        "columns": [column],
        "value": {"columnId": value_col_id},
        "_hex_cell_id": cell["cell_id"],  # stripped before POST; used to wire layout
    }


def _fields_by_channel(fields: list[dict]) -> dict[str, list[dict]]:
    by_channel: dict[str, list[dict]] = {}
    for f in fields:
        by_channel.setdefault(f.get("channel"), []).append(f)
    return by_channel


def _top_n_filter(field: dict, measure_col_id: str, warnings: list[str], label: str) -> dict | None:
    lump = field.get("lump")
    if not lump:
        return None
    predicate = lump.get("predicate") or {}
    if predicate.get("op") != "LTE" or lump.get("orderDirection") != "desc":
        warnings.append(f"'{label}': lump config ({lump}) isn't a plain top-N-descending "
                         "pattern — emitting a best-effort top-n filter; verify against the "
                         "Hex source.")
    return {
        "id": sigma_ids.sigma_short_id(),
        "columnId": measure_col_id,
        "kind": "top-n",
        "rankingFunction": "rank",
        "mode": "top-n",
        "rowCount": predicate.get("arg", 10),
        "includeNulls": "when-no-value-is-selected",
    }


def build_explore_element(cell: dict, dm_id: str, element_id: str,
                           columns_by_variable: dict, warnings: list[str]) -> dict | None:
    label = cell["label"] or cell["cell_id"]
    series = cell["series"]
    if len(series) != 1:
        warnings.append(f"EXPLORE cell '{label}' has {len(series)} series (combo/multi-series "
                         "charts aren't handled by this skill yet) — skipped.")
        return None
    series_type = series[0].get("type")
    kind = CHART_KIND.get(series_type)
    if not kind:
        warnings.append(f"EXPLORE cell '{label}': series type '{series_type}' has no confirmed "
                         "Sigma chart-kind mapping — skipped (never faked). Rebuild by hand.")
        return None

    dataframe = cell["dataframe"]
    by_channel = _fields_by_channel(cell["fields"])
    columns = []
    col_id_by_field = {}

    def add_column(field: dict) -> str | None:
        colname = field.get("value")
        if colname == "_HEX_COUNT_STAR_ARG_":
            # Hex's synthetic COUNT(*) token, not a real SQL column — no
            # direct Sigma equivalent wired up in v1 (only appears on
            # tooltip channels here, which this skill doesn't carry over).
            return None
        if not colname or not _resolve_col_id(dataframe, colname, columns_by_variable):
            warnings.append(f"EXPLORE cell '{label}': column '{colname}' not found on "
                             f"dataframe '{dataframe}' — field skipped.")
            return None
        col_id = sigma_ids.sigma_short_id()
        agg = field.get("aggregation")
        formula = _agg_formula(agg, colname) if agg else _qualified(colname)
        col = {"id": col_id, "name": colname, "formula": formula}
        columns.append(col)
        col_id_by_field[id(field)] = col_id
        return col_id

    element: dict = {
        "id": sigma_ids.sigma_short_id(),
        "kind": kind,
        "name": label,
        "source": _dm_source(dm_id, element_id),
    }
    filters = []

    if kind == "pie-chart":
        color_fields = by_channel.get("color", [])
        value_fields = by_channel.get("cross-axis", [])
        if not color_fields or not value_fields:
            warnings.append(f"EXPLORE cell '{label}' (pie): missing a color or value field — skipped.")
            return None
        color_id = add_column(color_fields[0])
        value_id = add_column(value_fields[0])
        if not color_id or not value_id:
            return None
        color_spec = {"id": color_id}
        sort_obj = _axis_sort(color_fields[0], color_id, value_id)
        if sort_obj:
            color_spec["sort"] = sort_obj
        element["color"] = color_spec
        element["value"] = {"id": value_id}
        top_n = _top_n_filter(color_fields[0], value_id, warnings, label)
        if top_n:
            filters.append(top_n)
    else:
        x_fields = by_channel.get("base-axis", [])
        y_fields = by_channel.get("cross-axis", [])
        if not x_fields or not y_fields:
            warnings.append(f"EXPLORE cell '{label}': missing a base-axis or cross-axis field — skipped.")
            return None
        x_id = add_column(x_fields[0])
        y_id = add_column(y_fields[0])
        if not x_id or not y_id:
            return None
        x_axis_spec = {"columnId": x_id}
        sort_obj = _axis_sort(x_fields[0], x_id, y_id)
        if sort_obj:
            x_axis_spec["sort"] = sort_obj
        element["xAxis"] = x_axis_spec
        element["yAxis"] = {"columnIds": [y_id]}
        if kind == "bar-chart" and cell.get("orientation") == "horizontal":
            element["orientation"] = "horizontal"
        top_n = _top_n_filter(x_fields[0], y_id, warnings, label)
        if top_n:
            filters.append(top_n)

    element["columns"] = columns
    if filters:
        element["filters"] = filters
    element["_hex_cell_id"] = cell["cell_id"]
    return element


# --- layout -----------------------------------------------------------------

_HEX_GRID_WIDTH = 120
_SIGMA_GRID_WIDTH = 24
_DEFAULT_ROW_SPAN = 8
_PX_PER_ROW = 40  # rough scale for turning a Hex pixel height into a row span


def _row_span(height: int | None) -> int:
    if not height:
        return _DEFAULT_ROW_SPAN
    return max(4, round(height / _PX_PER_ROW))


def build_layout_xml(page_id: str, tab: dict, elements_by_cell: dict[str, str]) -> str:
    """Two-tag grammar (sigma-workbooks/reference/specification/layout.md):
    one <Page> per workbook page, <LayoutElement> per leaf. Hex's column
    start/end are on a 0-120 scale; Sigma's grid is 24 columns (1-25 lines).
    Rows stack top-to-bottom per Hex row band; a band's height is its
    tallest element's row span. This is a first-pass proportional mapping —
    verify against a readback + PNG export (refs/layout-visual-qa.md) before
    treating it as final, same as every sibling skill's layout gate."""
    lines = [f'<Page type="grid" gridTemplateColumns="repeat({_SIGMA_GRID_WIDTH}, 1fr)" '
             f'gridTemplateRows="auto" id="{page_id}">']
    row_cursor = 1
    for row in tab["rows"]:
        band_span = 0
        col_lines = []
        for col in row["columns"]:
            cell_ids = [cid for cid in col["cell_ids"] if cid in elements_by_cell]
            if not cell_ids:
                continue
            start = round(col["start"] / _HEX_GRID_WIDTH * _SIGMA_GRID_WIDTH) + 1
            end = round(col["end"] / _HEX_GRID_WIDTH * _SIGMA_GRID_WIDTH) + 1
            # A Hex column can stack multiple cells; split its row range evenly.
            heights = [_row_span(None) for _ in cell_ids]  # heights filled in by caller if known
            sub_cursor = row_cursor
            for cid, span in zip(cell_ids, heights):
                el_id = elements_by_cell[cid]
                col_lines.append(
                    f'  <LayoutElement elementId="{el_id}" gridColumn="{start} / {end}" '
                    f'gridRow="{sub_cursor} / {sub_cursor + span}"/>'
                )
                sub_cursor += span
            band_span = max(band_span, sub_cursor - row_cursor)
        lines.extend(col_lines)
        row_cursor += band_span or _DEFAULT_ROW_SPAN
    lines.append("</Page>")
    return "\n".join(lines)


def build_workbook(doc: dict, dm_id: str, dm_element_id: str,
                    columns_by_variable: dict, wb_name: str, folder_id: str | None = None) -> dict:
    cells, cell_warnings = hex_yaml.parse_cells(doc)
    warnings = list(cell_warnings)
    stats = {"metric_cells": 0, "explore_cells": 0, "elements": 0}

    elements = []
    elements_by_cell: dict[str, str] = {}
    for cell in cells:
        el = None
        if cell["kind"] == "metric":
            el = build_metric_element(cell, dm_id, dm_element_id, columns_by_variable, warnings)
            if el:
                stats["metric_cells"] += 1
        elif cell["kind"] == "explore":
            el = build_explore_element(cell, dm_id, dm_element_id, columns_by_variable, warnings)
            if el:
                stats["explore_cells"] += 1
        if el:
            elements_by_cell[el.pop("_hex_cell_id")] = el["id"]
            elements.append(el)
            stats["elements"] += 1

    page_id = sigma_ids.sigma_short_id()
    tabs = hex_yaml.parse_app_layout(doc)
    layout_xml = build_layout_xml(page_id, tabs[0], elements_by_cell) if tabs else None

    page = {"id": page_id, "name": tabs[0]["name"] if tabs else "Page 1", "elements": elements}

    spec = {"name": wb_name, "schemaVersion": 1, "pages": [page]}
    if layout_xml:
        # `layout` is a TOP-LEVEL spec field (sibling to `pages`), not nested
        # inside the page object — live-verified 2026-07-30: nesting it under
        # the page is silently ignored (no error), and Sigma falls back to its
        # own auto-arrange (a single stacked column), exactly matching the
        # doc's "omit layout" behavior. The XML itself still wraps each page's
        # content in its own <Page id="..."> tag.
        spec["layout"] = layout_xml
    if folder_id:
        spec["folderId"] = folder_id
    return {"workbook": spec, "warnings": warnings, "stats": stats}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project", help="path to a .hex.yaml export")
    ap.add_argument("--dm-id", required=True, help="Sigma dataModelId (server-assigned, from "
                     "post-and-readback.rb's dm-map.json — a placeholder here will 400 at POST)")
    ap.add_argument("--dm-element-id", required=True, help="the DM's native-SQL element id "
                     "(server-assigned after readback)")
    ap.add_argument("--columns-map", required=True, help="dm.json's columns_by_variable, or the "
                     "equivalent server-assigned map from readback")
    ap.add_argument("--name", default=None)
    ap.add_argument("--folder", default=None, help="Sigma folderId to land the workbook in")
    args = ap.parse_args()

    doc = hex_yaml.load_project(args.project)
    with open(args.columns_map, encoding="utf-8") as fh:
        columns_by_variable = json.load(fh)

    wb_name = args.name or f"{hex_yaml.project_title(doc)}"
    result = build_workbook(doc, args.dm_id, args.dm_element_id, columns_by_variable, wb_name, args.folder)

    for w in result["warnings"]:
        print(f"WARN: {w}", file=sys.stderr)
    print(f"stats: {result['stats']}", file=sys.stderr)

    json.dump({"workbook": result["workbook"], "warnings": result["warnings"], "stats": result["stats"]},
              sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
