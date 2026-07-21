#!/usr/bin/env python3
"""Regression test for the sisense empty/vacuous-parity guards (2026-07-10).

Before: verify_parity.run([]) printed "0/0 GREEN" and returned True, and
verify_layout was GREEN with zero placed widgets — so an empty/placeholder
workbook passed both "must be GREEN" gates. These guards refuse a vacuous pass.
Offline (no Sisense/Snowflake needed): the empty paths never query.

    python3 scripts/test_verify_guards.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(cond, msg):
    print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        fails.append(msg)


# 1) verify_parity.run([]) must be falsy (was True → vacuous green).
spec = importlib.util.spec_from_file_location("vp", os.path.join(HERE, "verify_parity.py"))
vp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vp)
check(vp.run([], "tj") is False, "verify_parity.run([]) returns False (no vacuous 0/0 GREEN)")

# 2) verify_layout on an EMPTY dashboard/spec must exit non-zero (was GREEN).
with tempfile.TemporaryDirectory() as d:
    dash = os.path.join(d, "dash.json")
    spc = os.path.join(d, "spec.json")
    json.dump([{"title": "Empty", "widgets": []}], open(dash, "w"))
    json.dump({"pages": [{"id": "p", "elements": []}], "layout": ""}, open(spc, "w"))
    r = subprocess.run([sys.executable, os.path.join(HERE, "verify_layout.py"), dash, spc],
                       capture_output=True, text=True)
    check(r.returncode != 0, f"verify_layout on empty dashboard exits non-zero (got {r.returncode})")
    check("NON-EMPTY" in r.stdout, "verify_layout runs the NON-EMPTY check")

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("ALL PASS")
