#!/usr/bin/env python3
"""Grounding regression for the Sisense->Sigma dashboard classifier (beads-sigma-kvza).

Proves convert.py / jaql_expr.py are documentation-grounded and loud-on-unmapped:
  1. CATALOGS      — all four refs/catalogs/*.json load, are cited (source doc +
     per-row doc URL), have unique sources, and are stamped sigma_verified=n
     (LIVE query-verification is deferred this pass).
  2. NO INLINE MAP — the viz/format/aggregation/control maps are DERIVED from the
     catalogs (grep the builders); no residual inline literal bypasses the single
     source of truth, and the specific name-guessing silent default is GONE.
  3. LOUD FALLBACKS — the killed silent default (currency title-substring guess)
     now WARNS on a non-currency mask and no longer fabricates a $ format from a
     'Revenue'/'Cost' title; an unknown widget type and an unmapped agg each warn/
     flag rather than silently emitting a wrong element or a default aggregate.
  4. COVERAGE       — refs/sisense-coverage.md is fresh vs the catalogs.

No byte-golden: convert.py mints random element ids and there is no offline
workbook fixture, so verbatim extraction (asserted in test_convert.py's parity)
plus these unit checks are the contract.

Run: python3 tests/test_grounding.py   (exit 0 = pass)
"""
import copy, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL, "scripts")
CATDIR = os.path.join(SKILL, "refs", "catalogs")
FIX = os.path.join(SKILL, "fixtures")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(SCRIPTS, "lib"))

DIMS = {"viz-kind", "number-format", "aggregation", "control"}


def test_catalogs_valid():
    import coverage_catalog as cc
    cats = cc.load_all(CATDIR)
    assert set(cats) == DIMS, sorted(cats)
    for name, cat in cats.items():
        assert cat.rows, "empty catalog: " + name
        assert cat.source_tool == "sisense", (name, cat.source_tool)
        assert cat.authoritative_doc.startswith("http"), (name, "authoritative_doc not a URL")
        seen = set()
        for r in cat.rows:
            key = str(r["source"]).lower()
            assert key not in seen, "duplicate source in %s: %s" % (name, key)
            seen.add(key)
            assert r.get("doc_ref", "").startswith("http"), (name, r["source"], "doc_ref not a URL")
            assert "sigma" in r, (name, r["source"], "row missing 'sigma' key")
            # sigma_verified is 'n' for EVERY row this pass (no false 'y' claims)
            assert (r.get("sigma_verified") or {}).get("status") == "n", \
                (name, r["source"], "sigma_verified must be 'n' this pass")
    print("[ok] catalogs: 4 dimensions load, cited, unique sources, all sigma_verified=n")


def test_no_inline_maps():
    conv = open(os.path.join(SCRIPTS, "convert.py")).read()
    jaql = open(os.path.join(SCRIPTS, "jaql_expr.py")).read()
    # builders load the catalogs
    assert "coverage_catalog" in conv and "_cc.load(" in conv, "convert.py does not load catalogs"
    assert "coverage_catalog" in jaql and "_cc.load(" in jaql, "jaql_expr.py does not load catalogs"
    # every enumerable map is catalog-derived, not an inline literal
    assert "for r in VIZ_CAT.rows" in conv, "WIDGET_MAP/SIGMA_KIND not derived from viz-kind catalog"
    assert "FMT_CAT.target(" in conv, "MONEY not derived from number-format catalog"
    assert "for r in CTRL_CAT.rows" in conv, "_CTRL_KIND not derived from control catalog"
    assert "for r in _AGG_CAT.rows" in jaql, "AGG not derived from aggregation catalog"
    # the killed name-guessing silent default must be gone (code, not prose)
    assert '"Revenue" in (jaql' not in conv, "name-guessing 'Revenue' title guess still present"
    assert '"Cost" in (jaql' not in conv, "name-guessing 'Cost' title guess still present"
    # no residual inline widget map literal (old shape: '"indicator": "kpi-chart"')
    assert '"indicator": "kpi-chart"' not in conv, "residual inline SIGMA_KIND literal"
    assert '"indicator":     ("kpi"' not in conv, "residual inline WIDGET_MAP literal"
    print("[ok] no-inline-map: viz/format/agg/control maps derived from catalogs; "
          "title-substring guess removed")


def test_loud_number_format():
    """The killed silent fallback: currency-by-title guessing is GONE, and a
    non-currency mask now WARNS instead of silently dropping the format."""
    import convert as C
    # a 'Revenue'/'Cost'-titled measure with NO currency mask must NOT get $ format
    assert C._money_fmt({"title": "Total Revenue"}) is None, "title-guess still fabricates $"
    assert C._money_fmt({"title": "Cost of Goods Sold"}) is None, "title-guess still fabricates $"
    # a real currency mask still yields the MONEY format (behavior preserved)
    assert C._money_fmt({"title": "x", "format": {"mask": {"currency": True}}}) == C.MONEY
    # a present-but-non-currency mask -> LOUD warn + ship unformatted
    warns = []
    got = C._money_fmt({"title": "Margin %", "format": {"mask": {"percent": True}}}, warns)
    assert got is None and warns and "non-currency" in warns[0], warns
    print("[ok] loud number-format: title guess removed; non-currency mask warns "
          "(ships unformatted)")


def _live_dashboard():
    dashboards = json.load(open(os.path.join(FIX, "dashboards.json")))
    return copy.deepcopy(next(d for d in dashboards
                              if d.get("title") == "ECommerce Overview (Live)"))


def test_loud_unknown_widget():
    """An unknown Sisense widget type -> flagged, no element (never faked)."""
    import convert as C
    model = json.load(open(os.path.join(FIX, "model_ecommerce.json")))
    d = _live_dashboard()
    ghost = copy.deepcopy(d["widgets"][0])
    ghost.update(type="bloxwidget", title="Weird BloX", oid="ghost-1")
    d["widgets"].append(ghost)
    dm_info = {"dataModelId": "dm-x", "factElementId": "fact-x", "factName": "Commerce"}
    spec, flags = C.convert_dashboard([d], model, dm_info)
    names = [e.get("name") for e in spec["pages"][1]["elements"]]
    assert "Weird BloX" not in names, "unmapped widget silently emitted an element"
    assert any(isinstance(f, dict) and f.get("type") == "bloxwidget" for f in flags), flags
    print("[ok] loud viz-kind: unknown widget 'bloxwidget' flagged, no element emitted")


def test_loud_unknown_agg():
    """An unmapped JAQL agg raises Unsupported (which the converter FLAGS) — never
    a silent default aggregate."""
    import jaql_expr as J
    raised = False
    try:
        J.translate_agg({"dim": "[Commerce.Revenue]", "agg": "sum_distinct"})
    except J.Unsupported as e:
        raised = "sum_distinct" in str(e)
    assert raised, "unmapped agg did not raise Unsupported"
    # sanity: a mapped agg still resolves through the catalog-derived dict
    assert J.translate_agg({"dim": "[Commerce.Revenue]", "agg": "sum"}) == "Sum([Revenue])"
    print("[ok] loud aggregation: unmapped agg 'sum_distinct' raises Unsupported (flagged)")


def test_coverage_matrix_fresh():
    r = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "gen-coverage-matrix.py"),
         "--catalogs", CATDIR, "--skill", "sisense",
         "--out", os.path.join(SKILL, "refs", "sisense-coverage.md"), "--check"],
        capture_output=True, text=True)
    assert r.returncode == 0, ("coverage matrix is stale — regenerate:\n" + r.stderr)
    print("[ok] coverage matrix: refs/sisense-coverage.md matches the catalogs")


if __name__ == "__main__":
    test_catalogs_valid()
    test_no_inline_maps()
    test_loud_number_format()
    test_loud_unknown_widget()
    test_loud_unknown_agg()
    test_coverage_matrix_fresh()
    print("ALL PASS")
