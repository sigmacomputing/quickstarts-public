# Amazon QuickSight Assessment

A Claude Code skill that inventories an Amazon QuickSight account and produces a
migration-readiness readout. Designed to be run by a customer (or a Sigma rep
with the customer present) before deciding which QuickSight analyses to migrate
to Sigma.

**READ-ONLY.** Every call is a `list-*` / `describe-*` (GET-equivalent). The
skill never writes to QuickSight and never posts to Sigma.

This is the QuickSight sibling of [`tableau-assessment`](../../../tableau-to-sigma/skills/tableau-assessment/)
and [`powerbi-assessment`](../../../powerbi-to-sigma/skills/powerbi-assessment/) —
same file layout, same readout sections, same privacy discipline, same
value/cost shortlist scoring — adapted to QuickSight's two-artifact world
(analysis + datasets).

## What it produces

A directory (`/tmp/qs-assessment-<acct>/`) with:

- `readout.html` — a Sigma-branded, share-friendly HTML report (the customer
  deliverable): environment KPIs, analysis/dashboard priority, dataset reuse &
  concentration, data-source patterns (SPICE / DIRECT_QUERY, warehouse vs
  file/S3), ingestion & refresh activity, a value/cost-ranked **migration
  shortlist** + per-analysis conversion profile, data handling, hand-off package,
  and next steps. Render it with `scripts/render-readout-html.rb`.
- `readout.md` — the same report as markdown (template at `refs/readout-template.md`).
- `inventory.json` — raw environment + per-analysis + per-dataset metadata.
- `complexity.json` — per-analysis convertibility scoring
  (`n_auto` / `n_hint` / `n_manual` / `n_unhandled`).
- `shortlist.json` — the value/cost-ranked migration shortlist as JSON.
- `migration-plan.json` — per-analysis `recommended_path` + DM clusters (keyed on
  shared dataset), directly consumable by the `quicksight-to-sigma` skill.
- `raw-defs/`, `raw-datasets/` — decoded analysis + dataset definitions (delete
  after review).

Nothing in this directory is uploaded anywhere.

## Prerequisites

- Claude Code installed
- **AWS CLI v2**, authenticated to the account you want to assess (`aws sso login
  --profile <p>`, or `gimme-aws-creds` for Okta-fronted orgs). Confirm with
  `aws sts get-caller-identity --profile <p>`. No Python packages — the inventory
  script shells out to the CLI (see `scripts/requirements.txt`).
- **Enterprise edition** for the complexity layer. The
  `describe-analysis-definition` / `describe-data-set` APIs are Enterprise-only; a
  Standard account is detected and degraded to a counts-only readout (it never
  crashes).
- QuickSight reads from the **identity region** — pass `--region us-east-1` unless
  you know the account is regionalized differently.

## How to run

In Claude Code:

```
/quicksight-assessment
```

The skill will:

1. Probe access + edition (`get-caller-identity`, `list-analyses`).
2. Inventory analyses, dashboards, datasets, data sources; per-analysis
   AnalysisDefinition (visual mix, calc-field a/b/c buckets, params, FilterGroups,
   layout shape); per-dataset source / prep / RLS.
   (`quicksight-inventory.py` → `inventory.json`, `raw-defs/`, `raw-datasets/`)
3. Score per-analysis convertibility.
   (`score-quicksight-complexity.rb` → `complexity.json`)
4. Cross-tabulate into a value/cost-ranked migration shortlist.
   (`build-shortlist.rb` → `shortlist.json`)
5. Render the report.
   (`render-readout.rb` → `readout.md`; `render-readout-html.rb` → `readout.html`)
6. Compose the hand-off contract.
   (`migration-plan.rb` → `migration-plan.json`)
7. Offer to hand off to `quicksight-to-sigma`.

## Modes

| Mode | Setup | Coverage |
|---|---|---|
| **Complexity-only** *(default)* | AWS CLI + Enterprise | Environment + per-analysis visual/calc complexity + per-dataset sources + complexity-only shortlist |
| **Usage-weighted** | Supply a CloudTrail/CloudWatch-derived `usage.json` | Adds view/user weighting → usage-weighted shortlist + cold-analysis detection |

QuickSight has no per-analysis view-count API on the standard surface, so the
default is complexity-only; the readout says so.

## Convertibility taxonomy (what drives the scoring)

- **auto** (easy): built visuals (KPI / bar / line / pie), mechanical calc fields,
  warehouse-backed datasets (RelationalTable / CustomSql).
- **manual** (medium): mid-catalog visuals (table / pivot / combo / scatter /
  gauge / …), restructuring calc fields, dataset joins + data-prep transforms,
  parameters, RLS/CLS.
- **unhandled** (hard): window / table-calc functions (no Sigma equivalent →
  `/* TODO */`), exotic visuals (maps, sankey, insight ML, custom content,
  plugin), free-form / section-based layout, analysis-level FilterGroups, S3 /
  uploaded-file sources.

Per-analysis `cost = 10·unhandled + 3·manual + 1·hint`; `score = value / (1 + cost)`.

## What this is NOT

- **Not** a write tool. It cannot and will not modify QuickSight or Sigma.
- **Not** a complete account audit. It covers the signals that matter for Sigma
  migration scoping, scoped to **what the configured AWS credentials can reach**.
- **Not** the converter. It scopes; `quicksight-to-sigma` converts. The
  `migration-plan.json` is the hand-off between them.

## Privacy

This skill sends analysis/dataset metadata (not warehouse rows) through the
Anthropic API — including **calc-field expressions** from each AnalysisDefinition.
See [`PRIVACY.md`](./PRIVACY.md) for the full disclosure to review with your
privacy/legal team before running.

## Reusing this for migration

The `migration-plan.json` output is directly consumable by `quicksight-to-sigma`:

```
/quicksight-to-sigma migrate the top analyses from this plan: /tmp/qs-assessment-<acct>/migration-plan.json
```

Analyses are pre-grouped into DM clusters (analyses that reference the same
QuickSight dataset share one Sigma data model by construction), and the decoded
`raw-defs/` + `raw-datasets/` overlap the converter's Phase-2 discovery output —
the converter reuses them rather than re-calling the AWS CLI.

## Sibling skills

- [`quicksight-to-sigma`](../../) — the conversion skill this feeds into.
- [`tableau-assessment`](../../../tableau-to-sigma/skills/tableau-assessment/) — the Tableau analog.
- [`powerbi-assessment`](../../../powerbi-to-sigma/skills/powerbi-assessment/) — the Power BI analog.
