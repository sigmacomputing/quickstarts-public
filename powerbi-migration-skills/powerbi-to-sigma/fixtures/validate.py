#!/usr/bin/env python3
"""Validate every .bim fixture in this directory.

Checks each file is valid JSON and follows the TMSL shape of model_clean.bim:
- top-level `compatibilityLevel` and `model`
- `model.tables` is a non-empty list
- at least one table carries `measures`
- every measure has a `name` + `expression`; every calculated column has a
  `type == "calculated"` + `expression`

Prints a per-fixture count of explicit measures and calculated columns, then a
total. Exits non-zero if any fixture fails a structural assertion.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def validate(path: Path):
    """Return (n_measures, n_calc_columns). Raises AssertionError on bad shape."""
    with path.open() as fh:
        model = json.load(fh)  # raises JSONDecodeError if not valid JSON

    assert "compatibilityLevel" in model, "missing top-level compatibilityLevel"
    assert "model" in model, "missing top-level 'model'"
    tables = model["model"].get("tables")
    assert isinstance(tables, list) and tables, "model.tables must be a non-empty list"

    n_measures = 0
    n_calc_cols = 0
    has_any_measures = False

    for t in tables:
        assert "name" in t, "table missing name"
        # partitions are required for a real TMSL table
        assert t.get("partitions"), f"table {t['name']} missing partitions"

        for m in t.get("measures", []) or []:
            has_any_measures = True
            assert m.get("name"), f"measure missing name in table {t['name']}"
            assert m.get("expression"), f"measure {m.get('name')} missing expression"
            n_measures += 1

        for c in t.get("columns", []) or []:
            if c.get("type") == "calculated":
                assert c.get("expression"), (
                    f"calc column {c.get('name')} missing expression"
                )
                n_calc_cols += 1

    assert has_any_measures, "no table in the model carries any measures"
    return n_measures, n_calc_cols


def main():
    bims = sorted(HERE.glob("*.bim"))
    assert bims, "no .bim fixtures found"

    total_m = total_c = 0
    failures = []
    print(f"Validating {len(bims)} fixture(s) in {HERE}\n")
    for p in bims:
        try:
            nm, nc = validate(p)
        except (AssertionError, json.JSONDecodeError) as e:
            failures.append((p.name, str(e)))
            print(f"  FAIL  {p.name}: {e}")
            continue
        total_m += nm
        total_c += nc
        print(f"  PASS  {p.name}: {nm} measures, {nc} calc columns")

    print(f"\nTOTAL: {total_m} measures + {total_c} calc columns "
          f"= {total_m + total_c} DAX expressions across {len(bims)} fixtures")

    if failures:
        print(f"\n{len(failures)} fixture(s) FAILED")
        sys.exit(1)
    print("\nAll fixtures valid.")


if __name__ == "__main__":
    main()
