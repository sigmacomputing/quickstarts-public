# Tableau story points → Sigma pages

**Disposition: scripted pattern (beads-sigma-y6b).** Tableau stories are
sequential slide decks — each `<story-point>` captures a dashboard or
worksheet plus a navigator caption. Sigma has no story primitive; the
translation is **one Sigma page per story point, in story order**, with the
caption as both the page name and an annotation text element atop the page.

## Detection

`scripts/parse-twb-layout.rb` parses both story XML shapes:

- older: `<story name='X'> … <flipboard><story-points><story-point …/>`
- newer: `<dashboard name='X' type-v2='storyboard'>` containing the same
  flipboard tree (these dashboards are flagged `is_story: true` in
  `dashboard-layout.json` — do NOT build a regular page from a storyboard's
  flipboard chrome)

When any story exists, the parser writes **`story-plan.json`** next to the
layout output:

```json
[
  { "story": "FY26 Performance",
    "points": [
      { "id": "12", "caption": "Where we landed",
        "captured_sheet": "Overview Dash", "sheet_kind": "dashboard" },
      { "id": "13", "caption": "Regional attainment deep-dive",
        "captured_sheet": "Attainment by Region", "sheet_kind": "worksheet" }
    ] }
]
```

`sheet_kind` is resolved against the workbook's dashboard / worksheet name
sets: `dashboard` points clone a whole converted page, `worksheet` points
clone a single element.

`scan-workbook-gaps.rb` also reports `<story` usage (manual row) so the gap
report sets expectations before conversion.

## Build: `scripts/build-story-pages.rb`

Two passes, mirroring `build-dashboard-layout.rb`:

**Pass 1 — spec (before POST).** Appends one page per story point to the
workbook spec:

```bash
ruby scripts/build-story-pages.rb \
  --story-plan /tmp/<name>/story-plan.json \
  --spec /tmp/<name>/wb-spec.json \
  --out  /tmp/<name>/wb-spec-with-story.json \
  [--story "FY26 Performance"] [--replace-source-pages]
```

Per point: page named by the caption (truncated to ~58 chars, deduped with
`(2)` suffixes), an annotation text element
(`sp<N>-story-annotation`: caption + "Story point i of n · ◀ prev | next ▶"
navigation strip), and clones of the captured page's elements with fresh ids
(`sp<N>-` prefix). Cloned **controls get suffixed `controlId`s and every
cloned calc formula referencing them is rewritten** — the same discipline as
`build-charts-from-signals.rb --page-per-worksheet`. Cloned charts keep their
`source.elementId` (the Data-page master), so story pages share the master's
queries. `--replace-source-pages` drops the captured originals for a
story-only workbook.

**Pass 2 — layout (after `post-and-readback.rb`).** Banded layout per story
page: annotation in the dark header band (`lib/layout.rb#banded_page`
`header_el:`), charts tiled 2-per-row and reflowed:

```bash
ruby scripts/build-story-pages.rb \
  --story-plan /tmp/<name>/story-plan.json \
  --wb-ids /tmp/<name>/wb-ids.json \
  --layout-out /tmp/<name>/story-layout.xml
```

Writes `story-layout.xml` (only the story `<Page>` blocks — merge with the
workbook's other page layouts before `put-layout.rb`) plus
`story-layout.xml.elements.json` (container/header sidecar keyed by page id;
`put-layout.rb` injects these).

## What does NOT translate

- **Tableau's prev/next flipboard navigation** — Sigma's page tab bar IS the
  navigation; the annotation strip names the neighbors. There is no
  spec-level "go to page" button.
- **Per-point filter/highlight state divergence** (a story point that captures
  the same sheet twice with different filters): clone the page twice (the
  script does) and bake the per-point filter states by hand — or use
  `build-bookmark-workbooks.py` for one workbook per state.
- **Story-point UPDATE captions** (Tableau's "update" points that re-capture a
  modified state) carry no diffable XML — both points clone the same sheet;
  reapply the visual deltas manually.
