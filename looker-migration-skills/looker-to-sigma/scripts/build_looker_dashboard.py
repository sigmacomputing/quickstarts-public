#!/usr/bin/env python3
"""Build the 'Orders Overview' UDD on csa_thelook via the Looker API:
KPIs + trend + region/category/channel breakdowns + top-products table,
with 3 dashboard filters wired to every tile via result_maker.filterables.listen.
"""
import json
import sys
import looker_api as L

MODEL, EXPLORE = "csa_thelook", "order_fact"
FILTERS = [
    ("Order Date", "order_date.order_date"),
    ("Region", "customer_dim.region"),
    ("Category", "product_dim.category"),
]
LISTEN = [{"dashboard_filter_name": n, "field": f} for n, f in FILTERS]

# (title, vis_type, fields, sorts, limit, row, col, width, height)
TILES = [
    ("Net Revenue",        "single_value", ["order_fact.total_net_revenue"],            None, None, 0, 0, 6, 3),
    ("Orders",             "single_value", ["order_fact.distinct_order_count"],         None, None, 0, 6, 6, 3),
    ("Avg Order Value",    "single_value", ["order_fact.average_order_value"],          None, None, 0, 12, 6, 3),
    ("Units Ordered",      "single_value", ["order_fact.total_quantity"],               None, None, 0, 18, 6, 3),
    ("Net Revenue by Month",    "looker_line",   ["order_date.order_month", "order_fact.total_net_revenue"], ["order_date.order_month"], None, 3, 0, 12, 8),
    ("Net Revenue by Region",   "looker_column", ["customer_dim.region", "order_fact.total_net_revenue"], ["order_fact.total_net_revenue desc"], None, 3, 12, 12, 8),
    ("Net Revenue by Category", "looker_bar",    ["product_dim.category", "order_fact.total_net_revenue"], ["order_fact.total_net_revenue desc"], None, 11, 0, 8, 8),
    ("Net Revenue by Channel",  "looker_pie",    ["order_fact.order_channel", "order_fact.total_net_revenue"], ["order_fact.total_net_revenue desc"], None, 11, 8, 8, 8),
    ("Top Products",            "looker_grid",   ["product_dim.product_name", "order_fact.total_net_revenue", "order_fact.total_quantity"], ["order_fact.total_net_revenue desc"], 10, 11, 16, 8, 8),
]


def main(folder_id):
    # 1. dashboard
    code, d = L.call("POST", "/dashboards", {"title": "Orders Overview", "folder_id": str(folder_id),
                     "description": "Executive orders overview migrated source (Looker UDD)."})
    if code >= 300:
        print("dashboard create FAILED", code, d); sys.exit(1)
    did = d["id"]
    print(f"dashboard id={did}")

    # 2. filters
    for i, (name, field) in enumerate(FILTERS):
        code, f = L.call("POST", "/dashboard_filters", {
            "dashboard_id": did, "name": name, "title": name, "type": "field_filter",
            "dimension": field, "model": MODEL, "explore": EXPLORE,
            "allow_multiple_values": True, "row": i, "default_value": ""})
        print(f"  filter {name}: {code}")

    # 3. queries + elements (with listen via result_maker)
    eid_by_idx = []
    for (title, vis, fields, sorts, limit, *_pos) in TILES:
        qbody = {"model": MODEL, "view": EXPLORE, "fields": fields}
        if sorts: qbody["sorts"] = sorts
        if limit: qbody["limit"] = str(limit)
        qbody["vis_config"] = {"type": vis}
        code, q = L.call("POST", "/queries", qbody)
        if code >= 300:
            print("  query FAILED", title, code, q); sys.exit(1)
        qid = q["id"]
        # create with query_id directly
        code, e = L.call("POST", "/dashboard_elements",
                         {"dashboard_id": did, "type": "vis", "query_id": qid, "title": title})
        if code >= 300:
            print("  element FAILED", title, code, e); sys.exit(1)
        eid = e["id"]
        # wire dashboard-filter listeners onto the element's result_maker
        code, e2 = L.call("PATCH", f"/dashboard_elements/{eid}",
                          {"result_maker": {"query_id": qid, "vis_config": {"type": vis},
                                            "filterables": [{"model": MODEL, "view": EXPLORE,
                                                             "name": "", "listen": LISTEN}]}})
        listen_ok = code < 300
        eid_by_idx.append(eid)
        print(f"  element {title}: id={eid} listen_wired={listen_ok}")

    # 4. layout + components
    code, lay = L.call("POST", "/dashboard_layouts", {"dashboard_id": did, "type": "newspaper", "active": True})
    lid = lay["id"]
    print(f"layout id={lid}")
    for eid, (title, vis, fields, sorts, limit, row, col, width, height) in zip(eid_by_idx, TILES):
        code, c = L.call("POST", "/dashboard_layout_components", {
            "dashboard_layout_id": lid, "dashboard_element_id": eid,
            "row": row, "column": col, "width": width, "height": height})
        if code >= 300:
            print("  layout comp FAILED", title, code, c)
    print(f"\nDONE. dashboard {did}")
    return did


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "15")
