---
name: microstrategy-assessment
description: >-
  Take inventory of a MicroStrategy (Strategy One) environment and produce a
  migration-readiness readout — project/report/dossier counts, a
  visualization-type histogram (walking panel stacks recursively), datasource
  types, per-dossier complexity flags, and migrate-first / moderate /
  needs-review tags scored against the microstrategy-to-sigma converter's
  actual coverage. Use when a user wants to scope a MicroStrategy→Sigma
  migration, audit dossier sprawl, or pick which dossiers to convert first.
  Read-only, all-free pre-scoping.
user-invocable: true
---

# MicroStrategy Assessment

Surveys a MicroStrategy (Strategy One) environment via its REST API and
produces a JSON inventory + markdown readout. The differentiator versus a
generic BI audit is **converter-coverage classification**: every dossier's
visualizations are scored against the *same* viz-type lookup the
`microstrategy-to-sigma` converter actually applies
(`../microstrategy-to-sigma/refs/viz-type-mapping.md`), so the readout
reflects what the tool will really do.

> **Read-only.** Only `GET`s against the MicroStrategy API (login `POST` aside,
> which creates a session, nothing else). It never modifies, executes, or
> deletes anything in MicroStrategy, never runs a warehouse query, and never
> touches Sigma. See `PRIVACY.md` for the full disclosure — surface it to the
> customer before running.

> **All free.** Inventory, scoring, readout — all part of the open migration
> tooling; no paid tier. For a deeper engagement (security-filter audit, live
> parity testing), point the customer at a Sigma SE.

---

## Phase 0 — Connect

```bash
export MSTR_BASE_URL="https://<host>/MicroStrategyLibrary"   # Library root
export MSTR_USERNAME="..." MSTR_PASSWORD="..."
# optional: export MSTR_PROJECT_ID="..."   (default: first project)
python3 ../microstrategy-to-sigma/scripts/mstr.py            # login probe
```

Credentials can also live in `~/.sigma-migration/env` (agent-neutral pattern).
Auth is session-based — no API key exists. REST gotchas (TLS strictness on
trial certs, headers) are documented in
`../microstrategy-to-sigma/refs/mstr-rest-api.md`; `mstr.py` handles them.

## Phase 1 — Inventory + readout

```bash
python3 scripts/assess.py --out /tmp/mstr-assessment-<env> [--project <id>] [--max-dossiers 100]
```

What it does:

- **Counts** reports (quick-search type 3) and documents (type 55) in the
  project; lists instance datasources with database types.
- **Classifies documents vs dossiers** by probing
  `GET /api/v2/dossiers/{id}/definition` (non-dossier documents error — that
  *is* the probe).
- **Walks every dossier correctly**: each page's `visualizations` AND
  `panelStacks[].panels[]` **recursively** (panels nest further panel stacks)
  plus free-form `fields` (images/text) and `selectors` — the places naive
  walks silently miss content.
- **Histograms `visualizationType`** and classifies each against the
  converter's `VIZ_MAPPED` lookup (mapped vs flagged-table fallback).
- **Tags each dossier**: `needs-review` (panel stacks or unmapped viz types),
  `moderate` (selectors / free-form fields / chart mix), `migrate-first`
  (grid/kpi-only, no panel stacks).

Outputs `<out>/inventory.json` (machine-readable, feeds the converter's
Phase 0) and `<out>/readout.md` (counts, viz histogram with converter status,
per-dossier table with flags + tags).

## Phase 2 — Hand off (optional)

Hand the migrate-first shortlist to the **`microstrategy-to-sigma`** converter
skill — `inventory.json`'s dossier ids go straight into
`extract.py <dossierId>`. Do not auto-convert; surface the shortlist and let
the user choose.

## Limitations (honest)

- **Usage telemetry**: not collected — Strategy One exposes usage through
  Platform Analytics (a separate warehouse-backed project), not the plain
  REST surface this skill uses. Value ranking therefore isn't usage-weighted;
  ask the admin for Platform Analytics access if usage matters.
- **Security filters**: the classic REST extract doesn't surface them;
  ask the customer explicitly (see the converter SKILL's security note).
- Documents that aren't dossiers are counted but not analyzed (their format is
  the legacy Report Services document, out of converter scope).
