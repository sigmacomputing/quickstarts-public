# Tableau window / table calcs → Sigma-native window math

**Status: WINPROBE-validated 2026-06-12 (bead beads-sigma-427).** Every mapping
below was proven live against org `tj-wells-1989` / `CSA.TJ` with **930/930
cells exact** vs warehouse SQL ground truth, on **ONE data-model base element
with ZERO Custom SQL elements**. Regression fixture:
`corpus/tableau/winprobe-window-functions/` (Tableau wb
`aa126c36-608a-402c-9733-2c83797bc65c` on the 10ay/dataflow site).

## The placement rule (load-bearing)

Sigma window functions (`Cumulative*`, `Moving*`, `Rank`, `RankDense`,
`RankPercentile`, `RowNumber`, `Lag`, `Lead`, `PercentOfTotal`) are
**first-class as CHART-element viz formulas on the yAxis**. That is the ONLY
verified context:

- They **silently error** (column type `error`, blank chart) in DM-element
  calc columns and in workbook-master / grouping-table calc columns
  (memory: `feedback_sigma_window_functions` — still true).
- The `*Over` family (`SumOver`, `MaxOver`, `RankOver`, `CountOver`, …) is
  **`Unknown function` in every spec context** — never emit those.
- Windowed measures must land **on the yAxis**: the element CSV export (the
  Phase-6 pooled actuals collector) returns only the plotted axis/encoding
  columns.

Cumulative/rank functions **follow the chart's `xAxis.sort`** and
**auto-partition by the chart's color/series dim**. Tableau's
`<computed-sort>` ("sort field X by measure Y") must therefore be carried into
`xAxis.sort` — `build-charts-from-signals.rb` adds a hidden companion
aggregate column and targets the sort at it when the sort measure isn't
plotted (pareto / rank charts).

## The mapping table (all auto-emitted by build-charts-from-signals.rb)

| Tableau | Sigma | Notes |
|---|---|---|
| `RUNNING_SUM(agg)` | `CumulativeSum(agg)` | follows xAxis sort |
| `RUNNING_AVG / MAX / MIN / COUNT(agg)` | `CumulativeAvg / Max / Min / Count(agg)` | |
| `WINDOW_AVG(agg, -n, 0)` | `MovingAvg(agg, n)` | Tableau bounds are (first, last) offsets; Sigma takes positive back[, fwd] counts |
| `WINDOW_*(agg, -n, m)` | `Moving*(agg, n, m)` | SUM/MAX/MIN/COUNT same pattern |
| `WINDOW_STDEV(agg, -n[, m])` | `MovingStdDev(agg, n[, m])` | |
| `agg / WINDOW_SUM(agg)` (unbounded, same agg) | `PercentOfTotal(agg, "grand_total")` | share-of-total |
| `RUNNING_SUM(agg) / TOTAL(agg)` (same agg) | `CumulativeSum(PercentOfTotal(agg, "grand_total"))` | pareto; accumulation follows xAxis sort |
| `RANK(agg)` / `RANK_DENSE` / `RANK_PERCENTILE` | `Rank / RankDense / RankPercentile(agg, "desc")` | **Tableau defaults to DESC, Sigma to asc — the direction arg is mandatory** |
| `INDEX()` | `RowNumber()` | |
| `LOOKUP(agg, -n)` | `Lag(agg, n)` | negative offset = backward = Lag (the pre-2026-06-12 Lag/Lead mapping was reversed) |
| `LOOKUP(agg, n)` | `Lead(agg, n)` | |
| unbounded `WINDOW_MAX / MIN / SUM(agg)`, standalone `TOTAL(agg)` | hidden **two-level grouped helper** | see below |

### Week alignment

Tableau week-trunc is **Sunday-anchored**; Sigma `DateTrunc("week")` follows
the warehouse week start (Monday on Snowflake). Use the verified arithmetic
(`Weekday()` / `DatePart("weekday")` is 1 = Sunday):

```
DateAdd("day", 1 - Weekday([Master/Order Date]), DateTrunc("day", [Master/Order Date]))
```

### Unbounded partitioned WINDOW_MAX / MIN / SUM → two-level helper

A constant-per-partition window aggregate cannot be a single chart formula.
`build_window_helper` emits a hidden grouped element
(`visibleAsSource: false`) sourcing the master:

- **outer grouping (g1)** = the partition dims (chart color dim / pivot
  `rowsBy`; a constant `All Rows = 1` key when unpartitioned), computing the
  stage aggregates (`Max([value])` / `Min([value])` / `Sum([value])`)
- **inner grouping (g2)** = the addressing dims (chart x dim / pivot
  `columnsBy`), computing the window's operand (`Sum([Master/X])`)

The chart/pivot sources the helper and references the stage column via
`Max([Helper/Stage])` (or `Min` for WINDOW_MIN). **NEVER `Sum` — the
broadcast-down gotcha:** group calcs broadcast to base-grain rows when a chart
re-aggregates a grouped source, so `Sum` multiplies the constant by the row
count; `Max`/`Min` over identical replicas is exact.

### Measure Names / Measure Values long format

Tableau exports Measure-Names worksheets as LONG rows
(`Measure Names, <dim>, Measure Values`). build-charts dissolves the shape
into ONE multi-measure chart (one yAxis column per measure, **named with the
verbatim Tableau measure label** — `auto-parity-plan.rb` pivots the long CSV
to wide and matches by display name). Validated 384/384 on the WINPROBE
weekly funnel (CountD + Sum + ratio calc per week).

## STAYS MANUAL — flag, never guess

No validated mapping; `extract-calc-fields.rb` keeps `requires_custom_sql`
for these and build-charts emits a STAYS MANUAL warning:

- `WINDOW_MEDIAN`, `WINDOW_PERCENTILE`, `WINDOW_CORR`, `WINDOW_COVAR(P)`,
  `WINDOW_VAR(P)`, `WINDOW_STDEVP`
- `PREVIOUS_VALUE`, `SIZE()`, `FIRST()`, `LAST()` (incl. as window bounds)
- `RANK_UNIQUE`, `RANK_MODIFIED`
- shifted windows (`WINDOW_*(agg, 1, 3)` — first > 0 or last < 0)
- any compute-using / addressing variant beyond the default `Table (Across)`
  or a simple one-dim partition: "restart every", pane-relative addressing,
  compute-along-a-non-axis-dim. Detect and flag.
- cumulative/moving formulas inside a PIVOT grid (only the two-stage helper
  shape is pivot-validated)

Multi-dim partitions beyond a single color split are **untested** — the build
emits a verify-warning when it detects one.

## Manual-residue fallback: Custom SQL

The old "every window calc needs a Custom SQL element" rule is **disproven**
for the table above — reserve `kind: "sql"` DM elements for the manual
residues, translated as ANSI `OVER(...)` (see SKILL.md Phase 3 for the
element shape).
