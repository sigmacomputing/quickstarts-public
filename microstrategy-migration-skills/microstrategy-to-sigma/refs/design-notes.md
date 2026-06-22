# Design notes — MicroStrategy → Sigma converter

## Architecture (one-way data flow)

```
MSTR REST ──extract.py──> bundle.json ──convert.py──> sigma_dm_spec.json
                                              │            sigma_workbook_spec.json
              resolve_ae_winners.py ──────────┘  (ae_winners.json, when needed)
```

- **`bundle.json` is the contract.** `extract.py` walks a dossier definition →
  its dataset reports (templates, `showExpressionAs=tokens`) → the schema
  objects they reference (attributes incl. forms/expressions/lookup tables,
  facts, metrics incl. compound bases via a second pass, logical tables,
  hierarchy relationships). The converter never talks to MicroStrategy.
- **Everything in the output is derived from the bundle** — sources (one DM
  table element per logical table), the fact table (the logical table carrying
  fact expressions), joins (attribute key forms mapped to BOTH the fact table
  and a lookup table become left-outer join legs), a consumable join element
  with de-duplicated columns (each join's own key column is skipped on the
  lookup side — a cross-element passthrough of a join key compiles to type
  `error` in Sigma), metrics (token-parsed; `Count<Distinct=True>` →
  `CountDistinct`), and one workbook page per dossier chapter.
- Display formats: MSTR bundle format blocks come back empty, so formats are
  derived from semantics (count/quantity → integer, pct/margin/ratio →
  percent, money-named facts → currency).

## Validated scope (live trial, exact parity)

- Classic-schema path: star schema (fact + dims, incl. heterogeneous key
  columns like `ORDER_STORE_KEY = STORE_KEY`), 3 grid reports in a dossier →
  Sigma DM + workbook, **19/19 + 30/30 + 3/3 rows exact** (money/counts exact,
  ratios rel 1e-6). Includes a `Count<Distinct=True>` metric, a compound
  margin metric, and one AE-collapse report (see `ae-row-collapse.md`).

## Modeling gotchas that bite conversions (verified)

- **Attribute-count metrics cause cartesian-join governance aborts.** A metric
  like `Count(Customer)` (counting an *attribute*) makes the SQL engine join
  the attribute's lookup table without a constraining fact path — on a real
  warehouse the resulting cross join trips MicroStrategy's governance limits
  and kills the report. Count a **fact column** instead (e.g. a
  `CUSTOMER_KEY` fact on the fact table) — same number, sane SQL. The same
  applies on the Sigma side: count the key column of the join element.
- **Compound-metric denominators need `ZeroToNull()`.** A ratio like
  `[Profit] / [Revenue]` dies with a Snowflake division-by-zero error on any
  zero-denominator group. In MSTR wrap the denominator
  (`ZeroToNull([Total Net Revenue])`); the converter's Sigma output should
  use the equivalent null-guard if the source metric did.

## Roadmap (deliberately not in the validated path)

1. **Chart visualization emission** — the viz-type lookup
   (`viz-type-mapping.md`) is extraction-validated; emitting non-table Sigma
   elements (kpi/bar/line/combo + layout) is the long tail. Author the
   `fixtures/BUILD_SPEC.md` dossier on a trial to drive it.
2. **The newer "Data Model" object** (`/api/model/dataModels`) — fully
   REST-authorable (incl. `securityFilters`, publish, `connect_live`), unlike
   the classic schema. Two implications: (a) a richer, cleaner extraction
   source for customers who've adopted it; (b) `securityFilters` is the
   surface for an RLS detect→ask→port flow (same principles as the sibling
   converters: never silently dropped, never silently ported).
3. **Page-by, prompts, metric-condition selectors** — extracted structurally
   but not converted (metric-condition selectors land in
   `control-scope.json` `unbound` as MANUAL). Chapter filters + attribute
   selectors ARE converted (2026-06-12): selectors' declared `targets` viz
   lists drive the Sigma control filter wiring, `control-scope.json` is the
   intended-scope contract, and gate 7 (`scripts/lib/control_lint.rb`) +
   `scripts/probe-controls.rb` enforce/prove it. Verified strip gotcha: a
   list-control filter target on a DATETIME or NUMERIC column posts 200 and
   reads back `filters: null` — dates become date-range controls, numbers
   bind through a hidden `Text()` cast column. (The numeric variant is NOT
   yet in the shared `refs/control-parity.md` — candidate for the next
   cross-plugin sync.)
