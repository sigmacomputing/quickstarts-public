#!/usr/bin/env python3
"""Route an Excel workbook: audit + discover + classify, then print the next steps as JSON.

usage: migrate.py plan <file.xlsx|.xlsm> [--out-dir DIR]

Writes migration-audit.json, discovery.json and (when the audit has review issues)
review.template.json into DIR (default: the workbook's folder). Prints a JSON routing
record: audit status and issues, archetype, the refs worth reading, the decisions to
ask the user, the next commands, and the steps only the user can do in the Sigma UI.
Exit 2 only when the audit is BLOCKED.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))

from forecast_plan import PlanDraftError, draft_plan  # noqa: E402
from migration_gate import source_sha256  # noqa: E402
from xlsx_audit import audit_workbook  # noqa: E402

MACRO_SUFFIXES = {".xlsm", ".xlsb", ".xls"}
RESEARCH_HINTS = ("FY results", "PER SHARE", "PROFIT AND LOSS", "__FDSCACHE__")
PRESENTATION_CODES = {"CHARTS_PRESENT", "DATA_VALIDATION_PRESENT", "CONDITIONAL_FORMATTING_PRESENT"}


def run_json(*args):
    out = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)
    if out.returncode:
        lines = (out.stderr or out.stdout).strip().splitlines()
        raise RuntimeError(lines[-1] if lines else f"exit {out.returncode}")
    return json.loads(out.stdout)


def archetype(discovery):
    if any(hint in name for name in discovery.get("sheets", []) for hint in RESEARCH_HINTS):
        return "research"
    report = {s["sheet"]: s["classes"] for s in discovery.get("reportSheets", [])}
    if any(c.get("ACTUAL") or c.get("DRIVER_GROWTH") for c in report.values()):
        return "forecast"
    if discovery.get("tables"):
        return "input-table"
    return "unknown"


ROUTES = {
    "forecast": {
        "refs": ["refs/sigma-build-gotchas.md", "refs/model-taxonomy.md", "refs/forecast-recipes.md"],
        "decisions": ["intent: read-only | editable | what-if", "write-enabled connectionId", "target folderId"],
        "next": [
            "python scripts/draft-forecast-plan.py <file> --intent <intent> --connection <conn> "
            "--folder <folder> --out <workdir>/plan.json   # fails loudly on unknown shapes; verifies against cached values",
            "python scripts/build-forecast-model.py <workdir>/plan.json --out-dir <workdir>/build   "
            "# dry run: draft mode + local parity",
            "python scripts/build-forecast-model.py <workdir>/plan.json --post "
            "--review-dispositions <workdir>/review.json   # production: strict dispositions",
        ],
        "handoffs": ["Paste seed CSVs into the rate/manual input tables", "Publish the workbook"],
    },
    "research": {
        "refs": ["refs/sigma-build-gotchas.md", "refs/research-recipes.md", "refs/research-template-coa.md"],
        "decisions": ["sheet name and first/last line-item rows", "write-enabled connectionId", "target folderId"],
        "next": [
            "python scripts/infer-canonical-formulas.py <file> --sheet=<sheet> --first-row=<n> "
            "--last-row=<n> --out <workdir>/plan.json --draft",
            "python scripts/build-research-model.py <workdir>/plan.json --conn <conn> --folder <folder>   # dry run",
            "python scripts/build-research-model.py <workdir>/plan.json --conn <conn> --folder <folder> "
            "--post --review-dispositions <workdir>/review.json",
        ],
        "handoffs": ["Publish the workbook"],
    },
    "input-table": {
        "refs": ["refs/sigma-build-gotchas.md", "refs/input-tables.md", "refs/excel-translation.md"],
        "decisions": ["fact Table and canonical grain", "write-enabled connectionId"],
        "next": [
            "python scripts/xlsx-to-input-csv.py <file> --table <table> --out <workdir>/seed.csv",
            "python scripts/build-input-table-wb.py --name <name> --connection <conn> --columns <COL:type,...>",
            "python scripts/build-dm-on-view.py ...   # after the warehouse view exists",
        ],
        "handoffs": ["Paste seed.csv into the input table", "Publish", "Create warehouse view on the input table"],
    },
    # SUMIFS / driver signals, but not the shape the forecast drafter and builder support.
    "cell-model": {
        "refs": ["refs/sigma-build-gotchas.md", "refs/model-taxonomy.md", "refs/source-workbook-model.md",
                 "refs/workbook-expression-context.md", "refs/native-calculations.md"],
        "decisions": ["edit intent per sheet (read-only report / editable plan / live what-if)",
                      "which sheets and ranges carry the model", "write-enabled connectionId", "target folderId"],
        "next": [
            "python scripts/source-workbook.py <file> --out <workdir>/source-model.json   "
            "# source-bound cell/formula inventory",
            "Build source-specific with Sigma MCP Code Mode per refs/model-taxonomy.md; no bundled "
            "builder fits this shape (see routeReason)",
        ],
        "handoffs": [],
    },
    "unknown": {
        "refs": ["refs/sigma-build-gotchas.md", "refs/model-taxonomy.md"],
        "decisions": ["what the workbook is used for (entry vs report)"],
        "next": ["python scripts/xlsx-discover.py <file>   # read the human report and ask the user"],
        "handoffs": [],
    },
    "blocked": {
        "refs": [],
        "decisions": ["remove or replace the blocker (see issues), then re-run plan"],
        "next": [],
        "handoffs": [],
    },
}


def plan(args):
    source = Path(args.workbook).expanduser().resolve()
    if not source.is_file():
        print(f"source workbook not found: {source}", file=sys.stderr)
        return 1
    workdir = Path(args.out_dir or source.parent).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    audit = audit_workbook(source)
    (workdir / "migration-audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    blocked = audit["status"] == "BLOCKED"

    discovery, macros, notes = {}, None, []
    if blocked:
        kind = "blocked"
    else:
        try:
            discovery = run_json(HERE / "xlsx-discover.py", source, "--json")
        except RuntimeError as error:
            print(f"discovery failed: {error}", file=sys.stderr)
            return 1
        (workdir / "discovery.json").write_text(json.dumps(discovery, indent=2) + "\n", encoding="utf-8")
        kind = archetype(discovery)
    route_reason = None
    if kind == "forecast":
        # Same shape checks the drafter applies, so the route never names a command that
        # fails on this workbook. Placeholder connection/folder: nothing is written.
        try:
            _, shape = draft_plan(source, intent="what-if", connection="<connection>", folder="<folder>")
            route_reason = (f"forecast drafter accepts this workbook: {shape['lines']} lines "
                            f"{shape['kinds']} on {shape['reportSheet']!r}")
        except PlanDraftError as error:
            kind = "cell-model"
            route_reason = f"SUMIFS/driver signals, but the forecast drafter rejects the shape: {error}"
    route = ROUTES[kind]
    refs = list(route["refs"])

    if not blocked and source.suffix.lower() in MACRO_SUFFIXES:
        try:
            macros = run_json(HERE / "macro-classify.py", "--json", source)
        except RuntimeError as error:
            macros = {"error": str(error)}
            notes.append(f"macro-classify failed ({error}); resolve it before building.")
        refs.append("refs/macro-handling.md")
    if any(i.get("code") in PRESENTATION_CODES for i in audit.get("issues", [])):
        refs.append("refs/presentation-migration.md")

    digest = source_sha256(source)
    review_issues = [i for i in audit.get("issues", []) if i.get("severity") != "blocker"]
    review_template = {
        "sourceSha256": digest,
        "issues": [{"code": i["code"], "owner": "", "disposition": "", "verified": False}
                   for i in review_issues],
    }
    if review_template["issues"]:
        (workdir / "review.template.json").write_text(json.dumps(review_template, indent=2) + "\n",
                                                      encoding="utf-8")

    def fill(command):
        return command.replace("<file>", shlex.quote(str(source))).replace("<workdir>", shlex.quote(str(workdir)))

    result = {
        "source": str(source),
        "sourceSha256": digest,
        "auditStatus": audit["status"],
        "issues": [{"code": i["code"], "severity": i.get("severity"), "route": i.get("route")}
                   for i in audit.get("issues", [])],
        "archetype": kind,
        "routeReason": route_reason,
        "modelMap": {s["sheet"]: s["classes"] for s in discovery.get("reportSheets", [])},
        "tables": [{"name": t["name"], "sheet": t["sheet"], "rows": t["rows"]} for t in discovery.get("tables", [])],
        "macros": macros,
        "readRefs": list(dict.fromkeys(refs)),
        "beforePost": ["refs/coverage-contract.md"],
        "askUser": route["decisions"],
        "nextCommands": [fill(c) for c in route["next"]],
        "userHandoffs": route["handoffs"],
        "reviewTemplate": str(workdir / "review.template.json") if review_template["issues"] else None,
        "notes": notes + [
            "Local builds (no --post) run in draft mode; pending review issues do not block them.",
            "Fill review.template.json (owner, disposition, verified) only after the feature is built "
            "and checked, before --post.",
            "BLOCKED stops everything." if blocked else "Not blocked.",
        ] + (["The drafter may add plan review issues (e.g. FLAT_CARRY_POLICY); add their codes to "
              "review.json too before --post."] if kind == "forecast" else []),
    }
    print(json.dumps(result, indent=2))
    return 2 if blocked else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="audit, discover and print next steps")
    p.add_argument("workbook")
    p.add_argument("--out-dir", help="where to write audit/discovery/review-template JSON")
    args = parser.parse_args(argv)
    return plan(args)


if __name__ == "__main__":
    raise SystemExit(main())
