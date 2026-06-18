# Output shapes

`looker-inventory.py` emits **one JSON file** (`inventory.json`) plus a compact
`readout.md` to `<out>/`. `render-readout-html.rb` reads `inventory.json` alone to
produce the Sigma-branded `readout.html`; `looker-to-sigma` reads the `shortlist`
array.

Like `qlik-assessment` (and unlike `tableau-assessment`'s three files), Looker packs
everything into a single `inventory.json` — the REST API enumerates an instance's
environment, usage, and per-dashboard complexity in one pass. The renderer's section
vocabulary lines up with the other assessments
(dashboard↔workbook, tile↔sheet/view, explore↔datasource-field-set,
model↔semantic-layer, connection↔datasource, Look↔view, dashboard run↔access event).

## `inventory.json` (written by `looker-inventory.py`)

`--no-deep` mode writes the same shape with per-dashboard complexity fields all zero
and `feature_usage` / `viz_mix` empty.

```json
{
  "instance": {
    "name": "<host>",                       // e.g. hakkoda1.cloud.looker.com
    "url": "https://<host>",
    "generated_at": "YYYY-MM-DD",
    "usage_window_days": <int>,             // --usage-days (default 90)
    "mode": "rest-4.0 + deep" | "rest-4.0 inventory-only"
  },
  "environment_overview": {
    "models": <int>,
    "explores": <int>,                      // summed across all models
    "projects": <int>,
    "connections": <int>,
    "looks": <int>,
    "dashboards": <int>,
    "dashboards_udd": <int>,                // numeric id
    "dashboards_lookml": <int>,             // "model::name" id
    "users": <int>,                         // enabled (falls back to total if all enabled)
    "groups": <int>,
    "folders": <int>
  },
  "connections": {
    "n_connections": <int>,
    "dialects": [{ "dialect": "snowflake|bigquery|...", "n": <int> }, ...],
    "detail": [{ "name": "...", "dialect": "...", "database": "...", "host": "..." }, ...]
  },
  "activity": {                             // from system__activity / history
    "active_users": <int>,                  // user.count over the window
    "queries": <int>,                       // history.query_run_count
    "dashboard_runs": <int>,                // history.dashboard_run_count
    "looks_used": <int>,
    "look_usage": [{ "id": "<look id>", "queries": <int> }, ...]   // top 25
  },
  "feature_usage": {                        // summed across all scanned dashboards
    "pivots": <int>, "table_calcs": <int>, "merged_results": <int>,
    "custom_viz": <int>, "liquid": <int>, "cross_filtering": <int>
  },
  "viz_mix": [{ "type": "<looker vis type>", "n": <int> }, ...],
  "ownership": [
    { "owner": "<name/email>", "dashboards": <int>, "runs": <int>, "tiles": <int> }, ...
  ],
  "shortlist": [
    {
      "id": "<dashboard id>", "name": "...", "kind": "UDD"|"LookML",
      "folder": "...", "owner": "...",
      "runs": <int>, "queries": <int>,      // System Activity over the window
      "tiles": <int>, "filters": <int>,
      "viz_types": { "<type>": <int>, ... },
      "features": { "pivots": <int>, "table_calcs": <int>, "merged_results": <int>,
                    "custom_viz": <int>, "liquid": <int>, "cross_filtering": <int> },
      "n_auto": <int>, "n_hint": <int>, "n_manual": <int>, "n_unhandled": <int>,
      "cost": <int>, "score": <float>,
      "tag": "migrate-first"|"easy-win"|"moderate"|"needs-gap-scout"|"retire"
    }
  ],
  "dashboards": <int>, "models": <int>      // back-compat top-level counts
}
```

`shortlist` is sorted by `score` descending — index 0 is the top migration
candidate. The renderer treats the first 5 as the pilot and the first 15 as the
displayed shortlist + complexity table.

## Complexity buckets
Mirrors the other assessments' four-tier vocabulary (see `refs/complexity-scoring.md`):

- `n_auto` — tiles whose vis type Sigma covers directly.
- `n_hint` — reserved for parity with the shared renderer (Looker does not currently
  emit a `hint` tier; always 0).
- `n_manual` — **Setup**: pivots, table calcs, Liquid, and `manual`-tier vis types
  (geo / waterfall / heatmap / sankey).
- `n_unhandled` — **Review**: merged results and marketplace / custom-viz extensions.

## Scoring + tags
`cost = 10·n_unhandled + 3·n_manual + 1·n_hint`;
`value = dashboard_runs × √query_runs` (or `5 × tile_count` proxy when usage is
unavailable); `score = value / (1 + cost)`.

Tag rules:
- `runs == 0 and queries == 0`                   → `retire`
- `n_unhandled >= 1`                             → `needs-gap-scout`
- `score >= 20 and (manual + unhandled) == 0`    → `migrate-first`
- `score >= 10`                                  → `easy-win`
- else                                           → `moderate`

## `readout.html` / `readout.md`
`readout.html` is an 8-section Sigma-branded report: masthead + hero, 01 environment,
02 dashboard priority & usage, 03 ownership, 04 connections & dialects, 05 migration
shortlist + per-dashboard complexity, 07 estimated effort (tokens/$), 08 data
handling, 09 next steps. Sections 05/07 collapse out in `--no-deep` mode (no
shortlist), renumbering data-handling to 05 and next-steps to 06. `readout.md` is the
compact text equivalent written by the Python script.
