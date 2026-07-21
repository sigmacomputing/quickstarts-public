# Migration Operating Contract — read before you touch anything

> A tool- and model-agnostic set of guardrails for any agent running a BI→Sigma
> migration. The failure it prevents: an agent runs for an hour and ships a
> structurally-clean but visually-empty, numerically-wrong workbook, then reports
> "done, 0 errors." Fidelity is not optional and it is not eyeballed — it is gated.

## Ground truth
- **The source dashboard is the spec.** Before building, obtain (a) its **rendered
  image** — export the Sisense dashboard/widget (dashboard export or widget image via
  the REST API), or screenshot the rendered dashboard — and (b) its **calc definitions +
  filters** from the Sisense dashboard JSON (dashboards/widgets over REST), whose logic
  is written in **Sisense JAQL formulas**. You are matching *that*, not your idea of it.

## Build from the source's own logic
- **KPIs are usually JAQL-formula/ratio/expression-driven, not `SUM(column)`.** Read each
  field's JAQL. If the source already materialized its validated calc as a stored column,
  `SUM` *that* — it already encodes the per-row logic. Use the source's exact aggregate
  (`count` vs `countDistinct` / `dupCount` matters).
- **Map source filters/parameters → Sigma controls; wire `filters` to the base tables.**
  Apply the source's dashboard/widget filters so aggregates run over the same
  **population** — otherwise ratios/averages drift even when formulas are "right."
- **Rebuild every source viz** (indicators, trends, pivots). If a viz has no standalone
  data export, reconstruct it from the model. **Never silently drop a tile.**

## Verify — don't assume (this is what keeps you on the rails)
- After every write, GET the spec back. A rejected PUT is **atomic** — read the 400.
- **Render EVERY page** to PNG and compare side-by-side to the source image. A page
  that is >40% empty, missing tiles, or visually unlike the source is a **FAIL** — fix it.
- **Value-check**: for each KPI/table, compare the **number** to the source's number
  (Sisense's own JAQL engine is the oracle). "It compiles" is not "it matches." Record
  the comparison.
- Verify the model's existing filter state (`GET /columns`, read element `filters`)
  before assuming anything is or isn't applied.

## Don't spin, don't fake
- **"Can't verify" ≠ "passed."** If a gate can't pass, STOP and report the specific
  blocker. Do not waive it silently or loop to force green.
- Escape hatches (skip/allow flags) require a **named reason that goes in the report**.
- If you've retried the same failing step ~2×, change approach or surface it — never grind.

## Done means
- 0 error columns; every page rendered and visually matching the source; every KPI's
  number matching the source (or the delta explained); controls present and wired; no
  silently dropped tiles. Anything short of that is **reported, not hidden.**
