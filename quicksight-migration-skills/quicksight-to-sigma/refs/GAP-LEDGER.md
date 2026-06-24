# QuickSight → Sigma · Honest Gap Ledger (Pass 3 — comprehensive audit)

**Date:** 2026-06-06  ·  **Sigma org:** tj-wells-1989  ·  **QuickSight acct:** 153722385948 (us-east-1)
**Scope:** all 20 migration test dashboards (D1–D20). Every QuickSight Sheet, Visual, and field-well
was enumerated from `aws quicksight describe-analysis-definition` and compared against the produced
Sigma workbook spec (`GET /v2/workbooks/{id}/spec`) and live element schemas/queries (sigma-mcp-v2).

This ledger is deliberately blunt. Each row is classified **MATCH**, **FIXED-this-pass**, or
**DOCUMENTED-SIGMA-LIMITATION ((c)-tail)** with the specific reason. Parity = the headline metric was
re-computed directly from Snowflake (`CSA.TJ`) and confirmed against the Sigma element via MCP query.

## The big fix this pass — multi-sheet → multi-page

The builder previously flattened **all** of a QuickSight analysis's sheets onto a single Sigma page
(`page-dash`). The layout step only ever read `Sheets[0]`, so for any multi-sheet analysis every
visual on sheet 2..N existed in the spec **but received no layout placement** — i.e. it was invisible
/ effectively lost. That is the "missing data from QuickSight" the user observed.

`build-workbook-from-quicksight.rb` now emits **one Sigma PAGE per QuickSight SHEET** (page name =
sheet name), each page holding only that sheet's visuals, plus the single shared master/Data page.
`build-quicksight-layout.rb` now lays out **each page from its own sheet's QuickSight layout**.
Affected in this corpus: **D13** and **D14** (2 sheets each). Sheet-2 content recovered and
parity-verified (D13 page 2 "Revenue by Segment": Consumer $56,442.54 = Snowflake ✓).

> Honesty note: only D13 and D14 are genuinely multi-sheet in this corpus. D20 (flagged in the
> brief as possibly multi-sheet) is single-sheet — its gaps are the ML Insight + CustomContent drops,
> not a lost sheet.

## Other fixes this pass

- **D7 (what-if):** the calc `ProjectedProfit = {NET_REVENUE} * ${TargetMargin}` was migrating to a
  **broken** Sigma formula referencing a non-existent `[TargetMargin]` column (the live workbook was
  erroring). QuickSight `${parameter}` refs are now resolved to the parameter's **default value**
  inlined as a constant (0.25). ProjectedProfit = **$27,279.13** now matches `SUM(NET_REVENUE)*0.25`
  from Snowflake ✓. The interactive control itself is a manual Sigma re-author ((c)-tail, warned).
- **D12 (window):** the 4 window/table-calc columns (RunningRevenue, PctOfTotalRevenue, RevenueRank,
  MoMDiff) neutralize to Null and rendered as **blank columns** in the table. They are now **dropped
  from the workbook table** (kept in the data model with the original QuickSight expression in each
  column's description). The window-only line chart (its single measure was RunningRevenue) is now
  **skipped + warned** rather than drawn blank. The remaining table shows the 3 meaningful columns
  (May/Online $16,462.19 = Snowflake ✓).
- **D8 (scatter size):** the QuickSight scatter `Size` well (QUANTITY_ORDERED) is now **projected
  into the data model master** so the data migrates. Sigma's scatter element has **no size/radius
  channel** (verified against the element schema — the projected column is not bound to the viz), so
  bubbles render uniform — DOCUMENTED-SIGMA-LIMITATION.

---

## Per-dashboard ledger

### D1 — Single KPI · Total Revenue
- QS: 1 sheet, 1 visual (KPI), 1 field. Sigma: 1 page, 1 kpi-chart.
- **MATCH** — KPI total parity ✓.

### D2 — Bar by Region
- QS: 1 sheet, 1 visual (BarChart), 2 fields. Sigma: 1 page, 1 bar-chart.
- **MATCH** — bar-by-region parity ✓.

### D3 — Line + Pie
- QS: 1 sheet, 2 visuals (LineChart, PieChart), 3 fields. Sigma: 1 page, 2 elements.
- **MATCH** — line trend + pie (ArcThickness=WHOLE → pie not donut) ✓.

### D4 — Exec Summary
- QS: 1 sheet, 6 visuals (4 KPI, BarChart, LineChart), 5 fields. Sigma: 1 page, 6 elements.
- **MATCH** — all 6 elements; West $38,408.6 ✓.

### D5 — CustomSql Table
- QS: 1 sheet, 2 visuals (BarChart, Table), 4 fields. Sigma: 1 page, 2 elements.
- **MATCH** — CustomSql element named; parity ✓.

### D6 — Orders×Customers Join
- QS: 1 sheet, 2 visuals (KPI, BarChart), 2 fields. Sigma: 1 page, 2 elements.
- **MATCH** — join collapsed to one denormalized DM element; parity ✓.

### D7 — Orders What-If
- QS: 1 sheet, 2 visuals (KPI, BarChart), what-if params TargetMargin/ForecastUnits.
- **FIXED-this-pass** — `${TargetMargin}` was producing a broken `[TargetMargin]` ref; now inlined as
  default 0.25. ProjectedProfit $27,279.13 = Snowflake ✓.
- **(c)-tail** — interactive what-if control (slider/segmented) is a manual Sigma re-author.

### D8 — Orders Combo + Scatter
- QS: 1 sheet, 2 visuals (ComboChart, ScatterPlot), 5 fields.
- **MATCH** — combo dual-axis persists (bars=Net Revenue primary axis, line=Net Profit secondary via
  `{columnId,type:line}`); scatter X/Y + color-by-Category ✓.
- **FIXED-this-pass (data)** — scatter Size measure (Quantity Ordered) now projected to the master.
- **(c)-tail** — Sigma scatter has no size/bubble channel; bubbles render uniform-size.

### D9 — Gauge / Funnel / TreeMap
- QS: 1 sheet, 3 visuals, 3 fields. Sigma: 1 page, 3 elements.
- **MATCH (approximated)** — gauge→kpi-chart, funnel→bar, treemap→bar (Sigma has no native gauge/
  funnel/treemap kind; data + values parity ✓). Chart *kind* is the only (c)-tail.

### D10 — Employees Transforms
- QS: 1 sheet, 3 visuals, 4 fields. Sigma: 1 page, 3 elements.
- **MATCH** — Cast/Create/Rename transforms + dataset row-filter applied → 347 active headcount ✓.

### D11 — Multi-Level Pivot
- QS: 1 sheet, 1 PivotTable, 5 fields. Sigma: 1 page, 1 pivot-table (rowsBy/columnsBy {id} arrays).
- **MATCH** — multi-level pivot parity ✓.

### D12 — Window Table-Calc
- QS: 1 sheet, 2 visuals (Table, LineChart), 7 fields (incl. 4 window calcs).
- **FIXED-this-pass** — 4 null window columns dropped from the table (no more blank columns); table
  shows Month/Channel/Net Revenue (May/Online $16,462.19 = Snowflake ✓). Window-only line chart
  skipped.
- **(c)-tail** — runningSum/percentOfTotal/rank/difference have no live Sigma data-model equivalent;
  kept in the data model with the original QuickSight expression in each column description for
  re-authoring as Sigma window functions in the workbook.

### D13 — Cascading Cross-Sheet Filters  ★ multi-sheet
- QS: **2 sheets** (Overview: Revenue by Region; Detail: Revenue by Segment), 1 visual each.
- **FIXED-this-pass** — now 2 Sigma pages. Sheet-2 (Revenue by Segment) was previously **lost**;
  recovered + parity ✓ (Consumer $56,442.54 = Snowflake).
- **(c)-tail** — cross-sheet cascading FilterGroups are not reconstructed (Sigma cross-page filter
  wiring is a manual step).

### D14 — Visual Actions  ★ multi-sheet
- QS: **2 sheets** (Main: Revenue by Store Type; Detail: Revenue by Region), 1 visual each.
- **FIXED-this-pass** — now 2 Sigma pages; sheet-2 recovered.
- **(c)-tail** — QuickSight visual ACTIONS (filter / navigate / URL) have no spec-level equivalent;
  dropped + warned.

### D15 — Free-Form Overlap
- QS: 1 sheet, 2 visuals (KPI, BarChart) in an overlapping free-form layout.
- **MATCH** — data exact; pixel-overlap collision-resolved to a clean stacked grid (Sigma rejects
  element collisions). Layout approximation is intentional, not data loss.

### D16 — Paginated Ticket Report
- QS: 1 sheet, 1 Table in a SectionBasedLayout (header/body/footer/page-break).
- **MATCH (data)** — table exact.
- **(c)-tail** — Sigma has no paginated/section report construct; sections flatten to a single
  stacked grid. Page-break/header-footer pagination is not reproducible in a Sigma workbook.

### D17 — Workforce Maps
- QS: 1 sheet, 2 visuals (GeospatialMap points, FilledMap choropleth), 3 fields.
- **MATCH** — both → Sigma region-map; avg-salary-by-state matches Snowflake ✓. (Point-map vs
  region-map distinction handled by lat/long detection.)

### D18 — Exotic Chart Zoo
- QS: 1 sheet, 6 visuals: Waterfall, Sankey, BoxPlot, Histogram, WordCloud, Radar.
- **MATCH (data-migrated)** — all 6 produce a Sigma element: waterfall+histogram→bar, the rest→
  grouped tables. Top incident-type count 48 = Snowflake ✓.
- **(c)-tail** — the chart KINDS (waterfall/sankey/box-plot/histogram-binning/word-cloud/radar) have
  no Sigma equivalent; the data migrates, the exact visual encoding does not.

### D19 — Secured Conditional Table
- QS: 1 sheet, 1 Table with gradient ConditionalFormatting + (dataset) RLS/CLS.
- **MATCH** — data exact; gradient conditional formatting MIGRATED (QS gradient → Sigma
  backgroundScale, round-trips in spec).
- **(c)-tail** — RLS/CLS live at the QuickSight dataset level (not in the analysis definition), so
  they are not migratable from the analysis def — manual re-author in the Sigma data model.

### D20 — Kitchen Sink
- QS: 1 sheet (NOT multi-sheet), 4 visuals: BarChart, LineChart, Insight (ML), CustomContent.
- **MATCH** — bar honors QS Orientation=HORIZONTAL; line aggregated by MONTH via DateTrunc (matches
  Snowflake ✓). Window calc on the param-flagged bar neutralized to Null.
- **(c)-tail** — ML Insight (forecast/anomaly/narrative) and CustomContent (iframe/HTML embed) have
  no Sigma equivalent; dropped + warned.

---

## Honest summary

| Bucket | Count | Dashboards |
|---|---|---|
| Full match (data + chart) | 11 | D1, D2, D3, D4, D5, D6, D10, D11, D15, D17, D19 |
| Match w/ approximated chart kind (data exact) | 3 | D9 (gauge/funnel/treemap→kpi/bar), D18 (zoo→bars/tables), D20 (bar/line ok; ML+embed dropped) |
| Fixed this pass | 4 | D7 (param), D8 (scatter size data), D12 (window cols), D13+D14 (multi-sheet pages) |
| Documented Sigma limitation present | — | D7 (control), D8 (bubble-size), D12 (window funcs), D13 (cross-sheet filters), D14 (visual actions), D16 (pagination), D18 (chart kinds), D19 (RLS/CLS), D20 (ML/embed) |

**Data parity:** every dashboard's headline metric reproduces the Snowflake `CSA.TJ` source. No parity
regressions were introduced this pass (re-verified D7, D8, D12, D13, D14 via sigma-mcp-v2 after the
in-place re-migration).

**What is genuinely NOT parity (the real (c)-tail), stated plainly:**
- Interactive QuickSight constructs with no Sigma spec equivalent: what-if controls (D7), cross-sheet
  cascading filters (D13), visual actions (D14), ML Insights (D20), CustomContent embeds (D20).
- Visual encodings Sigma cannot render: scatter bubble-size (D8), waterfall/sankey/box-plot/
  histogram-binning/word-cloud/radar chart kinds (D18), gauge/funnel/treemap (D9, approximated to
  kpi/bar), paginated section reports (D16).
- Live window/table-calc functions in the data model (D12, D20) — migrated as documented Null columns
  with the source expression preserved for manual re-authoring.
- Dataset-level RLS/CLS (D19) — not present in the analysis definition, so not migratable from it.
