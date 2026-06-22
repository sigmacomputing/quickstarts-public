#!/usr/bin/env python3
"""
resolve_ae_winners.py — pin MicroStrategy Analytical-Engine representative rows.

Why: when an attribute's key form is non-unique in its lookup table (here:
Month.key = MONTH_NUMBER while DATE_DIM carries multiple MONTH_NAME spellings
and repeats month numbers across years), MicroStrategy's Analytical Engine
collapses the per-(parent, key) SQL result to ONE arbitrary-but-stable
representative row per key and cross-tabs it across the parent attribute.
The representative is a hash artifact of the engine — it cannot be derived
from the model bundle. This script pins it empirically:

  1. Re-execute each affected report via the MicroStrategy REST API.
  2. Compute the clean per-(parents, key) aggregates from the warehouse
     (same SQL MicroStrategy generated) via a temporary Sigma workbook.
  3. Match each key's MSTR-reported label+values to the unique clean row.
  4. Emit ae_winners.json for convert.py.

A report is affected when one of its attribute units has a DESC form
(label column distinct from the grouping key). Reports without such
attributes are skipped (their grids are clean).

Usage: python3 resolve_ae_winners.py --connection-id <uuid> --database CSA \
          [--bundle bundle.json] [--folder-id <uuid>] [--out ae_winners.json]
"""
import argparse
import csv
import io
import json
import time

import mstr
from convert import Bundle, friendly
from verify_parity import api, export_element


def run_mstr_grid(s, report_id):
    """Execute a report, return list of (keys_tuple, values_list)."""
    inst = s.post(f"/v2/reports/{report_id}/instances?limit=500", {})
    d, data = inst["definition"], inst["data"]
    rowsets = d["grid"]["rows"]
    attr_elems = []
    for unit in rowsets:
        attr_elems.append([
            e.get("formValues", [None])[0] if e.get("formValues") else e.get("name")
            for e in unit["elements"]])
    out = []
    for i, h in enumerate(data["headers"]["rows"]):
        keys = tuple(attr_elems[j][idx] for j, idx in enumerate(h))
        out.append((keys, data["metricValues"]["raw"][i]))
    return out


def clean_groups_via_sigma(b, args, report, quirk_aid, parent_aids):
    """Run the clean per-(parents, key) aggregation on the warehouse through a
    temporary Sigma workbook (sql element) and return the rows."""
    sql = b.build_clean_group_sql(args.database, report)
    spec = {
        "name": "zz-ae-resolver-probe",
        "folderId": args.folder_id,
        "schemaVersion": 1,
        "pages": [{"id": "p1", "name": "P", "elements": [{
            "id": "t1", "kind": "table", "name": "Probe",
            "source": {"kind": "sql", "connectionId": args.connection_id,
                       "statement": sql},
            "columns": [
                {"id": f"c{i}", "name": alias,
                 "formula": f"[Custom SQL/{alias}]"}
                for i, alias in enumerate(b.clean_group_aliases(report))
            ],
        }]}],
    }
    st, out = api("POST", "/v2/workbooks/spec", spec)
    if st >= 300:
        raise SystemExit(f"probe workbook POST failed {st}: {out[:500]}")
    wb_id = json.loads(out)["workbookId"]
    try:
        # element id may be remapped — read back
        import yaml
        st, out = api("GET", f"/v2/workbooks/{wb_id}/spec")
        eid = yaml.safe_load(out)["pages"][0]["elements"][0]["id"]
        csv_text = export_element(wb_id, eid)
    finally:
        api("DELETE", f"/v2/files/{wb_id}")
    return list(csv.DictReader(io.StringIO(csv_text)))


def close(a, b_, tol=1e-6):
    try:
        fa, fb = float(a), float(b_)
    except (TypeError, ValueError):
        return str(a) == str(b_)
    return abs(fa - fb) <= tol * max(abs(fb), 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default="bundle.json")
    ap.add_argument("--connection-id", required=True)
    ap.add_argument("--database", default="CSA")
    ap.add_argument("--folder-id", required=True)
    ap.add_argument("--out", default="ae_winners.json")
    args = ap.parse_args()

    b = Bundle(json.load(open(args.bundle)))
    s = mstr.Session()
    result = {}

    for rid, report in b.reports.items():
        rname = report["information"]["name"]
        units = report["dataSource"]["dataTemplate"]["units"]
        attr_units = [u for u in units if u.get("type") == "attribute"]
        quirk = None
        for u in attr_units:
            key_col, desc_col = b.attribute_unit_cols(u["id"])
            if desc_col:
                quirk = (u["id"], key_col, desc_col)
        if not quirk:
            continue  # clean report — no DESC-form attribute
        quirk_aid, qkey, qdesc = quirk
        parent_units = [u for u in attr_units if u["id"] != quirk_aid]
        parent_cols = [b.attribute_unit_cols(u["id"])[0] for u in parent_units]

        print(f"resolving AE representatives for {rname!r} "
              f"(quirk attr key={qkey} desc={qdesc})")
        grid = run_mstr_grid(s, rid)
        clean = clean_groups_via_sigma(b, args, report,
                                       quirk_aid, [u["id"] for u in parent_units])

        qkey_f, qdesc_f = friendly(qkey), friendly(qdesc)
        parent_f = [friendly(c) for c in parent_cols]
        metric_names = [el["name"] for u in units if u.get("type") == "metrics"
                        for el in u["elements"]]

        # MSTR grid: label + values per quirk element (identical across parents)
        per_label = {}
        for keys, vals in grid:
            label = keys[-1]  # quirk attr is rendered by its DESC form
            per_label.setdefault(label, vals)

        winners = []
        for label, vals in per_label.items():
            cands = [r for r in clean
                     if r[qdesc_f] == label
                     and all(close(r[m], v) for m, v in zip(metric_names, vals))]
            keys_seen = {tuple(r[p] for p in parent_f) +
                         (r[qkey_f],) for r in cands}
            if len(keys_seen) != 1:
                raise SystemExit(
                    f"{rname}: could not uniquely match label {label!r} "
                    f"{vals} -> {len(keys_seen)} candidates")
            r = cands[0]
            w = {qkey_f: r[qkey_f]}
            for p in parent_f:
                w[p] = r[p]
            winners.append(w)
            print(f"  {label!r:14} -> {w}")

        result[rname] = {
            "quirkKeyCol": qkey, "quirkDescCol": qdesc,
            "parentKeyCols": parent_cols,
            "winners": winners,
        }

    json.dump(result, open(args.out, "w"), indent=1)
    print(f"wrote {args.out} ({len(result)} report(s))")


if __name__ == "__main__":
    main()
