# Privacy & data handling — `thoughtspot-assessment`

Read this before running the skill, and share it with your privacy / security /
legal team if your organization needs to review tools that send report and
model metadata through a third-party LLM API.

## What this skill reads and writes

**READ-ONLY.** The skill never writes to ThoughtSpot and never posts to Sigma.
It connects to **two systems** on your behalf:

1. **Your ThoughtSpot instance**, via the ThoughtSpot REST v2 API, authenticated
   as **you** through `TS_HOST` + `TS_TOKEN` (an SSO session token or a
   Trusted-Auth service token). The skill reads:
   - Object listings via `metadata/search` (LOGICAL_TABLE / LIVEBOARD / ANSWER /
     CONNECTION) — counts, names, authors, connection types
   - Per-Liveboard **TML** via `metadata/tml/export` (visualization config, chart
     types, referenced models/worksheets, and any TML **formula** text)
   - Per-object **usage** via `searchdata` against the `TS: BI Server` system
     worksheet (views, distinct users, per-user activity) — admin scope
2. **The Anthropic API**, via Claude Code, to drive the agent.

Everything the skill reads passes through Claude (and therefore the Anthropic
API) on its way to producing the readout. Anthropic's API data handling:
<https://www.anthropic.com/legal/privacy>.

## What crosses the Anthropic API

| Crosses API | Stays in your environment |
|---|---|
| **Aggregate counts** (Liveboard / Answer / model / table / connection totals) | Warehouse rows (this skill **never** queries the underlying database) |
| **Names**: Liveboard, model/worksheet, table, connection names; author names | Connection / database credentials |
| **Liveboard TML** — visualization config, chart types, referenced models, and **TML formula expressions** (calculated-field definitions) | Falcon in-memory data and uploaded file (CSV/XLSX) contents |
| **Usage**: per-object views + distinct users, per-user action volume from `TS: BI Server` | Answer result-set data (only metadata is read, never the rendered values) |
| Connection **type** strings (e.g. `RDBMS_SNOWFLAKE`) — not credentials | |

The TML does **NOT** contain row-level data from your warehouse. If your TML
formulas encode business-sensitive logic, that text crosses the API — tell
stakeholders before running. ThoughtSpot has no Tableau-style custom SQL or
Power-BI-style RLS-role-definition surface in the TML the scan reads; the most
sensitive payload is the formula text.

## What stays local

All outputs are written to `~/thoughtspot-migration/` (or the `--out` directory
you choose) and are **not uploaded anywhere**. `assessment.json` holds the full
machine-readable report; `readout.html` is the share-friendly rendering. To share
with a Sigma rep, that's a deliberate action you take (zip and send).

You can delete the outputs after review:

```bash
rm -rf ~/thoughtspot-migration
```

## How to limit exposure

1. **Review `assessment.json` before sharing** — it carries Liveboard/model names
   and TML formula counts (the renderer surfaces counts, not formula bodies; the
   bodies live in the exported TML the agent read transiently).
2. **Run with a scoped identity** if you only want to assess a subset of content
   visible to that identity.
3. **Delete `~/thoughtspot-migration` immediately after rendering** (command
   above).

## Where to direct privacy questions

- Anthropic API privacy: <https://www.anthropic.com/legal/privacy>
- ThoughtSpot REST v2 API: <https://developers.thoughtspot.com/docs/rest-apiv2>
- This skill's source: every script under `scripts/` runs on your behalf and is
  readable — `scan.py` is the only one that touches the network, and every call
  is a read (`metadata/search`, `metadata/tml/export`, `searchdata`).
- Sigma privacy policy: <https://www.sigmacomputing.com/privacy-policy>
