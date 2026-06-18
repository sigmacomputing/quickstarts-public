# Looker complexity scoring rubric

Same framework as the other assessments — features classed **auto / hint / manual /
unhandled**; `cost = 10·n_unhandled + 3·n_manual + 1·n_hint`;
`value = dashboard_runs × sqrt(query_runs)` (or `5 × tile_count` proxy when usage is
unavailable); `score = value / (1 + cost)`.

Tags: `runs==0 and queries==0`→**retire**; `n_unhandled>=1`→**needs-gap-scout**;
`score>=20 and (manual+unhandled)==0`→**migrate-first**; `score>=10`→**easy-win**;
else **moderate**.

Looker-specific signals:

## 1. Tile vis-type → Sigma element coverage
Mirrors `looker-to-sigma`'s `build_workbook.py` tile map and the converter's coverage.

| Tier | Looker vis types |
|---|---|
| **auto** | `single_value`, `looker_single_record`, `table`, `looker_grid`, `looker_column`, `looker_bar`, `looker_line`, `looker_area`, `looker_scatter`, `looker_pie`, `looker_donut_multiples`, `looker_funnel`, `looker_google_map`, `text` (→ Sigma text element), `looker_timeline`, `looker_boxplot` |
| **manual** | `looker_map` / geo coordinates / choropleth, `looker_waterfall`, `looker_wordcloud`, `looker_heatmap`, `sankey` (recreate with the closest Sigma element) |
| **unhandled** | anything else — **marketplace / custom-viz extensions** (no direct Sigma equivalent) |
| **skipped** | `button`, `divider`, `image` — non-chart tiles; not counted as a migration cost |

## 2. Hard-to-migrate dashboard features (added to cost)
Detected on each tile's backing query (direct `query` or `result_maker.query`):

| Feature | Detected via | Tier | Sigma mapping |
|---|---|---|---|
| **Pivot** | `query.pivots` non-empty | `manual` | Sigma pivot table (`rowsBy` + `columnsBy`) |
| **Table calc** | `query.dynamic_fields` (a JSON string of calcs) | `manual` | Sigma formula (running_total → `CumulativeSum`, `sum()` → `GrandTotal`, etc.) |
| **Liquid** | `{{ }}` / `{% %}` anywhere in the query JSON | `manual` | re-author (parameterized SQL / dynamic refs) |
| **Merged result** | `merge_result_id` on the element / result_maker | `unhandled` | multiple explores stitched into one tile → a data-model join, reviewed case by case |
| **Custom / marketplace viz** | vis type outside the known set | `unhandled` | recreate or accept loss — needs review |

Each `manual` feature adds +1 to the dashboard's `n_manual`; each `unhandled`
feature adds +1 to `n_unhandled`. (`merge_result_id` adds to `n_unhandled`;
`custom_viz` is already counted when the tile's vis bucket is `unhandled`.)

## 3. Value (usage) — from System Activity
Looker exposes usage well through the `system__activity` model — query it via
`POST /queries/run/json`. The assessment uses three queries (window = `--usage-days`,
default 90):

| Query | model / view | fields | filters |
|---|---|---|---|
| **Dashboard runs** | `system__activity` / `history` | `dashboard.id`, `dashboard.title`, `history.query_run_count`, `history.dashboard_run_count` | `history.created_date: "<N> days"`, `dashboard.id: NOT NULL` |
| **Look usage** | `system__activity` / `history` | `look.id`, `look.title`, `history.query_run_count` | `history.created_date: "<N> days"`, `look.id: NOT NULL` |
| **Activity totals** | `system__activity` / `history` | `user.count` (active users), `history.query_run_count`, `history.dashboard_run_count` | `history.created_date: "<N> days"` |

- **Usage mode:** `value = dashboard_runs × √query_runs`.
- **Proxy (no System Activity access / cold dashboard):** `value = 5 × tile_count`.

> The `dashboard.view_count` / `favorite_count` fields on `GET /dashboards` come back
> `null` on the live instance — **do not** rely on them; System Activity is the
> authoritative usage source.

## Output (`inventory.json`)
Per dashboard: `{id, name, kind (UDD|LookML), folder, owner, runs, queries, tiles,
filters, viz_types:{...}, features:{pivots, table_calcs, merged_results, custom_viz,
liquid, cross_filtering}, n_auto, n_hint, n_manual, n_unhandled, cost, score, tag}`.
See `refs/output-shapes.md` for the full document shape.
