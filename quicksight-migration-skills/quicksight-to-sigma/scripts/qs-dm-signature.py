#!/usr/bin/env python3
"""qs-dm-signature.py — build a DM-reuse signature from QuickSight dataset JSON.

Feeds scripts/find-or-pick-dm.rb (Phase 3.5) so the migration REUSES an existing
Sigma data model that already covers the same warehouse tables instead of
creating a 4th near-identical one. Mirrors powerbi-to-sigma's
pbi-dm-signature.py. Emits the signature shape find-or-pick-dm expects:

  { "tableau_workbook": "<dataset name(s)>",      # label only
    "warehouse_tables":   ["DB.SCHEMA.TABLE", ...],
    "referenced_columns": ["COL", ...],
    "measures":           [] }                     # QS aggs live per-visual; omitted

Input = the Phase-2 discovery output: either --discover-dir (reads datasets/*.json)
or explicit dataset JSON paths (DescribeDataSet responses — fixtures/ shape).
Tables: RelationalTable Catalog.Schema.Name; CustomSql tables are lifted from the
SQL's FROM/JOIN clauses (3-part names only — else the element is CUSTOM_SQL, the
same sentinel the picker uses). Columns: physical InputColumns/Columns plus
CreateColumnsOperation calc columns. Pure (no network).

Usage: python3 scripts/qs-dm-signature.py --discover-dir ~/quicksight-migration/<name> \
         --out dm-signature.json
       python3 scripts/qs-dm-signature.py fixtures/dataset-orders-enriched.json --out sig.json
"""
import argparse, glob, json, os, re, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("datasets", nargs="*", help="dataset JSON file(s) (DescribeDataSet shape)")
    ap.add_argument("--discover-dir", help="Phase-2 discovery dir (reads datasets/*.json)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    paths = list(a.datasets)
    if a.discover_dir:
        paths += sorted(glob.glob(os.path.join(a.discover_dir, "datasets", "*.json")))
    if not paths:
        sys.exit("[qs-dm-signature] no dataset JSON given (positional or --discover-dir)")

    names, tables, cols = [], [], []
    for path in paths:
        doc = json.load(open(path))
        ds = doc.get("DataSet", doc)
        if ds.get("Name"):
            names.append(ds["Name"])
        for pt in (ds.get("PhysicalTableMap") or {}).values():
            rel = pt.get("RelationalTable")
            if rel:
                fqn = ".".join(p for p in [rel.get("Catalog"), rel.get("Schema"), rel.get("Name")] if p)
                tables.append(fqn.upper())
                cols += [c["Name"].upper() for c in rel.get("InputColumns", []) if c.get("Name")]
            sql = pt.get("CustomSql")
            if sql:
                found = re.findall(r'\b(?:from|join)\s+"?(\w+)"?\."?(\w+)"?\."?(\w+)"?',
                                   sql.get("SqlQuery", ""), re.I)
                tables += [".".join(g).upper() for g in found] or ["CUSTOM_SQL"]
                cols += [c["Name"].upper() for c in sql.get("Columns", []) if c.get("Name")]
        for lt in (ds.get("LogicalTableMap") or {}).values():
            for tr in lt.get("DataTransforms", []):
                for cc in tr.get("CreateColumnsOperation", {}).get("Columns", []):
                    if cc.get("ColumnName"):
                        cols.append(cc["ColumnName"].upper())

    sig = {"tableau_workbook": ", ".join(names) or "QuickSight dataset",
           "warehouse_tables": sorted(set(tables)),
           "referenced_columns": sorted(set(cols)),
           "measures": []}
    json.dump(sig, open(a.out, "w"), indent=2)
    print(f"[qs-dm-signature] {len(paths)} dataset(s): {len(sig['warehouse_tables'])} table(s), "
          f"{len(sig['referenced_columns'])} col(s) -> {a.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
