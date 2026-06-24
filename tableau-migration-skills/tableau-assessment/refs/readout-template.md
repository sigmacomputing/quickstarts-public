# Tableau Assessment — {{site_name}}

**Site:** `{{site_name}}` ({{site_url}}) | **Mode:** {{mode}} | **Generated:** {{generated_at}}

> Lightweight pre-scoping readout produced by the `tableau-assessment` skill.
> For a deeper assessment (pricing scenarios, full permissions audit, dataset
> similarity at depth), see Hakkoda's Assessment App on the Snowflake Marketplace.

---

## 1. Environment overview

| | |
|---|---|
| Workbooks | **{{workbooks}}** |
| Views | **{{views}}** ({{dashboards}} dashboards, {{sheets}} sheets, {{stories}} stories) |
| Datasources | **{{datasources}}** ({{ds_published}} published, {{ds_embedded}} embedded) |
| Projects | {{projects}} |
| Flows | {{flows}} |
| Metrics / Metric Definitions | {{metrics}} / {{metric_definitions}} |

{{#limited_mode_banner}}
> ⚠️ Running with limited access — the user driving this skill lacks Site Admin
> role, so license/refresh/usage sections are missing. Re-run as a Site Admin to
> unlock those. The Environment Overview above is still accurate.
{{/limited_mode_banner}}

---

## 2. Licenses

{{licenses_table}}

{{#has_pricing}}
### Cost scenario (illustrative)

| License | Users | Tableau list (annual) | Sigma equivalent (annual) | Δ |
|---|---:|---:|---:|---:|
{{pricing_rows}}

*Pricing rows use placeholder list prices — actual pricing is customer-negotiated. The math is computable from `User License Type` × a small lookup table.*
{{/has_pricing}}

---

## 3. Content ownership

{{ownership_table}}

Top-owner concentration: **{{top_owner_pct}}%** of workbooks owned by `{{top_owner_email}}`.

---

## 4. Datasource patterns

{{datasource_summary_table}}

Migration signal: **{{n_published_extracts}} published extracts** are the easy-to-relocate datasources (one-time hyper unload). The **{{n_embedded}} embedded** datasources require workbook-by-workbook re-pointing.

---

## 5. Refresh insights

{{refresh_table}}

{{refresh_notes}}

---

## 6. Workbook priority — usage-ranked

Top {{top_n_usage}} by Access-event count from `TS Events`:

{{usage_table}}

**Zero-access (cold) workbooks:** {{n_cold}} — {{cold_names}}. Retire-don't-migrate candidates.

---

{{#has_shortlist}}
## 7. Migration shortlist (value ÷ cost)

`value = accesses × √(distinct_viewers)`, `cost = 10·unhandled + 3·manual + 1·hint`, ranked by `value / (1 + cost)`. Higher score = better candidate.

{{shortlist_table}}

The top {{shortlist_top_n}} workbooks account for **{{shortlist_pct_usage}}% of site-wide accesses** with **{{shortlist_total_unhandled}} unhandled features between them**.

---

## 8. Per-workbook complexity

Feature counts from running `scan-workbook-gaps.rb` against every `.twb`. This
is the migration-cost predictor — auto features convert automatically; hints
get copy-paste formulas; manuals need post-publish wiring; **unhandled** features
need engineering triage before the workbook can be quoted.

{{complexity_table}}

**Total unhandled features across the site: {{total_unhandled}}** spanning {{n_workbooks_with_unhandled}} workbooks. Each gets a `gap-scout` subagent at migration time.

{{#has_consolidation}}
---

## 8b. Consolidation candidates

Workbook **variants** detected on the same datasource — copies that differ only
by a filter value, a year, or a copy/test suffix. In Sigma each group collapses
into **one workbook plus a control**, avoiding the extra conversions and
leaving one asset to govern. Recommendations are conservative — `consolidate`
only when the actually-used fields and sheet structure overlap heavily AND the
differences map to a control.

{{consolidation_table}}

**{{n_consol_groups}} candidate group(s)** — {{n_consolidate}} recommended to
consolidate, {{n_consol_review}} to review side-by-side; **{{conversions_avoidable}}
conversion(s) avoidable**. During migration you'll be prompted per group
(*consolidate into one workbook with controls* vs *migrate as-is*); decisions are
recorded in `migration-plan.json` for the conversion handoff. Full per-group
evidence in `consolidation-candidates.json`.
{{/has_consolidation}}
{{/has_shortlist}}

{{^has_shortlist}}
## 7. Migration shortlist

> ⚠️ Skipped — no PAT configured. With PAT mode the skill produces a value/cost-ranked
> migration shortlist plus per-workbook complexity scoring. To enable, run
> `ruby scripts/setup-tableau.sh` and re-run the assessment.
{{/has_shortlist}}

---

## 9. What this skill found vs. what it didn't

**Found via standard Tableau MCP (Site Admin scope):**
- Environment counts, view-type breakdown
- License-type breakdown + activity per user
- Content ownership distribution
- Datasource type and extract mix
- Refresh job history + success rate
- Per-workbook usage and distinct-viewer counts
- Cold-workbook detection

{{#has_shortlist}}
**Added by PAT mode:**
- Per-workbook calc-field / table-calc / custom-SQL / LOD detection
- Per-workbook feature-gap counts (auto / hint / manual / unhandled)
- Value/cost-adjusted migration shortlist
- Pre-flight gap-scout cost estimate
{{/has_shortlist}}

**Not gathered (out of scope for this skill):**
- Pairwise datasource similarity / dataset deduplication (depth-pricing tradeoff — defer to Hakkoda's full Assessment App)
- Permissions audit at user×content×capability resolution (Admin Insights `Permissions` datasource is available but not used here)
- Pricing scenarios with negotiated discounts (math is right but pricing inputs need to be customer-specific)

---

## 10. Privacy

What crossed Anthropic's API on its way through Claude during this assessment:

- Aggregate counts (workbook/user/datasource counts, refresh-job result counts)
- Workbook names, owner emails, project names
- `User License Type` and login dates from Admin Insights
{{#has_shortlist}}
- `.twb` XML for {{n_workbooks_scanned}} workbooks (calc-field definitions, custom SQL queries, layout XML)
{{/has_shortlist}}

What did NOT cross:
- View CSVs / warehouse rows (this skill does not query warehouse data)
- `.hyper` extract data files (skipped during `.twb` download)
- Customer database credentials

See `PRIVACY.md` for the full disclosure.

---

## 11. Hand-off package

This directory contains:

- `readout.md` — this report
- `inventory.json` — raw Admin Insights aggregates
{{#has_shortlist}}
- `complexity.json` — per-workbook gap-scan results
- `shortlist.json` — ranked migration shortlist
- `twbs/` — cached `.twb` files (delete after review if you'd rather not retain them)
{{/has_shortlist}}

To share with a Sigma rep or Hakkoda engagement: zip the directory (excluding `twbs/` if you'd prefer) and send manually. Nothing is uploaded automatically.

---

## 12. Next steps

{{#has_shortlist}}
1. **Pilot the top {{recommended_pilot_n}} workbooks** with the `tableau-to-sigma` skill — they account for {{recommended_pilot_pct}}% of site usage and have {{recommended_pilot_unhandled}} unhandled features between them.
2. **Triage the `needs-gap-scout` queue** ({{n_needs_scout}} workbooks): each gets a gap-scout subagent that either finds a translation rule or files a GitHub issue.
3. **Retire the `retire` queue** ({{n_retire}} workbooks): zero accesses, no migration value.
4. **For a deeper-still scoping**: Hakkoda's Assessment App via Snowflake Marketplace adds pricing scenarios, dataset similarity, and full permissions audit.
{{/has_shortlist}}

{{^has_shortlist}}
1. **Enable PAT mode** to get the migration shortlist. Run `ruby scripts/setup-tableau.sh` and re-run the assessment.
2. **For a deeper-still scoping**: Hakkoda's Assessment App via Snowflake Marketplace adds pricing scenarios, dataset similarity, and full permissions audit.
{{/has_shortlist}}
