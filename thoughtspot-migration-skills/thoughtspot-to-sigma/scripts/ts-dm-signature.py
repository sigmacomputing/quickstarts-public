#!/usr/bin/env python3
"""ts-dm-signature.py — build a DM-reuse signature from a ThoughtSpot model TML.

Feeds scripts/find-or-pick-dm.rb (Phase 2.5) so the migration REUSES an existing
Sigma data model that already covers the same warehouse tables instead of
creating a 4th near-identical one. Mirrors powerbi-to-sigma's
pbi-dm-signature.py. Emits the signature shape find-or-pick-dm expects:

  { "tableau_workbook": "<model name>",           # label only
    "warehouse_tables":   ["DB.SCHEMA.TABLE", ...],
    "referenced_columns": ["Col", ...],
    "measures":           [{"col": "Col", "derivation": "Sum|CountDistinct|..."}] }

Input = the exported model TML (the same `model:`-format YAML you feed
convert_thoughtspot_to_sigma — worksheet format works too). `model_tables[].fqn`
is a ThoughtSpot guid, NOT a warehouse path, so pass --database/--schema (the
same TS_DB/TS_SCHEMA you export for migrate.py) to qualify the table names.
Columns come from `columns[].name`; measures from columns whose
`properties.column_type == MEASURE` (derivation from `properties.aggregation`,
default Sum; col = the physical column behind `column_id`). Pure (no network).

Usage: python3 scripts/ts-dm-signature.py --tml model.tml \
         [--database CSA --schema TJ] --out dm-signature.json
"""
import argparse, json, sys

AGG = {"SUM": "Sum", "AVERAGE": "Avg", "MIN": "Min", "MAX": "Max",
       "COUNT": "Count", "COUNT_DISTINCT": "CountDistinct", "MEDIAN": "Median"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tml", required=True, help="model/worksheet TML (YAML)")
    ap.add_argument("--database"); ap.add_argument("--schema")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import yaml  # PyYAML; TML is YAML
    doc = yaml.safe_load(open(a.tml)) or {}
    model = doc.get("model") or doc.get("worksheet") or {}

    tables, cols, measures = [], [], []
    for t in (model.get("model_tables") or model.get("tables") or []):
        name = str(t.get("name", "")).upper()
        if not name:
            continue
        tables.append(".".join(p for p in [a.database, a.schema, name] if p).upper())

    for c in model.get("columns", []):
        name = c.get("name")
        if not name:
            continue
        cols.append(str(name))
        props = c.get("properties") or {}
        if str(props.get("column_type", "")).upper() == "MEASURE":
            # column_id is "TABLE::PHYSICAL_COL" (formulas: "formula_x")
            cid = str(c.get("column_id", ""))
            col = cid.split("::")[-1] if "::" in cid else str(name)
            deriv = AGG.get(str(props.get("aggregation", "SUM")).upper(), "Sum")
            measures.append({"col": col.upper(), "derivation": deriv})

    sig = {"tableau_workbook": model.get("name") or "ThoughtSpot model",
           "warehouse_tables": sorted(set(tables)),
           "referenced_columns": sorted(set(cols)),
           "measures": measures}
    json.dump(sig, open(a.out, "w"), indent=2)
    print(f"[ts-dm-signature] {len(sig['warehouse_tables'])} table(s), "
          f"{len(sig['referenced_columns'])} col(s), {len(measures)} measure(s) -> {a.out}",
          file=sys.stderr)

if __name__ == "__main__":
    main()
