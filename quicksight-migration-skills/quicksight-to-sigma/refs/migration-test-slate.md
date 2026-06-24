# QuickSight → Sigma: complexity taxonomy + 20-dashboard test slate

Reference for validating the quicksight-to-sigma skill against graduated complexity.
Grounded in the QuickSight `describe-analysis-definition` schema and cross-referenced
against this stack's known coverage + gaps.

## Converter / builder coverage snapshot
- **DM converter** (MCP `convert_quicksight_to_sigma`): handles RelationalTable, CustomSql,
  JoinInstruction, DataTransforms (CreateColumns/Rename/Cast/Filter/Project), calc fields
  (~40 functions; `ifelse`→If, `switch`→nested If). Params → Sigma controls.
- **DM GAPS**: window/table-calc functions (~28+: sumOver, runningSum, rank, lag/lead via
  periodOverPeriod*, percentOfTotal, window*, percentile*Over) → `/* TODO */` placeholder;
  S3Source & SaaSTable → placeholder; analysis-level FilterGroups → skipped;
  ColumnConfigurations (formatting) → skipped; dataset-of-datasets → out of scope.
- **Workbook builder** recreates (native Sigma kind): KPI, bar, line, area, donut/pie,
  combo, scatter, table, pivot, **region-map** (FilledMap + name-based GeospatialMap) and
  **point-map** (GeospatialMap with real lat/long). Approximated (no native kind): gauge→kpi,
  funnel/treemap→bar. NOT built — no Sigma element kind, emitted as a per-visual warning in
  `<out>.warnings.json` + STDERR: histogram, heat-map, box-plot, waterfall, sankey, word-cloud,
  radar, layer-map (multi-layer), insight (ML), customcontent, plugin, empty.
  - **Sigma's real chart-kind universe** (confirmed against the public OpenAPI element union,
    `/v2/workbooks/spec`, 2026-06-06): `kpi-chart`, `bar-chart`, `line-chart`, `area-chart`,
    `pie-chart`, `donut-chart`, `scatter-chart`, `combo-chart`, `table`, `pivot-table`,
    `point-map`, `region-map`, `geography-map` (+ non-chart `control`/`text`/`image`/`embed`/
    `container`/`divider`). There is **no** histogram/heat-map/treemap/waterfall/box-plot/
    radar/sankey/word-cloud kind — those names appear nowhere in the element union. `region-map`
    persistence + query parity verified live (POST→readback→MCP query) on the D17 DM.

## Visual catalog (API `Visual` union — 24 nodes) — per-node build status
**BUILT (native Sigma kind):** `KPIVisual`→kpi-chart, `BarChartVisual`→bar-chart,
`LineChartVisual`→line-chart, `PieChartVisual`→pie/donut-chart, `ComboChartVisual`→combo-chart,
`ScatterPlotVisual`→scatter-chart, `TableVisual`→table, `PivotTableVisual`→pivot-table,
`FilledMapVisual`→**region-map**, `GeospatialMapVisual`→**region-map** (name-based) or
**point-map** (lat/long).
**APPROXIMATED (no exact kind):** `GaugeChartVisual`→kpi-chart, `FunnelChartVisual`→bar-chart,
`TreeMapVisual`→bar-chart.
**(c)-TAIL — no Sigma element kind, dropped with a per-visual warning:** `HeatMapVisual`,
`HistogramVisual` (re-author as binned bar), `BoxPlotVisual`, `WaterfallVisual`,
`SankeyDiagramVisual`, `WordCloudVisual`, `RadarChartVisual`, `LayerMapVisual` (multi-layer),
`InsightVisual` (ML), `CustomContentVisual`, `PluginVisual`, `EmptyVisual` (no-op).

## Complexity axes (easy / medium / hard)
- **A. Data topology**: 1 RelationalTable → CustomSql → multi-table JoinInstruction → dataset-of-datasets(out of scope). S3/SaaS sources = GAP.
- **B. Data prep**: simple calc fields → transforms chain → window/table-calc funcs (GAP) / LAC.
- **C. Visual types**: KPI/bar/line/pie → mid catalog (table/pivot/combo/…) → maps/sankey → insight/custom/plugin (un-migratable).
- **D. Interactivity**: 1 filter control → param controls + relative-date → cascading/cross-sheet (FilterGroups GAP) → actions/drill (GAP).
- **E. Layout**: single tiled grid → multi-sheet/fixed grid → free-form (pixel) / section-based (paginated). Free-form & section → approximate to Sigma grid.
- **F. Governance/advanced**: text/images/themes → conditional formatting (GAP) → RLS/CLS → insight ML (un-migratable).

## The 20-dashboard slate (low → high)
**Tier 1 — trivial smoke (pass clean):**
- D1 Single KPI (total revenue). baseline happy path.
- D2 Bar by Region, simple `sum` calc.
- D3 Line trend + Pie mix (multi-element grid).

**Tier 2 — medium real-world:**
- D4 Exec summary: 4 KPIs + bar + line + 1 filter control (sheet scope).
- D5 CustomSql dataset → bar + **table** (table builder).
- D6 Two-dataset **JoinInstruction** (orders⋈customers) → bar + KPI (cross-element ref form).
- D7 **Parameters** + param controls (slider/dropdown) + what-if calc.
- D8 **Combo** (dual-axis) + **Scatter** (size+color).
- D9 **Gauge** + **Funnel** + **TreeMap**.
- D10 Data-prep **transforms** chain (Create/Rename/Cast/Filter) → bar+KPI on derived cols.

**Tier 3 — hard (hit gaps):**
- D11 **Pivot table** multi-level (2 row dims, 1 col, 2 measures, subtotals) — rowsBy/columnsBy `{id}` arrays.
- D12 **Window/table-calc** funcs (runningSum, percentOfTotal, rank, periodOverPeriod) → verify graceful `/* TODO */` degradation.
- D13 **Cascading + cross-sheet filters** (FilterGroup AllSheets) — FilterGroups GAP.
- D14 **Visual actions**: filter + navigation(+param) + URL — actions GAP (inventory/warn).
- D15 **Free-form layout** w/ overlap + text box + image.
- D16 **Section-based** paginated report (header/footer/page-break) + table.
- D17 **Maps**: geospatial points + filled choropleth. **BUILT (2026-06-06):** both →
  Sigma `region-map` (FilledMap STATE→us-state choropleth; GeospatialMap CITY→us-postal-place,
  since the dataset carries geo NAMES not lat/long — point-map is auto-selected only when real
  latitude+longitude fields are present). Live parity verified: avg-salary-by-state matches
  Snowflake exactly. Was 0 chart elements → now 2.
- D18 **Exotic zoo**: waterfall + sankey + boxplot + histogram + wordcloud + radar.
  **(c)-TAIL — confirmed:** none of these six has a Sigma element kind (verified against the
  OpenAPI element union). The builder now emits a per-visual warning manifest
  (`wb-spec.warnings.json`) + STDERR for each instead of silently producing nothing. Was 0
  chart elements / silent → now 0 chart elements + 6 explicit, reasoned warnings. DM still
  posts clean (6 columns).

**Tier 4 — very hard / governance + un-migratable:**
- D19 **RLS + CLS** secured + conditional formatting (color rules, data bars) on a table.
- D20 **Kitchen sink**: multi-dataset join + window calcs + cascading params + free-form + **InsightVisual (ML) + CustomContent + Plugin** — verify clean PARTIAL migration + full warning manifest.
- (optional D21: dataset-of-datasets recursion — negative test for the out-of-scope case.)

## Un-migratable → scope as known-(c)-tail, never "failed":
`InsightVisual` ML (forecast/anomaly/narrative); `CustomContentVisual` (iframe/HTML); `PluginVisual`
(Highcharts etc.); `SankeyDiagramVisual`, `RadarChartVisual`, `WordCloudVisual`, `BoxPlotVisual`,
`WaterfallVisual`, `HistogramVisual`, `HeatMapVisual`, `LayerMapVisual` (each has NO Sigma element
kind — confirmed against the OpenAPI element union, 2026-06-06); SectionBasedLayout + free-form
pixel overlap; cascading filter *actions*; SPICE ingestion metadata; dataset-of-datasets recursion.
The builder emits a structured `<out>.warnings.json` + STDERR line per dropped visual.
**NOTE — the map family is NO LONGER (c)-tail:** `FilledMapVisual` and name/lat-long-based
`GeospatialMapVisual` now build natively (Sigma `region-map`/`point-map`); only the multi-layer
`LayerMapVisual` remains a warning.

_Doc sources: QuickSight API_Visual, AnalysisDefinition, FilterGroup/FilterScopeConfiguration,
LayoutConfiguration/GridLayoutConfiguration, custom-actions, table-calculation-functions, RLS/CLS, ML-insights._
