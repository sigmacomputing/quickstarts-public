#!/usr/bin/env python3
"""lookml-dm-signature.py — build a DM-reuse signature from parsed LookML.

Feeds scripts/find-or-pick-dm.rb (Phase 2.5) so the converter REUSES an existing
Sigma data model that already covers the same warehouse tables instead of
creating a 4th near-identical one. Mirrors powerbi-to-sigma's
pbi-dm-signature.py. Emits the signature shape find-or-pick-dm expects:

  { "tableau_workbook": "<model/explore label>",   # label only
    "warehouse_tables":   ["DB.SCHEMA.TABLE", ...],
    "referenced_columns": ["field_name", ...],
    "measures":           [{"col": "COL", "derivation": "Sum|CountDistinct|..."}] }

Input = the LookML project dir (the same files you feed convert_lookml_to_sigma /
convert_dm.mjs): every `*.view.lkml` under --lookml-dir (recursively, so a views/
subdir works). Per view it lifts `sql_table_name` (the warehouse FQN) and every
dimension / dimension_group / measure name. Field names like `net_revenue` compare
clean against Sigma display names ("Net Revenue") because find-or-pick-dm
normalizes both sides to alnum-uppercase. This is a thin regex lift, NOT a LookML
parser — good enough for a reuse signature, not for conversion. Pure (no network).

Usage: python3 scripts/lookml-dm-signature.py --lookml-dir /path/to/lookml \
         [--label "Orders"] --out /tmp/looker/dm-signature.json
"""
import argparse, glob, json, os, re, sys

AGG = {"sum": "Sum", "average": "Avg", "avg": "Avg", "min": "Min", "max": "Max",
       "count": "Count", "count_distinct": "CountDistinct", "median": "Median"}

FIELD_RE = re.compile(r"^\s*(dimension|dimension_group|measure)\s*:\s*([A-Za-z_]\w*)\s*\{", re.M)
TABLE_RE = re.compile(r"^\s*sql_table_name\s*:\s*([^;]+?)\s*;;", re.M)
VIEW_RE  = re.compile(r"^\s*view\s*:\s*\+?([A-Za-z_]\w*)\s*\{", re.M)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookml-dir", required=True, help="dir containing *.view.lkml (searched recursively)")
    ap.add_argument("--label", help="signature label (defaults to the dir name)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.lookml_dir, "**", "*.view.lkml"), recursive=True))
    if not files:
        sys.exit(f"[lookml-dm-signature] no *.view.lkml under {a.lookml_dir}")

    tables, cols, measures = [], [], []
    for path in files:
        text = open(path).read()
        for t in TABLE_RE.findall(text):
            tables.append(t.strip().strip('"').upper())
        # walk fields; for measures grab the agg type + sql column inside the block
        for m in FIELD_RE.finditer(text):
            kind, name = m.group(1), m.group(2)
            cols.append(name.upper())
            if kind != "measure":
                continue
            block = text[m.end(): text.find("}", m.end()) + 1]
            tm = re.search(r"\btype\s*:\s*(\w+)", block)
            deriv = AGG.get(tm.group(1).lower()) if tm else None
            sm = re.search(r'\bsql\s*:\s*\$\{TABLE\}\.\"?(\w+)\"?', block)
            col = sm.group(1).upper() if sm else name.upper()
            measures.append({"col": col, "derivation": deriv})

    sig = {"tableau_workbook": a.label or os.path.basename(os.path.abspath(a.lookml_dir)),
           "warehouse_tables": sorted(set(tables)),
           "referenced_columns": sorted(set(cols)),
           "measures": measures}
    json.dump(sig, open(a.out, "w"), indent=2)
    print(f"[lookml-dm-signature] {len(files)} view file(s): {len(sig['warehouse_tables'])} table(s), "
          f"{len(sig['referenced_columns'])} col(s), {len(measures)} measure(s) -> {a.out}",
          file=sys.stderr)

if __name__ == "__main__":
    main()
