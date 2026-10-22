#!/usr/bin/env python3
"""
macro-classify.py — detect & classify Excel VBA macros, map each to its Sigma
disposition. Input: a .xlsm/.xlsb/.xls (VBA extracted via olevba) OR a raw VBA
source file (.bas/.cls/.frm/.vba/.txt). Output: a per-procedure inventory with a
Sigma target + porting status, plus a STOP-gate summary.

Porting status:
  AUTO    — reproduced by the data/formula conversion, or safely dropped (Sigma is live)
  CONTROL — becomes controls / parameters / an editable input table
  ACTION  — becomes an authorable Sigma Action (button/API/writeback/navigation)
  STORED_PROC — candidate for a call-stored-procedure action
  PYTHON_REVIEW — candidate for a Python code element after behavior/parity review
  DATA_REVIEW — external query/refresh must be re-sourced and verified
  FLAG    — must be reviewed by a human (external I/O or opaque imperative logic)

Never silent: every macro is surfaced with a disposition. A dropped macro the user
assumes still works is the FP&A equivalent of dropping row-level security.
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def extract_vba(path):
    """Return list of (proc_source) blocks' container code. Uses olevba for office
    binaries; reads text for raw VBA modules."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".bas", ".cls", ".frm", ".vba", ".txt"):
        return open(path, encoding="utf-8", errors="replace").read()
    # office container → olevba
    try:
        from oletools.olevba import VBA_Parser
    except ImportError:
        sys.exit("olevba not installed: pip install oletools  (or pass a .bas source file)")
    vp = VBA_Parser(path)
    if not vp.detect_vba_macros():
        return ""
    return "\n".join(code for (_f, _s, _name, code) in vp.extract_macros())

PROC_RE = re.compile(r"^[ \t]*(?:Public |Private |Friend )?(?:Static )?(Sub|Function)[ \t]+([A-Za-z0-9_]+)\s*\(", re.M)

def strip_comments(code):
    """Remove VBA comments (full-line and inline) so they can't drive classification.
    Respects string literals so a `'` inside "..." is kept."""
    out = []
    for line in code.splitlines():
        in_str = False; cut = len(line)
        for i, ch in enumerate(line):
            if ch == '"':
                in_str = not in_str
            elif ch == "'" and not in_str:
                cut = i; break
        out.append(line[:cut])
    return "\n".join(out)

def split_procedures(code):
    """Yield (name, kind, body) for each Sub/Function. Comments stripped first."""
    code = strip_comments(code)
    marks = [(m.start(), m.group(1), m.group(2)) for m in PROC_RE.finditer(code)]
    for i, (start, kind, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(code)
        yield name, kind, code[start:end]

# (label, status, regex signals, sigma target, note-template)
# Ordered by precedence — first matching class wins as PRIMARY; all hits reported.
RULES = [
    ("EXTERNAL_IO", "FLAG", [
        r"CreateObject\(\s*[\"']Outlook", r"SendMail", r"\bShell\b",
        r"ExportAsFixedFormat", r"FileSystemObject", r"Workbooks\.Open", r"\bKill\b",
        r"\bMkDir\b", r"\bEnviron\(", r"Open .* For (Output|Append|Input)"],
     "Sigma scheduled export / delivery, or external API job — usually NOT 1:1",
     "Reaches outside the workbook (email / file / shell / HTTP / PDF). Review: map to "
     "Sigma scheduled delivery or an external workflow; do not auto-port."),

    ("PYTHON_AUTOMATION", "PYTHON_REVIEW", [
        r"\bRunPython\b", r"\bxlwings\b", r"\bPyXLL\b",
        r"Application\.Run\s+[\"'][^\"']*(?:Python|PyXLL|xlwings)"],
     "Python code element + run-python-element action",
     "Python integration is representable, but packages, credentials, side effects, "
     "output shape, and parity must be reviewed before emitting code."),

    ("STORED_PROCEDURE", "STORED_PROC", [
        r"\badCmdStoredProc\b", r"\.CommandType\s*=\s*(?:4|adCmdStoredProc)\b",
        r"\.CommandText\s*=\s*[\"']\s*(?:EXEC(?:UTE)?|CALL)\s+",
        r"[\"']\s*(?:EXEC(?:UTE)?|CALL)\s+(?:\[[^\]]+\]|[A-Za-z_])"],
     "Sigma Action → call-stored-procedure",
     "A warehouse procedure call can become a call-stored-procedure effect. Confirm "
     "connection, fully-qualified path, signature, argument types, and side effects."),

    ("API_CALL", "ACTION", [
        r"MSXML2|WinHttp|ServerXMLHTTP",
        r"\.Open\s+[\"'](?:GET|POST|PUT|PATCH|DELETE)[\"']"],
     "Sigma Action → call-api (connector-backed)",
     "HTTP automation may map to call-api. Confirm connector ownership, authentication, "
     "arguments, response handling, retries, and secret boundaries."),

    ("EXTERNAL_DATA_REFRESH", "DATA_REVIEW", [
        r"\bRefreshAll\b", r"QueryTables(?:\.Add)?", r"\.QueryTable\b",
        r"ADODB\.(?:Connection|Recordset|Command)", r"\.CommandText\b",
        r"[\"']\s*(?:SELECT|WITH|INSERT|UPDATE|DELETE|MERGE)\b",
        r"WorkbookConnection", r"\.Connections\s*\("],
     "Governed warehouse/API source, data model, or stored procedure",
     "Refresh/query code is not automatically obsolete. Recreate the source pipeline, "
     "credentials, parameters, and refresh semantics, then verify data parity."),

    ("ACTION_WRITEBACK", "ACTION", [
        r"PasteSpecial\s+Paste:=xlPasteValues", r"ListRows\.Add",
        r"End\(xlUp\)[^\n]*\+\s*1"],   # nextRow = ...End(xlUp).Row + 1  → append target
     "Sigma Action → append rows to an input table (Scenarios / Snapshots)",
     "Button workflow that freezes/commits values into a history/scenario table. "
     "Becomes an Action that inserts rows into an input table."),

    ("WHATIF_SCENARIO", "CONTROL", [
        r"GoalSeek", r"Solver", r"Range\(\s*[\"']B\d", r"(Scenario|Assumption)",
        r"Select Case\s+\w*[Ss]cenario"],
     "Controls / parameters, or an editable assumptions input table",
     "Drives the model by changing assumption inputs (scenario swap / goal-seek). "
     "Maps to control parameters or the editable rates table; goal-seek → a what-if control."),

    ("TRANSFORM_ROLLUP", "PYTHON_REVIEW", [
        r"For\b.+\bTo\b", r"Cells\(\s*\w+\s*,.*\)\.Value\s*=", r"SumIf", r"WorksheetFunction"],
     "Data model formulas when proven equivalent; otherwise Python code element",
     "Imperative transforms cannot be assumed to evaporate. Translate declaratively "
     "when parity proves equivalence; otherwise route to reviewed Python."),

    ("RECALC", "AUTO", [
        r"\.Calculate(Full)?\b", r"Application\.Calculate\b", r"ScreenUpdating"],
     "None — Sigma is always live",
     "Local calculation/screen repaint wrapper. Safe to drop after formula parity."),

    ("NAVIGATION", "AUTO", [
        r"\.Activate\b", r"\.Select\b", r"\.Goto\b", r"\.Visible\s*="],
     "Page navigation / element visibility (or drop)",
     "Sheet/cell navigation. Map to Sigma page navigation or drop."),

    ("FORMAT_COSMETIC", "PYTHON_REVIEW", [
        r"\.Font\b", r"\.Interior\b", r"\.Borders\b", r"AutoFit", r"\.NumberFormat\b"],
     "Conditional formatting / element styling",
     "Formatting may encode business meaning. Inventory and map it, then render-check."),
]

RULES_MAP = {label: (status, target, note) for label, status, _s, target, note in RULES}
RULE_ORDER = {label: i for i, (label, *_) in enumerate(RULES)}
# bespoke-math fallback → OPAQUE: writes cells using non-declarative math
OPAQUE_MATH = re.compile(r"(Sin|Cos|Rnd|Sqr|Exp|Tan|Atn)\(|\bDo While\b|\bGoTo\b")
# only EXTERNAL_IO / ACTION_WRITEBACK outrank a bespoke-math FLAG
OPAQUE_OVERRIDABLE = {
    "WHATIF_SCENARIO", "TRANSFORM_ROLLUP", "NAVIGATION",
    "FORMAT_COSMETIC", "RECALC",
}


def classify(name, body):
    from lib.macro_behavior import _strip_comments, _analyze_body
    body = _strip_comments(body)
    # Header names are metadata, never executable routing evidence.
    body = "\n".join(line for line in body.splitlines()
                     if not PROC_RE.match(line) and not re.match(r"\s*End (Sub|Function)", line))
    behavior = _analyze_body(body)
    if (behavior['selectedRecord'] and behavior['writes']
            and not behavior['externalSideEffects']
            and not any(w['kind'] == 'append' for w in behavior['writes'])):
        return ('SELECTED_RECORD_UPDATE', 'ACTION',
                'Sigma Action → update selected input-table record',
                'Body updates selected record; bind real row ID, key, context, guards and outcome.',
                [w['target'] for w in behavior['writes'] if 'target' in w])
    hits = {}
    for label, status, sigs, target, note in RULES:
        matched = [s for s in sigs if re.search(s, body, re.I)]
        if matched:
            hits[label] = (status, target, note, matched)
    is_event = bool(re.match(r"(Workbook_|Worksheet_)", name))
    if hits:
        primary = min(hits, key=lambda l: RULE_ORDER[l])
        status, target, note, matched = hits[primary]
        # OPAQUE override: bespoke math + a weak/auto primary → flag for human review
        if primary in OPAQUE_OVERRIDABLE and OPAQUE_MATH.search(body):
            return "OPAQUE", "FLAG", "Human review — bespoke imperative logic", \
                   "Custom math writing cells (smoothing/allocation/iteration) with no clean declarative " \
                   "equivalent. Flag for a human to reproduce or confirm intent.", \
                   sorted({m for *_x, ms in hits.values() for m in ms})[:6]
        secondary = [l for l in hits if l != primary]
        tag = primary + (" + event-handler (auto-run)" if is_event else "")
        return tag, status, target, note, matched + ([f"(also: {', '.join(secondary)})"] if secondary else [])
    if OPAQUE_MATH.search(body):
        return "OPAQUE", "FLAG", "Human review — bespoke imperative logic", \
               "Custom imperative logic, no recognized pattern. Flag for human review.", []
    return "UNKNOWN", "FLAG", "Human review", "No recognized signals; review manually.", []

STATUS_ICON = {
    "AUTO": "✅ AUTO",
    "CONTROL": "🎛  CONTROL",
    "ACTION": "⚡ ACTION",
    "STORED_PROC": "🗄  STORED_PROC",
    "PYTHON_REVIEW": "🐍 PYTHON_REVIEW",
    "DATA_REVIEW": "🔌 DATA_REVIEW",
    "FLAG": "🚩 FLAG",
}

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    as_json = "--json" in sys.argv
    if not args:
        sys.exit("usage: macro-classify.py [--json] <file.xlsm | module.bas>")
    path = args[0]
    code = extract_vba(path)
    if not code.strip():
        print("[]" if as_json else f"No VBA macros found in {path}."); return
    procs = list(split_procedures(code))
    if as_json:
        import json
        from lib.macro_behavior import analyze_macro_source
        analysis = analyze_macro_source(path, source_kind=(
            "raw-module" if os.path.splitext(path)[1].lower() in
            (".bas", ".cls", ".frm", ".vba", ".txt") else "office-container-extraction"))
        by_name = {p['name']: p for p in analysis['procedures']}
        recs = []
        for name, kind, body in procs:
            cls, status, target, note, sigs = classify(name, body)
            recs.append({"name": name, "kind": kind, "class": cls, "status": status,
                         "sigmaTarget": target, "note": note, "signals": sigs,
                         "operation": by_name[name]['disposition']['operation'],
                         "analysis": {**{k: v for k, v in analysis.items() if k != 'procedures'},
                                      "procedure": by_name[name]}})
        print(json.dumps(recs, indent=2)); return
    print(f"# Macro inventory — {os.path.basename(path)}  ({len(procs)} procedures)\n")
    tally = {}
    for name, kind, body in procs:
        cls, status, target, note, sigs = classify(name, body)
        tally[status] = tally.get(status, 0) + 1
        print(f"## {name}  [{kind}]")
        print(f"   class    : {cls}")
        print(f"   status   : {STATUS_ICON.get(status, status)}")
        print(f"   → Sigma  : {target}")
        print(f"   note     : {note}")
        if sigs: print(f"   signals  : {', '.join(sigs[:6])}")
        print()
    print("=" * 64)
    print("DISPOSITION SUMMARY:", "  ".join(f"{STATUS_ICON[k].split()[0]} {k}={v}" for k, v in sorted(tally.items())))
    gated = sum(tally.get(status, 0) for status in
                ("ACTION", "STORED_PROC", "PYTHON_REVIEW", "DATA_REVIEW"))
    flagged = tally.get("FLAG", 0)
    if gated:
        print(f"\n⚠️  {gated} macro(s) have a Sigma route but require implementation "
              "and runtime/parity verification before migration is complete.")
    if flagged: print(f"🚩 {flagged} macro(s) require human review — DO NOT silently drop. Surface these to the user before build.")

if __name__ == "__main__":
    main()
