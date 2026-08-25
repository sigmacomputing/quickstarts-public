#!/usr/bin/env python3
"""Offline tests for visual-similarity.py (synthetic fixtures only).

Run: python3 scripts/test_visual_similarity.py
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "visual-similarity.py")

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    sys.stderr.write("tests require Pillow/numpy: pip install pillow numpy\n")
    sys.exit(2)


def _load_module():
    spec = importlib.util.spec_from_file_location("visual_similarity", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VS = _load_module()

# --- synthetic dashboard fixtures -------------------------------------------

BAR_HEIGHTS = [0.55, 0.8, 0.35, 0.95, 0.6, 0.45]


def draw_card(d, x0, y0, x1, y1, chrome, ink, accent, bars=6, lines=False):
    """One dashboard 'card': faint border, title bar, bar chart or text rows.

    bars < 6 models the mid-tier failure mode seen in the field: the panel
    chrome survives, but a single small bar sits where six categories should
    be, or a dense table collapses to a few stub rows, leaving whitespace
    (bar slots are always sized for six, so fewer bars = emptier panel).
    """
    d.rectangle([x0, y0, x1, y1], outline=chrome, width=1)
    d.rectangle([x0 + 8, y0 + 8, x1 - 8, y0 + 22], fill=accent)
    body_top, body_bot = y0 + 36, y1 - 12
    if lines:  # table-ish card; sparse variant drops most rows
        y = body_top
        step = 12 if bars >= 6 else 12 * 6 // max(1, bars)
        while y < body_bot - 6:
            d.rectangle([x0 + 12, y, x1 - 20, y + 4], fill=ink)
            y += step
        return
    span = (x1 - x0 - 24) / 6.0  # slot width is ALWAYS six-across
    scale = 1.0 if bars >= 6 else 0.5  # degenerate charts come out small too
    for i in range(bars):
        h = BAR_HEIGHTS[i % len(BAR_HEIGHTS)] * (body_bot - body_top) * scale
        bx0 = x0 + 12 + i * span
        bx1 = bx0 + span * 0.62
        d.rectangle([bx0, body_bot - h, bx1, body_bot], fill=accent)


def make_dashboard(w=1200, h=800, bg=(255, 255, 255), ink=(40, 40, 60),
                   accent=(46, 84, 158), bars=6, shift=0):
    """Deterministic synthetic dashboard: header + KPI row + 3x2 card grid.

    Card borders are drawn just above the background (delta < ink threshold),
    like modern borderless-card dashboards, so marks dominate the ink budget.
    """
    chrome = tuple(max(0, c - 10) for c in bg)
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im)
    s = shift
    d.rectangle([20 + s, 15 + s, w - 20 + s, 45 + s], fill=accent)  # header
    for k in range(4):  # KPI strip: value block + sparkline zigzag
        kx = 20 + s + k * (w - 40) // 4
        kx1 = kx + (w - 40) // 4 - 12
        d.rectangle([kx, 60 + s, kx1, 110 + s], outline=chrome, width=1)
        if bars >= 6:  # degenerate renders lose KPI innards, keep the frame
            d.rectangle([kx + 10, 70 + s, kx + 70, 86 + s], fill=ink)
            pts = [(kx + 10 + 7 * i, 100 + s - 8 * (i % 3)) for i in range(12)]
            d.line(pts, fill=accent, width=2)
    grid_top = 130 + s
    cw, ch = (w - 60) // 3, (h - grid_top - 30) // 2
    for r in range(2):
        for c in range(3):
            x0 = 20 + s + c * (cw + 10)
            y0 = grid_top + r * (ch + 10)
            draw_card(d, x0, y0, x0 + cw, y0 + ch, chrome, ink, accent,
                      bars=bars, lines=(c == 2))
    return im


def make_stack(src):
    """Catastrophe: the six grid cards restacked into one narrow column."""
    w, h = src.size
    cw, ch = (w - 60) // 3, (h - 130 - 30) // 2
    tiles = []
    for r in range(2):
        for c in range(3):
            x0, y0 = 20 + c * (cw + 10), 130 + r * (ch + 10)
            tiles.append(src.crop((x0, y0, x0 + cw, y0 + ch)))
    out = Image.new("RGB", (cw + 20, (ch + 10) * 6 + 20), (255, 255, 255))
    y = 10
    for t in tiles:
        out.paste(t, (10, y))
        y += ch + 10
    return out


class FixtureMixin:
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="vissim-test-")
        cls.paths = {}

        def save(name, im):
            p = os.path.join(cls.dir, name + ".png")
            im.save(p)
            cls.paths[name] = p
            return p

        src = make_dashboard()
        save("source", src)
        save("identical", src.copy())
        # recolored + font/padding-shifted copy: different palette, offset
        save("recolored", make_dashboard(bg=(244, 241, 252), ink=(70, 60, 90),
                                         accent=(180, 120, 60), shift=6))
        save("blank", Image.new("RGB", (1600, 900), (255, 255, 255)))
        half = src.copy()
        half.paste(Image.new("RGB", (src.width, src.height // 2),
                             (255, 255, 255)), (0, src.height // 2))
        save("halfempty", half)
        save("sparse", make_dashboard(bars=1))       # one bar vs six per panel
        save("stack", make_stack(src))               # single-column stack
        corrupt = os.path.join(cls.dir, "corrupt.png")
        with open(corrupt, "wb") as fh:
            fh.write(b"this is not a png file")
        cls.paths["corrupt"] = corrupt

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run_cli(self, source, render, json_out=None, env=None):
        json_out = json_out or os.path.join(self.dir, "out.json")
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--source", source, "--render", render,
             "--json-out", json_out],
            capture_output=True, text=True, env=env,
        )
        data = None
        if os.path.isfile(json_out) and proc.returncode in (0, 1):
            with open(json_out) as fh:
                data = json.load(fh)
        return proc, data


class TestScoring(FixtureMixin, unittest.TestCase):
    def test_identical_scores_near_one(self):
        res = VS.compare(self.paths["source"], self.paths["identical"])
        self.assertTrue(res["pass"])
        self.assertGreaterEqual(res["score_overall"], 0.98)
        self.assertGreaterEqual(res["score_ink"], 0.98)
        self.assertGreaterEqual(res["score_layout"], 0.98)

    def test_recolored_font_shifted_copy_passes(self):
        res = VS.compare(self.paths["source"], self.paths["recolored"])
        self.assertTrue(res["pass"], res)
        self.assertGreaterEqual(
            res["score_overall"], res["threshold"] + 0.05,
            "legit restyle must clear the threshold with margin",
        )

    def test_blank_render_fails(self):
        res = VS.compare(self.paths["source"], self.paths["blank"])
        self.assertFalse(res["pass"])
        self.assertLessEqual(res["score_overall"], res["threshold"] - 0.05)

    def test_half_empty_render_fails(self):
        res = VS.compare(self.paths["source"], self.paths["halfempty"])
        self.assertFalse(res["pass"])
        self.assertLessEqual(res["score_overall"], res["threshold"] - 0.05)

    def test_one_bar_vs_six_fails(self):
        res = VS.compare(self.paths["source"], self.paths["sparse"])
        self.assertFalse(res["pass"], res)
        self.assertLess(res["score_ink"], 0.40,
                        "mark-density floor should catch sparse panels")

    def test_single_column_stack_fails(self):
        res = VS.compare(self.paths["source"], self.paths["stack"])
        self.assertFalse(res["pass"], res)

    def test_symmetric_blank_source_noted(self):
        res = VS.compare(self.paths["blank"], self.paths["blank"])
        self.assertTrue(any("source appears blank" in n for n in res["notes"]))


class TestCLIContract(FixtureMixin, unittest.TestCase):
    def test_pass_exit_0_and_json_schema(self):
        out = os.path.join(self.dir, "nested", "dir", "verdict.json")
        proc, data = self.run_cli(self.paths["source"], self.paths["recolored"],
                                  json_out=out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for key, typ in (("score_layout", float), ("score_ink", float),
                         ("score_overall", float), ("pass", bool),
                         ("threshold", float), ("notes", list)):
            self.assertIn(key, data)
            self.assertIsInstance(data[key], typ)
        for key in ("score_layout", "score_ink", "score_overall"):
            self.assertGreaterEqual(data[key], 0.0)
            self.assertLessEqual(data[key], 1.0)

    def test_fail_exit_1(self):
        proc, data = self.run_cli(self.paths["source"], self.paths["blank"])
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(data["pass"])
        self.assertTrue(data["notes"], "failure must carry explanatory notes")

    def test_deterministic_output(self):
        out1 = os.path.join(self.dir, "det1.json")
        out2 = os.path.join(self.dir, "det2.json")
        self.run_cli(self.paths["source"], self.paths["recolored"], json_out=out1)
        self.run_cli(self.paths["source"], self.paths["recolored"], json_out=out2)
        with open(out1, "rb") as a, open(out2, "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_missing_input_exit_2(self):
        proc, _ = self.run_cli(os.path.join(self.dir, "nope.png"),
                               self.paths["source"])
        self.assertEqual(proc.returncode, 2)
        proc, _ = self.run_cli(self.paths["source"],
                               os.path.join(self.dir, "nope.png"))
        self.assertEqual(proc.returncode, 2)

    def test_corrupt_input_exit_2(self):
        proc, _ = self.run_cli(self.paths["source"], self.paths["corrupt"])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("could not analyze", proc.stderr)

    def test_missing_deps_exit_2_with_remediation(self):
        shim = os.path.join(self.dir, "shim")
        os.makedirs(shim, exist_ok=True)
        for mod in ("PIL", "numpy"):
            with open(os.path.join(shim, mod + ".py"), "w") as fh:
                fh.write("raise ImportError('simulated missing %s')\n" % mod)
        env = dict(os.environ)
        env["PYTHONPATH"] = shim
        proc, _ = self.run_cli(self.paths["source"], self.paths["identical"],
                               env=env)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("pip install pillow numpy", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
