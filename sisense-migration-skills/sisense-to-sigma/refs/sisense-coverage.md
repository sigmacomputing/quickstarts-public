# Sisense → Sigma — dashboard classifier coverage matrix

> **GENERATED — do not edit by hand.** Regenerate with `python3 scripts/gen-coverage-matrix.py --catalogs refs/catalogs --skill sisense --out refs/sisense-coverage.md`. The JSON catalogs in `refs/catalogs/` are the single source of truth; the classifier (`scripts/build_workbook.py` / `build-sigma-workbook.py`) LOADS them via `shared/lib/coverage_catalog.py`. A no-drift test asserts this file matches the catalogs.

Every documented source construct maps to a real, current Sigma target or a loud fallback — no silent wrong-defaults, no name-substring guessing (beads-sigma-kvza).

**`sigma_verified` legend:** ✅ y = the mapped Sigma target resolved at **query time** in a live migration (no `type=error` column) on the date shown; 🟡 n = target is documented but not yet query-verified.

**Coverage:** 36 documented constructs across 4 dimensions; 0 live-verified.

## Visualization / chart kind

_Sisense widget `type` -> Sigma workbook element. The single source of truth for convert.py's two widget classifiers: (1) `sigma` is the Sigma workbook element KIND the builder emits (convert_dashboard.SIGMA_KIND) — null means there is no native Sigma element and convert_dashboard FLAGS the widget (loud, no element); (2) `coverage_element` + `tag` reproduce the assessment coverage map (classify_dashboard.WIDGET_MAP), where the coarse element name and AUTO/HINT/MANUAL tag drive the coverage report only. Both dicts are derived from these rows. Widget type strings must be confirmed against live widget `type` values (see refs/widget-type-mapping.md); the trial has 0 dashboards so these are documentation-grounded, not yet query-verified. Unmapped/unknown widget types warn+flag._

Authoritative source: <https://docs.sisense.com/main/SisenseLinux/widget-designer.htm>

| construct | doc ref | Sigma target | sigma_verified | on-unmapped |
|---|---|---|---|---|
| `indicator` | [doc](https://docs.sisense.com/main/SisenseLinux/indicator.htm) | `kpi-chart` | 🟡 n | warn+flag |
| | | | | _Single numeric value -> Sigma KPI. Gauge/ticker variants collapse to a KPI._ |
| `chart/column` | [doc](https://docs.sisense.com/main/SisenseLinux/column-chart.htm) | `bar-chart` | 🟡 n | warn+flag |
| | | | | _Vertical columns -> Sigma bar-chart (no orientation key = vertical)._ |
| `chart/bar` | [doc](https://docs.sisense.com/main/SisenseLinux/bar-chart.htm) | `bar-chart` | 🟡 n | warn+flag |
| | | | | _Horizontal bars -> Sigma bar-chart; orientation from sub-type is applied downstream._ |
| `chart/line` | [doc](https://docs.sisense.com/main/SisenseLinux/line-chart.htm) | `line-chart` | 🟡 n | warn+flag |
| `chart/area` | [doc](https://docs.sisense.com/main/SisenseLinux/area-chart.htm) | `area-chart` | 🟡 n | warn+flag |
| `chart/pie` | [doc](https://docs.sisense.com/main/SisenseLinux/pie-chart.htm) | `pie-chart` | 🟡 n | warn+flag |
| `pivot2` | [doc](https://docs.sisense.com/main/SisenseLinux/pivot.htm) | `pivot-table` | 🟡 n | warn+flag |
| | | | | _`pivot2` is the current Sisense pivot widget type; rows/columns/values panels -> Sigma grouped table._ |
| `pivot` | [doc](https://docs.sisense.com/main/SisenseLinux/pivot.htm) | `pivot-table` | 🟡 n | warn+flag |
| | | | | _Legacy pivot widget type alias._ |
| `tablewidget` | [doc](https://docs.sisense.com/main/SisenseLinux/widget-designer.htm) | `table` | 🟡 n | warn+flag |
| `chart/scatter` | [doc](https://docs.sisense.com/main/SisenseLinux/scatter-chart.htm) | `scatter-chart` | 🟡 n | warn+flag |
| | | | | _Verify axis/size mapping (Sisense scatter has X/Y + size + color)._ |
| `chart/polar` | [doc](https://docs.sisense.com/main/SisenseLinux/polar-chart.htm) | `bar-chart` | 🟡 n | warn+flag |
| | | | | _Sigma has no polar/radar element; the builder emits a bar-chart while the coverage report labels the closest match 'radar' (HINT — verify)._ |
| `chart/funnel` | [doc](https://docs.sisense.com/main/SisenseLinux/widget-designer.htm) | `bar-chart` | 🟡 n | warn+flag |
| | | | | _No native Sigma funnel; emitted as a bar-chart + flag note (HINT)._ |
| `treemap` | [doc](https://docs.sisense.com/main/SisenseLinux/treemap.htm) | — (no Sigma equivalent) | 🟡 n | warn+flag |
| | | | | _No native Sigma equivalent -> convert_dashboard flags the widget (no element). Coverage report marks it MANUAL._ |
| `sunburst` | [doc](https://docs.sisense.com/main/SisenseLinux/sunburst-widget.htm) | — (no Sigma equivalent) | 🟡 n | warn+flag |
| | | | | _No native Sigma equivalent -> flagged (no element), MANUAL in the coverage report._ |
| `map/area` | [doc](https://docs.sisense.com/main/SisenseLinux/area-map.htm) | — (no Sigma equivalent) | 🟡 n | warn+flag |
| | | | | _The coverage report suggests a Sigma geography-region map (HINT), but the builder has no SIGMA_KIND entry -> the widget is flagged (no element emitted) and the geo mapping is done manually. VERIFY geo level._ |
| `map/scatter` | [doc](https://docs.sisense.com/win/SisenseWin/scatter-map.htm) | — (no Sigma equivalent) | 🟡 n | warn+flag |
| | | | | _Coverage report suggests a Sigma geography-point map (HINT); builder flags it (no element) — recreate the point map manually._ |

## Number format

_Sisense widget JAQL number-format signal -> Sigma column `format` object. The ONLY documentation-grounded numeric-format signal convert.py ports is the currency mask (JAQL `format.mask.currency: true`), which maps to a Sigma currency number format. IMPORTANT (beads-sigma-kvza): the previous `_money_fmt` ALSO returned a $ format when the widget TITLE contained the substring 'Revenue' or 'Cost' — a name-guessing heuristic that mis-formatted any non-currency measure with those words in its title. That title-substring guess has been REMOVED. A JAQL `format.mask` that is present but is NOT a currency signal (e.g. a percent/number mask) is a formatting intent this converter does not yet port -> it now LOUDLY warns and ships the column unformatted, rather than silently dropping it or wrong-guessing. Sisense's default currency symbol is USD '$' per the cited doc._

Authoritative source: <https://docs.sisense.com/main/SisenseLinux/formatting-numbers-in-widgets.htm>

| construct | doc ref | Sigma target | sigma_verified | on-unmapped |
|---|---|---|---|---|
| `mask.currency` | [doc](https://docs.sisense.com/main/SisenseLinux/formatting-numbers-in-widgets.htm) | `$,.0f` | 🟡 n | warn+ship-unformatted |
| | | | | _JAQL `format.mask.currency: true` -> Sigma format {kind:number, formatString:'$,.0f', currencySymbol:'$'} (the MONEY object). This is the sole signal that yields a currency format; the removed title-substring heuristic is documented in the dimension description above._ |

## Aggregation

_Sisense JAQL `agg` value -> Sigma aggregate function. Extracted verbatim from jaql_expr.AGG; jaql_expr.translate_agg() derives this dict from these rows and raises Unsupported (which the converter turns into a FLAG) on any agg not listed here. The full JAQL aggregation-type enumeration is documented at the cited Sisense reference. Compositional surfaces stay as cited CODE, not this flat table: the JAQL formula function translator (jaql_expr.SAFE_FUNC / FLAG_FUNC — arithmetic + scalar/agg function-name rewriting, with PREV/PAST/RSUM/GROWTH/QUARTILE/CONTRIBUTION etc. flagged) and the date-level DateTrunc map (jaql_expr.LEVEL). See refs/jaql-mapping.md._

Authoritative source: <https://developer.sisense.com/reference/jaql/>

| construct | doc ref | Sigma target | sigma_verified | on-unmapped |
|---|---|---|---|---|
| `sum` | [doc](https://developer.sisense.com/guides/sdk/modules/sdk-data/variables/variable.AggregationTypes.html) | `Sum` | 🟡 n | raise Unsupported->flag |
| `count` | [doc](https://developer.sisense.com/guides/sdk/modules/sdk-data/variables/variable.AggregationTypes.html) | `Count` | 🟡 n | raise Unsupported->flag |
| `countdistinct` | [doc](https://developer.sisense.com/guides/sdk/modules/sdk-data/variables/variable.AggregationTypes.html) | `CountDistinct` | 🟡 n | raise Unsupported->flag |
| | | | | _JAQL agg value is `countDistinct`; keys are normalized to lowercase (jaql lowercases before lookup)._ |
| `avg` | [doc](https://developer.sisense.com/guides/sdk/modules/sdk-data/variables/variable.AggregationTypes.html) | `Avg` | 🟡 n | raise Unsupported->flag |
| `average` | [doc](https://developer.sisense.com/guides/sdk/modules/sdk-data/variables/variable.AggregationTypes.html) | `Avg` | 🟡 n | raise Unsupported->flag |
| | | | | _Alias of `avg` (some JAQL emits the long form)._ |
| `min` | [doc](https://developer.sisense.com/guides/sdk/modules/sdk-data/variables/variable.AggregationTypes.html) | `Min` | 🟡 n | raise Unsupported->flag |
| `max` | [doc](https://developer.sisense.com/guides/sdk/modules/sdk-data/variables/variable.AggregationTypes.html) | `Max` | 🟡 n | raise Unsupported->flag |
| `median` | [doc](https://developer.sisense.com/guides/sdk/modules/sdk-data/variables/variable.AggregationTypes.html) | `Median` | 🟡 n | raise Unsupported->flag |
| `stdev` | [doc](https://developer.sisense.com/guides/sdk/modules/sdk-data/variables/variable.AggregationTypes.html) | `Stdev` | 🟡 n | raise Unsupported->flag |
| | | | | _Sigma Stdev = sample standard deviation; verify vs Sisense stdev semantics on live data._ |
| `var` | [doc](https://developer.sisense.com/guides/sdk/modules/sdk-data/variables/variable.AggregationTypes.html) | `Var` | 🟡 n | raise Unsupported->flag |
| | | | | _Sigma Var = sample variance; verify vs Sisense var semantics on live data._ |

## Control / filter

_Sisense dashboard-filter shape/datatype -> Sigma control kind (from convert.py._emit_control). A member/explicit selection or a text (descriptive) field -> `list`; a date/datetime field OR a JAQL date-`level` grouping -> `date-range`; a numeric field -> `number-range`. The DEFAULT for an unrecognized datatype is a categorical `list` control — a DOCUMENTED default (Sisense filters default to a List filter on descriptive fields per the cited doc), NOT a silent wrong guess. `_emit_control` resolves the control-kind vocabulary from these rows; its compound branching (filter-shape + datatype + date-level) stays as cited code because it is not a flat 1:1 lookup. A filter whose `dim` cannot be parsed returns None and is LOUDLY flagged for manual recreation (never faked)._

Authoritative source: <https://docs.sisense.com/main/SisenseLinux/configuring-how-filters-affect-the-dashboard-and-widgets.htm>

| construct | doc ref | Sigma target | sigma_verified | on-unmapped |
|---|---|---|---|---|
| `members` | [doc](https://docs.sisense.com/main/SisenseLinux/configuring-how-filters-affect-the-dashboard-and-widgets.htm) | `list` | 🟡 n | n/a |
| | | | | _Member-list filter (JAQL filter.members) — the most common categorical filter -> Sigma list control seeded with the selected members._ |
| `explicit` | [doc](https://docs.sisense.com/main/SisenseLinux/configuring-how-filters-affect-the-dashboard-and-widgets.htm) | `list` | 🟡 n | n/a |
| | | | | _Explicit member-set filter (JAQL filter.explicit.members) -> Sigma list control._ |
| `text` | [doc](https://docs.sisense.com/main/SisenseLinux/configuring-how-filters-affect-the-dashboard-and-widgets.htm) | `list` | 🟡 n | n/a |
| | | | | _Descriptive/text datatype (datatype/dimType 'text' or unset with no date level) -> Sigma list control._ |
| `datetime` | [doc](https://docs.sisense.com/main/SisenseLinux/configuring-how-filters-affect-the-dashboard-and-widgets.htm) | `date-range` | 🟡 n | n/a |
| | | | | _Date/datetime field -> Sigma date-range control (a list control bound to a datetime column comes back empty on POST)._ |
| `date` | [doc](https://docs.sisense.com/main/SisenseLinux/configuring-how-filters-affect-the-dashboard-and-widgets.htm) | `date-range` | 🟡 n | n/a |
| `level` | [doc](https://docs.sisense.com/main/SisenseLinux/configuring-how-filters-affect-the-dashboard-and-widgets.htm) | `date-range` | 🟡 n | n/a |
| | | | | _A JAQL date-`level` grouping (years/quarters/months/...) on the filtered dim forces a date-range control regardless of the declared datatype (compositional signal)._ |
| `numeric` | [doc](https://docs.sisense.com/main/SisenseLinux/configuring-how-filters-affect-the-dashboard-and-widgets.htm) | `number-range` | 🟡 n | n/a |
| | | | | _Numeric field -> Sigma number-range (between) control._ |
| `number` | [doc](https://docs.sisense.com/main/SisenseLinux/configuring-how-filters-affect-the-dashboard-and-widgets.htm) | `number-range` | 🟡 n | n/a |
| | | | | _Alias of `numeric`._ |
| `*` | [doc](https://docs.sisense.com/main/SisenseLinux/configuring-how-filters-affect-the-dashboard-and-widgets.htm) | `list` | 🟡 n | n/a |
| | | | | _DOCUMENTED DEFAULT: an unrecognized filter datatype becomes a categorical list control (Sisense's own default filter kind for descriptive fields). Not a silent wrong-default — the fallback is the documented categorical control._ |

---
_Compositional constructs that do not serialize to a flat table (Set Analysis, filtered `*If`, ratio measures, TO_CHAR/Excel mask parsers, count-on-joined-view) stay as cited predicates in the classifier; this matrix covers the enumerable maps._
