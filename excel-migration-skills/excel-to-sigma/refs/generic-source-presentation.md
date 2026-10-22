# Generic source presentation inventory and construction

`scripts/build-source-presentation.py` inventories presentation features in any
`.xlsx` or `.xlsm` workbook. It has no workflow or fixture-name chart routing.
It reuses `presentation.extract_presentation` for source rules and formatting,
then walks every OOXML plot and series in each chart part, including unsupported
chart types. Each series retains its plot kind, point count, and all available
source reference roles and cells (`xVal`/`yVal` for scatter charts).
Source files are read only.

```bash
python3 scripts/build-source-presentation.py SOURCE.xlsx --out source-presentation-plan.json
```

The versioned plan binds the exact source SHA256 and its own `planHash` to each
chart's title, kind, series order, category and value ranges, individual source
cells, source formulas, point order, aggregation, unit, and source format.
`cachedExpectations` are retained solely as diagnostic source-cache values.
Each aggregate check marks its reference qualification
`PENDING_INDEPENDENT_ORACLE`; source caches alone cannot establish or pass
runtime parity.
An unsupported chart still has an inventory and an unresolved reason. A missing
or inconsistent range also remains unresolved.
Mixed-plot charts retain every plot and series but remain unresolved until a
complete native combination mapping is reviewed; no partial chart is emitted.

To preview construction with synthetic bindings, supply `--bindings ...
--preview`. The result says `LOGICAL_FIXTURE_ONLY` and cannot be used with
`--contents`. The binding file has these fields:

- `sourceHash`, `presentationPlanHash`, `documentId`, `documentVersion`;
- `viewSourceElementId`, `mainElementId`, `detailElementId`, `editElementId`,
  `mainViewColumns`, and `detailViewColumns`;
- `charts[chartId]` with a live `sourceElementId`, exact ordered
  `categorySourceCells`, a live `categoryFormula` and `orderFormula`, and one
  `series` record per source series containing exact `sourceCells` and a live
  `formula`;
- `points` with one entry per source point. Each entry names the exact source
  category cell and series value cells, a unique target category key, its
  one-based source order, and the same live category and value expressions.

These structural facts identify a queryable target for each source point. They
do not establish runtime aggregate parity. The emitted `aggregateChecks` remain
`PENDING_RUNTIME_QUERY`; cached values never become chart series or proof.
Unreviewed source formulas remain in `formulaAccounting` and an unresolved
formula scope, including unsupported roots and their dependencies.

Actual emission requires the existing migration manifest, named staging
approval, matching `APPROVED_STAGING` receipt, current OpenAPI document, and
the same binding file with `manifestPlanHash` and `stagingReceiptHash`. The
command reruns `validate_manifest`, `gate_plan_staging_source`, and
`gate_input_staging`, then compares the complete recomputed receipt and audits
the documented chart spec fields, including the native donut schema when a
source doughnut exists. The manifest's `planProjection` must carry an
approved `sharedInputArchitecture`; this entry point does not create a second
staging or security gate.

Each actual chart binding requires a `review` object with `status: "approved"`,
named `reviewer`, `evidenceId`, `sourceHash`, `presentationPlanHash`,
`manifestPlanHash`, `stagingReceiptHash`, `documentId`, `documentVersion`, and
`bindingHash` (canonical SHA256 of that chart binding without `review`).
`validationTargets` and `conditionalTargets` may name target columns for a
source rule. Every target requires `elementId`, `columnId`, exact `sourceSheet`
and `sourceRange`, and the same review identity fields with
`targetBindingHash` over that target without `review`. A missing mapping stays
unresolved; a malformed or stale supplied mapping fails.

```bash
python3 scripts/build-source-presentation.py SOURCE.xlsx \
  --bindings reviewed-bindings.json --manifest migration-manifest.json \
  --approval staging-approval.json --staging-receipt approved-staging.json \
  --openapi current-openapi.json --out presentation-artifact.json
```

Add `--contents current-get.json` to produce a version-guarded full-contents
PUT body using the existing `presentation.integrate_presentation` collision and
referenced-element checks. The GET response must name the exact approved
workbook and document version. Apply only the `contents` and `documentVersion`
fields through the existing REST workflow. Actual source-target aggregation,
chart rendering and order, input validation, conditional rule precedence,
and source formula parity remain separate runtime acceptance checks.

The emitter uses the existing guarded bar/line chart, table, text, page,
validation, and conditional-format shapes. It places source-titled charts on an
overview page and provides edit and detail pages. Source formats drive chart
value and date-category formats where a bounded mapping exists. Partial
accounting/negative styles, monthly date labels, and unknown formats remain
explicit in `unresolved` until visual readback. A whole-number validation is
emitted as a finite value list only where the extractor has an exact supported
mapping; open-ended whole-number domains are unresolved, never weakened to a
fraction-accepting numeric range. Unmapped source rules and unsupported
color-scale midpoints remain unresolved with their original rule provenance.

A one-series Excel doughnut maps to Sigma's native `donut-chart` using its
source category column for `color`, source value column for `value`, and
source-order column for color sorting. For the six-point sales-pipeline chart,
all six source points and their categories remain in the pending checks. The
source hole is 10%; the documented target `innerRadius` minimum is 40%, so the
emitter uses 40% and records the geometry difference in `unresolved`. The
source first-slice angle is 0 degrees, while the target schema has no rotation
field; this is also recorded for visual review. Construction of the chart does
not establish exact visual fidelity or runtime aggregate parity.
