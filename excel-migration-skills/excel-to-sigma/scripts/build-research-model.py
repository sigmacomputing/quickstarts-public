#!/usr/bin/env python3
"""
build-research-model.py — one-shot builder for the EQUITY-RESEARCH archetype
(broker/FactSet house-template models). Consumes the plan JSON emitted by
infer-canonical-formulas.py and builds, entirely via the Sigma REST API:

  DATA LAYER      (DM element `data`)     — the hard-coded grid as inline VALUES:
                                            one row per YEAR, one column per line item
                                            (safe id c<row>), typed values or NULL.
  LINE DIM        (DM element `linedim`)  — id -> label / section / order (inline VALUES).
  COMPUTATION     (wb table `calc`)       — one column per line item:
                                            input   -> [data/c<row>]
                                            derived -> Coalesce([data/c<row>], <canonical>)
                                            (canonical references sibling c<row> columns;
                                             ONE formula per line, all years — no triplets).
  LONG            (wb transpose `long`)   — column-to-row unpivot -> (Year, LineId, Value).
  LABELED         (wb join `labeled`)     — long ⋈ linedim -> adds Label/Section/orders.
  DISPLAY         (wb pivot)              — rowsBy Section->Label, columnsBy Year, Sum(Value).

This is the "start from the hard-coded values, then build the pivot with the formulas
in it" architecture — the clean version of a hand build (no User/Calc/(1) sprawl).

Creds: reads SIGMA_BASE_URL / SIGMA_CLIENT_ID / SIGMA_CLIENT_SECRET from the environment
if set, else ~/.sigma-migration/env. (Point it at any org via env vars.)

Usage:
  build-research-model.py <plan.json> --conn <connId> --folder <folderId>
                          [--name "..."] [--post]         # default = dry-run to /tmp
"""
import argparse, sys, os, json, re, urllib.request, urllib.parse, urllib.error
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
import workbook_wire  # noqa: E402
from lib.migration_gate import MigrationGateError, gate_plan_source  # noqa: E402
from lib.input_sync import include_research_line_input_literals, sigma_input_type  # noqa: E402

OUTDIR = "/tmp/research-build"
NUM = {"kind": "number", "formatString": "#,##0.0"}


def q(s):
    return "'" + str(s).replace("'", "''") + "'"


def numeric_literal(value):
    """Preserve source precision while retaining stable decimal SQL literals."""
    text = repr(float(value))
    if "e" not in text.lower():
        whole, dot, fraction = text.partition(".")
        if not dot:
            return whole + ".000000"
        if len(fraction) < 6:
            return whole + "." + fraction.ljust(6, "0")
    return text


def env():
    e = dict(os.environ)
    if all(k in e and e[k] for k in ("SIGMA_BASE_URL", "SIGMA_CLIENT_ID", "SIGMA_CLIENT_SECRET")):
        return e
    p = os.path.expanduser("~/.sigma-migration/env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip().replace("export ", "")
            if "=" in line:
                k, v = line.split("=", 1); e.setdefault(k, v.strip().strip('"').strip("'"))
    return e


def token(e):
    d = urllib.parse.urlencode({"grant_type": "client_credentials",
                                "client_id": e["SIGMA_CLIENT_ID"],
                                "client_secret": e["SIGMA_CLIENT_SECRET"]}).encode()
    req = urllib.request.Request(e["SIGMA_BASE_URL"] + "/v2/auth/token", data=d,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    return json.load(urllib.request.urlopen(req))["access_token"]


def api(base, tok, method, path, body=None):
    req = urllib.request.Request(base + path, data=(json.dumps(body).encode() if body else None),
                                 method=method,
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as ex:
        print("HTTP", ex.code, ex.read().decode()[:2000]); raise


# ---------------------------------------------------------------- DM specs
def data_sql(plan, data_lines):
    """Wide VALUES: row per year, col per line (typed or NULL), cast so all-NULL cols type."""
    years = [p["year"] for p in plan["periods"]]
    cols = ["YR"] + [ln["col_id"] for ln in data_lines]
    rows = []
    for y in years:
        cells = [str(y)]
        for ln in data_lines:
            values = ln.get("literalInputs", ln.get("typed", {}))
            v = values.get(str(y), values.get(y))
            cells.append("NULL" if v is None else numeric_literal(v))
        rows.append("(" + ",".join(cells) + ")")
    inner = "select * from (values\n" + ",\n".join(rows) + "\n) as t(" + ", ".join(cols) + ")"
    casts = ["YR::int as YR"] + [f"{ln['col_id']}::float as {ln['col_id']}" for ln in data_lines]
    return f"select {', '.join(casts)} from (\n{inner}\n) s"


def display_labels(plan):
    """Give generic research ratios a useful label, with stable identity as fallback."""
    candidates = []
    for index, line in enumerate(plan["lines"]):
        label = str(line.get("label") or line["col_id"]).strip()
        normalized = label.casefold()
        descriptor = None
        if "growth" in normalized and normalized.lstrip().startswith("%"):
            descriptor = "growth"
        elif "margin" in normalized and normalized.lstrip().startswith("%"):
            descriptor = "margin"
        if descriptor:
            for prior in reversed(plan["lines"][:index]):
                prior_label = str(prior.get("label") or prior["col_id"]).strip()
                if prior.get("section") == line.get("section") and not prior_label.startswith("%"):
                    label = f"{prior_label} {descriptor}"
                    break
        candidates.append(label)

    counts = {}
    for label in candidates:
        counts[label.casefold()] = counts.get(label.casefold(), 0) + 1
    result = {}
    for line, label in zip(plan["lines"], candidates):
        if counts[label.casefold()] > 1:
            identity = line.get("row", line["col_id"])
            label = f"{label} (row {identity})"
        result[line["col_id"]] = label
    return result


def linedim_sql(plan):
    labels = display_labels(plan)
    rows = []
    for ln in plan["lines"]:
        rows.append("(" + ",".join([q(ln["col_id"]), q(labels[ln["col_id"]]),
                                    q(ln["section"]), str(ln["sec_order"]), str(ln["line_order"]),
                                    q(ln["kind"])]) + ")")
    inner = "select * from (values\n" + ",\n".join(rows) + \
            "\n) as t(LINE_ID, LABEL, SECTION, SEC_ORDER, LINE_ORDER, KIND)"
    return inner


def dmcol(i, alias, name):
    return {"id": f"k{i}", "name": name, "formula": f"[Custom SQL/{alias}]"}


def build_dm(plan, conn, folder, name):
    data_lines = [ln for ln in plan["lines"]
                  if ln.get("literalInputs", ln.get("typed", {}))]
    data_lines += [
        {"col_id": item["id"], "literalInputs": item.get("values", {}),
         "typed": item.get("values", {}), "sourceInput": True,
         "label": item.get("sourceCellId", item["id"])}
        for item in plan.get("sourceInputs", [])
    ]
    data_el = {"id": "data", "kind": "table",
               "source": {"kind": "sql", "connectionId": conn, "statement": data_sql(plan, data_lines)},
               "columns": [dmcol(0, "YR", "Year")] +
                          [dmcol(i + 1, ln["col_id"], ln["col_id"]) for i, ln in enumerate(data_lines)]}
    linedim_el = {"id": "linedim", "kind": "table",
                  "source": {"kind": "sql", "connectionId": conn, "statement": linedim_sql(plan)},
                  "columns": [dmcol(0, "LINE_ID", "Line Id"), dmcol(1, "LABEL", "Label"),
                              dmcol(2, "SECTION", "Section"), dmcol(3, "SEC_ORDER", "Sec Order"),
                              dmcol(4, "LINE_ORDER", "Line Order"), dmcol(5, "KIND", "Kind")]}
    spec = {"name": name + " — Model", "schemaVersion": 1, "folderId": folder,
            "pages": [{"id": "m", "name": "Model", "elements": [data_el, linedim_el]}]}
    return spec, data_lines


def map_dm(full):
    out = {}
    for el in full["pages"][0]["elements"]:
        names = {c["name"] for c in el["columns"]}
        if "Label" in names:
            out["linedim"] = el["id"]
        elif "Year" in names:
            out["data"] = el["id"]
    return out


# ---------------------------------------------------------------- workbook spec
def build_wb(plan, dm_id, els, data_lines, folder, name):
    DMP = "Custom SQL"
    dcols = {ln["col_id"] for ln in data_lines}

    def dm(elid):
        return {"kind": "data-model", "dataModelId": dm_id, "elementId": els[elid]}

    include_research_line_input_literals(plan)
    source_inputs = list(plan.get("sourceInputs") or [])
    target_scope = plan.get("targetScope") or {}
    research_input = None
    model_base = None
    calc_source = dm("data")
    calc_namespace = DMP
    input_namespace = None
    if source_inputs:
        connection_id = target_scope.get("connectionId")
        if not connection_id:
            raise ValueError("editable research inputs require targetScope.connectionId in the hash-bound plan")
        research_input = {
            "id": "researchInputs", "kind": "input-table", "name": "Research Model Inputs",
            "inputMode": "edit", "source": {"kind": "empty", "connectionId": connection_id},
            "columns": [{"id": "SCOPE", "type": "text", "name": "Scope"}] + [
                {"id": item["id"], "type": sigma_input_type(item.get("defaultValue")),
                 "name": item["id"]}
                for item in source_inputs
            ],
            "order": ["SCOPE"] + [item["id"] for item in source_inputs],
        }
        model_base = {
            "id": "modelBase", "kind": "table", "name": "Research Source Values",
            "source": dm("data"),
            "columns": [{"id": "mb_year", "name": "Year", "formula": f"[{DMP}/Year]"},
                        {"id": "mb_scope", "name": "Scope", "formula": '"shared"'}] + [
                {"id": "mb_" + item["col_id"], "name": item["col_id"],
                 "formula": f"[{DMP}/{item['col_id']}]"}
                for item in data_lines
            ],
        }
        calc_source = {
            "kind": "join", "name": "CJ",
            "primarySource": {"kind": "table", "elementId": "modelBase"},
            "joins": [{
                "name": "Inputs", "joinType": "left-outer",
                "left": {"kind": "table", "elementId": "modelBase"},
                "right": {"kind": "table", "elementId": "researchInputs"},
                "columns": [{"left": "[Scope]", "right": "[Scope]"}],
            }],
        }
        calc_namespace = "CJ"
        input_namespace = "Inputs"

    # ---- calc: one column per line, in the same element (siblings referenced by name) ----
    calc_cols = [{"id": "yr", "name": "Year", "formula": f"[{calc_namespace}/Year]"}]
    for item in source_inputs:
        base = f"[{calc_namespace}/{item['id']}]"
        calc_cols.append({"id": item["id"], "name": item["id"],
                          "formula": (f"If(IsNull([{input_namespace}/Scope]), {base}, "
                                      f"[{input_namespace}/{item['id']}])")})

    literal_bindings = {}
    period_by_column = {str(period.get("col")): str(period["year"])
                        for period in plan.get("periods", [])
                        if period.get("col") and period.get("year") is not None}
    for item in source_inputs:
        if item.get("role") != "source_literal":
            continue
        match = re.fullmatch(r"([^!]+)!([A-Z]+)(\d+)", item.get("sourceCellId", ""))
        if not match:
            raise ValueError(f"source literal has invalid sourceCellId: {item.get('id')}")
        expected_address = f"{match.group(2)}{match.group(3)}"
        if (not plan.get("sheet") or item.get("sheet") != plan.get("sheet")
                or match.group(1) != plan.get("sheet")
                or item.get("address") != expected_address):
            raise ValueError(f"source literal sheet/address metadata is inconsistent: {item.get('id')}")
        year = period_by_column.get(match.group(2))
        if year is None:
            raise ValueError(f"source literal requires period column metadata: {item.get('id')}")
        literal_bindings[(int(match.group(3)), year)] = item["id"]
    merge = []
    for ln in plan["lines"]:
        cid = ln["col_id"]; merge.append(cid)
        has_data = cid in dcols
        period_formulas = dict(ln.get("periodFormulas") or {})
        if source_inputs:
            for (row, year), input_id in literal_bindings.items():
                if row == ln.get("row"):
                    # A source literal belongs only to its actual source column's
                    # period. Never let inference carry values replace authored
                    # formulas from later source cells.
                    period_formulas.setdefault(year, f"[{input_id}]")
        if period_formulas:
            f = f"[{calc_namespace}/{cid}]" if has_data and source_inputs else "Null"
            for year, expression in sorted(period_formulas.items(), key=lambda item: int(item[0]), reverse=True):
                f = f"If([Year] = {int(year)}, {expression}, {f})"
            if has_data and not source_inputs:
                f = f"Coalesce([{DMP}/{cid}], {f})"
        elif ln["kind"] == "input" or not ln.get("canonical"):
            f = f"[{calc_namespace}/{cid}]" if has_data else "Null"      # carried / input / quarantined
        elif has_data:
            f = f"Coalesce([{calc_namespace}/{cid}], {ln['canonical']})"  # override wins, else compute
        else:
            f = ln["canonical"]                                # pure derived, one formula
        calc_cols.append({"id": cid, "name": cid, "formula": f})
    calc = {"id": "calc", "kind": "table", "name": "Calc",
            "source": calc_source, "columns": calc_cols}

    # ---- long: transpose (column-to-row) all line columns -> (Year, LineId, Value) ----
    # NB: a transpose element takes NO explicit name; Sigma auto-names it "Transpose of <source>"
    # and its OWN columns must self-reference via that auto name.
    TR = "Transpose of Calc"
    long_el = {"id": "long", "kind": "table",
               "source": {"kind": "transpose", "source": {"kind": "table", "elementId": "calc"},
                          "direction": "column-to-row", "columnsToMerge": merge,
                          "columnLabelForMergedColumns": "LineId", "columnLabelForValues": "Value"},
               "columns": [{"id": "l_yr", "name": "Year", "formula": f"[{TR}/Year]"},
                           {"id": "l_id", "name": "LineId", "formula": f"[{TR}/LineId]"},
                           {"id": "l_v", "name": "Value", "formula": f"[{TR}/Value]"}]}

    # ---- linedim wrap (a DM leg can't sit inside a join) ----
    dimw = {"id": "dimw", "kind": "table", "name": "Dim",
            "source": dm("linedim"),
            "columns": [{"id": "d_id", "name": "Line Id", "formula": f"[{DMP}/Line Id]"},
                        {"id": "d_lab", "name": "Label", "formula": f"[{DMP}/Label]"},
                        {"id": "d_sec", "name": "Section", "formula": f"[{DMP}/Section]"},
                        {"id": "d_so", "name": "Sec Order", "formula": f"[{DMP}/Sec Order]"},
                        {"id": "d_lo", "name": "Line Order", "formula": f"[{DMP}/Line Order]"}]}

    # ---- labeled: long ⋈ dim on LineId ----
    labeled = {"id": "labeled", "kind": "table", "name": "Labeled",
               "source": {"kind": "join", "name": "LJ",
                          "primarySource": {"kind": "table", "elementId": "long"},
                          "joins": [{"name": "D", "joinType": "left-outer",
                                     "left": {"kind": "table", "elementId": "long"},
                                     "right": {"kind": "table", "elementId": "dimw"},
                                     "columns": [{"left": "[LineId]", "right": "[Line Id]"}]}]},
               "columns": [{"id": "x_yr", "name": "Year", "formula": "[LJ/Year]"},
                           {"id": "x_v", "name": "Value", "formula": "[LJ/Value]"},
                           {"id": "x_lab", "name": "Line Item", "formula": "[D/Label]"},
                           {"id": "x_sec", "name": "Section", "formula": "[D/Section]"},
                           {"id": "x_so", "name": "Sec Order", "formula": "[D/Sec Order]"},
                           {"id": "x_lo", "name": "Line Order", "formula": "[D/Line Order]"}]}

    # ---- display pivot ----
    pivot = {"id": "pivot", "kind": "pivot-table", "name": name,
             "source": {"kind": "table", "elementId": "labeled"},
             "columns": [{"id": "pv_sec", "name": "Section", "formula": "[Labeled/Section]"},
                         {"id": "pv_so", "name": "Sec Order", "formula": "[Labeled/Sec Order]"},
                         {"id": "pv_line", "name": "Line Item", "formula": "[Labeled/Line Item]"},
                         {"id": "pv_lo", "name": "Line Order", "formula": "[Labeled/Line Order]"},
                         {"id": "pv_yr", "name": "Year", "formula": "[Labeled/Year]"},
                         {"id": "pv_v", "name": "Value", "formula": "Sum([Labeled/Value])"}],
             "values": ["pv_v"],
             "rowsBy": [{"columnId": "pv_sec", "sort": {"direction": "ascending", "by": "pv_so", "aggregation": "min"}},
                        {"columnId": "pv_line", "sort": {"direction": "ascending", "by": "pv_lo", "aggregation": "min"}}],
             "columnsBy": [{"columnId": "pv_yr", "sort": {"direction": "ascending"}}],
             "axisTotals": [{"axisId": "pv_sec", "visibility": "hidden"},
                            {"axisId": "pv_yr", "visibility": "hidden"},
                            {"axisId": "grand-row-total", "visibility": "hidden"},
                            {"axisId": "grand-column-total", "visibility": "hidden"}]}

    data_tbl = {"id": "datatbl", "kind": "table", "name": "FY results — hard-coded values (data page)",
                "source": dm("data"),
                "columns": [{"id": "dt_yr", "name": "Year", "formula": f"[{DMP}/Year]"}] +
                           [{"id": f"dt_{ln['col_id']}", "name": ln["label"] or ln["col_id"],
                             "formula": f"[{DMP}/{ln['col_id']}]"} for ln in data_lines[:40]]}

    input_pages = ([{"id": "inputs", "name": "Model Inputs", "elements": [research_input]}]
                   if research_input else [])
    plumbing = [item for item in [model_base, calc, long_el, dimw, labeled] if item]
    pages = [
        {"id": "main", "name": "FY results", "elements": [pivot]},
        {"id": "datap", "name": "Data page", "elements": [data_tbl]},
        *input_pages,
        {"id": "plumb", "name": "plumbing", "visibility": "hidden",
         "elements": plumbing},
    ]
    # Nested draft; wire_workbook flattens + wraps at the POST / dry-run boundary.
    return {"name": name, "schemaVersion": 1, "kind": "workbook",
            "folderId": folder, "pages": pages}


# ---------------------------------------------------------------- main
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", help="inferred research plan JSON")
    parser.add_argument("--conn", help="Sigma connection ID")
    parser.add_argument("--folder", help="Sigma folder ID")
    parser.add_argument("--name", help="workbook name")
    parser.add_argument("--source", help="source XLSX used to produce the plan")
    parser.add_argument("--review-dispositions", help="source-bound review dispositions JSON")
    parser.add_argument("--post", action="store_true", help="create the data model and workbook")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    with open(args.plan, encoding="utf-8") as stream:
        plan = json.load(stream)
    try:
        source_path, gate_report = gate_plan_source(
            plan,
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
    conn = args.conn; folder = args.folder
    if conn:
        plan.setdefault("targetScope", {})["connectionId"] = conn
    source_name = plan.get("source") or source_path.name
    name = args.name or (os.path.splitext(source_name)[0][:60] + " (auto)")
    do_post = args.post
    os.makedirs(OUTDIR, exist_ok=True)

    s = plan["summary"]; par = plan["parity"]
    tot = par.get("live", 0) + par.get("frozen", 0)
    print(f"Plan: {s.get('input',0)} input, {s.get('derived',0)} derived, {s.get('ratio',0)} ratio, "
          f"{s.get('needs_review',0)} needs-review; formula cells {par.get('live',0)}/{tot} live-verified, "
          f"{par.get('frozen',0)} frozen to Excel cached")
    print(f"Anchors: {list(plan['anchors'])}")

    if not (conn and folder):
        print("(dry-run needs --conn and --folder to embed real ids; writing spec skeletons anyway)")
    dm_spec, data_lines = build_dm(plan, conn or "<conn>", folder or "<folder>", name)
    with open(f"{OUTDIR}/dm_spec.json", "w", encoding="utf-8") as stream:
        json.dump(dm_spec, stream, indent=1)
    print(f"data columns (lines with typed values): {len(data_lines)} ; total lines: {len(plan['lines'])}")

    if not do_post:
        wb_spec = workbook_wire.wire_workbook(
            build_wb(plan, "<dm-id>", {"data": "data", "linedim": "linedim"},
                     data_lines, folder or "<folder>", name))
        with open(f"{OUTDIR}/wb_spec.json", "w", encoding="utf-8") as stream:
            json.dump(wb_spec, stream, indent=1)
        print(f"DRY RUN — {OUTDIR}/dm_spec.json + wb_spec.json. Re-run with --post (and --conn/--folder) to build live.")
        return 0

    e = env(); base = e["SIGMA_BASE_URL"]; tok = token(e)
    dm = api(base, tok, "POST", "/v2/dataModels/spec", dm_spec); dm_id = dm["dataModelId"]
    print("dataModelId:", dm_id)
    full = api(base, tok, "GET", f"/v2/dataModels/{dm_id}/spec")
    els = map_dm(full)
    # Layout is the last write before the current contents API validates + creates.
    wb_spec = workbook_wire.wire_workbook(
        build_wb(plan, dm_id, els, data_lines, folder, name))
    with open(f"{OUTDIR}/wb_spec_live.json", "w", encoding="utf-8") as stream:
        json.dump(wb_spec, stream, indent=1)
    checked = api(base, tok, "POST", "/v2/workbooks",
                  workbook_wire.dry_run_request(wb_spec))
    workbook_wire.assert_dry_run_success(checked)
    wb = api(base, tok, "POST", "/v2/workbooks", wb_spec)
    print("workbookId:", wb.get("workbookId"), "| url:", wb.get("url"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
