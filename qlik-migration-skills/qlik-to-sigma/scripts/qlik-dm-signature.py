#!/usr/bin/env python3
"""qlik-dm-signature.py — build a DM-reuse signature from the Qlik converter input.

Feeds scripts/vendor/find-or-pick-dm.rb (Phase 2.5) so the converter REUSES an
existing Sigma data model that already covers the same warehouse tables instead
of creating a 4th near-identical one. Mirrors powerbi-to-sigma's
pbi-dm-signature.py. Emits the signature shape find-or-pick-dm expects:

  { "tableau_workbook": "<app name>",            # label only
    "warehouse_tables":   ["DB.SCHEMA.TABLE", ...],
    "referenced_columns": ["COL", ...],
    "measures":           [{"col": "COL", "derivation": "Sum|CountDistinct|..."}] }

Input = the Phase-1 converter-input JSON ({appName, tables[{name, fields[{name}]}],
masterMeasures[{title, qDef}]} — see refs/example-converter-input.json). Qlik table
names are bare (the load script hides the warehouse FQN), so pass --database/--schema
to qualify them — same values you hand convert_qlik_to_sigma. Measures are parsed
from each qDef's first aggregation (set-analysis modifiers `{<...>}` are stripped —
they don't change which column/derivation the measure hangs on). Pure (no network).

Usage: python3 scripts/qlik-dm-signature.py --model /tmp/qlik/model.json \
         [--database CSA --schema TJ] --out /tmp/qlik/dm-signature.json
"""
import argparse, json, re, sys

AGG = {"SUM": "Sum", "AVG": "Avg", "MIN": "Min", "MAX": "Max",
       "COUNT": "Count", "MEDIAN": "Median"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Phase-1 converter-input JSON")
    ap.add_argument("--database"); ap.add_argument("--schema")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    model = json.load(open(a.model))

    tables, cols, measures = [], [], []
    for t in model.get("tables", []):
        name = str(t.get("name", "")).upper()
        if not name:
            continue
        fqn = ".".join(p for p in [a.database, a.schema, name] if p).upper()
        tables.append(fqn)
        for f in t.get("fields", []):
            fn = f.get("name")
            if fn:
                cols.append(str(fn).upper())

    for m in model.get("masterMeasures", []):
        qdef = str(m.get("qDef", ""))
        expr = re.sub(r"\{<[^}]*>\}|\{1\}", "", qdef)  # strip set analysis
        mm = re.search(r"\b(" + "|".join(AGG) + r")\s*\(\s*(DISTINCT\s+)?([A-Za-z_][\w .]*?)\s*[),]",
                       expr, re.I)
        if mm:
            deriv = "CountDistinct" if (mm.group(2) and mm.group(1).upper() == "COUNT") \
                    else AGG[mm.group(1).upper()]
            measures.append({"col": mm.group(3).strip().upper(), "derivation": deriv})
        else:
            measures.append({"col": m.get("title", ""), "derivation": None})

    sig = {"tableau_workbook": model.get("appName") or "Qlik app",
           "warehouse_tables": sorted(set(tables)),
           "referenced_columns": sorted(set(cols)),
           "measures": measures}
    json.dump(sig, open(a.out, "w"), indent=2)
    print(f"[qlik-dm-signature] {len(sig['warehouse_tables'])} table(s), "
          f"{len(sig['referenced_columns'])} col(s), {len(measures)} measure(s) -> {a.out}",
          file=sys.stderr)

if __name__ == "__main__":
    main()
