#!/usr/bin/env python3
"""Convert a Hex project's SQL cells into a Sigma data-model spec.

Every Hex SQL cell is raw SQL with no query DSL (unlike Metabase's MBQL) —
so unlike metabase-to-sigma's dual-path decision (auto-remodel a "simple"
native SELECT into a structured Sigma table/join model, fall back to a
Custom SQL element for anything complex), a Hex SQL cell always takes the
"native SQL element" path: wrap the cell's raw `source` verbatim into a
Sigma `{kind:'table', source:{kind:'sql', statement}}` element — the exact
shape metabase-to-sigma's converter/metabase.ts (lines 860-885) uses for its
own native-SQL fallback, ported here since it's source-language-agnostic.

Column discovery: Hex's YAML export never lists a SQL cell's *output*
columns directly (there's no `result_metadata` equivalent) — but the cell's
own `tableDisplayConfig.columnProperties[]` enumerates every resolved
preview-grid column, which is the same information. Hex's column aliases are
already the human-authored display names (the demo SQL cell quotes
`"Visit ID"`, `"Category"`, etc.) — so unlike Metabase (whose raw aliases are
machine-generated snake_case that MUST be run through sigmaDisplayName()),
Hex column names are used verbatim as both the formula alias and the display
label. Running them through sigma_display_name() would be wrong here (it
would mangle "Brand ID" into "Brand Id").

Usage:
    python3 convert_dm.py <project.hex.yaml> --connection <SIGMA_CONNECTION_ID> \\
        [--name "Hex Demo"] > dm.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys

import hex_yaml
import sigma_ids

_QUOTED_IDENT = re.compile(r'"([^"]+)"')


def _select_clause_output_names(statement: str) -> set[str] | None:
    """Cross-check guard (live-verified 2026-07-30): Hex's cached
    tableDisplayConfig.columnProperties[] can include STALE entries left over
    from an earlier version of the SQL — e.g. a join-key column that appears
    only in a JOIN...ON clause, never in the SELECT list, but still lingers
    in the cell's preview-grid config. Posting a DM column for a name that
    isn't genuinely in the query's output 400s at POST ("dependency not
    found") since Sigma can't resolve [Custom SQL/<name>] against anything.

    Returns the set of quoted identifiers appearing in the SELECT clause
    (before the first top-level FROM), or None if no FROM was found (caller
    should skip the cross-check rather than risk dropping everything on a
    parse failure this heuristic doesn't handle)."""
    m = re.search(r"\bFROM\b", statement, re.IGNORECASE)
    if not m:
        return None
    select_clause = statement[:m.start()]
    return set(_QUOTED_IDENT.findall(select_clause))


def build_dm(doc: dict, connection_id: str, dm_name: str, folder_id: str | None = None) -> dict:
    """Returns {"dataModel": <spec>, "warnings": [...], "stats": {...},
    "columns_by_variable": {resultVariableName: {colName: clientColumnId}}} —
    the last map is CLIENT-SIDE only, for wiring the workbook spec before
    POST. Per family convention (C5 hard gate), the real element/column ids
    come from the POST + readback step (post-and-readback.rb) — never trust
    client-side ids past that point."""
    cells, warnings = hex_yaml.parse_cells(doc)
    sql_cells = [c for c in cells if c["kind"] == "sql"]

    elements = []
    order = []
    columns_by_variable: dict[str, dict[str, str]] = {}
    stats = {"sql_cells": len(sql_cells), "elements": 0, "columns": 0}

    for cell in sql_cells:
        statement = (cell["source"] or "").strip()
        if not statement:
            warnings.append(f"SQL cell '{cell['label'] or cell['cell_id']}' has an empty "
                             "source — skipped.")
            continue
        # Sigma wraps a custom-SQL element's statement as a subquery `( … )`;
        # a trailing `;` is a syntax error at POST (same fixup metabase-to-sigma
        # applies for the same reason).
        statement = statement.rstrip(";").rstrip()

        select_names = _select_clause_output_names(statement)
        candidate_columns = cell["columns"]
        if select_names is not None:
            stale = [c for c in candidate_columns if c not in select_names]
            if stale:
                warnings.append(
                    f"SQL cell '{cell['label'] or cell['cell_id']}': dropped "
                    f"{len(stale)} stale column(s) from Hex's cached preview-grid "
                    f"config that aren't in the SELECT clause's output (e.g. a "
                    f"join-key referenced only in JOIN...ON, not selected): "
                    f"{', '.join(stale)}."
                )
            candidate_columns = [c for c in candidate_columns if c in select_names]

        element_id = sigma_ids.sigma_short_id()
        col_ids: dict[str, str] = {}
        cols = []
        for col_name in candidate_columns:
            col_id = sigma_ids.sigma_short_id()
            cols.append({
                "id": col_id,
                "name": col_name,
                # [Custom SQL/ALIAS] — live-verified 2026-07-30: a bare [ALIAS] ref
                # here self-references the column's OWN name and compiles to a
                # "Ref Cycle" error (confirmed via GET .../columns). "Custom SQL" is
                # Sigma's fixed sentinel for "the raw output of this element's own
                # SQL statement" — not a cross-element name — matching Metabase's
                # confirmed finding for the same native-SQL-element shape.
                "formula": f"[Custom SQL/{col_name}]",
            })
            col_ids[col_name] = col_id

        element = {
            # No `name` field — Sigma derives the sql element's own identifier
            # ("Custom SQL"), same as every sibling skill's native-SQL element.
            "id": element_id,
            "kind": "table",
            "source": {"kind": "sql", "connectionId": connection_id, "statement": statement},
            "columns": cols,
            "order": [c["id"] for c in cols],
        }
        elements.append(element)
        order.append(element_id)
        columns_by_variable[cell["result_variable"]] = col_ids
        stats["elements"] += 1
        stats["columns"] += len(cols)

    dm = {
        "name": dm_name,
        "schemaVersion": 1,
        "pages": [{"id": sigma_ids.sigma_short_id(), "name": "Page 1", "elements": elements}],
    }
    if folder_id:
        dm["folderId"] = folder_id

    return {
        "dataModel": dm,
        "warnings": warnings,
        "stats": stats,
        "columns_by_variable": columns_by_variable,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project", help="path to a .hex.yaml export")
    ap.add_argument("--connection", required=True, help="Sigma warehouse connectionId "
                     "(full UUID — a short prefix fails with 'Source not found')")
    ap.add_argument("--name", default=None, help="data model name (default: '<project title> DM')")
    ap.add_argument("--folder", default=None, help="Sigma folderId to land the data model in")
    args = ap.parse_args()

    doc = hex_yaml.load_project(args.project)
    dm_name = args.name or f"{hex_yaml.project_title(doc)} DM"
    result = build_dm(doc, args.connection, dm_name, args.folder)

    for w in result["warnings"]:
        print(f"WARN: {w}", file=sys.stderr)
    print(f"stats: {result['stats']}", file=sys.stderr)

    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
