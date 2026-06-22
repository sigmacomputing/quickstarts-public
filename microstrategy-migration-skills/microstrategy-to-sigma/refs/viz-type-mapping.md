# Dossier visualization types → Sigma element kinds

What the dossier API exposes per visualization is **shallow**: only
`visualizationType` + `definition.grid` (`rows` / `columns` / `metrics` /
`crossTab` / `metricsPosition`). There are no slot/encoding details beyond
which attributes and metrics sit on which grid axis. The converter therefore
maps `visualizationType` → a Sigma element kind via this lookup, feeds the
grid axes into the closest Sigma slots, and falls back to a **flagged table**
(data preserved, loud warning) for anything unmapped — never silently wrong.

**Status legend** — *extraction validated*: the type was pulled from real
demo-content dossiers and its `definition.grid` parsed as documented.
*Build*: whether the Sigma-element emission is part of the validated path
(the live-validated fixture used grid reports; chart emission is roadmap).

Counts below are from a 365-dossier / ~7,400-viz sweep of MicroStrategy's
public demo environment (Tutorial, MobileDashboards, Embedded Analytics,
AI Auto projects, 2026-06) — the extractor walker parsed **all** of them,
so every listed type is extraction-validated. Counts double as gap priority.

| MSTR `visualizationType` | n | Sigma element kind | Build |
|---|---|---|---|
| `grid` | 1893 | `table` (pivot when `crossTab: true`) | **validated (parity-verified)** |
| `kpi` | 1633 | `kpi-chart` | roadmap (top priority by volume) |
| `bar_chart` | 810 | `bar` | roadmap |
| `geospatial_service` | 331 | `region-map` / `point-map` (by geo attribute granularity — cognos `tiledmap` precedent) | roadmap |
| `line_chart` | 252 | `line` | roadmap |
| `bubble_chart` | 221 | `scatter` (size slot) | roadmap |
| `heat_map` | 188 | flagged `table` (size+color tile grid has no Sigma analog) | fallback |
| `combo_chart` | 182 | `combo` | roadmap |
| `area_chart` | 170 | `area` | roadmap |
| `multi_metric_kpi` | 168 | one `kpi-chart` per metric | roadmap |
| `compound_grid` | 155 | `table` | roadmap |
| `microcharts` | 113 | `table` + flagged sparkline columns | fallback |
| `ring_chart` | 111 | `pie` (donut variant) | roadmap |
| `google_map` | 104 | `region-map` / `point-map` | roadmap |
| `pie_chart` | 90 | `pie` | roadmap |
| `comparison_kpi` | 67 | `kpi-chart` (comparison value flagged) | roadmap |
| `sankey` | 42 | flagged `table` | fallback |
| `gauge` | 33 | `kpi-chart` (gauge bands flagged) | fallback |
| `histogram` | 27 | `bar` (pre-binned) or flagged | fallback |
| `network` | 25 | flagged `table` | fallback |
| `waterfall` | 23 | flagged `table` | fallback |
| `esri_map` | 21 | `region-map` / `point-map` | roadmap |
| `box_plot` | 16 | `box` if available, else flagged | fallback |
| `key_driver`, `time_series`, `auto_narratives`, `sequences_sunburst`, `forecast_line_chart`, `PageBy`, `ImageOverlay` | ≤12 ea | flagged `table` | fallback |
| **custom/marketplace vizzes** — any `HC*` (Highcharts), `D3*`, `Vitara*`, `EChart*`, `Arria*`, `Google*`, `CardWidget`, `RadarChart`, `SimpleKPIChart`, … | ~230 total | flagged `table` — third-party viz plugins, unconvertible by definition | fallback |
| *anything else* | — | flagged `table` fallback | fallback |

Custom-viz names are not a closed set (they're marketplace plugins) — treat
any type not in this table as custom and flag it.

**Structural-feature frequencies** from the same sweep (extractor handles all
of these; converter coverage noted): selectors 51% of dossiers, chapter
filters 49%, multi-dataset 42%, free-form `fields` — text 65% / image 54% /
shape 33% / **html 11%** — and nested panelStacks 23%. Free-form text →
Sigma `text` elements; images/shapes/html are flagged; **attribute selectors
+ chapter filters → Sigma controls** (CONVERTED — wired to the selectors'
declared `targets` viz lists, `control-scope.json` sidecar, gate 7 +
flip-test; panel selectors and metric-condition selectors are flagged MANUAL
in the sidecar); multi-dataset chapters → one Sigma element per dataset-backed
viz (each viz names its dataset).

`fixtures/BUILD_SPEC.md` is the drag-and-drop spec for an "every viz type"
fixture dossier (REST cannot author visualizations — Library UI only); use it
to extend the validated set.

Keep `VIZ_MAPPED` in `../../microstrategy-assessment/scripts/assess.py` in
sync with this table — the assessment classifies estates against it.
