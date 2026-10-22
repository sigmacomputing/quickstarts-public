#!/usr/bin/env python3
"""Phase 0 — discover an .xlsx workbook.

Inventories formal Tables (the migration's Rosetta Stone), pivots/charts, and a
formula census (flagging untranslatable / report-style sheets). Prints a summary
and, for each formal Table, its columns + inferred grain.

Usage:
    python xlsx-discover.py "Sample Forecast.xlsx"
"""
import sys
import re
import json
from collections import Counter
from datetime import date, datetime
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from lib.excel_expression import ExpressionError, Reference, parse_expression

# functions we translate today (see refs/excel-translation.md)
TRANSLATABLE = {
    "IF", "IFS", "SWITCH", "IFERROR", "AND", "OR", "NOT",
    "SUM", "SUMIF", "SUMIFS", "COUNT", "COUNTA", "COUNTIF", "COUNTIFS",
    "AVERAGE", "AVERAGEIF", "AVERAGEIFS", "MIN", "MAX", "MEDIAN",
    "VLOOKUP", "XLOOKUP", "HLOOKUP", "INDEX", "MATCH", "LOOKUP",
    "LEFT", "RIGHT", "MID", "LEN", "CONCAT", "CONCATENATE", "TRIM",
    "UPPER", "LOWER", "SUBSTITUTE", "FIND", "TEXT",
    "TODAY", "NOW", "YEAR", "MONTH", "DAY", "DATEDIF", "EDATE",
    "EOMONTH", "WEEKDAY", "DATE",
    "ROUND", "ROUNDUP", "ROUNDDOWN", "CEILING", "FLOOR", "ABS", "POWER", "MOD",
    "SUMPRODUCT",
}
# fail-loud: these usually mark a "report drawn in cells" needing manual rebuild
VOLATILE = {"OFFSET", "INDIRECT", "INDEX_VOLATILE"}

FUNC_RE = re.compile(r"\b([A-Z][A-Z0-9_.]+)\s*\(")
PK_RE = re.compile(r"(^id|_id|id|code|key|num)$", re.I)
# headers that look like a spread dimension (a wide cross-tab axis)
WIDE_HDR_RE = re.compile(
    r"^(\d{4}([-_/ ]?\d{1,2})?|\d{1,2}[-_/ ]\d{2,4}|"
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|q[1-4]|fy\d+|\d+)$", re.I)


def chart_title(chart):
    """Return the visible chart title without depending on openpyxl internals."""
    if not chart.title:
        return "(untitled)"
    if isinstance(chart.title, str):
        return chart.title
    try:
        paragraphs = chart.title.tx.rich.p
        text = "".join(
            run.t or ""
            for paragraph in paragraphs
            for run in paragraph.r
        )
        return text or "(untitled)"
    except (AttributeError, TypeError):
        return "(untitled)"


def chart_anchor(chart):
    """Return an A1-style top-left anchor for one/two-cell chart anchors."""
    if isinstance(chart.anchor, str):
        return chart.anchor
    marker = getattr(chart.anchor, "_from", None)
    if marker is None:
        return "(unknown)"
    return f"{get_column_letter(marker.col + 1)}{marker.row + 1}"


def classify(headers, body_rows, nrows, referenced_by_others):
    """Return (route, why) — entered → input table; derived → read-only DM;
    reference → maintained-list (input table if users maintain it)."""
    analysis = analyze_table(headers, body_rows, nrows, referenced_by_others)
    return analysis["route"], analysis["reason"], bool(analysis["wideAxis"])


def _date_axis(value):
    if isinstance(value, (date, datetime)):
        return True
    if isinstance(value, str):
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False
    return False


def analyze_table(headers, body_rows, nrows, referenced_by_others):
    """Separate literal source cells from formulas before choosing a table route."""
    columns = []
    for index, header in enumerate(headers):
        literals, formulas, blanks = [], [], []
        numeric = 0
        for row in body_rows:
            cell = row[index]
            value = cell.value
            if cell.data_type == "f":
                formulas.append(cell.coordinate)
            elif value is None or value == "":
                blanks.append(cell.coordinate)
            else:
                literals.append(cell.coordinate)
                numeric += isinstance(value, (int, float)) and not isinstance(value, bool)
        role = ("MIXED_REVIEW" if literals and formulas else
                "DERIVED" if formulas else "SOURCE" if literals else "EMPTY_REVIEW")
        columns.append({"name": str(header) if header is not None else "",
                        "role": role, "literalCells": len(literals),
                        "formulaCells": len(formulas), "blankCells": len(blanks),
                        "literalCellRefs": literals, "formulaCellRefs": formulas,
                        "_numeric": numeric})

    pk = any(PK_RE.search(str(h).strip()) for h in headers if h)
    wide = sum(1 for h in headers if h and WIDE_HDR_RE.match(str(h).strip()))
    date_values = [row[0].value for row in body_rows if row[0].value is not None] if body_rows else []
    measure_axis = (len(date_values) >= 3 and
                    sum(_date_axis(v) for v in date_values) >= len(date_values) * 0.8 and
                    sum(c["_numeric"] >= max(3, nrows * 0.8) and c["formulaCells"] == 0
                        for c in columns[1:]) >= 3)
    wide_axis = "POSSIBLE_MEASURE_AXIS" if measure_axis else "CALENDAR_HEADERS" if wide >= 4 else None
    for column in columns:
        del column["_numeric"]
    roles = {column["role"] for column in columns}
    if roles == {"EMPTY_REVIEW"}:
        route = "REVIEW"
        reason = "blank template has no observed entry or formula provenance"
    elif "MIXED_REVIEW" in roles or "EMPTY_REVIEW" in roles or {"SOURCE", "DERIVED"} <= roles:
        route = "MIXED"
        reason = "literal source cells and formula cells require separate routes; review edit intent"
    elif roles == {"DERIVED"}:
        route = "DERIVED"
        reason = "formula columns require live calculations"
    elif nrows <= 30 and pk and referenced_by_others:
        route = "REFERENCE"
        reason = "small referenced key table; review whether users maintain it"
    else:
        route = "ENTERED"
        reason = "literal source columns are candidates for editable input"
    action = ("Review editable source columns and map formula columns to live calculations; "
              "never seed formula results as inputs." if route == "MIXED" else
              "Review template intent and intended entry columns before choosing a route." if route == "REVIEW" else
              "Review whether this reference list is maintained." if route == "REFERENCE" else
              "Map formulas to live calculations." if route == "DERIVED" else
              "Review whether literal source values should remain editable.")
    if wide_axis:
        action += " Review the possible wide measure axis and grain before any unpivot."
    return {"route": route, "reason": reason, "wideAxis": wide_axis,
            "columns": columns, "action": action}


SHEET_REF_RE = re.compile(r"(?:'([^']+)'|([A-Za-z0-9_]+))!\$?[A-Z]+\$?\d+")
GROWTH_RE = re.compile(r"^=\s*\$?[A-Z]+\$?\d+\s*\*\s*\(\s*1\s*[+\-]", re.I)   # prior*(1±rate)
SUMIFS_RE = re.compile(r"\bSUMIFS?\b|\bSUMPRODUCT\b", re.I)
ARITH_RE  = re.compile(r"[A-Z]+\$?\d+\s*[-+*/]\s*\$?[A-Z]+\$?\d+|^=IF\(", re.I)


def direct_reference(formula, sheet):
    """Return a local cell reference only when the whole formula is that edge."""
    if not isinstance(formula, str) or not formula.startswith("="):
        return None
    try:
        expression = parse_expression(formula, sheet=sheet)
    except ExpressionError:
        return None
    if isinstance(expression, Reference) and expression.value.address:
        return expression.value
    return None

def classify_report_cells(wb):
    """Cell-level model map for 'report drawn in cells' sheets (no formal Table).
    Returns per-sheet counts by class + the detected source/driver sheets."""
    table_sheets = {ws.title for ws in wb.worksheets if len(ws.tables)}
    sheetmap = {}          # sheet -> Counter of classes
    source_sheets = Counter()   # tabs feeding SUMIFS (actuals source)
    driver_sheets = Counter()   # tabs referenced by growth (1+rate) formulas
    for ws in wb.worksheets:
        if ws.title in table_sheets:
            continue
        counts = Counter()
        # which rows contain a formula (to spot manual literals sitting among formulas)
        rows_with_formula = set()
        numeric_cells = []
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if c.data_type == "f":
                    rows_with_formula.add(c.row)
                elif isinstance(v, (int, float)) and c.column > 1:
                    numeric_cells.append(c)
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if c.data_type != "f":
                    continue
                if isinstance(v, str) and SUMIFS_RE.search(v):
                    counts["ACTUAL"] += 1
                    for m in SHEET_REF_RE.finditer(v):
                        source_sheets[m.group(1) or m.group(2)] += 1
                elif isinstance(v, str) and GROWTH_RE.match(v):
                    counts["DRIVER_GROWTH"] += 1
                    for m in SHEET_REF_RE.finditer(v):
                        driver_sheets[m.group(1) or m.group(2)] += 1
                elif direct_reference(v, ws.title):
                    counts["DEPENDENCY_LINK"] += 1
                elif isinstance(v, str) and ARITH_RE.search(v):
                    counts["DERIVED"] += 1
                else:
                    counts["OTHER_FORMULA"] += 1
        # manual inputs = numeric literals sitting in rows that are otherwise formula-driven
        manual = sum(1 for c in numeric_cells if c.row in rows_with_formula)
        if manual:
            counts["MANUAL"] = manual
        if counts:
            sheetmap[ws.title] = counts
    return sheetmap, source_sheets, driver_sheets


def dependency_links(wb):
    """Keep direct-reference formulas as live edges with their source coordinates."""
    table_sheets = {ws.title for ws in wb.worksheets if ws.tables}
    links = {}
    for ws in wb.worksheets:
        if ws.title in table_sheets:
            continue
        sheet_links = []
        for row in ws.iter_rows():
            for cell in row:
                ref = direct_reference(cell.value, ws.title) if cell.data_type == "f" else None
                if ref:
                    sheet_links.append({"cell": cell.coordinate,
                                        "sourceSheet": ref.sheet,
                                        "sourceCell": ref.address})
        if sheet_links:
            links[ws.title] = sheet_links
    return links


def main(path, json_output=False):
    wb = load_workbook(path, data_only=False)

    # all formula strings (with their sheet) — for cross-sheet reference detection
    all_formulas = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.data_type == "f":
                    text = c.value if isinstance(c.value, str) else getattr(c.value, "text", None)
                    if isinstance(text, str):
                        all_formulas.append((ws.title, text))

    # ---- formal Tables + routing ----
    tables = []
    for ws in wb.worksheets:
        for name in ws.tables:
            ref = ws.tables[name].ref
            cells = ws[ref]
            headers = [c.value for c in cells[0]] if cells else []
            body = cells[1:] if cells else []
            nrows = len(body)
            referenced = any(s != ws.title and (ws.title in f or name in f)
                             for s, f in all_formulas)
            analysis = analyze_table(headers, body, nrows, referenced)
            tables.append({"name": name, "sheet": ws.title, "ref": ref,
                           "rows": nrows, **analysis})

    sheetmap, source_sheets, driver_sheets = classify_report_cells(wb)
    links = dependency_links(wb)
    if json_output:
        print(json.dumps({"source": str(path), "sheets": wb.sheetnames, "tables": tables,
                          "reportSheets": [{"sheet": sheet, "classes": dict(counts),
                                            "dependencyLinks": links.get(sheet, [])}
                                           for sheet, counts in sheetmap.items()]}, indent=2))
        return

    print(f"# Discovery: {path}\n")
    print(f"Sheets ({len(wb.sheetnames)}): {', '.join(wb.sheetnames)}\n")

    print(f"## Formal Tables ({len(tables)}) — with routing")
    routes = Counter()
    for table in tables:
        name, sheet, ref, nrows = (table[key] for key in ("name", "sheet", "ref", "rows"))
        route, why, wide = table["route"], table["reason"], table["wideAxis"]
        headers = [column["name"] for column in table["columns"]]
        routes[route] += 1
        tag = {"ENTERED": "✏️  ENTERED", "DERIVED": "🔒 DERIVED",
               "REFERENCE": "📒 REFERENCE", "MIXED": "⚠️ MIXED",
               "REVIEW": "❓ REVIEW"}[route]
        print(f"\n  • {name}  (sheet '{sheet}', {ref}, ~{nrows} rows)  →  {tag}")
        print(f"    columns: {', '.join(str(h) for h in headers)}")
        print(f"    routing: {why}")
        for column in table["columns"]:
            print(f"    {column['name']}: {column['role']} "
                  f"({column['literalCells']} literal, {column['formulaCells']} formula, "
                  f"{column['blankCells']} blank)")
        print(f"    action: {table['action']}")
        if wide:
            print(f"    ⚠️ {wide}: review the axis and grain before choosing a reshape")
    if not tables:
        print("  (none — workbook is likely 'report drawn in cells'; expect manual rebuild)")
    else:
        print(f"\n  routing summary: " + ", ".join(f"{n} {r.lower()}" for r, n in routes.items()))
        print("  → Route literal source and formula columns separately; review edit intent and "
              "preserve formula dependencies.")

    # ---- pivots / charts ----
    n_charts = sum(len(getattr(ws, "_charts", [])) for ws in wb.worksheets)
    n_pivots = sum(len(getattr(ws, "_pivots", [])) for ws in wb.worksheets)
    print(f"\n## Visuals: {n_charts} chart(s), {n_pivots} pivot table(s)")
    for ws in wb.worksheets:
        for chart in getattr(ws, "_charts", []):
            chart_type = chart.__class__.__name__.removesuffix("Chart")
            print(
                f"  • {chart_type} chart '{chart_title(chart)}' "
                f"(sheet '{ws.title}', anchor {chart_anchor(chart)})"
            )

    # ---- formula census ----
    func_counts = Counter()
    formula_cells = 0
    report_sheets = Counter()
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.data_type == "f":
                    formula_cells += 1
                    text = c.value if isinstance(c.value, str) else getattr(c.value, "text", None)
                    for m in FUNC_RE.findall(text) if isinstance(text, str) else ():
                        func_counts[m] += 1
                        if m in VOLATILE:
                            report_sheets[ws.title] += 1
    print(f"\n## Formula census: {formula_cells} formula cells, "
          f"{len(func_counts)} distinct functions")
    untranslatable = {f: n for f, n in func_counts.items()
                      if f not in TRANSLATABLE and f in VOLATILE}
    unknown = {f: n for f, n in func_counts.items()
               if f not in TRANSLATABLE and f not in VOLATILE}
    top = func_counts.most_common(15)
    print("  top functions:", ", ".join(f"{f}×{n}" for f, n in top))
    if untranslatable:
        print(f"  ⚠️ volatile/untranslatable (manual rebuild): "
              + ", ".join(f"{f}×{n}" for f, n in untranslatable.items()))
        print(f"     report-style sheets: {', '.join(report_sheets)}")
    if unknown:
        print(f"  ❓ not yet in the rules table (verify): "
              + ", ".join(f"{f}×{n}" for f, n in sorted(unknown.items())))

    # ---- derived report sheets (formula-driven, no formal table) ----
    table_sheets = {ws.title for ws in wb.worksheets if len(ws.tables)}
    per_sheet = Counter(s for s, _ in all_formulas)
    derived = [s for s, n in per_sheet.items() if n and s not in table_sheets]
    if derived:
        print(f"\n## Formula report sheets (no formal table): "
              f"{', '.join(derived)}")
        print("  Review formula dependencies and any literal inputs before choosing "
              "computed or editable targets.")

    # ---- cell-level MODEL MAP (for report-drawn-in-cells models; see refs/model-taxonomy.md) ----
    if sheetmap:
        print("\n## Model map (cell-level) — for report sheets drawn in cells")
        ICON = {"ACTUAL": "📥 ACTUAL (live source)", "DRIVER_GROWTH": "📈 DRIVER-grown",
                "MANUAL": "✏️  MANUAL input", "DERIVED": "🧮 DERIVED", "DEPENDENCY_LINK": "🔗 live dependency",
                "OTHER_FORMULA": "❓ review formula"}
        for sheet, counts in sheetmap.items():
            parts = [f"{ICON.get(k,k)}={v}" for k, v in counts.most_common()]
            print(f"  • {sheet}: " + ", ".join(parts))
            if sheet in links:
                print("    direct links: " + ", ".join(
                    f"{item['cell']}={item['sourceSheet']}!{item['sourceCell']}" for item in links[sheet]))
        if source_sheets:
            print(f"  → actuals source (SUMIFS targets): {', '.join(source_sheets)}  "
                  f"= live read-only DM element")
        if driver_sheets:
            print(f"  → driver/assumptions sheet (1±rate refs): {', '.join(driver_sheets)}  "
                  f"= editable rates table / controls")
        if source_sheets and driver_sheets:
            print("  Candidate driver forecast: review source, driver, and manual-input roles "
                  "before using refs/forecast-recipes.md.")
        else:
            print("  Review report formulas and dependencies before choosing a build architecture.")
        print("  Review intended edits and source freshness before building. "
              "See refs/model-taxonomy.md.")

    print("\nNext: review source roles, edit intent, dependency links, and any wide axis "
          "before choosing builders; macros → macro-classify.py.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: xlsx-discover.py <file.xlsx> [--json]")
    main(sys.argv[1], json_output="--json" in sys.argv[2:])
