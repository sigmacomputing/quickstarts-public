# Migration Operating Contract — read before you touch anything

> A tool- and model-agnostic set of guardrails for any agent running a BI→Sigma
> migration. The failure it prevents: an agent runs for an hour and ships a
> structurally-clean but visually-empty, numerically-wrong workbook, then reports
> "done, 0 errors." Fidelity is not optional and it is not eyeballed — it is gated.

## Ground truth
- **The source dashboard is the spec.** Before building, obtain (a) its **rendered
  image** — run the Cognos report to an output format over the CA REST API (report
  output / `.../reports/{id}/reportData`), or screenshot the rendered report /
  dashboard in Cognos Analytics — and (b) its **calc definitions + filters** from the
  Cognos report-spec XML (and dashboard/exploration JSON), whose logic is written in
  **Cognos report expressions**. You are matching *that*, not your idea of it.

## Build from the source's own logic
- **KPIs are usually parameter/ratio/expression-driven, not `SUM(column)`.** Read each
  field's calc. If the source already materialized its validated calc as a stored
  column, `SUM` *that* — it already encodes the per-row logic. Use the source's exact
  aggregate (`Count` vs `CountDistinct` matters).
- **Map source parameters/prompts/filters → Sigma controls; wire `filters` to the base
  tables.** Apply the source's dashboard/period filters so aggregates run over the same
  **population** — otherwise ratios/averages drift even when formulas are "right."
- **Rebuild every source viz** (donuts, trends, crosstabs). If a viz has no standalone
  data export, reconstruct it from the model. **Never silently drop a tile.**

## Verify — don't assume (this is what keeps you on the rails)
- After every write, GET the spec back. A rejected PUT is **atomic** — read the 400.
- **Render EVERY page** to PNG and compare side-by-side to the source image. A page
  that is >40% empty, missing tiles, or visually unlike the source is a **FAIL** — fix it.
- **Value-check**: for each KPI/table, compare the **number** to the source's number.
  "It compiles" is not "it matches." Record the comparison.
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
