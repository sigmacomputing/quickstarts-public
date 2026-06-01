# Tableau Assessment

A Claude Code skill that inventories a Tableau Cloud site and produces a
migration-readiness readout in about 90 seconds. Designed to be run by a
customer admin (or a Sigma rep with the customer present) before deciding
whether to migrate to Sigma or invest in a deeper Hakkoda assessment.

## What it produces

A directory with five files:

- `readout.md` — a 12-section markdown report covering environment counts,
  licenses, ownership, datasource mix, refresh history, per-workbook usage,
  a value-ranked **migration shortlist**, and a per-workbook complexity table.
- `inventory.json` — raw aggregated counts from Tableau's built-in Admin
  Insights datasources.
- `complexity.json` — per-workbook gap-scan results from running the
  `tableau-to-sigma` skill's static-analysis pass against every `.twb`.
- `shortlist.json` — the migration shortlist as machine-readable JSON, suitable
  for handing to the `tableau-to-sigma` skill to actually convert the top N.
- `twbs/` — cached `.twb` files (you can delete these after review).

Nothing in this directory is uploaded anywhere. If you want to share it, do so
deliberately (zip and email, for example).

## Prerequisites

- Claude Code installed
- A Tableau Cloud account with **Site Admin** role on the site you want to assess
  (Site Admin is the role that can read Admin Insights — Tableau's built-in
  audit datasources)
- For the full readout: a Tableau Personal Access Token (PAT) — see "Setting up
  PAT" below. Without a PAT, the skill runs in limited mode and skips the
  per-workbook complexity layer.

## How to run

In Claude Code, with the Tableau MCP loaded:

```
/tableau-assessment
```

The skill will:

1. Probe whether Admin Insights is reachable (gates the license / refresh / usage sections)
2. Pull aggregated counts via MCP `query-datasource` calls against Admin Insights
3. *(PAT mode)* Download every workbook's `.twb` content in parallel and run the
   tableau-to-sigma gap-scanner against each
4. Cross-tabulate usage with complexity to produce the migration shortlist
5. Render `readout.md` and the JSON files into `/tmp/assessment-<sitename>/`

Total runtime: ~30 seconds in MCP-only mode, ~90 seconds in PAT mode.

## Setting up PAT

PAT mode is recommended — it unlocks the migration shortlist and per-workbook
complexity scoring. To configure:

1. In Tableau Cloud, go to your account settings → **Personal Access Tokens**.
   Create a new token. Save the secret somewhere safe — Tableau only shows it once.
2. Run the setup wizard:
   ```
   ruby scripts/setup-tableau.sh
   ```
   It will ask for: site URL, site contentUrl (the path segment after `/site/`),
   PAT name, PAT secret. It stores them in `~/.tableau-to-sigma/config.yaml`.
3. The skill will use the PAT automatically on subsequent runs.

If your PAT expires or you get authentication errors after the token's been
unused for a while, re-run the setup wizard.

## What this is NOT

- **Not** a replacement for Hakkoda's Assessment App. That tool runs inside
  your Snowflake account and never sends data outside; it's the right choice
  when you've moved past pre-scoping into a real migration evaluation. This
  skill is the 5-minute precursor.
- **Not** a complete inventory of every Tableau feature. It covers the
  signals that matter for Sigma migration scoping. For a permissions audit
  or dataset-similarity deep-dive, use Hakkoda's app.
- **Not** a Tableau Server (on-prem) tool. Built and tested for Tableau Cloud
  only. Server *probably* works (Admin Insights exists there too) but is
  untested.

## Privacy

This skill sends workbook metadata (not warehouse rows) through the Anthropic
API on its way through Claude. See [`PRIVACY.md`](./PRIVACY.md) for the full
disclosure to review with your privacy/legal team before running. The short
version: aggregate counts and `.twb` XML cross the wire; view CSVs, warehouse
rows, and `.hyper` extracts do not.

## Reusing this for migration

The whole point of running this is to plan the next step. The `shortlist.json`
output is directly consumable by the `tableau-to-sigma` skill:

```
/tableau-to-sigma migrate the top 5 from this shortlist: <paths or URLs>
```

The top of the shortlist by `value / (1 + cost)` is, by construction, the
highest-leverage / lowest-risk batch to start with.

## Troubleshooting

See `SKILL.md` "Troubleshooting" section. Common things:

- **"Admin Insights is empty"** → you're not a Site Admin. Either get the role
  granted or run in limited mode.
- **PAT signin fails 4 times in a row** → Tableau Cloud invalidates the PAT.
  Mint a new one in account settings and re-run `setup-tableau.sh`.
- **`get-datasource-metadata` returns 401 under parallel fan-out** → known
  VizQL session contention. The skill serializes these calls, so this only
  affects manual probing.

## Where it lives

This skill ships with the `Migrating From Tableau Made Easy` QuickStart in [`sigmacomputing/quickstarts-public`](https://github.com/sigmacomputing/quickstarts-public/tree/main/tableau-migration-skills), alongside its sibling skills `tableau-to-sigma` and `tableau-vds-to-snowflake`.

Sibling skill: [`tableau-to-sigma`](../tableau-to-sigma/) — the conversion skill the migration shortlist feeds into.
