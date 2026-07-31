---
name: hex-assessment
description: Inventory a Hex instance and produce a migration-readiness readout — environment counts, content mix, complexity, and a value/cost-ranked shortlist. Read-only.
---

# Hex migration assessment (read-only)

> SCAFFOLD — deferred. `hex-to-sigma`'s first pass (a single-project
> conversion) was the priority; this assessment skill is not yet built out.
> Assessments never write to the source or post to Sigma. Produce the
> standard readout (see other `*-assessment` skills) and hand off to
> `hex-to-sigma`.

## Phase 0 — Connect
TODO: auth to Hex. Note for whoever builds this: Hex's public REST API
(`learn.hex.tech/docs/api/api-overview`) DOES cover project listing/metadata
and `GetQueriedTables` (Enterprise-only, useful for estate-wide table-usage
counts) even though it can't return cell content — that's enough for an
inventory pass without needing per-project `.hex.yaml` exports.

## Phase 1 — Inventory
TODO: enumerate projects via `ListProjects`/`GetProject`; dedup with
`scripts/dup-dashboards.py`. Per-project complexity scoring (cell-type mix,
Python-cell prevalence, chart-type mix) needs the `.hex.yaml` export per
project — no way around that for content-level detail, only counts/metadata
are API-reachable.

## Phase 2 — Score + shortlist
TODO: complexity score + value/cost-ranked migration shortlist + readout.
Flag Python-heavy projects as higher-effort up front (see `hex-to-sigma`
SKILL.md's Gaps section — Python/CODE cells have no automatic translation).
