#!/usr/bin/env python3
"""Phase 1 (Discover): cheap regex scan of a LookML project (and/or model JSON)
for row-level-security (RLS) constructs, so the migration can make ONE
consolidated, reviewed decision about porting them to Sigma — never silently
drop RLS, never silently port a wrong mapping.

NEVER SILENT, but also NEVER SLOW when there's nothing to decide:
if no RLS construct is found, this prints NOTHING and exits 0 — the happy
path is untouched. When hits ARE found, it emits a structured summary (and a
recommended Sigma mapping per finding) and exits 0; pass --json for machine
output. Exit 2 only on a usage/IO error.

Looker RLS constructs detected (and their Sigma target):
  - access_filter    (explore: maps a user_attribute → a field)
                       → Sigma user attribute + a row filter
                         LookupUserAttributeText(...)/CurrentUserAttributeText(...)
  - sql_always_where (hardcoded row filter on an explore)
                       → Sigma data-model / element filter
  - access_grant     (model-level grant gating explores/fields/joins)
                       → note (review; map to Sigma permissions / a filter)
  - user_attribute   (any other reference, e.g. in a sql_always_where / Liquid)
                       → flagged so the user_attribute is provisioned in Sigma

Dependency-free (stdlib only). Mirrors the style of the other scripts here.

Usage:
    python3 detect_rls.py <lookml_dir_or_file> [<more> ...] [--json]
    # also accepts a model JSON (e.g. from `looker_api.py raw GET
    # /lookml_models/<model>/explores/<explore>`) — its access_filters /
    # sql_always_where show up the same way.

Scoping (bead 8nq5): a project dir can hold MANY models; RLS on a model the
converted dashboard never touches must not hard-stop the migration. Pass
    --scope-models m1,m2  and/or  --scope-explores e1,e2
to partition findings: a finding positively attributable to ANOTHER model
(source file `<other>.model.lkml`) or ANOTHER explore is demoted to
informational. Un-attributable findings (e.g. Liquid user_attribute refs in a
shared view file) stay IN scope — the safe default. With either flag, --json
emits {"findings": [...], "informational": [...]} instead of a bare list.
"""
import argparse
import json
import os
import re
import sys

# --- regexes (line/block tolerant; LookML is whitespace-loose) -------------
# access_filter blocks live inside an explore: access_filter { field: x  user_attribute: y }
_ACCESS_FILTER = re.compile(r"access_filter\s*:?\s*\{(.*?)\}", re.DOTALL)
_AF_FIELD = re.compile(r"\bfield\s*:\s*([A-Za-z0-9_.]+)")
_AF_USERATTR = re.compile(r"\buser_attribute\s*:\s*([A-Za-z0-9_.]+)")
# sql_always_where: <expr> ;;   (terminated by ;; or newline)
_SQL_ALWAYS_WHERE = re.compile(r"sql_always_where\s*:\s*(.*?)(?:;;|$)", re.DOTALL | re.MULTILINE)
# access_grant: name { user_attribute: x  allowed_values: [...] }
_ACCESS_GRANT = re.compile(r"access_grant\s*:\s*([A-Za-z0-9_]+)\s*\{(.*?)\}", re.DOTALL)
# any user_attribute reference (Liquid {{ _user_attributes['x'] }} or bare user_attribute: x)
_LIQUID_USERATTR = re.compile(r"_user_attributes\s*\[\s*['\"]([^'\"]+)['\"]\s*\]")
_BARE_USERATTR = re.compile(r"\buser_attribute\s*:\s*([A-Za-z0-9_.]+)")
# rough explore name, so we can attribute a finding to an explore
_EXPLORE = re.compile(r"\bexplore\s*:\s*([A-Za-z0-9_]+)\s*\{")


def _explore_for(text, pos):
    """Best-effort: the nearest `explore:` declared before `pos`."""
    last = None
    for m in _EXPLORE.finditer(text):
        if m.start() > pos:
            break
        last = m.group(1)
    return last


def scan_text(text, source):
    """Return a list of finding dicts for one file's text."""
    findings = []
    seen_userattrs = set()

    for m in _ACCESS_FILTER.finditer(text):
        body = m.group(1)
        field = _AF_FIELD.search(body)
        ua = _AF_USERATTR.search(body)
        ua_name = ua.group(1) if ua else None
        if ua_name:
            seen_userattrs.add(ua_name)
        findings.append({
            "construct": "access_filter",
            "source": source,
            "explore": _explore_for(text, m.start()),
            "field": field.group(1) if field else None,
            "user_attribute": ua_name,
            "sigma_mapping": "Sigma user attribute + row filter "
                             "(LookupUserAttributeText/CurrentUserAttributeText) on the field",
        })

    for m in _SQL_ALWAYS_WHERE.finditer(text):
        expr = m.group(1).strip()
        if not expr:
            continue
        for ua in _LIQUID_USERATTR.findall(expr):
            seen_userattrs.add(ua)
        findings.append({
            "construct": "sql_always_where",
            "source": source,
            "explore": _explore_for(text, m.start()),
            "field": None,
            "expression": expr,
            "sigma_mapping": "Sigma data-model / element filter "
                             "(if it references a user_attribute, use a user-attribute row filter)",
        })

    for m in _ACCESS_GRANT.finditer(text):
        name = m.group(1)
        body = m.group(2)
        ua = _BARE_USERATTR.search(body)
        ua_name = ua.group(1) if ua else None
        if ua_name:
            seen_userattrs.add(ua_name)
        findings.append({
            "construct": "access_grant",
            "source": source,
            "name": name,
            "user_attribute": ua_name,
            "sigma_mapping": "Note — review; map to Sigma permissions or a user-attribute filter "
                             "(access_grant gates explores/fields/joins, no 1:1 Sigma analog)",
        })

    # Any remaining user_attribute references (Liquid / bare) not already captured.
    for ua in _LIQUID_USERATTR.findall(text):
        if ua not in seen_userattrs:
            seen_userattrs.add(ua)
            findings.append({
                "construct": "user_attribute",
                "source": source,
                "user_attribute": ua,
                "sigma_mapping": "Provision the matching Sigma user attribute (reuse if it exists)",
            })

    return findings


def _iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for fn in files:
                    if fn.endswith((".lkml", ".lookml", ".json")):
                        yield os.path.join(root, fn)
        elif os.path.isfile(p):
            yield p
        else:
            print(f"detect_rls: no such path: {p}", file=sys.stderr)


def scan(paths):
    findings = []
    for fp in _iter_files(paths):
        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as e:
            print(f"detect_rls: cannot read {fp}: {e}", file=sys.stderr)
            continue
        # Model JSON: scan its raw text too — access_filters / sql_always_where
        # serialize as the same keywords, so the regexes still match.
        findings.extend(scan_text(text, os.path.relpath(fp)))
    return findings


def render(findings):
    by = {}
    for f in findings:
        by.setdefault(f["construct"], []).append(f)
    lines = []
    lines.append("ROW-LEVEL SECURITY DETECTED in the Looker source — review before building.")
    lines.append(f"  {len(findings)} finding(s) across {len(by)} construct type(s).")
    order = ["access_filter", "sql_always_where", "access_grant", "user_attribute"]
    for c in order:
        items = by.get(c)
        if not items:
            continue
        lines.append("")
        lines.append(f"  {c}  ({len(items)}):")
        for it in items:
            bits = []
            if it.get("explore"):
                bits.append(f"explore={it['explore']}")
            if it.get("field"):
                bits.append(f"field={it['field']}")
            if it.get("user_attribute"):
                bits.append(f"user_attribute={it['user_attribute']}")
            if it.get("name"):
                bits.append(f"name={it['name']}")
            if it.get("expression"):
                bits.append(f"where={it['expression']}")
            lines.append(f"    - {it['source']}: " + ("  ".join(bits) if bits else "(matched)"))
            lines.append(f"        → {it['sigma_mapping']}")
    lines.append("")
    lines.append("Next: present ONE consolidated RLS decision gate (confirm / edit / skip), "
                 "reuse existing Sigma user attributes + data models first, and record the "
                 "outcome (ported / skipped / reused) in the migration summary.")
    return "\n".join(lines)


_MODEL_FILE = re.compile(r"^(.+)\.model\.(?:lkml|lookml)$")


def split_scope(findings, models, explores):
    """Partition findings into (in_scope, informational). A finding is demoted
    ONLY when positively attributable to a model/explore outside the scope;
    anything ambiguous stays in scope (never silently drop real RLS)."""
    in_scope, info = [], []
    for f in findings:
        out = False
        m = _MODEL_FILE.match(os.path.basename(str(f.get("source") or "")))
        if models and m and m.group(1) not in models:
            out = True
        ex = f.get("explore")
        if explores and ex and ex not in explores:
            out = True
        (info if out else in_scope).append(f)
    return in_scope, info


def main():
    ap = argparse.ArgumentParser(description="Scan LookML for RLS constructs (silent if none).")
    ap.add_argument("paths", nargs="+", help="LookML dir(s)/file(s) and/or model JSON")
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    ap.add_argument("--scope-models", help="comma-separated model name(s) the dashboard uses — "
                    "findings on OTHER models become informational (bead 8nq5)")
    ap.add_argument("--scope-explores", help="comma-separated explore name(s) the dashboard uses — "
                    "findings on OTHER explores become informational")
    a = ap.parse_args()

    findings = scan(a.paths)
    scoped = bool(a.scope_models or a.scope_explores)
    informational = []
    if scoped:
        models = {m.strip() for m in (a.scope_models or "").split(",") if m.strip()}
        explores = {e.strip() for e in (a.scope_explores or "").split(",") if e.strip()}
        findings, informational = split_scope(findings, models, explores)

    # Zero-overhead happy path: nothing found → print nothing, exit clean.
    if not findings and not informational:
        if a.json:
            print(json.dumps({"findings": [], "informational": []}) if scoped else "[]")
        return 0

    if a.json:
        print(json.dumps({"findings": findings, "informational": informational}, indent=2)
              if scoped else json.dumps(findings, indent=2))
        return 0
    if findings:
        print(render(findings))
    if informational:
        print(f"\nINFORMATIONAL — {len(informational)} RLS finding(s) on model(s)/explore(s) "
              "this dashboard does NOT use (no decision needed for THIS migration; "
              "they matter when those models are migrated):")
        for it in informational:
            bits = [f"{k}={it[k]}" for k in ("explore", "field", "user_attribute", "name") if it.get(k)]
            print(f"  - [{it['construct']}] {it['source']}: " + ("  ".join(bits) or "(matched)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
