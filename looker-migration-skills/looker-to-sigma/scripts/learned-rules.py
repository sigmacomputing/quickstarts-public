#!/usr/bin/env python3
"""learned-rules — load + apply gap-scout translation rules (Looker → Sigma).

Rules live in the customer's HOME (`~/.looker-to-sigma/learned-rules.yaml`), NOT the
skill repo — so `git pull` of the skill never clobbers what a customer's scout has
discovered, and wins persist across every dashboard they migrate. Override the dir
with the `LOOKER_TO_SIGMA_HOME` env var. (Identical loader to the sibling Qlik/Power BI
copies; only the default home + env var differ.)

The conversion build step imports this and calls `apply()` on each LookML measure
expression before falling back to the converter / a WARN line.

    from learned_rules import load, apply
    rules = load(home="~/.looker-to-sigma")
    sigma_formula, hint = apply(rules, lookml_expr)   # (None, None) if no rule matches
"""
import os, re, yaml

def home_dir(home=None, env=None):
    if home: return os.path.expanduser(home)
    if env and os.environ.get(env): return os.path.expanduser(os.environ[env])
    return os.path.expanduser("~/.looker-to-sigma")

def load(home=None, env="LOOKER_TO_SIGMA_HOME"):
    path = os.path.join(home_dir(home, env), "learned-rules.yaml")
    if not os.path.exists(path): return []
    doc = yaml.safe_load(open(path)) or {}
    return doc.get("rules", [])

def apply(rules, expr):
    """Return (translated_formula, hint) for the first matching rule, else (None, None)."""
    for r in rules:
        pat = r.get("source_pattern") or r.get("tableau_pattern") or r.get("dax_pattern")
        tmpl = r.get("sigma_template")
        if not pat or not tmpl: continue
        m = re.search(pat, expr, re.IGNORECASE)
        if m:
            out = tmpl
            for i, g in enumerate(m.groups(), start=1):
                out = out.replace("\\%d" % i, g or "").replace("CAP%d" % i, g or "")
            return out, r.get("hint", "")
    return None, None

if __name__ == "__main__":
    import sys, json
    rules = load(home=(sys.argv[2] if len(sys.argv) > 2 else None))
    expr = sys.argv[1] if len(sys.argv) > 1 else ""
    out, hint = apply(rules, expr)
    print(json.dumps({"input": expr, "translated": out, "hint": hint, "rules_loaded": len(rules)}, indent=2))
