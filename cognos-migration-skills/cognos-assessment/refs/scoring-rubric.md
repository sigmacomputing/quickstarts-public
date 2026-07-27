# Cognos→Sigma coverage scoring rubric

`score-coverage.mjs` classifies every feature into one of four buckets by
detecting the **exact** signals the `cognos-to-sigma` converter
(`cognos.ts` + `cognos-report.ts`) acts on. It does not re-run the converter; it
mirrors what the converter translates cleanly vs. flags. Each detected gap is
recorded with a count, the reason, and the remediation shown in the readout.

## Buckets

| Bucket | Meaning | Converter behavior |
|---|---|---|
| **auto** | Converts cleanly, zero touch | emitted directly (table, column, metric, relationship, chart, control, supported DSL) |
| **hint** | Converts, but needs one one-time decision (no logic rebuild) | converts; a setup choice (land a file in the warehouse, dedupe layered subjects) |
| **manual** | Brief re-creation in Sigma | converter passes through + warns; you rebuild it by hand |
| **unhandled** | No clean Sigma analog — needs a human design decision | converter emits a flagged placeholder + a loud warning |

## Cost / value / tag (same framework as every `*-assessment` skill)

- `cost  = 10·n_unhandled + 3·n_manual + 1·n_hint`
- `value = 10 · n_features`  *(proxy — CA exposes no view counts; see `usage-telemetry.md`)*
- `score = value / (1 + cost)`
- complexity: `n_unhandled>0 → high`; else `n_manual>0 → medium`; else `low`
- tag: `n_unhandled≥1 → needs-review`; else `(manual+unhandled)==0 → migrate-first`; else `score≥10 → easy-win`; else `moderate`
- `pct_auto_migratable = (n_auto + n_hint) / n_features` — hint is a decision, not rework, so it counts as auto-migratable.

## Module signals (from `cognos.ts`)

| Signal | Bucket | Reason | Remediation |
|---|---|---|---|
| query subject (`querySubject.ref` tail) | auto | → Sigma warehouse-table element | — |
| plain column item / measure item (`usage:fact/measure` + `regularAggregate≠none`) | auto | → Sigma column / metric | — |
| translatable calc — `total/average/count/min/max`, `if/then/else`, `_add_days`/`_add_months`/`_add_years`/`_days_between`/`extract`, `substring/substr/upper/lower/trim/substitute`, `\|\|`, `cast(… as char/text)`, `coalesce` | auto | maps via `translateCognosExpr` | — |
| single equi-join (`link.leftRef = link.rightRef`) | auto | → DM relationship | — |
| file-backed source (`useSpec.type:"file"`) | hint | uploaded file backs the module | land the file in the warehouse first (original upload is not re-downloadable via REST), then point the DM at the warehouse table |
| layered module (base + presentation subjects, `useSpec.type:"module"`) | hint | both layers convert | dedupe to the physical-table layer in Sigma to avoid redundant elements |
| `CASE … WHEN … END` | manual | converter does `if/then/else`, not `CASE` | re-author as nested Sigma `If()` / `Switch()` |
| aggregate `… for …` scope | manual | → Sigma `*Over` window function | verify the grouping in a DM element (window fns have known caveats) |
| composite / non-equi join (`link[]` length > 1, or expression with `and`/`or`/inequality) | manual | converter does single equi-joins only | re-create the relationship + keys by hand |
| `running-total`/`running-count`/`running-average`/`running-difference`/`moving-total`/`moving-average`/`rank`/`percentile`/`quantile`/`tertile` | unhandled | window/running calc | re-author as a Sigma window function |
| `GetResourceString(...)` | unhandled | localization-resource lookup | replace with the literal label or model a lookup table |
| unmapped `bareword()` function | unhandled | no confirmed Sigma mapping | review/translate by hand |

## Report signals (from `cognos-report.ts` + `format-shapes.md`)

| Signal | Bucket | Reason | Remediation |
|---|---|---|---|
| `<list>` | auto | → Sigma table | — |
| `<crosstab>` | auto | → Sigma pivot | — |
| RAVE2 viz `clusteredBar/stackedBar/clusteredColumn/stackedColumn/line/spline/area/pie/donut/clusteredCombination/bubble/scatter` | auto | → native Sigma chart | — |
| `tiledmap` | auto | → Sigma region-map / point-map | — |
| `prompt('p')` / `?p?` | auto | → Sigma control | — |
| `Total(x)` / `Summary(x)` footers | auto | → `Sum([x])` etc. | — |
| detail / summary filter | manual | not auto-applied | re-create as a Sigma element/page filter |
| drill-through | manual | — | re-implement as a Sigma action |
| runtime macro `# … prompt(…,'token') … #` | unhandled | builds the column/SQL at runtime (e.g. swap-measure picker) | model as a Sigma control + `Switch([Control], …)`; converter emits a placeholder |
| `treemap` / `network` / `wordcloud` / `packedBubble` | unhandled | no native Sigma element | data preserved as a flagged table; re-pick the closest Sigma element |
| `rank()` in a data item | unhandled | window function | re-author as a Sigma `Rank` in a grouped element |

## Calibrating against the bundled samples

Running against `~/cognos-samples/` (7 modules + 6 reports) should flag, at minimum:
- **go-sales-performance** — the swap-measure runtime macro (multiple `#…prompt(…,'token')…#`).
- **sales-overview**, **hospital-admissions** — `rank()` + `treemap`.
- **global-sales** — `network` viz; **product-line-revenue** — `wordcloud` + `packedBubble`.
- **hospital** module — `GetResourceString` localization.
- **telco-churn**, **sample-data-module**, **hospital** modules — `CASE…WHEN…END`.
- **prof-services** module — an aggregate `… for …` window scope.

If those don't show up, the scorer regressed.
