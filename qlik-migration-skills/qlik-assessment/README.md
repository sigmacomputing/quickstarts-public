# Qlik Cloud Assessment

A Claude Code skill that inventories a Qlik Cloud tenant and produces a
migration-readiness readout. Designed to be run by a customer (or a Sigma rep
with the customer present) before deciding which Qlik apps to migrate to Sigma.

**READ-ONLY** in inventory mode. With `--deep` the only writes are a temporary
`MeasureList` object per app (created then immediately removed, solely to
enumerate master measures — qlik-cli has no read-only listing for them). The
skill never reads warehouse rows and never posts to Sigma.

## What it produces

A directory (`/tmp/assessment-<tenant>/`) with:

- `inventory.json` — environment counts, per-app metadata (usage, reload, Section
  Access / DirectQuery flags), per-app complexity buckets, an ownership rollup,
  data-connection rollup, reload-activity rollup, and the value/cost-ranked
  **migration shortlist**. This is the single file the renderers consume.
- `readout.md` — a compact markdown summary (environment, per-app complexity,
  shortlist, caveats), written by `qlik-inventory.py`.
- `readout.html` — a customer-facing, Sigma-branded HTML report (the same theme
  as `tableau-assessment` / `powerbi-assessment`), written by
  `render-readout-html.rb`. Open it in a browser or print to PDF to share.

Nothing in this directory is uploaded anywhere. To share, zip and send deliberately.

## Prerequisites

- Claude Code installed
- A working **qlik-cli context** (API key or OAuth M2M) for the tenant you want
  to assess — see `../qlik-to-sigma/refs/connection.md` for the auth recipe and
  the two M2M gotchas (an M2M identity only sees spaces it has been granted, and
  cannot reload space-connection apps).
- Ruby (for the HTML renderer) and Python 3 (for the inventory script)

For the **usage axis** (app views), the tenant exposes `itemViews` on every app
the context can see — no special admin role is required, but note `itemViews` is
a **28-day rolling window**, not all-time.

## How to run

In Claude Code:

```
/qlik-assessment
```

The skill will:

1. Probe the active qlik-cli context and confirm space/user visibility
2. Inventory apps (+ usage, reload status/duration, Section Access, DirectQuery),
   spaces, users, and data connections
3. *(with `--deep`)* Open each app to bucket master-measure expressions and chart
   viz types against Sigma coverage
4. Score `value / (1 + cost)` and tag each app
5. Write `inventory.json` + `readout.md` (`qlik-inventory.py`), then render
   `readout.html` (`render-readout-html.rb`)
6. Offer to hand off the shortlist to `qlik-to-sigma`

```
ruby scripts/render-readout-html.rb --out /tmp/assessment-<tenant>
```

## The key idea

The same `convert_qlik_to_sigma` translation rules that drive the converter also
**predict migration effort**: bucket each master-measure expression
(auto / manual / unhandled) and each chart's viz type against Sigma's coverage.
Set Analysis → `manual` (Sigma `SumIf`); `Aggr()` / `Dual()` / selection-state /
`Range*` / alternate states → `unhandled`. See `refs/complexity-scoring.md`.

## What this is NOT

- **Not** a write tool. It cannot and will not modify app content or post to Sigma.
- **Not** a complete tenant audit. It covers the signals that matter for Sigma
  migration scoping, scoped to **what the active context can access** (an M2M
  identity sees only its granted spaces). A tenant-wide sprawl scan needs the
  Qlik governance "App analyzer" apps.
- **Not** the converter. It scopes; `qlik-to-sigma` converts. The `shortlist` in
  `inventory.json` is the hand-off between them.

## Privacy

This skill sends app/tenant metadata (not warehouse rows) through the Anthropic
API. With `--deep` it pulls **master-measure expressions and chart object
definitions** to bucket complexity. See [`PRIVACY.md`](./PRIVACY.md) for the full
disclosure to review with your privacy/legal team before running.

## Sibling skills

- [`qlik-to-sigma`](../../../qlik-to-sigma/) — the conversion skill this feeds into.
- `tableau-assessment` / `powerbi-assessment` — the analogs this skill mirrors
  (same scoring framework, same Sigma-branded readout theme).
