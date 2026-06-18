#!/usr/bin/env python3
"""Build 'Orders Deep Dive' UDD on csa_thelook via the Looker API — advanced viz:
area, pivot table, table-calcs (running total + % of total), scatter, donut, text tile.
Exercises the harder dashboard surface for the Looker->Sigma converter.
"""
import json, sys
import looker_api as L

MODEL, EXPLORE = "csa_thelook", "order_fact"
FILTERS = [("Order Date", "order_date.order_date"), ("Region", "customer_dim.region")]
LISTEN = [{"dashboard_filter_name": n, "field": f} for n, f in FILTERS]

# table calcs for the running-total tile
DYN = json.dumps([
    {"table_calculation": "running_revenue", "label": "Running Net Revenue",
     "expression": "running_total(${order_fact.total_net_revenue})",
     "value_format_name": "usd", "_kind_hint": "measure", "_type_hint": "number"},
    {"table_calculation": "pct_of_total", "label": "% of Total",
     "expression": "${order_fact.total_net_revenue}/sum(${order_fact.total_net_revenue})",
     "value_format_name": "percent_1", "_kind_hint": "measure", "_type_hint": "number"},
])

# (title, vis, fields, pivots, sorts, limit, dynamic_fields, vis_extra, row,col,w,h)
TILES = [
    ("Revenue & Profit Trend", "looker_area",
     ["order_date.order_month", "order_fact.total_net_revenue", "order_fact.total_net_profit"],
     [], ["order_date.order_month"], None, None, {}, 3, 0, 12, 8),
    ("Net Revenue by Region x Channel", "looker_grid",
     ["customer_dim.region", "order_fact.total_net_revenue"],
     ["order_fact.order_channel"], ["customer_dim.region"], None, None, {}, 3, 12, 12, 8),
    ("Net Revenue Running Total by Month", "looker_grid",
     ["order_date.order_month", "order_fact.total_net_revenue"],
     [], ["order_date.order_month"], None, DYN, {}, 11, 0, 12, 8),
    ("Price vs Volume by Category", "looker_scatter",
     ["product_dim.category", "order_fact.avg_unit_price", "order_fact.total_quantity"],
     [], ["order_fact.total_quantity desc"], None, None, {}, 11, 12, 6, 8),
    ("Net Revenue by Loyalty Tier", "looker_pie",
     ["customer_dim.loyalty_tier", "order_fact.total_net_revenue"],
     [], ["order_fact.total_net_revenue desc"], None, None, {"inner_radius": 50}, 11, 18, 6, 8),
]


def main(folder_id):
    code, d = L.call("POST", "/dashboards", {"title": "Orders Deep Dive", "folder_id": str(folder_id),
                     "description": "Advanced viz coverage: area, pivot, table-calcs, scatter, donut, text."})
    did = d["id"]; print("dashboard id=", did)

    for i, (name, field) in enumerate(FILTERS):
        L.call("POST", "/dashboard_filters", {"dashboard_id": did, "name": name, "title": name,
            "type": "field_filter", "dimension": field, "model": MODEL, "explore": EXPLORE,
            "allow_multiple_values": True, "row": i, "default_value": ""})

    eids = []
    # text/markdown tile
    code, te = L.call("POST", "/dashboard_elements", {"dashboard_id": did, "type": "text",
        "title_text": "Orders Deep Dive",
        "body_text": "## Orders Deep Dive\nAdvanced analytics — trend, pivot, running totals, price/volume, mix."})
    eids.append(("text", te["id"]))

    for (title, vis, fields, pivots, sorts, limit, dyn, vextra, *_pos) in TILES:
        q = {"model": MODEL, "view": EXPLORE, "fields": fields, "vis_config": dict({"type": vis}, **vextra)}
        if pivots: q["pivots"] = pivots
        if sorts: q["sorts"] = sorts
        if limit: q["limit"] = str(limit)
        if dyn: q["dynamic_fields"] = dyn
        code, qr = L.call("POST", "/queries", q)
        if code >= 300: print("query FAIL", title, code, qr); sys.exit(1)
        code, e = L.call("POST", "/dashboard_elements",
            {"dashboard_id": did, "type": "vis", "query_id": qr["id"], "title": title})
        if code >= 300: print("element FAIL", title, code, e); sys.exit(1)
        eid = e["id"]
        L.call("PATCH", f"/dashboard_elements/{eid}", {"result_maker": {"query_id": qr["id"],
            "vis_config": dict({"type": vis}, **vextra),
            "filterables": [{"model": MODEL, "view": EXPLORE, "name": "", "listen": LISTEN}]}})
        eids.append((title, eid))
        print(f"  {title}: {eid}")

    # layout
    code, d2 = L.call("GET", f"/dashboards/{did}")
    lay = next((l for l in d2["dashboard_layouts"] if l.get("active")), d2["dashboard_layouts"][0])
    L.call("PATCH", f"/dashboard_layouts/{lay['id']}", {"active": True})
    title_to_pos = {t[0]: (t[8], t[9], t[10], t[11]) for t in TILES}
    title_to_pos["Orders Deep Dive"] = (0, 0, 24, 3)  # text tile top
    eltitle = {e["id"]: (e.get("title") or e.get("title_text")) for e in d2["dashboard_elements"]}
    for c in lay["dashboard_layout_components"]:
        t = eltitle.get(c["dashboard_element_id"])
        if t in title_to_pos:
            r, col, w, h = title_to_pos[t]
            L.call("PATCH", f"/dashboard_layout_components/{c['id']}", {"row": r, "column": col, "width": w, "height": h})
    print("DONE dashboard", did)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "15")
