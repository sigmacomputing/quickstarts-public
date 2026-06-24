# Amazon QuickSight Assessment — 153722385948

**Account:** `153722385948` | **Region:** us-east-1 | **Edition:** Enterprise | **Mode:** Complexity-only | **Generated:** 2026-06-06

> Lightweight pre-scoping readout produced by the `quicksight-assessment` skill.
> READ-ONLY — nothing was written to QuickSight or posted to Sigma. The migration
> shortlist below feeds directly into the `quicksight-to-sigma` conversion skill.



---

## 1. Environment overview

| | |
|---|---|
| Analyses | **3** |
| Dashboards | 2 |
| Datasets | **2** |
| Data sources | 1 |


> ⚠️ Running WITHOUT per-analysis usage data. QuickSight has no per-analysis
> view-count API on the standard surface, so the shortlist below is
> **complexity-only**: it ranks analyses by size/richness, not by who actually
> uses them. Supply a `usage.json` (CloudTrail/CloudWatch-derived) to add the
> usage axis. Everything else (visual mix, calc-field buckets, dataset sources)
> is accurate.


---

## 2. Visual-type mix (account-wide)

QuickSight visuals the workbook builder reproduces directly: KPI, bar, line,
pie/donut. Everything else is a manual rebuild (mid catalog: table, pivot,
combo, scatter, gauge, funnel, treemap, …) or has no Sigma equivalent (maps,
sankey, insight ML, custom content, plugin).

| Visual type | Count |
|---|---|
| KPIVisual | 4 |
| BarChartVisual | 3 |
| LineChartVisual | 3 |
| PivotTableVisual | 1 |
| ComboChartVisual | 1 |
| InsightVisual | 1 |
| GeospatialMapVisual | 1 |
| SankeyDiagramVisual | 1 |
| PieChartVisual | 1 |
| TableVisual | 1 |


---

## 3. Analysis complexity

Each analysis's conversion burden = its visual mix + calc fields + parameters,
plus its datasets' source/prep/RLS burden (inherited via dataset references).

| Analysis | Sheets | Visuals | CalcFields | Window | Params | Calc a/b/c |
|---|---|---|---|---|---|---|
| Exec ML Board | 1 | 4 | 4 | 3 | 0 | 1/0/3 |
| Sales Deep Dive | 2 | 8 | 6 | 1 | 2 | 4/1/1 |
| Orders Overview | 1 | 5 | 3 | 0 | 1 | 3/0/0 |


Calc-field convertibility buckets (from `refs/migration-test-slate.md`):
- **a — mechanical** (~most calc fields): direct Sigma-formula rewrite
  (`ifelse`→`If`, `switch`→nested `If`, arithmetic, string, date funcs).
- **b — restructuring**: needs a grouped element or pre-aggregation.
- **c — no Sigma equivalent**: window / table-calc functions (`sumOver`,
  `runningSum`, `rank`, `percentOfTotal`, `periodOverPeriod*`, …) — the converter
  degrades these to a `/* TODO */` placeholder.

Across all scanned analyses: **8 mechanical / 1
restructuring / 4 no-equivalent** calc fields.

---

## 4. Datasets & sources

Physical source kinds parsed from each dataset's `PhysicalTableMap`:

| Physical source kind | Datasets |
|---|---|
| CustomSql | 1 |
| RelationalTable | 1 |


- **1** dataset(s) use **CustomSql** (converted via the
  `[Custom SQL/<ALIAS>]` fixup — see `quicksight-to-sigma`).
- **1** dataset(s) have **row-level security** enabled.

Migration signal: datasets on a cloud warehouse Sigma already supports
(Snowflake, Redshift, Athena, BigQuery, Databricks, Postgres) are **drop-in** —
Sigma reads the same tables directly. **S3 / SaaS** physical sources are a
converter gap (placeholder) and surface as unhandled.

---

## 5. Analysis priority — by complexity proxy

| Analysis | Sheets | Visuals | Views | Users |
|---|---|---|---|---|
| Orders Overview | 1 | 5 | — | — |
| Sales Deep Dive | 2 | 8 | — | — |
| Exec ML Board | 1 | 4 | — | — |




> Usage data unavailable. Analyses above are ranked by a complexity proxy
> (sheet + visual count), not real view counts.


---

## 6. Migration shortlist (complexity-only proxy (sheets + visuals/4))

`cost = 10·unhandled + 3·manual + 1·hint`, ranked by `value / (1 + cost)`.
Higher score = better first-migration candidate. For QuickSight, `manual` =
restructuring calc + mid-catalog visuals + dataset joins/transforms + parameters
+ RLS/CLS; `unhandled` = window/table-calc + exotic visuals + free-form/section
layout + FilterGroups + S3/SaaS source.

| Analysis | Views | Calc a/b/c | Auto/Hint/Man/Unh | Value | Score | Tag |
|---|---|---|---|---|---|---|
| Orders Overview | — | 3/0/0 | 8/0/2/0 | 22.5 | 3.21 | moderate |
| Sales Deep Dive | — | 4/1/1 | 9/0/8/2 | 40.0 | 0.89 | ⚠️ needs-gap-scout |
| Exec ML Board | — | 1/0/3 | 2/0/1/7 | 20.0 | 0.27 | ⚠️ needs-gap-scout |


The top 3 analyses have **9
unhandled features between them**.

---

## 7. Per-analysis complexity

| Analysis | Sheets | Visuals | CalcFields | Window | RLS | Manual | Unhandled |
|---|---|---|---|---|---|---|---|
| Exec ML Board | 1 | 4 | 4 | 3 | 0 | 1 | **7** |
| Sales Deep Dive | 2 | 8 | 6 | 1 | 1 | 8 | **2** |
| Orders Overview | 1 | 5 | 3 | 0 | 0 | 2 | 0 |


**Total unhandled features across the account: 9** spanning
2 analyses. Each gets a `gap-scout`-style triage at conversion
time.

---

## 8. What this skill found vs. what it didn't

**Found (read-only, AWS-CLI delegated):**
- Environment counts (analyses, dashboards, datasets, data sources)
- Per-analysis: sheet count, visual count, visual-kind histogram
- Per-analysis: calc-field count + a/b/c convertibility buckets, window-function detection
- Per-analysis: parameter count, FilterGroup count, layout shape (free-form / section-based)
- Per-dataset: source type(s), import mode (SPICE/DirectQuery), custom-sql, joins, transform count, RLS/CLS



**Not gathered (out of scope):**
- Per-visual field-level bindings (the converter re-derives these from the analysis definition at conversion time)

- Usage / adoption — QuickSight has no per-analysis view-count API on the
  standard surface; supply a CloudTrail/CloudWatch-derived `usage.json` to add it.


---

## 9. Privacy

What crossed Anthropic's API on its way through Claude during this assessment:

- Aggregate counts (analysis / dataset / data-source counts)
- Analysis, dataset, and data-source names
- **Analysis definitions** — visual configuration + **calc-field expressions**
- Dataset metadata — physical source kinds, custom-sql presence, RLS/CLS flags

What did NOT cross:
- Warehouse / SPICE rows (this skill never queries the underlying data)
- AWS credentials (handled by the AWS CLI, not surfaced)
- Actual visual cell values

---

## 10. Hand-off package

This directory contains:

- `readout.md` — this report
- `inventory.json` — raw environment + per-analysis + per-dataset metadata
- `complexity.json` — per-analysis convertibility scoring
- `shortlist.json` — value/cost-ranked migration shortlist
- `migration-plan.json` — per-analysis `recommended_path` + DM clusters (by shared dataset)
- `raw-defs/` — decoded analysis definitions (delete after review if you'd rather not retain calc-field text)
- `raw-datasets/` — decoded dataset describes

Nothing is uploaded automatically. To share, zip and send deliberately.

---

## 11. Next steps

1. **Pilot the top 3 analyses** with the
   `quicksight-to-sigma` skill — the migration-plan groups them into DM clusters
   that share a Sigma data model (by shared dataset).
2. **Triage the `needs-gap-scout` queue** (2 analyses):
   window/table-calc functions, exotic visuals, or free-form layout that need a
   design decision first.

4. **Supply usage data** (CloudTrail/CloudWatch) to get a usage-weighted (not
   complexity-only) shortlist.
