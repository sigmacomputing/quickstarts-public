# Cognos expression DSL → Sigma formula

The Cognos expression language is a SQL-ish hybrid with MDX echoes. `converter/cognos.ts`
(`translateCognosExpr`) handles the mappings below; report-level refs are pre-resolved by
`cognos-report.ts` (`translate`) before handing arithmetic/aggregates here.

## Translated (automatic)

| Cognos | Sigma | Notes |
|---|---|---|
| `total(x)` `sum(x)` | `Sum(x)` | also `average→Avg`, `count→Count`, `maximum→Max`, `minimum→Min` |
| `total(x for a, b)` | `SumOver(x, [a], [b])` | the `for` scope → `*Over` window funcs (`AvgOver`, `CountOver`, …) |
| `if (c) then (a) else (b)` | `If(c, a, b)` | nested `else if` chains supported |
| `_add_days(d, n)` | `DateAdd("day", n, d)` | `_add_months`→month, `_add_years`→year |
| `_days_between(a, b)` | `DateDiff("day", b, a)` | |
| `extract(month, d)` | `DatePart("month", d)` | year/month/day |
| `substring(s,…)` `substr(s,…)` | `Mid(s,…)` | 1-indexed in both |
| `substitute(pat, rep, src)` | `RegexpReplace(src, pat, rep)` | arg order reordered |
| `cast(x as varchar/char)` | `Text(x)` | numeric casts (`as integer/decimal`) → passthrough |
| `varchar(x)` `char(x)` | `Text(x)` | standalone coercion fns |
| `decimal(x)` `double(x)` | `x` | numeric passthrough |
| `upper/lower/trim/coalesce` | `Upper/Lower/Trim/Coalesce` | |
| `\|\|` (concat) | `&` | |
| `'string'` | `"string"` | single → double quotes |
| model ref `[C].[Module].[Subject].[Col]` | `[Subject/Col]` | report side; resolves to the migrated DM element |
| dataItem cross-ref `[Other Item]` | `[Other Item]` | sibling column |
| `prompt('p')` | `[P]` (control ref) | a Sigma control is registered |
| list `Summary(x)` / `Total(x)` footers | `Sum([x])` (or the named aggregate) | |

## Flagged — never faked (emit a warning + placeholder)

| Cognos | Why | What to do |
|---|---|---|
| **Macros** `#…# prompt(…,'token',…)` | builds the column/SQL at runtime (e.g. "swap measure" measure picker) | model as a control + `Switch([control], …)` mapping the prompt tokens to columns |
| `running-total` / `running-*` / `moving-*` | windowed running calc, no single-column analog | rebuild in a date-grouped Sigma chart/table (`CumulativeSum`, window funcs) |
| `rank` / `lag` / `lead` / `percentile` | ordered window functions | rebuild in the consuming Sigma element |
| `GetResourceString(…)` | localization lookup | substitute the literal label, or a control |
| composite / non-equi join | `A.k=B.k AND …` or `>` joins | author the relationship manually in Sigma |
| detail / summary filter | report-time condition | re-create as a Sigma element/page filter (expression is surfaced in the warning) |

> The converter resolves bare-identifier expressions (`"Quantity"`) and `[Subject].[Col]`
> self-refs as plain columns, so they are NOT mis-flagged as calcs.
