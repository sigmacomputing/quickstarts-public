# Amazon QuickSight Assessment — {{account_name}}

**Account:** `{{account_name}}` | **Region:** {{region}} | **Edition:** {{edition}} | **Mode:** {{mode}} | **Generated:** {{generated_at}}

> Lightweight pre-scoping readout produced by the `quicksight-assessment` skill.
> READ-ONLY — nothing was written to QuickSight or posted to Sigma. The migration
> shortlist below feeds directly into the `quicksight-to-sigma` conversion skill.

{{#standard_edition_banner}}
> ⛔ The `describe-*-definition` / `describe-data-set` APIs were rejected — this
> looks like a **Standard-edition** account. Those APIs are **Enterprise-only**,
> so per-analysis visual / calc-field complexity is **unavailable**: the readout
> below is counts-only. Upgrade to Enterprise (or run against an Enterprise
> account) to get the full complexity scoring and a real migration shortlist.
{{/standard_edition_banner}}

---

## 1. Environment overview

| | |
|---|---|
| Analyses | **{{analyses}}** |
| Dashboards | {{dashboards}} |
| Datasets | **{{datasets}}** |
| Data sources | {{data_sources}} |

{{#limited_mode_banner}}
> ⚠️ Running WITHOUT per-analysis usage data. QuickSight has no per-analysis
> view-count API on the standard surface, so the shortlist below is
> **complexity-only**: it ranks analyses by size/richness, not by who actually
> uses them. Supply a `usage.json` (CloudTrail/CloudWatch-derived) to add the
> usage axis. Everything else (visual mix, calc-field buckets, dataset sources)
> is accurate.
{{/limited_mode_banner}}

---

## 2. Visual-type mix (account-wide)

QuickSight visuals the workbook builder reproduces directly: KPI, bar, line,
pie/donut. Everything else is a manual rebuild (mid catalog: table, pivot,
combo, scatter, gauge, funnel, treemap, …) or has no Sigma equivalent (maps,
sankey, insight ML, custom content, plugin).

{{visuals_table}}

---

## 3. Analysis complexity

Each analysis's conversion burden = its visual mix + calc fields + parameters,
plus its datasets' source/prep/RLS burden (inherited via dataset references).

{{analyses_table}}

Calc-field convertibility buckets (from `refs/migration-test-slate.md`):
- **a — mechanical** (~most calc fields): direct Sigma-formula rewrite
  (`ifelse`→`If`, `switch`→nested `If`, arithmetic, string, date funcs).
- **b — restructuring**: needs a grouped element or pre-aggregation.
- **c — no Sigma equivalent**: window / table-calc functions (`sumOver`,
  `runningSum`, `rank`, `percentOfTotal`, `periodOverPeriod*`, …) — the converter
  degrades these to a `/* TODO */` placeholder.

Across all scanned analyses: **{{total_calc_a}} mechanical / {{total_calc_b}}
restructuring / {{total_calc_c}} no-equivalent** calc fields.

---

## 4. Datasets & sources

Physical source kinds parsed from each dataset's `PhysicalTableMap`:

{{source_table}}

- **{{n_custom_sql}}** dataset(s) use **CustomSql** (converted via the
  `[Custom SQL/<ALIAS>]` fixup — see `quicksight-to-sigma`).
- **{{n_rls}}** dataset(s) have **row-level security** enabled.

Migration signal: datasets on a cloud warehouse Sigma already supports
(Snowflake, Redshift, Athena, BigQuery, Databricks, Postgres) are **drop-in** —
Sigma reads the same tables directly. **S3 / SaaS** physical sources are a
converter gap (placeholder) and surface as unhandled.

---

## 5. Analysis priority — {{usage_basis}}

{{usage_table}}

{{#has_usage}}
**Cold (zero-view) analyses:** {{n_cold}} — retire-don't-migrate candidates.
{{/has_usage}}
{{^has_usage}}
> Usage data unavailable. Analyses above are ranked by a complexity proxy
> (sheet + visual count), not real view counts.
{{/has_usage}}

---

## 6. Migration shortlist ({{value_basis}})

`cost = 10·unhandled + 3·manual + 1·hint`, ranked by `value / (1 + cost)`.
Higher score = better first-migration candidate. For QuickSight, `manual` =
restructuring calc + mid-catalog visuals + dataset joins/transforms + parameters
+ RLS/CLS; `unhandled` = window/table-calc + exotic visuals + free-form/section
layout + FilterGroups + S3/SaaS source.

{{shortlist_table}}

The top {{shortlist_top_n}} analyses have **{{shortlist_total_unhandled}}
unhandled features between them**.

---

## 7. Per-analysis complexity

{{complexity_table}}

**Total unhandled features across the account: {{total_unhandled}}** spanning
{{n_with_unhandled}} analyses. Each gets a `gap-scout`-style triage at conversion
time.

---

## 8. What this skill found vs. what it didn't

**Found (read-only, AWS-CLI delegated):**
- Environment counts (analyses, dashboards, datasets, data sources)
- Per-analysis: sheet count, visual count, visual-kind histogram
- Per-analysis: calc-field count + a/b/c convertibility buckets, window-function detection
- Per-analysis: parameter count, FilterGroup count, layout shape (free-form / section-based)
- Per-dataset: source type(s), import mode (SPICE/DirectQuery), custom-sql, joins, transform count, RLS/CLS

{{#has_usage}}
**Added by supplied usage data:**
- Per-analysis view counts and distinct-user counts
- Usage-weighted migration shortlist
- Cold-analysis detection
{{/has_usage}}

**Not gathered (out of scope):**
- Per-visual field-level bindings (the converter re-derives these from the analysis definition at conversion time)
{{^has_usage}}
- Usage / adoption — QuickSight has no per-analysis view-count API on the
  standard surface; supply a CloudTrail/CloudWatch-derived `usage.json` to add it.
{{/has_usage}}

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

1. **Pilot the top {{recommended_pilot_n}} analyses** with the
   `quicksight-to-sigma` skill — the migration-plan groups them into DM clusters
   that share a Sigma data model (by shared dataset).
2. **Triage the `needs-gap-scout` queue** ({{n_needs_scout}} analyses):
   window/table-calc functions, exotic visuals, or free-form layout that need a
   design decision first.
{{#has_usage}}
3. **Retire the `retire` queue** ({{n_retire}} analyses): zero views, no migration value.
{{/has_usage}}
4. **Supply usage data** (CloudTrail/CloudWatch) to get a usage-weighted (not
   complexity-only) shortlist.
