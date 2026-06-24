---
name: quicksight-assessment
description: Take inventory of an Amazon QuickSight account and produce a migration-readiness readout — environment counts, per-analysis visual-type mix, calc-field complexity (mechanical / restructuring / window-table-calc buckets), parameter + FilterGroup + layout-shape signals, per-dataset source types / custom-sql / joins / RLS, and a value/cost-ranked migration shortlist. Use when a user wants to scope a QuickSight→Sigma migration, audit BI sprawl, or pick which analyses to convert first. READ-ONLY — never writes to QuickSight or posts to Sigma. AWS-CLI auth (no boto3). Enterprise edition required for full complexity. Feeds the quicksight-to-sigma conversion skill.
user-invocable: true
---

# Amazon QuickSight Assessment

Surveys an Amazon QuickSight account — **what the configured AWS credentials can
reach** — via the AWS CLI (`aws quicksight ...`, shelled out via subprocess; no
boto3). Emits a markdown readout + JSON inventory + a value/cost-ranked migration
shortlist the user can hand to a Sigma rep or directly to the
`quicksight-to-sigma` conversion skill.

This is the QuickSight sibling of `powerbi-assessment` and `tableau-assessment` —
same file layout, same readout sections, same privacy discipline, same
value/cost shortlist scoring — adapted to QuickSight's two-artifact world
(analysis + datasets).

> **READ-ONLY.** Every call is a `list-*` or `describe-*` GET-equivalent. The
> skill **never** writes to QuickSight and **never** posts to Sigma. It does not
> edit anything outside its output directory.

> **Enterprise edition required for complexity.** The `describe-analysis-definition`,
> `describe-dashboard-definition`, and `describe-data-set` APIs are
> **Enterprise-only** — a Standard-edition account rejects them. The skill
> detects that, flags the account as Standard, and degrades to a counts-only
> readout (it never crashes on a Standard account, but it also can't score
> complexity there).

> **Warehouse-agnostic.** QuickSight datasets source from many places
> (Snowflake, Redshift, Athena, BigQuery, Databricks, Postgres, S3, SaaS). The
> skill reports each dataset's physical source kind; the downstream
> `quicksight-to-sigma` converter re-points Sigma at the same tables (S3/SaaS
> are a known gap). Worked examples use Snowflake because that's where the dev
> fixtures live.

---

## Privacy posture (READ FIRST, surface to the customer)

**This skill reads analysis / dataset metadata, not warehouse data.** What
crosses Anthropic's API on its way through Claude:

| Crosses Anthropic API | Stays local |
|---|---|
| Aggregate counts (analysis / dataset / data-source counts) | Warehouse / SPICE rows (never queried) |
| Analysis, dataset, data-source names | AWS credentials |
| **Analysis definitions** — visual config + **calc-field expressions** | Actual visual cell values |
| Dataset metadata — physical source kinds, custom-sql, RLS/CLS flags | |

> If calc-field expressions encode business-sensitive logic, that text crosses
> the API. Tell the customer before running.

---

## When to use this skill

- A QuickSight customer wants a fast scoping view before a deeper migration engagement
- A Sigma SE preparing for a discovery call wants a pre-built migration shortlist
- A customer is deciding which QuickSight analyses to retire vs. migrate
- A `quicksight-to-sigma` invocation needs a Phase 0 inventory of the source account

---

## Setup (one-time)

No Python packages required — the inventory script shells out to the **AWS CLI
v2** (which you install + authenticate separately). See `scripts/requirements.txt`.

```bash
# SSO orgs:
aws sso login --profile <profile>
# Okta-fronted orgs: gimme-aws-creds writes a usable profile
gimme-aws-creds --profile <profile>
# confirm + grab the account id:
aws sts get-caller-identity --profile <profile>
```

QuickSight's **identity region is often `us-east-1`** even when data lives
elsewhere — analyses/datasets/data-sources are read from the identity region.
Pass `--region us-east-1` unless you know the account is regionalized
differently.

---

## Scripts overview

| Script | Lang | Purpose | Reused from powerbi-assessment? |
|---|---|---|---|
| `scripts/quicksight-inventory.py` | Python | Phase 1-3: analyses + dashboards + datasets + data sources, per-analysis definition complexity (visual mix, calc-field buckets, params, FilterGroups, layout shape) + per-dataset source/prep/RLS → `inventory.json`, `raw-defs/`, `raw-datasets/` | **New** (AWS CLI + AnalysisDefinition parsing has no PBI analog) |
| `scripts/score-quicksight-complexity.rb` | Ruby | Derive per-analysis convertibility (easy/medium/hard → auto/manual/unhandled) → `complexity.json` | **New** (calc/visual-bucket logic), but emits the shared `n_auto/n_hint/n_manual/n_unhandled` shape |
| `scripts/build-shortlist.rb` | Ruby | Cross-tab usage × complexity; `score = value/(1+cost)` → `shortlist.json` | **Adapted** — same scoring formula & tag rules; QS value-source + complexity-only fallback |
| `scripts/render-readout.rb` | Ruby | Compose `readout.md` from the JSON files | **Adapted** — `md_table`/`section_block`/`md_cell` helpers reused verbatim; gather-body is QS-specific |
| `scripts/migration-plan.rb` | Ruby | Per-analysis `recommended_path` + DM clusters (by shared dataset) → `migration-plan.json` | **Adapted** — same contract shape; clustering keyed on shared dataset instead of shared semantic model |

> **What was reused vs rewritten:** the renderer's templating helpers and the
> shortlist's value/cost scoring + tag vocabulary are lifted from
> `powerbi-assessment` (which lifted them from `tableau-assessment`). The auth
> layer (AWS CLI), AnalysisDefinition parsing, calc-field classification, and the
> dataset-centric clustering are new because QuickSight's data shape has no
> direct PBI/Tableau equivalent.

---

## Modes

| Mode | Setup | Coverage | Use when |
|---|---|---|---|
| **Complexity-only** *(default)* | AWS CLI + Enterprise | Environment + per-analysis visual/calc complexity + per-dataset sources + **complexity-only** shortlist | Any user; the common case |
| **Usage-weighted** | Supply `usage.json` (CloudTrail/CloudWatch-derived views) | Adds view/user weighting → usage-weighted shortlist + cold-analysis detection | When you have audit-trail usage data |

QuickSight has no per-analysis view-count API on the standard surface, so the
default is complexity-only; the readout says so.

---

## Phase 0 — Probe access + edition

```bash
aws sts get-caller-identity --profile <profile>            # account id + creds OK?
aws quicksight list-analyses --aws-account-id <ID> --region us-east-1 --profile <profile> | head
```

If `list-analyses` works but `describe-analysis-definition` later 4xx's with a
Standard/Enterprise/AccessDenied message, the inventory flags the account
`enterprise: false` and degrades to counts-only.

---

## Phase 1-3 — Inventory + complexity (always runs)

```bash
python3 scripts/quicksight-inventory.py \
  --account-id <ID> --region us-east-1 --profile <profile> \
  --out /tmp/qs-assessment-<acct>
ruby scripts/score-quicksight-complexity.rb --out /tmp/qs-assessment-<acct>
```

`quicksight-inventory.py` does:
- `list-analyses` / `list-data-sets` / `list-data-sources` (+ `list-dashboards`
  with `--dashboards-too`) → environment counts.
- Per analysis: `describe-analysis-definition` → sheet/visual counts, visual-kind
  histogram (bucketed built / mid-catalog / unhandled per `refs/migration-test-slate.md`),
  calc-field a/b/c classification (window/table-calc funcs → `c`), parameter +
  FilterGroup counts, free-form / section-based layout detection. Decoded def
  saved to `raw-defs/<id>.json`.
- Per referenced dataset (once): `describe-data-set` → physical source kind(s),
  import mode, custom-sql, joins, transform count, RLS/CLS. Saved to
  `raw-datasets/<id>.json`.

`score-quicksight-complexity.rb` maps easy/medium/hard onto the shared
`auto/manual/unhandled` tiers and folds in dataset joins, transforms, RLS, and
layout/visual gaps.

### Convertibility scoring

Grounded in `refs/migration-test-slate.md`:
- **easy → auto**: built visuals (KPI/bar/line/pie) + mechanical calc fields +
  RelationalTable/CustomSql sources.
- **medium → manual**: mid-catalog visuals (table/pivot/combo/scatter/gauge/…),
  restructuring calc fields, dataset joins + data-prep transforms, parameters, RLS/CLS.
- **hard → unhandled**: window / table-calc functions (no Sigma equivalent →
  `/* TODO */`), exotic visuals (maps, sankey, insight ML, custom content,
  plugin), free-form / section-based layout, analysis-level FilterGroups, S3/SaaS sources.

Per-analysis `cost = 10·unhandled + 3·manual` in the shortlist.

---

## Phase 4 — Shortlist

```bash
ruby scripts/build-shortlist.rb --out /tmp/qs-assessment-<acct>
```

Scores each analysis:
- `value = views × √(distinct_users)` *(if `usage.json` supplied)* — or
  `10 × (sheets + visuals/4)` *(complexity-only fallback)*
- `cost  = 10·unhandled + 3·manual + 1·hint`
- `score = value / (1 + cost)`

Same tag vocabulary as the other assessment skills: `migrate-first` / `easy-win`
/ `moderate` / `needs-gap-scout` / `retire`.

---

## Phase 5 — Render the readout

```bash
ruby scripts/render-readout.rb --out /tmp/qs-assessment-<acct>
```

Composes the markdown report (template at `refs/readout-template.md`). Sections:
environment, visual-type mix, analysis complexity, datasets/sources, priority,
shortlist, per-analysis complexity, found-vs-not, privacy, hand-off, next steps.
Carries a Standard-edition banner when the definition APIs were rejected and a
limited-mode banner when usage data is absent.

---

## Phase 6 — Migration plan (always run)

```bash
ruby scripts/migration-plan.rb --out /tmp/qs-assessment-<acct>
```

Composes `migration-plan.json` — the hand-off contract for `quicksight-to-sigma`.
Each analysis gets a `recommended_path`:

| `recommended_path` | Means |
|---|---|
| `quicksight-to-sigma` | Ready for conversion. ≤5 manual/unhandled features. |
| `quicksight-to-sigma-with-scout` | Has window calcs / exotic visuals / free-form layout — needs a design decision first. |
| `retire` | Zero views (usage-supplied mode only); recommend not migrating. |
| `blocked` | >5 manual/unhandled features; needs human rework first. |

**DM clusters** are keyed on the **shared dataset** — analyses that reference the
same QuickSight dataset (or transitively overlap) share a Sigma data model by
construction. Cleaner than Tableau's `.twb`-table Jaccard; like Power BI's
shared-model clustering.

---

## Phase 7 — Hand off to `quicksight-to-sigma`

Present the migration-plan summary and let the user pick the next step (single
analysis, top-N batch, or just keep the readout). Invoke the converter in the
same conversation:

```
Skill(
  skill: "quicksight-to-sigma",
  args:  "Convert analysis <id> (<name>) from the just-finished assessment at
          /tmp/qs-assessment-<acct>. Read migration-plan.json for the
          recommended_path, blockers, dataset_source_types, and the cluster's
          shared datasets. The decoded analysis definition is in raw-defs/ and
          the dataset describes in raw-datasets/ — reuse them instead of
          re-extracting."
)
```

The decoded `raw-defs/` and `raw-datasets/` overlap the converter's Phase-2
discovery output; the converter can reuse them rather than re-calling the AWS
CLI.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `list-analyses FAILED` | AWS creds not configured / wrong region | `aws sso login` (or `gimme-aws-creds`); confirm `aws sts get-caller-identity`; try `--region us-east-1` |
| All analyses show `def_error` + `enterprise: false` | Standard-edition account | Expected — definition APIs are Enterprise-only; readout degrades to counts-only |
| `def_error: AccessDenied` on an Enterprise account | IAM/QuickSight permissions missing the `quicksight:DescribeAnalysisDefinition` action | Grant the describe-definition + describe-data-set permissions |
| Empty visual histogram on an analysis you know is rich | Visual union node name not in the built/mid/unhandled sets | Check `VISUAL_*` sets in `quicksight-inventory.py`; unknown nodes default to mid |
| Datasets section empty | Datasets describe failed or analysis uses dataset-of-datasets | Check `raw-datasets/`; dataset-of-datasets is out of scope (a known converter gap) |
| `region` wrong / resources missing | Identity region ≠ data region | QuickSight reads from the identity region — almost always `us-east-1` |

See `refs/migration-test-slate.md` (in the `quicksight-to-sigma` skill) for the
complexity taxonomy + 20-dashboard test slate the buckets are grounded in.
