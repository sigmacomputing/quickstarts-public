# Visual-similarity floor — the deterministic gate under the visual verdict

`scripts/visual-similarity.py` is a deterministic sanity floor that runs before any
model-judged visual verdict counts. Its job is narrow: make it **impossible to record a
passing visual verdict over a render that is structurally nothing like the source**. It is
NOT a match-scorer and it does not measure migration quality — the RCF loop
(`refs/phase-5g-rcf.md`, `refs/fidelity-rubric.md`) and Phase 6 parity own that. A floor
pass means only "these two images are plausibly the same dashboard"; the real visual QA
still happens on top of it.

## Contract

```
python3 scripts/visual-similarity.py --source <src.png> --render <render.png> --json-out <out.json>
```

Exit codes: `0` = pass, `1` = fail, `2` = dependencies missing or input unreadable.
**Exit 2 is never a pass** — treat it as a blocked gate: fix the environment
(`bash scripts/bootstrap.sh` — installs Pillow/numpy `--user`, no admin) or
re-export the image, then re-run. The gate wiring must propagate 2 as a hard
stop, not fall through to the model verdict.

JSON written to `--json-out`:

| field           | meaning                                                                 |
|-----------------|-------------------------------------------------------------------------|
| `score_ink`     | 0–1. Render mark density (edges: text, bars, lines) as a fraction of the source's. Asymmetric — extra ink is never penalized; missing ink is. |
| `score_layout`  | 0–1. Spatial distribution agreement: worst-band ink balance over row/column thirds (dominant term), plus coarse ink-pattern and row/column profile correlations. |
| `score_overall` | 0–1. `aspect_factor * (0.42*score_ink + 0.58*score_layout)`.            |
| `threshold`     | The calibrated pass line for `score_overall` (currently **0.45**).      |
| `pass`          | `score_overall >= threshold` AND `score_ink >= 0.40` AND band balance `>= 0.10`. The two sub-floors catch sparse-marks and emptied-region failures even when the blend stays high. |
| `notes`         | Human-readable reasons for any failure or anomaly (blank source, aspect mismatch, tripped sub-floor). |
| `components`    | Diagnostic sub-signals (coverage, band_balance, pattern_corr, profile_corr, aspect_factor). |

The comparison is fully deterministic: same two files in → byte-identical JSON out. No
randomness, no model calls, no network.

## What the floor catches

- **Blank / mostly-empty pages** — render draws little or none of the source's ink.
- **One-bar-vs-six-bars panels** — panel chrome survives but the marks are gone
  (`score_ink` sub-floor at 0.40).
- **Missing whole columns / sections / tables** — a page region that holds content in the
  source is near-empty in the render (band-balance sub-floor at 0.10).
- **Single-column stacks** — a grid dashboard collapsed into one long column; the page's
  extreme aspect-ratio mismatch (>2.2x) zeroes the score.

## What the floor deliberately tolerates

Different fonts, colors, themes, padding, spacing, and margins; different aspect ratios
(landscape source → longer Sigma page is normal); moderate panel rearrangement and re-flow
(verified-faithful migrations in the calibration set include a 2x3 grid re-flowed to 4x3
and landscape→portrait re-stacks — all pass with margin). If a render passes the floor but
looks off, that is exactly what the RCF rubric is for.

## Threshold provenance — do not tune it

Threshold 0.45 and the sub-floors were calibrated on **20 verified-faithful migration
pairs** (real Tableau dashboard exports vs their accepted Sigma renders, spanning dense
KPI dashboards, app-style layouts, dark themes, text-heavy pages, and 10 chart-gallery
pages) plus **17 failure-mode negatives** (1 real failed field migration with 1-bar-vs-6
panels and whitespace, plus synthesized blank-page, half-page-empty, quarter-content, and
single-column-stack renders). Every positive clears the threshold by ≥ 0.08 and every
negative misses it by ≥ 0.10; the sub-floors clear their nearest positive by ≥ 0.10. The
per-pair table is embedded as a comment block in `scripts/visual-similarity.py`.

**If the floor fails, the render's STRUCTURE diverges from the source.** The fix is always
in the workbook: re-run the RCF loop, restore the missing sections/marks, and re-render.
Never raise `--threshold`-style knobs, edit the constants, or re-crop the screenshots to
squeeze a failing render through — a tuned floor is worse than no floor, because it
launders a broken render into a recorded visual pass.

## Dependencies

Pillow + numpy only (no OpenCV/scikit). If either is missing the script exits 2
with a remediation line — the fix is the bootstrap (`bash scripts/bootstrap.sh`,
which pip-installs them `--user`). Runtime is well under a second per pair.

## Tests

`python3 scripts/test_visual_similarity.py` — offline synthetic-fixture suite covering the
scoring behaviors (identical ≈ 1.0, recolored/shifted copy passes, blank / half-empty /
sparse / stacked renders fail) and the full CLI exit-code contract, including a
missing-dependency simulation.
