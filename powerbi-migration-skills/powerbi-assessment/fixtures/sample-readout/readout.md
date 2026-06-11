# Power BI / Fabric Assessment — sigmacomputing

**Tenant:** `sigmacomputing` | **Mode:** User-delegated (complexity-only) | **Generated:** 2026-05-31

> Lightweight pre-scoping readout produced by the `powerbi-assessment` skill.
> READ-ONLY — nothing was written to Power BI or posted to Sigma. The migration
> shortlist below feeds directly into the `powerbi-to-sigma` conversion skill.

---

## 1. Environment overview

| | |
|---|---|
| Workspaces | **2** (2 on Fabric capacity) |
| Semantic models | **2** |
| Reports | **3** |
| Dashboards | 0 |
| Dataflows | 0 |
| Lakehouses / Warehouses | 0 / 0 |
| Notebooks / other items | 0 / 0 |


> ⚠️ Running WITHOUT the Fabric Administrator role — usage/adoption (views,
> distinct users) and tenant-wide sprawl (Scanner API) are unavailable. The
> shortlist below is **complexity-only**: it ranks reports by size/richness, not
> by who actually uses them. Re-run as a Fabric Administrator to add the usage
> axis. Everything else (per-model DAX complexity, per-report visuals) is
> independent of admin role and is accurate.


---

## 2. Workspaces

| Workspace | On capacity | Items |
|---|---|---|
| My workspace | ✓ | Report:1, SemanticModel:1 |
| Test | ✓ | Report:2, SemanticModel:1 |


On-capacity workspaces are writable via the Fabric API; "My workspace" content
is per-user and usually the first to consolidate.

---

## 3. Semantic-model complexity

Power BI's real conversion burden lives in the **semantic model** (DAX measures,
calculated columns, calculated tables, RLS roles, DirectQuery), not the report.
This is the richest signal in the assessment.

| Model | Workspace | Tables | Measures | CalcCols | CalcTbls | RLS | Mode | DAX a/b/c |
|---|---|---|---|---|---|---|---|---|
| Report | My workspace | 8 | 3 | 30 | 5 | 0 | import | 33/0/0 |
| Workforce KitchenSink (complex DAX test) | Test | 4 | 20 | 4 | 1 | 0 | import | 17/7/0 |


DAX-convertibility buckets (from `research/dax-to-sigma-coverage.md`, validated
against `powerbi-to-sigma/fixtures`):
- **a — mechanical** (~70% of typical measures): direct Sigma-formula rewrite.
- **b — restructuring**: needs a grouped element, a parallel join, or a
  pre-aggregated element (TOTALYTD, RANKX, USERELATIONSHIP, ALL/ALLEXCEPT).
- **c — no Sigma equivalent**: dynamic context the formula language can't
  express (PATH hierarchies). Rare.

Across all scanned models: **50 mechanical / 7
restructuring / 0 no-equivalent** measures.

---

## 4. Warehouse sources

Parsed from each model's M (Power Query) expressions:

| Warehouse source (from M) | Models |
|---|---|
| Snowflake:ymb68310.snowflakecomputing.com | 2 |


Migration signal: models on a cloud warehouse Sigma already supports (Snowflake,
BigQuery, Databricks, Redshift, Synapse, Postgres) are **drop-in** — Sigma reads
the same tables directly, no extract relocation. Import-mode models hide the
warehouse behind a cached extract; the M source above is what Sigma re-points to.

---

## 5. Refresh insights

_No refresh history rows (models may be DirectQuery or never refreshed)._



---

## 6. Report priority — by complexity proxy

| Report | Workspace | Pages | Visuals | Views | Users |
|---|---|---|---|---|---|
| EMPLOYEE DASHBOARD | My workspace | 1 | 5 | — | — |
| Employee Dashboard | Test | 1 | 5 | — | — |
| Workforce KitchenSink Report | Test | 1 | 1 | — | — |




> Usage data unavailable (no Fabric Administrator role). Reports above are ranked
> by a complexity proxy (page + visual count), not real view counts.


---

## 7. Migration shortlist (complexity-only proxy (pages + visuals/4))

`cost = 10·unhandled + 3·manual + 1·hint`, ranked by `value / (1 + cost)`.
Higher score = better first-migration candidate. For Power BI, `manual` =
restructuring DAX + calculated tables + RLS roles; `unhandled` = no-equivalent
DAX + unsupported custom visuals.

| Report | Views | DAX a/b/c | Auto/Hint/Man/Unh | Value | Score | Tag |
|---|---|---|---|---|---|---|
| EMPLOYEE DASHBOARD | — | 0/0/0 | 0/0/0/0 | 22.5 | 22.50 | **migrate-first** |
| Employee Dashboard | — | 33/0/0 | 33/0/5/0 | 22.5 | 1.41 | moderate |
| Workforce KitchenSink Report | — | 17/7/0 | 17/0/8/0 | 12.5 | 0.50 | moderate |


The top 3 reports have **0
unhandled features between them**.

---

## 8. Per-report complexity

| Report | Pages | Visuals | Measures | CalcTbls | RLS | DAX a/b/c | Manual | Unhandled |
|---|---|---|---|---|---|---|---|---|
| Workforce KitchenSink Report | 1 | 1 | 20 | 1 | 0 | 17/7/0 | 8 | 0 |
| Employee Dashboard | 1 | 5 | 3 | 5 | 0 | 33/0/0 | 5 | 0 |
| EMPLOYEE DASHBOARD | 1 | 5 | 0 | 0 | 0 | 0/0/0 | 0 | 0 |


**Total unhandled features across the tenant: 0** spanning
0 reports. Each gets a `gap-scout`-style triage at
conversion time.

---

## 9. What this skill found vs. what it didn't

**Found (independent of admin role, user-delegated token):**
- Environment counts (workspaces, models, reports, dashboards, dataflows, lakehouses)
- On-capacity flag per workspace
- Per-model: table / measure / calc-column / calc-table counts, RLS roles,
  import-vs-DirectQuery, warehouse sources (parsed from M)
- Per-model DAX-convertibility classification (a / b / c)
- Per-report: page count, visual count, visual-kind histogram, custom-visual usage
- Refresh history (when the Power BI REST token is available)



**Not gathered (out of scope):**
- Per-visual field-level bindings (the converter re-derives these from PBIR at conversion time)

- Usage / adoption (views, distinct users) — needs the **Fabric Administrator**
  role for the Activity Events API. Re-run as admin to add it.
- Tenant-wide sprawl beyond the signed-in user's accessible workspaces — needs
  the **Scanner API** (also Fabric Administrator).


---

## 10. Privacy

What crossed Anthropic's API on its way through Claude during this assessment:

- Aggregate counts (workspace / model / report counts)
- Model and report names, workspace names, owner where available
- **Full TMSL** for each semantic model — this includes **DAX measure
  expressions and RLS role definitions** (richer and more sensitive than
  Tableau's `.twb`)
- **PBIR** report definitions — visual configuration
- Refresh job results (when available)

What did NOT cross:
- Warehouse rows (this skill never queries the underlying database)
- Power BI / Entra credentials (handled by the device-code cache, not surfaced)
- Actual report cell values

See `PRIVACY.md` for the full disclosure.

---

## 11. Hand-off package

This directory contains:

- `readout.md` — this report
- `inventory.json` — raw environment + per-model + per-report metadata
- `complexity.json` — per-report DAX / visual complexity scoring
- `shortlist.json` — value/cost-ranked migration shortlist
- `migration-plan.json` — per-report `recommended_path` + DM clusters
- `raw-tmsl/` — decoded TMSL per model (delete after review if you'd rather not retain DAX text)
- `raw-pbir/` — decoded PBIR per report

Nothing is uploaded automatically. To share, zip and send deliberately.

---

## 12. Next steps

1. **Pilot the top 3 reports** with the `powerbi-to-sigma`
   skill — the migration-plan groups them into DM clusters that share a Sigma
   data model.
2. **Triage the `needs-gap-scout` queue** (0 reports): no-equivalent
   DAX or unsupported custom visuals that need a design decision first.

4. **Re-run as a Fabric Administrator** to add the usage axis if you want a
   usage-weighted (not complexity-only) shortlist.
