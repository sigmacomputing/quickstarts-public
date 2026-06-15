# Output shapes

`qlik-inventory.py` emits **one JSON file** (`inventory.json`) plus a compact
`readout.md` to `<out>/`. `render-readout-html.rb` reads `inventory.json` alone
to produce the Sigma-branded `readout.html`; `qlik-to-sigma` reads the
`shortlist` array.

Unlike `tableau-assessment` (three JSON files) and `powerbi-assessment` (four),
Qlik packs everything into a single `inventory.json` — there is no separate
`complexity.json` / `shortlist.json`, because qlik-cli enumerates an app's
measures, charts, usage, and flags in one pass. The renderer's section
vocabulary still lines up with the other assessments (app↔workbook,
sheet↔view, master measure↔measure, space↔project, data connection↔datasource,
Section Access↔RLS, DirectQuery↔live, reload↔refresh).

## `inventory.json` (written by `qlik-inventory.py`)

Inventory-only mode (no `--deep`) writes the same shape with per-app complexity
fields all zero and `connection_types` possibly empty.

```json
{
  "tenant": {
    "name": "<tenant host or QLIK_TENANT>",
    "url": "<QLIK_TENANT_URL or ''>",
    "generated_at": "YYYY-MM-DD",
    "mode": "qlik-cli + deep" | "qlik-cli inventory-only"
  },
  "environment_overview": {
    "apps": <int>,
    "sheets": <int>,            // summed across apps (deep only; else 0)
    "master_measures": <int>,   // summed master-measure count (deep only; else 0)
    "spaces": <int>,
    "data_connections": <int>
  },
  "data_sources": {
    "n_connections": <int>,
    "n_directquery_apps": <int>,        // isDirectQueryMode = true
    "n_inmemory_apps": <int>,           // apps - directquery
    "n_section_access_apps": <int>,     // hasSectionAccess = true
    "n_file_based_connections": <int>,  // connection type matches qvd/csv/xls/file/folder
    "connection_types": [{ "type": "<str>", "n": <int> }, ...]
  },
  "reload_activity": {
    "by_status": [{ "status": "SUCCEEDED|FAILED|unknown|...", "n": <int> }, ...],
    "avg_duration_s": <float>|null,
    "max_duration_s": <float>|null,
    "n_with_duration": <int>
  },
  "ownership": [
    { "owner": "<name/email>", "apps": <int>, "views": <int>, "measures": <int> }, ...
  ],
  "shortlist": [
    {
      "id": "...", "name": "...", "space": "...", "owner": "...",
      "views": <int>,                 // itemViews — 28-day rolling window
      "reloadStatus": "...", "lastReload": "...", "reloadDurationS": <num>|null,
      "sectionAccess": <bool>, "directQuery": <bool>,
      "sheets": <int>, "measures": <int>,
      "n_auto": <int>, "n_hint": <int>, "n_manual": <int>, "n_unhandled": <int>,
      "measure_buckets": { "auto": <int>, "manual": <int>, "unhandled": <int> },
      "viz_types": { "<qViz type>": <int>, ... },
      "cost": <int>, "score": <float>,
      "tag": "migrate-first"|"easy-win"|"moderate"|"needs-gap-scout"|"retire"
    }
  ],
  "apps": <int>, "spaces": <int>     // back-compat top-level counts
}
```

`shortlist` is sorted by `score` descending — index 0 is the top migration
candidate. The renderer treats the first 5 as the pilot and the first 15 as the
displayed shortlist + complexity table.

## Complexity buckets

Mirrors the other assessments' four-tier vocabulary (see
`refs/complexity-scoring.md`):

- `n_auto` — master measures + charts that convert mechanically.
- `n_hint` — reserved for parity with the shared renderer (Qlik does not
  currently emit a `hint` tier; always 0).
- `n_manual` — **Setup**: Set Analysis (→ Sigma `SumIf`), `Class()` binning,
  manual-recreate viz (mekko/funnel/sankey/map/...), **plus** +1 each for
  `sectionAccess` and `directQuery`.
- `n_unhandled` — **Review**: `Aggr()`, `Dual()`, selection-state functions,
  `Range*`, alternate states, and Qlik extensions / custom-viz objects.

## Scoring + tags

`cost = 10·n_unhandled + 3·n_manual + 1·n_hint`;
`value = itemViews × √itemViews` (or `10×(charts + measures/4)` proxy when usage
is unavailable); `score = value / (1 + cost)`.

Tag rules:
- `views == 0`                                   → `retire`
- `n_unhandled >= 1`                             → `needs-gap-scout`
- `score >= 20 and (manual + unhandled) == 0`    → `migrate-first`
- `score >= 10`                                  → `easy-win`
- else                                           → `moderate`

## `readout.html` / `readout.md`

`readout.html` is an 8-section Sigma-branded report (see
`refs/readout-template.md`): masthead + hero, 01 environment, 02 app priority &
usage, 03 ownership, 04 data sources & load-script patterns, 05 reload activity,
06 migration shortlist + per-app complexity, 07 data handling, 08 next steps.
Sections 06–08 collapse to 06–07 in inventory-only mode (no shortlist).
`readout.md` is the compact text equivalent written by the Python script.
