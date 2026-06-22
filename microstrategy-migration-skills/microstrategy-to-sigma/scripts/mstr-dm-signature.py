#!/usr/bin/env python3
"""mstr-dm-signature.py — build a DM-reuse signature from the MicroStrategy converter output.

Feeds scripts/find-or-pick-dm.rb (Phase 2.6) so the migration REUSES an existing
Sigma data model that already covers the same warehouse tables instead of
creating a near-identical one. Structurally mirrors cognos-dm-signature.py /
pbi-dm-signature.py (the Sigma DM JSON shape is the same across converters).
Emits the signature shape find-or-pick-dm expects:

  { "tableau_workbook": "<dossier/project name>",  # label only
    "warehouse_tables":   ["DB.SCHEMA.TABLE", ...],
    "referenced_columns": ["Col", ...],
    "measures":           [{"col": "Col", "derivation": "Sum|CountDistinct|..."}] }

Input = the Phase-2 converter output `sigma_dm_spec.json` (the Sigma data-model
JSON, BEFORE it is POSTed). Walks every element: `source.path` (warehouse-table)
-> tables, column `name`/formula tail -> columns, element `metrics` -> measures.
Custom-SQL elements surface as a CUSTOM_SQL sentinel, same as the picker uses for
candidate DMs. Pure (no network).

Usage: python3 scripts/mstr-dm-signature.py --dm-spec sigma_dm_spec.json --out dm-signature.json
"""
import argparse, json, re, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dm-spec", required=True, help="Phase-2 converter output (sigma_dm_spec.json)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    spec = json.load(open(a.dm_spec))

    elements = spec.get("elements") or [e for p in spec.get("pages", []) for e in p.get("elements", [])]
    tables, cols, measures = [], [], []
    for el in elements:
        src = el.get("source") or {}
        kind = src.get("kind")
        if kind in ("warehouse-table", "table"):
            path = src.get("path")
            fqn = ".".join(path) if isinstance(path, list) else \
                  (path or ".".join(p for p in [src.get("database"), src.get("schema"), src.get("name")] if p))
            if fqn:
                tables.append(str(fqn).upper())
        elif kind == "sql":
            tables.append("CUSTOM_SQL")
        for c in el.get("columns", []):
            name = c.get("name")
            if not name:
                m = re.search(r"\[.*?([^/\]]+)\]", str(c.get("formula", "")))
                name = m.group(1) if m else None
            if name:
                cols.append(name)
        for m in el.get("metrics", []):
            measures.append({"col": m.get("name", ""),
                             "derivation": m.get("aggregation") or m.get("derivation")})

    sig = {"tableau_workbook": spec.get("name") or "MicroStrategy dossier",
           "warehouse_tables": sorted(set(tables)),
           "referenced_columns": sorted(set(cols)),
           "measures": measures}
    json.dump(sig, open(a.out, "w"), indent=2)
    print(f"[mstr-dm-signature] {len(elements)} element(s): {len(sig['warehouse_tables'])} table(s), "
          f"{len(sig['referenced_columns'])} col(s), {len(measures)} measure(s) -> {a.out}",
          file=sys.stderr)

if __name__ == "__main__":
    main()
