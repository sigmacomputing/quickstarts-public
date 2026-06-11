# Power BI / Fabric Assessment

A Claude Code skill that inventories a Power BI / Fabric tenant and produces a
migration-readiness readout. Designed to be run by a customer (or a Sigma rep
with the customer present) before deciding which Power BI reports to migrate to
Sigma.

**READ-ONLY.** Every call is a GET (plus one read-only Scanner-API probe). The
skill never writes to Power BI and never posts to Sigma.

## What it produces

A directory (`/tmp/pbi-assessment-<tenant>/`) with:

- `readout.md` — a 12-section markdown report: environment counts, per-workspace
  on-capacity flags, **per-semantic-model DAX complexity** (measures / calc
  columns / calc tables / RLS / DirectQuery / warehouse sources), per-report
  visual complexity, refresh history, a value-ranked **migration shortlist**,
  and a per-report complexity table.
- `inventory.json` — raw environment + per-model + per-report metadata.
- `complexity.json` — per-report DAX/visual complexity scoring.
- `shortlist.json` — the migration shortlist as machine-readable JSON.
- `migration-plan.json` — per-report `recommended_path` + DM clusters, directly
  consumable by the `powerbi-to-sigma` skill.
- `raw-tmsl/`, `raw-pbir/` — decoded model + report definitions (delete after review).

Nothing in this directory is uploaded anywhere.

## Prerequisites

- Claude Code installed
- A Power BI / Fabric account on the tenant you want to assess (any user — no
  admin role required for the core readout)
- Python venv at `/tmp/pbiauth` with `msal`, `requests`, `truststore` (shared
  with the `powerbi-to-sigma` skill). Install: `pip install -r scripts/requirements.txt`
- A signed-in token cached at `/tmp/pbiauth/cache.bin` (any `powerbi-to-sigma`
  run seeds it; otherwise the skill signs you in once via device code)

For the **usage axis** (views, distinct users), you need the **Fabric
Administrator** role. Without it the skill runs in complexity-only mode and says
so — it never fails.

## How to run

In Claude Code:

```
/powerbi-assessment
```

The skill will:

1. Probe whether you have the Fabric Administrator role (gates the usage section)
2. Inventory workspaces, items, semantic models (TMSL), reports (PBIR), refresh history
3. Score per-report DAX-convertibility + visual complexity
4. *(admin only)* Pull per-report usage via the Activity Events API
5. Cross-tabulate into a value/cost-ranked migration shortlist
6. Render `readout.md` and the JSON files into `/tmp/pbi-assessment-<tenant>/`
7. Compose `migration-plan.json` and offer to hand off to `powerbi-to-sigma`

## Auth — the no-Entra-app recipe

This skill uses device-code sign-in against a Microsoft first-party public
client (the well-known PowerBI Desktop client), so it needs **no Entra app
registration and no admin consent**. The full rationale (why XMLA, Git
integration, and app registration are dead ends in a locked-down corp tenant)
is in `powerbi-to-sigma/refs/connection.md`. `truststore.inject_into_ssl()` is
mandatory on corp networks that MITM-inspect TLS.

## What this is NOT

- **Not** a write tool. It cannot and will not modify Power BI or Sigma.
- **Not** a complete tenant audit. It covers the signals that matter for Sigma
  migration scoping, scoped to **what the signed-in user can access**. A
  tenant-wide sprawl scan needs the Scanner API (Fabric Administrator).
- **Not** the converter. It scopes; `powerbi-to-sigma` converts. The
  `migration-plan.json` is the hand-off between them.

## Privacy

This skill sends report/model metadata (not warehouse rows) through the
Anthropic API. Critically, it pulls **full TMSL (DAX expressions + RLS role
definitions)** and **PBIR (visual config)** — richer and more sensitive than the
Tableau assessment's `.twb` scan. See [`PRIVACY.md`](./PRIVACY.md) for the full
disclosure to review with your privacy/legal team before running.

## Reusing this for migration

The `migration-plan.json` output is directly consumable by `powerbi-to-sigma`:

```
/powerbi-to-sigma migrate the top reports from this plan: /tmp/pbi-assessment-<tenant>/migration-plan.json
```

Reports are pre-grouped into DM clusters (one Sigma data model per Power BI
semantic model), so a cluster's reports can share a single converted data model.

## Sibling skills

- [`powerbi-to-sigma`](../powerbi-to-sigma/) — the conversion skill this feeds into.
- [`tableau-assessment`](../tableau-assessment/) — the Tableau analog this skill mirrors.

## Where it lives

Part of `sigma-skills-staging` — Sigma's staging repo for not-yet-graduated
skills. Once validated against real customer tenants it moves to the public repo.
