#!/usr/bin/env python3
"""Discover a ThoughtSpot object's structure for migration planning.

Usage:
  python3 ts_discover.py                       # list models + liveboards
  python3 ts_discover.py <id> [LIVEBOARD|LOGICAL_TABLE]   # summarize one object

For a LIVEBOARD: prints each visualization's chart type, search query, and the
model it reads. For a model (LOGICAL_TABLE): prints tables, joins, formulas,
and column counts — i.e. what convert_thoughtspot_to_sigma will consume.
Env: TS_HOST, TS_TOKEN.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml, ts_lib

def summarize_liveboard(edoc):
    lb = yaml.safe_load(edoc)["liveboard"]
    print(f"Liveboard: {lb.get('name')}")
    models = set()
    types = {}
    for v in lb.get("visualizations", []):
        a = v.get("answer")
        if not a:
            print(f"  - {v.get('id')}: (note/header tile)"); continue
        ct = (a.get("chart") or {}).get("type") or a.get("display_mode", "?")
        types[ct] = types.get(ct, 0) + 1
        for t in a.get("tables", []):
            models.add(t.get("name"))
        print(f"  - {a.get('name'):32s} [{ct}]  q={a.get('search_query','')!r}")
    print(f"  chart types: {types}")
    print(f"  reads models: {sorted(models)}")

def summarize_model(edoc):
    m = yaml.safe_load(edoc)
    root = m.get("model") or m.get("worksheet") or m
    print(f"Model: {root.get('name')}")
    mts = root.get("model_tables") or root.get("tables") or []
    joins = sum(len(t.get("joins", [])) for t in mts) or len(root.get("joins", []))
    print(f"  tables: {len(mts)}  joins: {joins}  formulas: {len(root.get('formulas', []))}  columns: {len(root.get('columns', root.get('worksheet_columns', [])))}")
    for t in mts:
        print(f"    - {t.get('name')}  (joins: {len(t.get('joins', []))})")

def main():
    if len(sys.argv) < 2:
        print("=== Models (worksheets) ===")
        for x in ts_lib.search("LOGICAL_TABLE"):
            if x.get("metadata_header", {}).get("type") in ("WORKSHEET", "MODEL"):
                print(f"  {x['metadata_id']}  {x['metadata_name']}")
        print("=== Liveboards ===")
        for x in ts_lib.search("LIVEBOARD"):
            print(f"  {x['metadata_id']}  {x['metadata_name']}")
        return
    ident = sys.argv[1]
    mtype = sys.argv[2] if len(sys.argv) > 2 else "LIVEBOARD"
    edoc, err = ts_lib.export_tml(ident, mtype)
    if err:
        print("export error:", err); return
    (summarize_liveboard if mtype == "LIVEBOARD" else summarize_model)(edoc)

if __name__ == "__main__":
    main()
