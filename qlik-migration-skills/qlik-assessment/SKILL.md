---
name: qlik-assessment
description: >-
  Take inventory of a Qlik Cloud tenant and produce a migration-readiness readout
  — app/space/user counts, per-app complexity (master-measure expression
  convertibility, chart-type coverage, Set Analysis / Section Access flags, data
  model size), reload health, and a value/cost-ranked migration shortlist. Use to
  scope a Qlik→Sigma migration or audit BI sprawl. qlik-cli driven; hands off to
  qlik-to-sigma.
user-invocable: true
---

# Qlik Assessment

> **STATUS: working inventory (qlik-cli driven).** Mirrors `tableau-assessment` /
> `powerbi-assessment` / `domo-assessment`: same `value / (1 + cost)` scoring and
> `migrate-first / easy-win / moderate / needs-gap-scout / retire` tags.

**Read first:**
- `refs/complexity-scoring.md` — the Qlik convertibility rubric (expression + viz buckets)
- `../qlik-to-sigma/refs/connection.md` — qlik-cli auth + the two M2M gotchas
- `PRIVACY.md` — read-only posture
- `refs/output-shapes.md` — exact `inventory.json` shape the renderers consume
- `refs/readout-template.md` — `readout.html` section ordering + Sigma-branded theme

## The key idea
The same `convert_qlik_to_sigma` translation rules that drive the converter also
**predict migration effort**: bucket each master-measure expression (auto / manual /
unhandled) and each chart's viz type against Sigma's coverage. Set Analysis →
`manual` (Sigma `SumIf`); `Aggr()`/`Dual()`/selection-state/`Range*` → `unhandled`.

## Phases
0. **Probe** — `qlik context use`; `qlik item ls --resourceType app`; confirm spaces/users visibility (M2M only sees granted spaces — see connection.md).
1–2. **Inventory** — apps (+ `itemViews`, `resourceReloadStatus`, `lastReloadTime`, `hasSectionAccess`, `isDirectQueryMode`, `resourceSize`), spaces, users. `scripts/qlik-inventory.py`.
3. **Per-app complexity** — master measures (Engine `MeasureList`) bucketed by expression; chart objects bucketed by viz type; Section Access & DirectQuery flags; data-model table count from the load script.
4. **Shortlist** — `cost = 10·unhandled + 3·manual + 1·hint`; `value = itemViews × √(distinct, when available)` else size/complexity proxy; `score = value/(1+cost)`; tag.
5. **Readout** — `qlik-inventory.py` writes `inventory.json` + `readout.md`; then
   `scripts/render-readout-html.rb --out <dir>` renders the customer-facing,
   Sigma-branded `readout.html` (same theme as `tableau-assessment`).
6. **Hand off** — to `qlik-to-sigma` (ask the user which apps first).

## Scripts
| Script | Phase | Purpose |
|---|---|---|
| `scripts/qlik-inventory.py` | 0–4 | Enumerate apps/spaces/users, per-app expression+viz complexity, score + tag → `inventory.json` + `readout.md` |
| `scripts/render-readout-html.rb` | 5 | Render the Sigma-branded `readout.html` from `inventory.json` (`ruby scripts/render-readout-html.rb --out <dir>`) |

`qlik-inventory.py --out assessment-<tenant>` (uses the active qlik-cli context).
Per-app deep complexity reuses the `MeasureList` enumeration from
`qlik-to-sigma/scripts/qlik-discover.py`.

## Open work
- Usage granularity: `itemViews` is app-level; per-sheet usage needs the tenant audit/usage API.
- Cross-tenant roll-up via the DomoStats-equivalent (Qlik "App analyzer" governance apps).
