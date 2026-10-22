#!/usr/bin/env python3
"""
build-research-workbook.py — MULTI-SHEET, MULTI-TABLE driver for the equity-research
archetype. Converts a whole broker model (many analysis sheets) into ONE Sigma workbook.

TWO ELEMENTS PER SHEET (the transparent pattern):
  * `Raw data — <sheet>` — the raw hard-coded data (Period rows x line columns). A SQL table
    (data pre-loaded) by default, or an editable input table (paste to load) with --editable
    / --editable-sheet. Rename with --raw-label (e.g. --raw-label "Dati grezzi").
  * `<sheet>` (the model) — sources the raw; EVERY line item is a column WITH its formula.
Columns are named `c<row> · <Label>` (e.g. `c13 · Gross profit`) — ref-safe AND readable, so
each formula reads in plain terms and is clickable in place. No transpose, no hidden plumbing.

Each sheet may hold several sub-tables at different year alignments; detect_tables converts
each on its OWN axis (no year shift). Every workbook POST goes through workbook_wire.

Usage:
  build-research-workbook.py <file.xlsx> --conn <id> --folder <id> [--name "..."]
        [--sheets "Annuals,Segments,..."]          # default: auto-pick financial sheets
        [--editable | --editable-sheet "Annuals"]  # input tables (paste); default = SQL/loaded
        [--raw-label "Raw data"] [--post]           # default dry-run to /tmp
"""
import argparse
import sys, os, json, csv, re, importlib.util, warnings
from lib.migration_gate import MigrationGateError, gate_source, plan_review_issues
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
def _load(fn, name):
    s = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
INF = _load("infer-canonical-formulas.py", "inf")
BRM = _load("build-research-model.py", "brm")

NUM = {"kind": "number", "formatString": "#,##0.0"}
DMP = "Custom SQL"
RAW_LABEL = "Raw data"          # name of the per-sheet raw-data element (override with --raw-label)


def abbr(title):
    a = re.sub(r"[^a-z0-9]", "", title.lower())[:6] or "s"
    return a


def namespace_plan(plan, pre):
    """Rewrite col_ids -> <pre>c<row> and every [cN] ref in canonicals, so a sub-table's
    columns are globally unique across the workbook."""
    ren = {ln["col_id"]: f"{pre}{ln['col_id']}" for ln in plan["lines"]}
    for ln in plan["lines"]:
        ln["col_id"] = ren[ln["col_id"]]
        if ln.get("canonical"):
            ln["canonical"] = re.sub(r"\[c(\d+)\]", lambda m: f"[{pre}c{m.group(1)}]", ln["canonical"])
    return plan


def subtable_plans(path, sheet):
    """All sub-tables on a sheet, each an inferred + namespaced plan (skips empties/failures)."""
    wf, wv = INF.load(path);
    if sheet not in wf.sheetnames:
        return []
    tables = INF.detect_tables(wf[sheet], wv[sheet]) or []
    if not tables:                                       # single-table sheet: normal detect
        try:
            p = INF.infer(path, sheet=sheet)
            return [(f"{abbr(sheet)}0", p, None)]
        except Exception:
            return []
    out = []
    for i, t in enumerate(tables):
        try:
            p = INF.infer(path, sheet=sheet, axis_override=t["axis"], header_row=t["header_row"],
                          first_row=t["first_row"], last_row=t["last_row"])
        except Exception:
            continue
        if not p["lines"] or not p["periods"]:
            continue
        pre = f"{abbr(sheet)}{i}"
        out.append((pre, namespace_plan(p, pre), t))
    return out


def dm_elements(pre, plan):
    """DM `<pre>_data` (inline VALUES, editable-default) + `<pre>_dim` (line dim)."""
    data_lines = [ln for ln in plan["lines"] if ln["typed"]]
    years = [p["year"] for p in plan["periods"]]
    cols = ["YR"] + [ln["col_id"] for ln in data_lines]
    rows = []
    for y in years:
        cells = [str(y)] + ["NULL" if (ln["typed"].get(str(y), ln["typed"].get(y)) is None)
                            else f"{float(ln['typed'].get(str(y), ln['typed'].get(y))):.6f}"
                            for ln in data_lines]
        rows.append("(" + ",".join(cells) + ")")
    inner = "select * from (values\n" + ",\n".join(rows) + "\n) as t(" + ", ".join(cols) + ")"
    casts = ["YR::int as YR"] + [f"{ln['col_id']}::float as {ln['col_id']}" for ln in data_lines]
    data_sql = f"select {', '.join(casts)} from (\n{inner}\n) s"
    dim_sql = ("select * from (values\n" +
               ",\n".join("(" + ",".join([BRM.q(ln["col_id"]), BRM.q(ln["label"] or ln["col_id"]),
                                          BRM.q(plan["sheet"]), str(ln["sec_order"]), str(ln["line_order"])]) + ")"
                          for ln in plan["lines"]) +
               "\n) as t(LINE_ID, LABEL, SECTION, SEC_ORDER, LINE_ORDER)")
    data_el = {"id": f"{pre}_data", "kind": "table",
               "source": {"kind": "sql", "connectionId": CONN, "statement": data_sql},
               "columns": [BRM.dmcol(0, "YR", "Year")] +
                          [BRM.dmcol(i + 1, ln["col_id"], ln["col_id"]) for i, ln in enumerate(data_lines)]}
    dim_el = {"id": f"{pre}_dim", "kind": "table",
              "source": {"kind": "sql", "connectionId": CONN, "statement": dim_sql},
              "columns": [BRM.dmcol(0, "LINE_ID", "Line Id"), BRM.dmcol(1, "LABEL", "Label"),
                          BRM.dmcol(2, "SECTION", "Section"), BRM.dmcol(3, "SEC_ORDER", "Sec Order"),
                          BRM.dmcol(4, "LINE_ORDER", "Line Order")]}
    return data_el, dim_el, data_lines


def _san(lbl):
    """Ref-safe label for the display name: '/', '[', ']' break Sigma column refs."""
    return (str(lbl or "").replace("/", "∕").replace("[", "(").replace("]", ")").strip()) or "line"


def wb_elements(pre, plan, dm_id, data_el_id, dim_el_id, data_lines, title, editable=False):
    """The LIKED two-element pattern: a `raw` data element (SQL table, or editable input
    table) with Period rows x line columns, then a `model` table whose columns are the line
    items WITH their formulas. Columns are named 'c<row> · <Label>' — ref-safe + readable,
    so every formula reads e.g. 'Coalesce([c13 · Gross profit], [c8 · TURNOVER]-...)' and is
    clickable in place. No transpose, no hidden plumbing."""
    dcols = {ln["col_id"] for ln in data_lines}
    byid = {ln["col_id"]: ln for ln in plan["lines"]}
    def dm(eid): return {"kind": "data-model", "dataModelId": dm_id, "elementId": eid}
    # display name  c<row> · Label   (strip the namespacing prefix from the id part)
    def disp(ln): return f"c{ln['row']} · {_san(ln['label'] or ln['col_id'])}"
    dmap = {cid: disp(ln) for cid, ln in byid.items()}
    def to_disp(formula):                # rewrite canonical refs [<colid>] -> [c<row> · Label], [Year] -> [Period]
        f = re.sub(r"\[([^\]]+)\]", lambda m: f"[{dmap[m.group(1)]}]" if m.group(1) in dmap else m.group(0), formula)
        return f.replace("[Year]", "[Period]")

    RAW = f"{RAW_LABEL} — {title}"[:70]
    raw_cols = [{"id": f"{pre}_period", "name": "Period", "formula": f"[{DMP}/Year]"},
                {"id": f"{pre}_order", "name": "Period Order", "formula": f"[{DMP}/Year]"}]
    if editable:
        # editable input table (empty; paste to load). Period + one editable column per line item.
        raw = {"id": f"{pre}_raw", "kind": "input-table", "name": RAW, "inputMode": "edit",
               "source": {"kind": "empty", "connectionId": CONN},
               "columns": [{"id": "ID"}, {"id": f"{pre}_period", "type": "number", "name": "Period"}] +
                          [{"id": ln["col_id"], "type": "number", "name": disp(ln)} for ln in data_lines],
               "order": [f"{pre}_period"] + [ln["col_id"] for ln in data_lines]}
    else:
        raw = {"id": f"{pre}_raw", "kind": "table", "name": RAW, "source": dm(data_el_id),
               "columns": raw_cols + [{"id": ln["col_id"], "name": disp(ln),
                                       "formula": f"[{DMP}/{ln['col_id']}]"} for ln in data_lines]}
    # model: sources raw; every line item is a column with its formula, named c<row> · Label
    mcols = [{"id": f"{pre}_mperiod", "name": "Period", "formula": f"[{RAW}/Period]"},
             {"id": f"{pre}_morder", "name": "Period Order", "formula": f"[{RAW}/Period]"}]
    for ln in plan["lines"]:
        cid = ln["col_id"]; has = cid in dcols; nm = disp(ln)
        if ln["kind"] == "input" or not ln.get("canonical"):
            f = f"[{RAW}/{nm}]" if has else "Null"                       # raw passthrough (editable surface)
        elif has:
            f = f"Coalesce([{RAW}/{nm}], {to_disp(ln['canonical'])})"    # typed override wins, else formula
        else:
            f = to_disp(ln["canonical"])                                 # pure formula
        mcols.append({"id": f"{pre}_m_{cid}", "name": nm, "formula": f})
    model = {"id": f"{pre}_model", "kind": "table", "name": title[:70],
             "source": {"kind": "table", "elementId": f"{pre}_raw"}, "columns": mcols}
    return {"model": model, "raw": raw}


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook")
    parser.add_argument("--conn", default="<conn>")
    parser.add_argument("--folder", default="<folder>")
    parser.add_argument("--name")
    parser.add_argument("--sheets")
    parser.add_argument("--editable", action="store_true")
    parser.add_argument("--editable-sheet")
    parser.add_argument("--raw-label", default="Raw data")
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--review-dispositions")
    parser.add_argument("--draft", action="store_true",
                        help="local dry-run: report pending review issues instead of failing "
                             "(not valid with --post)")
    return parser


def main(argv=None):
    global CONN, RAW_LABEL
    parser = _parser()
    args = parser.parse_args(argv)
    if args.draft and args.post:
        parser.error("--draft is for local dry-runs only; --post needs --review-dispositions")
    path = args.workbook
    CONN = args.conn
    folder = args.folder
    RAW_LABEL = args.raw_label       # name of the raw-data element per sheet
    name = args.name or (os.path.splitext(os.path.basename(path))[0][:50] + " (auto)")
    do_post = args.post
    try:
        gate_source(path, args.review_dispositions, draft=args.draft)
    except MigrationGateError as error:
        print(f"MIGRATION GATE: {error}", file=sys.stderr)
        return error.exit_code
    wf, wv = INF.load(path)
    if args.sheets:
        sheets = [s.strip() for s in args.sheets.split(",")]
    else:                                                # auto: sheets with a detectable financial table
        sheets = []
        for ws in wf.worksheets:
            if ws.sheet_state != "visible" or ws.title.startswith("__") or ws.title.endswith(">>"):
                continue
            try:
                if INF.detect_tables(wf[ws.title], wv[ws.title]):
                    sheets.append(ws.title)
            except Exception:
                pass
    print("sheets to convert:", sheets)

    dm_data, dm_dim, dm_els = [], [], {}
    pages, plumb_all, verify = [], [], []
    for sheet in sheets:
        subs = subtable_plans(path, sheet)
        page_tables = []
        for j, (pre, plan, tbl) in enumerate(subs):
            de, di, dl = dm_elements(pre, plan)
            if not dl:                                   # nothing typed -> skip (all-derived/empty)
                continue
            dm_data.append(de)
            dm_els[pre] = {"data_cols": {c["name"] for c in de["columns"]}, "plan": plan, "dl": dl,
                           "title": f"{sheet}" + (f" — table {j+1}" if len(subs) > 1 else "")}
            page_tables.append(pre)
        if page_tables:
            pages.append((sheet, page_tables))
    if not dm_data:
        sys.exit("no convertible tables found")

    derived_issues = []
    seen_issue_codes = set()
    for info in dm_els.values():
        for issue in plan_review_issues(info["plan"]):
            if issue["code"] not in seen_issue_codes:
                derived_issues.append(issue)
                seen_issue_codes.add(issue["code"])
    try:
        gate_report = gate_source(path, args.review_dispositions, derived_issues, draft=args.draft)
    except MigrationGateError as error:
        print(f"MIGRATION GATE: {error}", file=sys.stderr)
        return error.exit_code
    if gate_report.get("pendingReview"):
        print("DRAFT MODE: review pending for " + ", ".join(gate_report["pendingReview"])
              + " — fine for a local build; resolve before --post.")

    dm_spec = {"name": name + " — Model", "schemaVersion": 1, "folderId": folder,
               "pages": [{"id": "m", "name": "Model", "elements": dm_data}]}
    os.makedirs("/tmp/research-wb", exist_ok=True)
    json.dump(dm_spec, open("/tmp/research-wb/dm.json", "w"), indent=1)
    print(f"DM: {len(dm_data)} data elements across {len(pages)} pages")
    if not do_post:
        print("DRY RUN — /tmp/research-wb/dm.json written. Re-run with --post --conn --folder to build.")
        return 0

    e = BRM.env(); base = e["SIGMA_BASE_URL"]; tok = BRM.token(e)
    dm = BRM.api(base, tok, "POST", "/v2/dataModels/spec", dm_spec); dm_id = dm["dataModelId"]
    print("dataModelId:", dm_id)
    full = BRM.api(base, tok, "GET", f"/v2/dataModels/{dm_id}/spec")
    id_by_cols = {frozenset(c["name"] for c in el["columns"]): el["id"] for el in full["pages"][0]["elements"]}
    all_edit = args.editable                               # every sheet -> editable input table
    edit_sheet = args.editable_sheet                     # or just one named sheet's primary table
    main_pages, seeds = [], []
    for sheet, pres in pages:
        elems = []
        for k, pre in enumerate(pres):
            info = dm_els[pre]
            de_id = id_by_cols.get(frozenset(info["data_cols"]))
            editable = all_edit or (edit_sheet and sheet == edit_sheet and k == 0)
            els = wb_elements(pre, info["plan"], dm_id, de_id, None, info["dl"], info["title"], editable=editable)
            elems += [els["raw"], els["model"]]                  # both on the page (data + formulas)
            if editable:
                seeds.append((pre, info["plan"], info["dl"]))
        main_pages.append({"id": abbr(sheet), "name": sheet[:40], "elements": elems})
    for pre, plan, dl in seeds:                                  # seed CSV matching the input-table columns
        icols = [ln for ln in dl]
        sp = f"/tmp/research-wb/{pre}_inputs_seed.csv"
        with open(sp, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Period"] + [f"c{ln['row']} · {_san(ln['label'])}" for ln in icols])
            for p in plan["periods"]:
                y = p["year"]
                w.writerow([y] + ["" if (ln["typed"].get(str(y), ln["typed"].get(y)) is None)
                                  else round(ln["typed"].get(str(y), ln["typed"].get(y)), 6) for ln in icols])
        print(f"seed CSV: {sp}")
    wb_spec = {"name": name, "schemaVersion": 1, "kind": "workbook", "folderId": folder, "pages": main_pages}
    ww = _load("lib/workbook_wire.py", "ww")
    wb_spec = ww.wire_workbook(wb_spec)
    json.dump(wb_spec, open("/tmp/research-wb/wb.json", "w"), indent=1)
    checked = BRM.api(base, tok, "POST", "/v2/workbooks",
                      ww.dry_run_request(wb_spec))
    ww.assert_dry_run_success(checked)
    wb = BRM.api(base, tok, "POST", "/v2/workbooks", wb_spec)
    print("workbookId:", wb.get("workbookId"), "| url:", wb.get("url"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
