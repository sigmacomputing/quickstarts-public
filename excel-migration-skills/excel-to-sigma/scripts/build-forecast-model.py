#!/usr/bin/env python3
"""
build-forecast-model.py — one-shot builder for an actuals + driver-grown + manual
planning model (the architecture in refs/forecast-recipes.md). Consumes a model-plan
JSON (drafted from xlsx-discover.py's model map + the intent answers) and emits:
  - a Sigma data model (GL actuals VALUES + assumptions + raw forecast spine)
  - a workbook (union[actuals, forecast] → KPIs, P&L pivot w/ Actual|Forecast cols,
    monthly summary, trend, GL detail, assumptions; editable rate+manual input tables
    when intent is editable/what-if)
  - paste-ready seed CSVs for the editable tables
  - a LOCAL parity check (when the plan carries `parityTargets`, fails the run if the
    plan's recomputed Revenue / Gross Profit / EBITDA / Net Income differ from them)

Default = dry-run (writes specs to --out-dir, default /tmp/fcst-build; runs parity, no API;
pending review issues are reported as DRAFT MODE and do not block). `--post` builds live and
keeps the strict source-bound `--review-dispositions` contract.

Intent (plan.intent):
  read-only          → forecast baked from default rates (no input tables)
  editable | what-if → rates + manual cells are editable input tables (Coalesce override)
"""
import argparse, sys, os, json, csv, urllib.request, urllib.parse, urllib.error
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
import workbook_wire  # noqa: E402
from lib.migration_gate import MigrationGateError, gate_plan_source  # noqa: E402

CUR = lambda p: {"kind": "number", "formatString": p["currencyFormat"]}
PCT = lambda p: {"kind": "number", "formatString": p.get("pctFormat", ".1%")}
DATEF = {"kind": "datetime", "formatString": "%b-%y"}
def q(s): return "'" + str(s).replace("'", "''") + "'"


def forecast_layout(editable, extra_model_ids=(), chart_ids=()):
    """Dense four-page layout: overview, detail, editable inputs, hidden plumbing.

    Source-chart ids sit beside the monthly trend (first) and then full width below it.
    """
    charts = [("monthlyTrend", 1, 25 if not chart_ids else 13, 10, 25)]
    if chart_ids:
        charts.append((chart_ids[0], 13, 25, 10, 25))
    for i, element_id in enumerate(chart_ids[1:]):
        charts.append((element_id, 1, 25, 25 + i * 15, 40 + i * 15))
    pivot_row = 25 + max(len(chart_ids) - 1, 0) * 15
    pages = [
        ("pnl", [
            ("pnlHeader", 1, 25, 1, 4),
            ("kpiRev", 1, 7, 4, 10),
            ("kpiEbitda", 7, 13, 4, 10),
            ("kpiNI", 13, 19, 4, 10),
            ("kpiGM", 19, 25, 4, 10),
            *charts,
            ("pnlPivot", 1, 25, pivot_row, pivot_row + 30),
        ]),
        ("detail", [("glTable", 1, 25, 1, 37)]),
        ("inputs", [
            ("assumpTable", 1, 25, 1, 13),
            *([("rateInput", 1, 25, 13, 29), ("manualInput", 1, 25, 29, 49)] if editable else []),
        ]),
        ("model", [
            ("actuals", 1, 25, 1, 13),
            ("spineWrap", 1, 25, 13, 25),
            ("forecast", 1, 25, 25, 37),
            ("pnlCombined", 1, 25, 37, 49),
            *[(element_id, 1, 25, 49+i*12, 61+i*12) for i, element_id in enumerate(extra_model_ids)],
        ]),
    ]
    blocks = []
    for page_id, placements in pages:
        lines = [
            f'<Page type="grid" gridTemplateColumns="repeat(24, 1fr)" '
            f'gridTemplateRows="auto" id="{page_id}">'
        ]
        for element_id, col_start, col_end, row_start, row_end in placements:
            lines.append(
                f'  <Element elementId="{element_id}" gridColumn="{col_start} / {col_end}" '
                f'gridRow="{row_start} / {row_end}"/>'
            )
        lines.append("</Page>")
        blocks.append("\n".join(lines))
    return '<?xml version="1.0" encoding="utf-8"?>\n' + "\n".join(blocks)

def env():
    e = {}
    for line in open(os.path.expanduser("~/.sigma-migration/env")):
        line = line.strip().replace("export ", "")
        if "=" in line: k, v = line.split("=", 1); e[k] = v.strip().strip('"').strip("'")
    return e
def token(e):
    d = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": e["SIGMA_CLIENT_ID"], "client_secret": e["SIGMA_CLIENT_SECRET"]}).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(e["SIGMA_BASE_URL"] + "/v2/auth/token", data=d, headers={"Content-Type": "application/x-www-form-urlencoded"})))["access_token"]
def api(base, tok, method, path, body=None):
    r = urllib.request.Request(base + path, data=(json.dumps(body).encode() if body else None), method=method,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "Accept": "application/json"})
    try: return json.load(urllib.request.urlopen(r))
    except urllib.error.HTTPError as ex: print("HTTP", ex.code, ex.read().decode()[:1500]); raise

# ---------- DM ----------
def values_sql(rows, cols):
    body = ",\n".join("(" + ",".join(rows[i]) + ")" for i in range(len(rows)))
    return f"select * from (values\n{body}\n) as t({', '.join(cols)})"

def build_dm_spec(P):
    conn = P["connectionId"]
    # GL detail (actuals, transaction grain)
    gl = []
    for r in P["actuals"]:
        gl.append([f"{q(r['date'])}::date", q(r['month']), q(r['line']), q(r['section']),
                   str(r['secOrder']), str(r['lineOrder']), q(r['dept']), q(r['vendor']), f"{float(r['amt']):.2f}"])
    mnum = {m["month"]: m["num"] for m in P["actualMonths"]}; mend = {m["month"]: m["end"] for m in P["actualMonths"]}
    gl_cols = ["TXN_DATE", "MONTH", "LINE_ITEM", "SECTION", "SEC_ORDER", "LINE_ORDER", "DEPARTMENT", "VENDOR", "AMOUNT"]
    # add MONTH_NUM / MONTH_END derived
    for row, r in zip(gl, P["actuals"]):
        row.insert(2, str(mnum[r['month']])); row.insert(3, f"{q(mend[r['month']])}::date")
    gl_cols[2:2] = ["MONTH_NUM", "MONTH_END"]
    glDetail = {"id": "glDetail", "kind": "table", "source": {"kind": "sql", "connectionId": conn, "statement": values_sql(gl, gl_cols)},
                "columns": dmcols([("TXN_DATE","Txn Date"),("MONTH","Month"),("MONTH_NUM","Month Num"),("MONTH_END","Month End"),("LINE_ITEM","Line Item"),("SECTION","Section"),("SEC_ORDER","Section Order"),("LINE_ORDER","Line Order"),("DEPARTMENT","Department"),("VENDOR","Vendor"),("AMOUNT","Amount")])}
    # assumptions
    arows = [[q(a), f"{b}", q(c)] for a, b, c in P["assumptions"]]
    assumptions = {"id": "assumptions", "kind": "table", "source": {"kind": "sql", "connectionId": conn, "statement": values_sql(arows, ["DRIVER","MONTHLY_RATE","BASIS"])},
                   "columns": dmcols([("DRIVER","Driver"),("MONTHLY_RATE","Monthly Rate"),("BASIS","Basis")])}
    # raw forecast spine
    srows = []
    for ln in P["lines"]:
        for i, m in enumerate(P["forecastMonths"]):
            n = m["num"] - P["actualMonths"][-1]["num"]
            kind = ln["kind"]
            drate = f"{ln['rate']}" if kind == "growth" else "NULL"
            mv = f"{ln['manual'][i]:.2f}" if kind == "manual" else "NULL"
            jb = f"{ln['juneBase']:.2f}" if kind in ("growth", "flat") else "NULL"
            srows.append([q(ln["line"]), q(ln["section"]), str(ln["secOrder"]), str(ln["lineOrder"]),
                          q(m["month"]), str(m["num"]), f"{q(m['end'])}::date", str(n), q(kind), drate, mv, jb])
    scols = ["LINE_ITEM","SECTION","SEC_ORDER","LINE_ORDER","MONTH","MONTH_NUM","MONTH_END","N","KIND","DEFAULT_RATE","MANUAL_VALUE","JUNE_BASE"]
    spine = {"id": "spine", "kind": "table", "source": {"kind": "sql", "connectionId": conn, "statement": values_sql(srows, scols)},
             "columns": dmcols([("LINE_ITEM","Line Item"),("SECTION","Section"),("SEC_ORDER","Section Order"),("LINE_ORDER","Line Order"),("MONTH","Month"),("MONTH_NUM","Month Num"),("MONTH_END","Month End"),("N","N"),("KIND","Kind"),("DEFAULT_RATE","Default Rate"),("MANUAL_VALUE","Manual Value"),("JUNE_BASE","June Base")])}
    return {"name": P["name"] + " — Model", "schemaVersion": 1, "folderId": P["folderId"],
            "pages": [{"id": "model", "name": "Model", "elements": [glDetail, assumptions, spine]}]}

def dmcols(pairs):
    return [{"id": f"c{i}", "name": nm, "formula": f"[Custom SQL/{al}]"} for i, (al, nm) in enumerate(pairs, 1)]

def map_dm_elements(spec):
    """Identify element ids by a signature column name (names round-trip; ids reassign)."""
    out = {}
    for el in spec["pages"][0]["elements"]:
        names = {c["name"] for c in el["columns"]}
        if "Vendor" in names: out["glDetail"] = el["id"]
        elif "Kind" in names: out["spine"] = el["id"]
        elif "Driver" in names: out["assumptions"] = el["id"]
    return out

# ---------- parity (local) ----------
SECTIONS = ("Revenue", "Cost of Revenue", "Operating Expenses", "Below the Line")
PARITY_METRICS = ("Revenue", "Gross Profit", "EBITDA", "Net Income")


class PlanError(ValueError):
    """The model plan has a shape this builder does not support."""


def _section_sum_key(section, where):
    if section not in SECTIONS:
        raise PlanError(
            f"unsupported section {section!r} in {where}; this builder supports only "
            + ", ".join(SECTIONS) + " (unknown sections need explicit review, not coercion)")
    return section


def parity(P):
    rev = cogs = opex = below = 0.0
    secsum = {s: 0.0 for s in SECTIONS}
    # actuals
    for i, r in enumerate(P["actuals"]):
        secsum[_section_sum_key(r["section"], f"actuals[{i}] ({r.get('line')!r})")] += r["amt"]
    # forecast
    for ln in P["lines"]:
        _section_sum_key(ln["section"], f"line {ln['line']!r}")
        base = ln.get("juneBase", 0)
        for i, m in enumerate(P["forecastMonths"]):
            n = m["num"] - P["actualMonths"][-1]["num"]
            v = ln["manual"][i] if ln["kind"] == "manual" else (base if ln["kind"] == "flat" else base * (1 + ln["rate"]) ** n)
            secsum[ln["section"]] += v
    rev, cogs, opex, below = secsum["Revenue"], secsum["Cost of Revenue"], secsum["Operating Expenses"], secsum["Below the Line"]
    return {"Revenue": rev, "Gross Profit": rev - cogs, "EBITDA": rev - cogs - opex, "Net Income": rev - cogs - opex - below}


def check_parity(P, computed, tolerance):
    """Compare computed totals to plan['parityTargets']; print one line per metric.

    Returns True when every present target matches within ``tolerance`` (absolute).
    Plans without targets are reported as unchecked and do not fail.
    """
    targets = P.get("parityTargets") or {}
    present = [m for m in PARITY_METRICS if targets.get(m) is not None]
    if not present:
        print("LOCAL PARITY: not checked — plan has no parityTargets")
        return True
    ok = True
    for metric in present:
        want, got = float(targets[metric]), computed[metric]
        passed = abs(got - want) <= tolerance
        ok = ok and passed
        print(f"PARITY {'PASS' if passed else 'FAIL'} {metric}: plan={got:,.2f} source={want:,.2f} "
              f"diff={got - want:,.4f}")
    return ok

# ---------- seed CSVs ----------
def seed_csvs(P, outdir):
    rate_p = os.path.join(outdir, "rate_seed.csv"); man_p = os.path.join(outdir, "manual_seed.csv")
    with open(rate_p, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["LINE_ITEM", "RATE"])
        for ln in P["lines"]:
            if ln["kind"] == "growth": w.writerow([ln["line"], ln["rate"]])
    with open(man_p, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["LINE_ITEM", "MONTH", "MONTH_NUM", "MONTH_END", "AMOUNT"])
        for ln in P["lines"]:
            if ln["kind"] == "manual":
                for i, m in enumerate(P["forecastMonths"]): w.writerow([ln["line"], m["month"], m["num"], m["end"], f"{ln['manual'][i]:.2f}"])
    return rate_p, man_p

# ---------- workbook ----------
def build_wb_spec(P, dm_id, els, *, approved_inputs=None):
    conn = P["connectionId"]; editable = P["intent"] in ("editable", "what-if"); DMP = "Custom SQL"; C = "PnL Combined"
    U = "Union of 2 Sources"
    if approved_inputs is not None:
        manifest, receipt = approved_inputs["manifest"], approved_inputs["receipt"]
        architecture = manifest.get("planProjection", {}).get("sharedInputArchitecture", {})
        if (P.get("sourceSha256") != manifest.get("sourceHash")
                or architecture.get("presentationInputFeature") != "forecastBusinessInput"
                or architecture.get("targetScope", {}).get("connectionId") != conn):
            raise ValueError("approved forecast adapter source/connection is stale")
        from input_sync import emit_workbook_wiring
        approved_graph = emit_workbook_wiring(manifest, receipt)["wiring"]
        editable = False  # Assigned wide input is the only editable surface.
    cur = CUR(P)
    def dm(elid): return {"kind": "data-model", "dataModelId": dm_id, "elementId": els[elid]}
    elements = []
    # actuals wrap (live)
    actuals = {"id": "actuals", "kind": "table", "name": "Actuals", "source": dm("glDetail"),
        "columns": [{"id":"a_sec","name":"Section","formula":f"[{DMP}/Section]"},{"id":"a_so","name":"Section Order","formula":f"[{DMP}/Section Order]"},
                    {"id":"a_line","name":"Line Item","formula":f"[{DMP}/Line Item]"},{"id":"a_lo","name":"Line Order","formula":f"[{DMP}/Line Order]"},
                    {"id":"a_m","name":"Month","formula":f"[{DMP}/Month]"},{"id":"a_mn","name":"Month Num","formula":f"[{DMP}/Month Num]"},
                    {"id":"a_me","name":"Month End","formula":f"[{DMP}/Month End]"},{"id":"a_amt","name":"Amount","formula":f"[{DMP}/Amount]"},
                    {"id":"a_p","name":"Period","formula":'"Actual"'}]}
    spineWrap = {"id":"spineWrap","kind":"table","name":"Forecast Spine","source":dm("spine"),
        "columns":[{"id":f"s_{k}","name":nm,"formula":f"[{DMP}/{nm}]"} for k,nm in
                   [("sec","Section"),("so","Section Order"),("line","Line Item"),("lo","Line Order"),("m","Month"),("mn","Month Num"),("me","Month End"),("n","N"),("k","Kind"),("dr","Default Rate"),("mv","Manual Value"),("jb","June Base")]]}
    # forecast element
    if editable:
        rateInput = {"id":"rateInput","kind":"input-table","name":"Growth Rates (editable)","inputMode":"edit","source":{"kind":"empty","connectionId":conn},
            "columns":[{"id":"ID"},{"id":"LINE_ITEM","type":"text","name":"Line Item"},{"id":"RATE","type":"number","name":"Rate","format":PCT(P)}],"order":["LINE_ITEM","RATE"]}
        manualInput = {"id":"manualInput","kind":"input-table","name":"Manual Forecast (editable)","inputMode":"edit","source":{"kind":"empty","connectionId":conn},
            "columns":[{"id":"ID"},{"id":"LINE_ITEM","type":"text","name":"Line Item"},{"id":"MONTH","type":"text","name":"Month"},{"id":"MONTH_NUM","type":"number","name":"Month Num"},{"id":"MONTH_END","type":"datetime","name":"Month End"},{"id":"AMOUNT","type":"number","name":"Amount","format":cur}],"order":["LINE_ITEM","MONTH","AMOUNT"]}
        forecast = {"id":"forecast","kind":"table","name":"Forecast",
            "source":{"kind":"join","name":"FJ","primarySource":{"kind":"table","elementId":"spineWrap"},
                "joins":[{"name":"Rates","joinType":"left-outer","left":{"kind":"table","elementId":"spineWrap"},"right":{"kind":"table","elementId":"rateInput"},"columns":[{"left":"[Line Item]","right":"[Line Item]"}]},
                         {"name":"Manual","joinType":"left-outer","left":{"kind":"table","elementId":"spineWrap"},"right":{"kind":"table","elementId":"manualInput"},"columns":[{"left":"[Line Item]","right":"[Line Item]"},{"left":"[Month Num]","right":"[Month Num]"}]}]},
            "columns":[{"id":"f_sec","name":"Section","formula":"[FJ/Section]"},{"id":"f_so","name":"Section Order","formula":"[FJ/Section Order]"},
                {"id":"f_line","name":"Line Item","formula":"[FJ/Line Item]"},{"id":"f_lo","name":"Line Order","formula":"[FJ/Line Order]"},
                {"id":"f_m","name":"Month","formula":"[FJ/Month]"},{"id":"f_mn","name":"Month Num","formula":"[FJ/Month Num]"},{"id":"f_me","name":"Month End","formula":"[FJ/Month End]"},
                {"id":"f_n","name":"N","formula":"[FJ/N]"},{"id":"f_k","name":"Kind","formula":"[FJ/Kind]"},{"id":"f_jb","name":"June Base","formula":"[FJ/June Base]"},
                {"id":"f_er","name":"Eff Rate","formula":"Coalesce([Rates/Rate], [FJ/Default Rate])"},
                {"id":"f_em","name":"Eff Manual","formula":"Coalesce([Manual/Amount], [FJ/Manual Value])"},
                {"id":"f_amt","name":"Amount","formula":'If([Kind] = "manual", [Eff Manual], [Kind] = "flat", [June Base], [June Base] * (1 + [Eff Rate]) ^ [N])',"format":cur},
                {"id":"f_p","name":"Period","formula":'"Forecast"'}]}
    else:
        forecast = {"id":"forecast","kind":"table","name":"Forecast","source":{"kind":"table","elementId":"spineWrap"},
            "columns":[{"id":"f_sec","name":"Section","formula":"[Forecast Spine/Section]"},{"id":"f_so","name":"Section Order","formula":"[Forecast Spine/Section Order]"},
                {"id":"f_line","name":"Line Item","formula":"[Forecast Spine/Line Item]"},{"id":"f_lo","name":"Line Order","formula":"[Forecast Spine/Line Order]"},
                {"id":"f_m","name":"Month","formula":"[Forecast Spine/Month]"},{"id":"f_mn","name":"Month Num","formula":"[Forecast Spine/Month Num]"},{"id":"f_me","name":"Month End","formula":"[Forecast Spine/Month End]"},
                {"id":"f_amt","name":"Amount","formula":'If([Forecast Spine/Kind] = "manual", [Forecast Spine/Manual Value], [Forecast Spine/Kind] = "flat", [Forecast Spine/June Base], [Forecast Spine/June Base] * (1 + [Forecast Spine/Default Rate]) ^ [Forecast Spine/N])',"format":cur},
                {"id":"f_p","name":"Period","formula":'"Forecast"'}]}
    def m(nm): return {"outputColumnName": nm, "sourceColumns": [f"[{nm}]", f"[{nm}]"]}
    pnlCombined = {"id":"pnlCombined","kind":"table","name":C,
        "source":{"kind":"union","sources":[{"kind":"table","elementId":"actuals"},{"kind":"table","elementId":"forecast"}],
                  "matches":[m("Section"),m("Section Order"),m("Line Item"),m("Line Order"),m("Month"),m("Month Num"),m("Month End"),m("Amount"),m("Period")]},
        "columns":[{"id":"c_sec","name":"Section","formula":f"[{U}/Section]"},{"id":"c_so","name":"Section Order","formula":f"[{U}/Section Order]"},
            {"id":"c_line","name":"Line Item","formula":f"[{U}/Line Item]"},{"id":"c_lo","name":"Line Order","formula":f"[{U}/Line Order]"},
            {"id":"c_m","name":"Month","formula":f"[{U}/Month]"},{"id":"c_mn","name":"Month Num","formula":f"[{U}/Month Num]"},{"id":"c_me","name":"Month End","formula":f"[{U}/Month End]"},
            {"id":"c_amt","name":"Amount","formula":f"[{U}/Amount]","format":cur},{"id":"c_p","name":"Period","formula":f"[{U}/Period]"},
            {"id":"c_rev","name":"Revenue Amt","formula":f'If([{U}/Section] = "Revenue", [{U}/Amount], 0)'},
            {"id":"c_cogs","name":"COGS Amt","formula":f'If([{U}/Section] = "Cost of Revenue", [{U}/Amount], 0)'},
            {"id":"c_opex","name":"OpEx Amt","formula":f'If([{U}/Section] = "Operating Expenses", [{U}/Amount], 0)'},
            {"id":"c_below","name":"Below Amt","formula":f'If([{U}/Section] = "Below the Line", [{U}/Amount], 0)'}]}
    if approved_inputs is not None:
        approved_nodes = {node["id"]: node for node in approved_graph["elements"]}
        actuals, spineWrap, forecast, pnlCombined = (
            approved_nodes[key] for key in ("actuals", "spineWrap", "forecast", "pnlCombined"))
    REV=f"Sum([{C}/Revenue Amt])"; COGS=f"Sum([{C}/COGS Amt])"; OPEX=f"Sum([{C}/OpEx Amt])"; BELOW=f"Sum([{C}/Below Amt])"
    card_style = {"backgroundColor":"#FFFFFF","borderColor":{"kind":"theme","ref":"colors-border"},"borderWidth":1,"borderRadius":"round"}
    def kpi(eid,name,f,fmt): return {"id":eid,"kind":"kpi-chart","name":name,"source":{"kind":"table","elementId":"pnlCombined"},"columns":[{"id":"v","formula":f,"format":fmt}],"value":{"columnId":"v"},"style":dict(card_style)}
    kpis=[kpi("kpiRev","Total Revenue",REV,cur),kpi("kpiEbitda","EBITDA",f"{REV} - {COGS} - {OPEX}",cur),
          kpi("kpiNI","Net Income",f"{REV} - {COGS} - {OPEX} - {BELOW}",cur),kpi("kpiGM","Gross Margin %",f"({REV} - {COGS}) / {REV}",PCT(P))]
    kpis[0]["style"]["borderColor"] = "#2563EB"
    header={"id":"pnlHeader","kind":"text","body":f"# {P['name']}\nMonthly actuals and forecast performance",
        "style":{"backgroundColor":"#F8FAFC","color":"#0F172A","borderRadius":"round"}}
    trend={"id":"monthlyTrend","kind":"line-chart","name":"Monthly Revenue, EBITDA & Net Income",
        "source":{"kind":"table","elementId":"pnlCombined"},
        "columns":[
            {"id":"t_month","name":"Month","formula":f'DateTrunc("month", [{C}/Month End])',"format":DATEF},
            {"id":"t_revenue","name":"Revenue","formula":f"Sum([{C}/Revenue Amt])","format":cur},
            {"id":"t_ebitda","name":"EBITDA","formula":f"Sum([{C}/Revenue Amt]) - Sum([{C}/COGS Amt]) - Sum([{C}/OpEx Amt])","format":cur},
            {"id":"t_net_income","name":"Net Income","formula":f"Sum([{C}/Revenue Amt]) - Sum([{C}/COGS Amt]) - Sum([{C}/OpEx Amt]) - Sum([{C}/Below Amt])","format":cur}],
        "xAxis":{"columnId":"t_month","sort":{"direction":"ascending"}},
        "yAxis":{"columnIds":["t_revenue","t_ebitda","t_net_income"],"format":{"marks":"grid","scale":{"type":"linear","zero":False}}},
        "legend":{"position":"bottom"},"lineAreaStyle":{"interpolation":"monotone"},
        "style":{"backgroundColor":"#FFFFFF","borderColor":{"kind":"theme","ref":"colors-border"},"borderWidth":1,"borderRadius":"round"}}
    pivot={"id":"pnlPivot","kind":"pivot-table","name":"P&L Statement","source":{"kind":"table","elementId":"pnlCombined"},
        "columns":[{"id":"p_sec","name":"Section","formula":f"[{C}/Section]"},{"id":"p_so","name":"Section Order","formula":f"[{C}/Section Order]"},
            {"id":"p_line","name":"Line Item","formula":f"[{C}/Line Item]"},{"id":"p_lo","name":"Line Order","formula":f"[{C}/Line Order]"},
            {"id":"p_per","name":"Period","formula":f"[{C}/Period]"},{"id":"p_m","name":"Month","formula":f"[{C}/Month End]","format":DATEF},
            {"id":"p_amt","name":"Amount","formula":f"Sum([{C}/Amount])","format":cur}],
        "values":["p_amt"],
        "rowsBy":[{"columnId":"p_sec","sort":{"direction":"ascending","by":"p_so","aggregation":"min"}},{"columnId":"p_line","sort":{"direction":"ascending","by":"p_lo","aggregation":"min"}}],
        "columnsBy":[{"columnId":"p_per","sort":{"direction":"ascending"}},{"columnId":"p_m","sort":{"direction":"ascending"}}],
        "axisTotals":[{"axisId":"grand-row-total","visibility":"hidden"}],
        "style":{"backgroundColor":"#FFFFFF","borderColor":{"kind":"theme","ref":"colors-border"},"borderWidth":1,"borderRadius":"round"}}
    glTable={"id":"glTable","kind":"table","name":"GL Transaction Detail (Actuals)","source":dm("glDetail"),
        "columns":[{"id":"g1","name":"Txn Date","formula":f"[{DMP}/Txn Date]"},{"id":"g2","name":"Month","formula":f"[{DMP}/Month]"},{"id":"g3","name":"Line Item","formula":f"[{DMP}/Line Item]"},{"id":"g4","name":"Department","formula":f"[{DMP}/Department]"},{"id":"g5","name":"Vendor","formula":f"[{DMP}/Vendor]"},{"id":"g6","name":"Amount","formula":f"[{DMP}/Amount]","format":cur}]}
    assumpTable={"id":"assumpTable","kind":"table","name":"Forecast Assumptions","source":dm("assumptions"),
        "columns":[{"id":"d1","name":"Driver","formula":f"[{DMP}/Driver]"},{"id":"d2","name":"Monthly Rate","formula":f"[{DMP}/Monthly Rate]","format":PCT(P)},{"id":"d3","name":"Basis","formula":f"[{DMP}/Basis]"}]}
    # Source-workbook charts the drafter mapped and verified (plan.sourceCharts).
    metric_formula = {"Revenue": REV, "Gross Profit": f"{REV} - {COGS}",
                      "EBITDA": f"{REV} - {COGS} - {OPEX}", "Net Income": f"{REV} - {COGS} - {OPEX} - {BELOW}"}
    source_charts = []
    for i, sc in enumerate(P.get("sourceCharts") or [], 1):
        if sc["grain"] == "quarter":
            x = {"id": f"s{i}_x", "name": "Quarter",
                 "formula": f'Concat(Text(DatePart("year", [{C}/Month End])), " Q", Text(DatePart("quarter", [{C}/Month End])))'}
        else:
            x = {"id": f"s{i}_x", "name": "Month", "formula": f'DateTrunc("month", [{C}/Month End])', "format": DATEF}
        ys = [{"id": f"s{i}_y{j}", "name": metric, "formula": metric_formula[metric], "format": cur}
              for j, metric in enumerate(sc["series"], 1)]
        # Keep the source chart's period range (a Jan-Mar chart stays Jan-Mar).
        period = {"id": f"s{i}_d", "name": "Period Date", "formula": f"[{C}/Month End]"}
        period_filter = [{"id": f"s{i}_range", "columnId": period["id"], "kind": "date-range",
                          "mode": "between", "startDate": sc["periodStart"], "endDate": sc["periodEnd"]}]
        source_charts.append({"id": f"sourceChart{i}", "kind": "line-chart", "name": sc["title"],
            "source": {"kind": "table", "elementId": "pnlCombined"}, "columns": [x] + ys + [period],
            "filters": period_filter,
            "xAxis": {"columnId": x["id"], "sort": {"direction": "ascending"}},
            "yAxis": {"columnIds": [y["id"] for y in ys], "format": {"marks": "grid", "scale": {"type": "linear", "zero": False}}},
            "legend": {"position": "bottom"},
            "style": {"backgroundColor": "#FFFFFF", "borderColor": {"kind": "theme", "ref": "colors-border"}, "borderWidth": 1, "borderRadius": "round"}})
    main_els=[header]+kpis+[trend]+source_charts+[pivot]
    detail_els=[glTable]
    input_els=[assumpTable]
    hidden_els=[actuals,spineWrap,forecast,pnlCombined]
    extra_model_ids = []
    if approved_inputs is not None:
        extra = [e for e in approved_graph["elements"] if e["id"] not in {n["id"] for n in hidden_els}]
        hidden_els += extra
        extra_model_ids = [e["id"] for e in extra]
    if editable: input_els+=[rateInput,manualInput]
    pages=[{"id":"pnl","name":"P&L Overview","elements":main_els},
           {"id":"detail","name":"Detail","elements":detail_els},
           {"id":"inputs","name":"Inputs","elements":input_els},
           {"id":"model","name":"Model (sources)","visibility":"hidden","elements":hidden_els}]
    # Nested draft; wire_workbook flattens + wraps at the POST / dry-run boundary.
    return {"name":P["name"],"schemaVersion":1,"kind":"workbook","folderId":P["folderId"],
            "pages":pages,"layout":forecast_layout(editable, extra_model_ids, [c["id"] for c in source_charts])}

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", help="model-plan JSON")
    parser.add_argument("--source", help="source XLSX used to produce the plan")
    parser.add_argument("--review-dispositions", help="source-bound review dispositions JSON")
    parser.add_argument("--post", action="store_true", help="create the data model and workbook")
    parser.add_argument("--out-dir", default="/tmp/fcst-build",
                        help="where specs and seed CSVs are written (default: /tmp/fcst-build)")
    parser.add_argument("--parity-tolerance", type=float, default=0.01,
                        help="absolute tolerance for plan.parityTargets (default: 0.01)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    with open(args.plan, encoding="utf-8") as stream:
        P = json.load(stream)
    try:
        source_path, gate_report = gate_plan_source(
            P,
            source_arg=args.source,
            dispositions_path=args.review_dispositions,
            plan_path=args.plan,
            draft=not args.post,
        )
    except MigrationGateError as error:
        print(f"MIGRATION GATE: {error}", file=sys.stderr)
        return error.exit_code
    print(
        f"MIGRATION GATE: {gate_report['status']} "
        f"source={source_path.name} sha256={gate_report['sourceSha256']}"
    )
    if gate_report.get("pendingReview"):
        print("DRAFT MODE: review pending for " + ", ".join(gate_report["pendingReview"])
              + " — fine for a local build; resolve before --post.")
    do_post = args.post
    outdir = args.out_dir
    # parity — a mismatch stops the run before any spec is written or posted
    try:
        par=parity(P)
    except PlanError as error:
        print(f"PLAN ERROR: {error}", file=sys.stderr)
        return 1
    print("LOCAL PARITY (from plan):", "  ".join(f"{k}={v:,.2f}" for k,v in par.items()))
    if not check_parity(P, par, args.parity_tolerance):
        print("LOCAL PARITY FAILED — no specs written; fix the plan (or the source) before building.",
              file=sys.stderr)
        return 1
    os.makedirs(outdir, exist_ok=True)
    rate_csv,man_csv=seed_csvs(P,outdir)
    print(f"seed CSVs: {rate_csv}, {man_csv}")
    dm_spec=build_dm_spec(P)
    with open(f"{outdir}/dm_spec.json", "w", encoding="utf-8") as stream:
        json.dump(dm_spec, stream, indent=1)
    if not do_post:
        # map ids from the local spec (ids as-authored) for a dry-run wb spec
        els={"glDetail":"glDetail","spine":"spine","assumptions":"assumptions"}
        wb_spec=workbook_wire.wire_workbook(build_wb_spec(P,"<dm-id>",els))
        with open(f"{outdir}/wb_spec.json", "w", encoding="utf-8") as stream:
            json.dump(wb_spec, stream, indent=1)
        print(f"DRY RUN — specs written to {outdir}/ (dm_spec.json, wb_spec.json). Re-run with --post to build live.")
        return 0
    e=env(); base=e["SIGMA_BASE_URL"]; tok=token(e)
    dm=api(base,tok,"POST","/v2/dataModels/spec",dm_spec); dm_id=dm["dataModelId"]
    print("dataModelId:",dm_id)
    full=api(base,tok,"GET",f"/v2/dataModels/{dm_id}/spec")
    els=map_dm_elements(full)
    # Layout is the last write before the current contents API validates + creates.
    wb_spec=workbook_wire.wire_workbook(build_wb_spec(P,dm_id,els))
    checked=api(base,tok,"POST","/v2/workbooks",workbook_wire.dry_run_request(wb_spec))
    workbook_wire.assert_dry_run_success(checked)
    wb=api(base,tok,"POST","/v2/workbooks",wb_spec)
    print("workbookId:",wb["workbookId"],"| url:",wb.get("url"))
    print("NOTE: POST uses a stacked notebook-flow layout via code_rep; refine with wb-rep push if needed.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
