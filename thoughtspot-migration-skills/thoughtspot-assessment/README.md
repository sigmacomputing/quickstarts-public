# ThoughtSpot Assessment

A Claude Code skill that inventories a ThoughtSpot instance and produces a
migration-readiness readout. Designed to be run by a customer (or a Sigma rep
with the customer present) before deciding which Liveboards to migrate to Sigma.

**READ-ONLY.** Every call is a read (`metadata/search`, `metadata/tml/export`,
`searchdata`). The skill never writes to ThoughtSpot and never posts to Sigma.

Built for a **real, populated production instance** — per-object usage from the
`TS: BI Server` system worksheet is a first-class input, not an optional extra.

## What it produces

A directory (`~/thoughtspot-migration/`) with:

- `readout.html` — a Sigma-branded, share-friendly report: environment counts,
  usage-ranked Liveboard priority, ownership concentration, Embrace-vs-Falcon
  data-source patterns, user activity, a value/cost-ranked **migration
  shortlist**, per-Liveboard complexity, and chart-type coverage.
- `assessment.json` — the full machine-readable report (the renderer's input).

Nothing in this directory is uploaded anywhere.

## Prerequisites

- Claude Code installed
- `TS_HOST` + `TS_TOKEN` for the instance you want to assess (an SSO session
  token or a Trusted-Auth service token). For the usage axis, the identity needs
  **admin scope** so it can read `TS: BI Server`.
- Python 3 with `pyyaml` (`pip install pyyaml`)
- Ruby (for the renderer — stdlib only, no gems)

## How to run

In Claude Code:

```
/thoughtspot-assessment
```

The skill will:

1. Inventory connections, tables, models/worksheets, Liveboards, Answers via
   `metadata/search`
2. Resolve the `TS: BI Server` system worksheet and query per-Liveboard views +
   distinct users + per-user activity
3. Export each Liveboard's TML and score per-Liveboard complexity (viz count,
   chart kinds, models touched, TML formulas, filters)
4. Classify connections (Embrace live vs Falcon in-memory) and flag file-uploaded
   tables
5. Cross-tabulate into a value/cost-ranked migration shortlist
6. Write `assessment.json`, then render `readout.html`:
   `ruby scripts/render-readout-html.rb --out ~/thoughtspot-migration`

## Usage data — the populated-instance assumption

`TS: BI Server` is ThoughtSpot's built-in activity log. On a populated instance
it yields per-object views + distinct users and per-user activity, which drives
the value/cost shortlist and cold-content (retirement) detection. If the
worksheet is genuinely absent — a brand-new instance, or an identity without
admin scope — the scan records a single note and falls back to ranking by
conversion effort. It never fails.

## What this is NOT

- **Not** a write tool. It cannot and will not modify ThoughtSpot or Sigma.
- **Not** a complete instance audit. It covers the signals that matter for Sigma
  migration scoping, scoped to **what the authenticated identity can read**.
  System / sample Liveboards are export-forbidden and counted separately.
- **Not** the converter. It scopes; `thoughtspot-to-sigma` converts.

## Privacy

This skill sends Liveboard/model metadata and TML (including TML formula text)
through the Anthropic API — not warehouse rows. See [`PRIVACY.md`](./PRIVACY.md)
for the full disclosure to review with your privacy/legal team before running.

## Sibling skills

- [`thoughtspot-to-sigma`](../thoughtspot-to-sigma/) — the conversion skill this feeds into.
- [`tableau-assessment`](../../tableau-to-sigma/skills/tableau-assessment/) — the gold-standard analog this skill mirrors.

## Where it lives

Part of the `sigma-migration-skills` plugin set. The renderer
(`scripts/render-readout-html.rb`) shares its Sigma-branded theme byte-for-byte
with the tableau / powerbi / qlik / quicksight assessment readouts.
