author: Sigma Computing
summary: Migrating from MicroStrategy made easy — convert Strategy One semantic models and dossiers to Sigma with Claude Code
id: developers_migrating_from_microstrategy_made_easy
categories: Developers, Migration, AI
environments: Web
status: Draft
feedback link: https://github.com/twells89/microstrategy-to-sigma/issues

# Migrating from MicroStrategy to Sigma made easy

## Introduction & why it matters
Duration: 2

Rebuilding MicroStrategy content by hand means re-deriving every attribute's
key mapping, re-typing every metric formula, and hoping the numbers still tie
out — across a semantic layer (attributes, facts, metrics), reports, and
dossiers.

This quickstart automates the path with **your coding agent** (Claude Code,
Cursor, Cortex Code, …) + the MicroStrategy→Sigma skills: discover content
over the MicroStrategy REST API, extract the dossier *and* the semantic model
behind it, build a Sigma data model and matching workbook, and **verify data
parity** against the same warehouse.

positive
: **Validation status:** live-validated end-to-end on a Strategy One cloud
trial against Snowflake — exact parity on every row of every report in the
fixture (money/counts exact, ratios 1e-6), for both the classic project
schema **and** the newer Mosaic "Data Model" objects.

negative
: Dossier **visualization authoring** has no public REST surface, so the
parity-proven build path is grids; chart viz types are extracted and mapped
by lookup, and anything unmapped is **flagged as a table, never faked**.

## Who this is for
Duration: 1

- Sigma SEs and technical CSMs
- Migration partners
- MicroStrategy admins evaluating a move to Sigma

## Prerequisites
Duration: 2

- **A coding agent that runs skills** — Claude Code (CLI or desktop), Cursor, etc.
- **MicroStrategy REST access** — any Library deployment exposes it at
  `…/MicroStrategyLibrary/api` (cloud trials included; no API key concept —
  standard login works): `MSTR_BASE_URL`, `MSTR_USERNAME`, `MSTR_PASSWORD`.
- **Sigma API credentials** (`SIGMA_CLIENT_ID` / `SIGMA_CLIENT_SECRET`,
  or `~/.sigma-migration/env`).
- **The same warehouse on both sides** — Sigma's connection must reach the
  database MicroStrategy queries. In-memory cubes migrate as their
  *underlying* warehouse tables.

## Assess the estate (optional, ~minutes)
Duration: 5

```bash
export MSTR_BASE_URL="https://<env>/MicroStrategyLibrary" \
       MSTR_USERNAME="…" MSTR_PASSWORD="…"
python3 skills/microstrategy-assessment/scripts/assess.py --out /tmp/mstr-assessment
open /tmp/mstr-assessment/readout.md
```

The readout inventories projects, reports, documents, and dossiers, walks
panel stacks for a visualization-type histogram, and tags each dossier
migrate-first / moderate / needs-review against the converter's actual
coverage.

## Migrate a dossier
Duration: 15

Ask your agent:

> Migrate my MicroStrategy dossier "Orders Performance Overview" to Sigma.

The `microstrategy-to-sigma` skill walks the phases: discover → `extract.py`
(dossier + every attribute/fact/metric/table it touches → `bundle.json`;
join keys are recovered from attributes whose ID form maps to both the fact
and a lookup table) → `convert.py` (→ Sigma data model + workbook specs,
metrics translated incl. `Count<Distinct=True>` and compound ratios) →
POST + readback gate (hard-fails on any error-typed column) →
`verify_parity.py` (hard gate: every row compared to numbers re-executed
from MicroStrategy itself — expected values are never invented).

negative
: If a report groups by an attribute with a **non-unique key**, MicroStrategy's
Analytical Engine silently collapses groups to arbitrary representative rows.
The skill detects this and reproduces it deterministically
(`resolve_ae_winners.py`) instead of shipping a near-miss.

## Strategy One Data Models (Mosaic)
Duration: 3

If the customer models in the newer **Data Model** objects instead of the
classic schema, the same flow applies: `extract_datamodel.py` pulls tables,
attributes, factMetrics, metrics, and relationships (`refs/datamodels.md`
documents the dataServer-pipeline binding and the
`POST /v2/cubes/{id}/instances` parity-query path).

## Verify & wrap up
Duration: 3

- Parity gate: `verify_parity.py` green — all rows, exact (ratios 1e-6).
- Readback gate: no `type: "error"` columns in the DM or workbook spec.
- Finalize gate: `assert-phase6-ran.rb` — seven shared gates including the
  layout lint and the control-wiring lint (dossier selectors/chapter filters
  convert to Sigma controls wired to their declared viz targets).
- Anything flagged (unmapped viz types, prompts, panel selectors) is listed
  in the conversion notes and `control-scope.json` for human follow-up —
  loud and explicit, never silent.
