---
name: thoughtspot-assessment
description: Take inventory of a ThoughtSpot instance and produce a migration-readiness readout — models/worksheets, Liveboards, Answers, tables, connections, per-object usage (views + distinct users from TS: BI Server), per-Liveboard chart-type mix and complexity, ownership concentration, Embrace-vs-Falcon data-source patterns, and a value/cost-ranked migration shortlist. Use to scope a ThoughtSpot→Sigma migration or audit BI sprawl. Read-only.
user-invocable: true
---

# ThoughtSpot migration assessment

Read-only pre-scoping for a ThoughtSpot → Sigma migration. Complements
`thoughtspot-to-sigma` (which does the actual conversion). Designed for a **real,
populated production instance** — usage data is a first-class signal, not an
optional extra.

## Auth
Same as `thoughtspot-to-sigma`: `TS_HOST` + `TS_TOKEN` (SSO session token or
Trusted-Auth service token). For the usage axis the identity needs admin scope so
it can read the `TS: BI Server` system worksheet. No Sigma credentials needed —
this only reads ThoughtSpot.

## Run
`scripts/scan.py` — inventories the instance via `metadata/search`
(LOGICAL_TABLE / LIVEBOARD / ANSWER / CONNECTION), pulls per-object usage from
`TS: BI Server`, exports each Liveboard's TML, and per Liveboard scores migration
complexity: viz count + distinct chart kinds + models touched + TML formula and
filter weight. Writes `~/thoughtspot-migration/assessment.json`.

Then render the customer-facing report:
`ruby scripts/render-readout-html.rb --out ~/thoughtspot-migration`
→ `~/thoughtspot-migration/readout.html` (Sigma-branded, share-friendly).

`scripts/render-readout-html.rb` is the **canonical renderer** (the old
`render_html.py` is superseded — keep using the Ruby one for parity with the
tableau / powerbi / qlik / quicksight assessment skills).

## What the readout covers
- **01 Environment overview** — KPI tiles: Liveboards, Answers, models/worksheets,
  tables, connections.
- **02 Liveboard priority & usage** — usage-ranked with bars from `TS: BI Server`;
  cold / zero-view detection for retirement candidates.
- **03 Ownership & concentration** — Liveboards by author; top-author concentration.
- **04 Data-source patterns** — Embrace (live warehouse) vs Falcon (in-memory),
  file-uploaded tables flagged for warehouse landing.
- **05 User activity** — per-user action volume (only when `TS: BI Server` usage
  is present).
- **Migration shortlist + per-Liveboard complexity** — value/cost ranking, tag
  pills (migrate-first / easy-win / needs-review / retire), chart-type coverage,
  and the set of models the Liveboards depend on (migrate these first).

## Usage data
On a populated instance, `TS: BI Server` (ThoughtSpot's built-in activity log)
yields per-Liveboard views + distinct users and per-user activity (admin scope).
This drives the value/cost shortlist and cold-content detection. If the worksheet
is genuinely absent (a brand-new instance, or a non-admin identity), the scan
records a single note and falls back to effort-only ranking — but the design and
the readout assume the populated case.

## Chart-type coverage
The `thoughtspot-to-sigma` pipeline maps KPI / COLUMN / BAR / LINE / PIE / TABLE
/ ADVANCED_COLUMN / stacked / area / LINE_COLUMN to Sigma equivalents. Flagged
for review (no direct 1:1 in the current pipeline): SCATTER, BUBBLE, GEO_AREA,
PIVOT_TABLE, WATERFALL, FUNNEL, TREEMAP, LINE_STACKED_COLUMN. Sigma supports most
of these natively — they just need element-builder mapping work.

## Notes
- TML export embeds raw control chars in JSON → `json.loads(..., strict=False)`.
- ThoughtSpot TML uses bare `=` (`oper: =`) which trips PyYAML's value tag — the
  scan registers a constructor that reads it as a string.
- System / sample Liveboards are export-FORBIDDEN for a normal identity; the scan
  counts them separately ("system/locked") rather than treating that as failure.
- Privacy: see `PRIVACY.md`. Output shapes: see `refs/output-shapes.md`. Readout
  layout: see `refs/readout-template.md`.
