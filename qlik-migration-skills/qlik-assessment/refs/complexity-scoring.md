# Qlik complexity scoring rubric

Same framework as the other assessments — features classed **auto / hint / manual /
unhandled**; `cost = 10·n_unhandled + 3·n_manual + 1·n_hint`;
`value = itemViews × sqrt(distinct_viewers)` (or `10×(charts + measures/4)` proxy when
usage is unavailable); `score = value / (1 + cost)`.

Tags: `views==0`→**retire**; `n_unhandled>=1`→**needs-gap-scout**;
`score>=20 and (manual+unhandled)==0`→**migrate-first**; `score>=10`→**easy-win**; else **moderate**.

Qlik-specific signals:

## 1. Master-measure / chart expression buckets
Derived from `convert_qlik_to_sigma`'s `qlikExprToSigma` (the converter's own rules):

| Bucket | Tier | Qlik expression patterns |
|---|---|---|
| **auto** | `auto` | `Sum/Avg/Count/Count(DISTINCT)/Min/Max`, arithmetic, `If`, `Concat`, string fns, date fns (`Year/Month/Day/MakeDate`), `Only`, `Fabs/Fmod/Pow/Log/Ceil` (mapped) |
| **Set Analysis** | `manual` | `Sum({<Field={val}>} Expr)` → Sigma `SumIf([Expr], <cond>)` (cross-element if the set field is in another table) |
| **binning** | `manual` | `Class(...)` → `If()` range buckets |
| **no equivalent** | `unhandled` | `Aggr(...)`, `Dual(...)`, `GetSelectedCount`/`GetFieldSelections`/selection-state, `RangeSum/RangeAvg/...`, alternate states |

## 2. Chart type → Sigma element coverage
| Tier | Qlik viz |
|---|---|
| `auto` | barchart, linechart, combochart, piechart, kpi, table, pivot-table, scatterplot, gauge(simple), text |
| `manual` | mekko, funnel, sankey, map/geo, boxplot, waterfall, distribution, bullet (recreate w/ closest Sigma viz) |
| `unhandled` | Qlik **extensions** / custom-viz objects, Insight Advisor objects, mashup-only widgets |

## 3. App-level flags (added to cost)
| Signal (from `item ls` resourceAttributes) | Adds |
|---|---|
| `hasSectionAccess: true` | +manual (row-level security → Sigma column/row security) |
| `isDirectQueryMode: true` | +manual (already live-query; maps to a Sigma warehouse connection) |
| large `resourceSize` / many data-model tables | informational (bigger reload/model) |
| alternate states / variables-heavy script | +manual |

## 4. Value
- **Usage mode:** `itemViews` (app-level views) as the value driver.
- **Proxy (no usage):** `10 × (chart_count + master_measure_count/4)`.

## Output (`inventory.json`)
Per app: `{id, name, space, views, reloadStatus, lastReload, sectionAccess, directQuery,
n_auto, n_hint, n_manual, n_unhandled, measure_buckets:{auto,manual,unhandled},
viz_types:{...}, value, cost, score, tag}`.
