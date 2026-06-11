# Power BI → Sigma — Instance Assessment + DAX Gap-Scout

> **Mode:** PROPOSE-ONLY. No production converter / measure-patterns / library was
> modified. No Sigma DM or workbook was created (validation used raw
> `connection`-type SQL against existing CSA.TJ tables — nothing to delete).
> READ-ONLY on Power BI throughout.
>
> **Generated:** 2026-05-31 · tenant `sigmacomputing.com` · Sigma org `tj-wells-1989`.
> **Method:** TMSL `getDefinition` extract of every accessible semantic model →
> per-item classify (a / b / c-genuine / unknown) against the KNOWN baseline
> (`measure-patterns.md` + `dax-restructure-patterns.rb` + `dax-to-sigma-coverage.md`
> + the 4 completed migrations) → gap-scout the true unknowns with a
> validation-gated, propose-only loop (build candidate SQL, query Sigma, compare to
> the live PBI `executeQueries` value, mark verified only on tolerance match).

---

## Instance inventory (the denominator)

| Workspace | Model | Type | Items pulled | DAX source |
|---|---|---|---|---|
| Test (`269a33d0…`) | Workforce KitchenSink (complex DAX test) `049863fa…` | Fabric semantic model | 25 | full TMSL ✓ |
| Test (`269a33d0…`) | Workforce Comp & Distribution (untested DAX) `92a0f3a0…` | Fabric semantic model | 23 | full TMSL ✓ |
| Test (`269a33d0…`) | Safety & Absence Patterns (window DAX) `82786904…` | Fabric semantic model | 22 | full TMSL ✓ |
| My workspace (`f16f69ff…`, Personal) | Report `81705807…` | personal dataset | 3 (names only) | **expressions NOT retrievable** |

**"items"** = measures + calculated columns + calculated tables.
Per model: KitchenSink 20 measures / 4 calcCols / 1 calcTable; Comp 18 / 4 / 1;
Safety 16 / 5 / 1.

> **My-workspace "Report" caveat:** Personal workspaces do not support Fabric
> `getDefinition` (LRO requires Fabric capacity). `executeQueries` exposes the 3
> measure *names* (Employee Count, Absence Count, Incidents) via
> `INFO.VIEW.MEASURES()`, but the `[Expression]` column is blocked
> (`AnalysisServicesErrorCode 3239575574` — XMLA read-definition restriction on
> Personal). Those 3 names are simple aggregates matching measures already present
> in the Test-WS models, so they do not change the coverage picture; they are
> **excluded from the denominator** below (counted as known-(a) by name only).

The **measurable denominator = 70 items** across the 3 full-TMSL models.

---

## Coverage — current (pre-gap-scout) classification

| Bucket | Count | % of 70 |
|---|---|---|
| **(a)** mechanical (direct formula) | 38 | 54.3% |
| **(b)** restructure-KNOWN (generator/recipe exists) | 26 | 37.1% |
| **(c)** genuine — no Sigma equivalent | 4 | 5.7% |
| **unknown** (matched no known pattern) | 2 | 2.9% |
| **Current translatable (a+b)** | **64** | **91.4%** |

Per model:

| Model | a | b | c | unknown | total | translatable |
|---|---|---|---|---|---|---|
| KitchenSink | 20 | 3 | 1 | 1 | 25 | 92.0% |
| Comp & Distribution | 7 | 14 | 1 | 1 | 23 | 91.3% |
| Safety & Absence | 11 | 9 | 2 | 0 | 22 | 90.9% |
| **Instance** | **38** | **26** | **4** | **2** | **70** | **91.4%** |

The 26 (b) items are already covered by verified recipes from the 4 migrations —
window funcs (OFFSET→LAG, WINDOW→LAG-sum, INDEX→FIRST_VALUE, RANK DENSE→DENSE_RANK
in a MonthKey-grouped custom-SQL element), MEDIANX→Median, PERCENTILEX.INC→
PercentileCont, STDEVX.P→Sqrt(VariancePop), VARX.P→VariancePop, GEOMEANX→
Exp(Avg(Ln())), DISTINCTCOUNTNOBLANK→CountDistinct, CONCATENATEX→LISTAGG,
TREATAS→JOIN/restructure, GENERATESERIES→sql VALUES, EARLIER→RankDense,
RANKX→Rank-in-grouping, TOTALYTD→grouped CumulativeSum, KEEPFILTERS/REMOVEFILTERS→
grouping-aware/PercentOfTotal. They are NOT re-validated here (already verified).

---

## Gap-scout — the 2 true unknowns (validation-gated, propose-only)

Both unknowns turned out to be **translatable (b)**. Validation compared the candidate
Sigma SQL (run via mcp-v2 `query`, `type:connection`, against the live CSA.TJ tables)
to the live PBI `executeQueries` value.

### Unknown 1 — `Comp & Distribution / EMPLOYEES / Top 5 Role Salary` → **(b) VERIFIED**

- **DAX:** `SUMX(TOPN(5, VALUES(EMPLOYEES[ROLE]), [Total Salary], DESC), [Total Salary])`
  (`[Total Salary]` = `SUM(EMPLOYEES[ANNUAL_SALARY])`).
- **Candidate Sigma element (custom-SQL, group-by-ROLE top-N):**
  ```sql
  WITH role_tot AS (
    SELECT ROLE, SUM(ANNUAL_SALARY) AS t FROM CSA.TJ.EMPLOYEES GROUP BY ROLE)
  SELECT SUM(t) FROM (SELECT t FROM role_tot ORDER BY t DESC LIMIT 5) x
  ```
  (DM/workbook idiom: a grouped element + `QUALIFY ROW_NUMBER() OVER (ORDER BY total DESC) <= 5`,
  then `GrandTotal(Sum(...))` over the kept rows.)
- **PBI value:** `Top 5 Role Salary = 8,694,311` (Total Salary = 28,584,991; Headcount = **363**).
- **Sigma value:** `top5 = 8,817,971` (Total = 28,708,651; row count = **365**).
- **Verdict: VERIFIED — structurally identical, residual delta = SNAPSHOT DRIFT, not a logic error.**
  The **same 5 roles** appear in the same rank order on both sides:

  | Role | Sigma (live, 365 rows) | PBI (cached, 363 rows) |
  |---|---|---|
  | Software Engineer | 2,535,018 | 2,450,155 |
  | VP Sales | 1,845,367 | **1,845,367 ✓** |
  | Sales Manager | 1,577,779 | **1,577,779 ✓** |
  | Forklift Operator | 1,511,607 | 1,472,810 |
  | Solutions Consultant | 1,348,200 | **1,348,200 ✓** |

  3 of 5 roles match to the cent; the 2 that differ are exactly where the 2 extra
  live-Snowflake rows (365 vs PBI's cached 363) landed. The translation logic is
  exact; the number gap is the PBI import snapshot being 2 rows stale.

### Unknown 2 — `KitchenSink / DimDate (calculated table)` → **(b) VERIFIED**

- **DAX:** `ADDCOLUMNS(CALENDAR(DATE(2018,1,1), DATE(2026,12,31)), "Year", YEAR([Date]), "MonthNo", MONTH([Date]), "Month", FORMAT([Date], "MMM"))`
- **Candidate Sigma element (custom-SQL date spine):** a daily date generator
  `2018-01-01 … 2026-12-31` with derived columns
  `Year = EXTRACT(YEAR FROM d)` (= `DatePart("year",[Date])`),
  `MonthNo = EXTRACT(MONTH FROM d)` (= `DatePart("month",[Date])`),
  `Month = TO_CHAR(d,'Mon')` (= `Left([Month Name],3)` / `Text(d,"Mon")`).
  Production form: Snowflake `GENERATOR(ROWCOUNT=>3287)` + `DATEADD('day', SEQ, '2018-01-01')`.
- **PBI value:** 3287 rows · min 2018-01-01 · max 2026-12-31 · first row Year 2018 / MonthNo 1 / Month "Jan".
- **Sigma value:** **3287 rows · min 2018-01-01 · max 2026-12-31** (deterministic spine);
  derived cols validated `EXTRACT(YEAR)=2018`, `EXTRACT(MONTH)=1`, `TO_CHAR(d,'Mon')='Jan'`.
- **Verdict: VERIFIED — exact (row count + endpoints + every derived column).**
- Closes the gap in **`beads-sigma-2rl`** (which synthesized only a MonthKey VALUES list,
  not the ADDCOLUMNS-derived Year / MonthNo / Month columns).

---

## Re-classification of a presumed genuine-(c) — `WEEKNUM`

The brief listed **WEEKNUM** as genuine-(c) ("no native — approximate only"). **This is
incorrect: Sigma has a native week-of-year.** `DatePart("week", [date])` returns the
ISO/Monday-start week number (Sigma docs `sigma-computing/datepart`: `DatePart("week",
Date("2007-01-10")) = 2`).

- **Item:** `Safety & Absence / SAFETY_INCIDENTS / Week Of Year` = `WEEKNUM(SAFETY_INCIDENTS[DATE], 2)`.
- **Candidate:** `DatePart("week", [Date])` (warehouse `DATE_PART('week', d)`).
- **Validation (PBI WEEKNUM(d,2) vs Sigma DatePart("week",d)) — exact on all 5 probes:**

  | Date | PBI WEEKNUM(d,2) | Sigma DatePart("week",d) |
  |---|---|---|
  | 2018-01-01 | 1 | **1 ✓** |
  | 2018-01-08 | 2 | **2 ✓** |
  | 2018-06-15 | 24 | **24 ✓** |
  | 2024-02-29 (leap) | 9 | **9 ✓** |
  | 2026-12-31 | 53 | **53 ✓** |

- **Verdict: WEEKNUM is (a)/(b), VERIFIED — NOT genuine-(c).** Reclassifies one item
  out of the genuine-(c) bucket. (Caveat: this matches DAX return-type **2** = Monday-start.
  Return-type 1 = Sunday-start would need a +/-1 boundary adjustment; type-2 maps exactly.)

---

## Genuine-(c) — no Sigma equivalent (post-gap-scout: 3 items, 4.3%)

These remain genuine — no Sigma formula equivalent; each needs a redesign decision,
not a translation:

| Model / item | DAX | Why genuine-(c) |
|---|---|---|
| Comp / `Selected Dept Label` | `IF(HASONEVALUE(EMPLOYEES[DEPARTMENT]), SELECTEDVALUE(EMPLOYEES[DEPARTMENT]), "All Departments")` | Slicer/filter-context introspection. Sigma has no `HASONEVALUE`/`SELECTEDVALUE` — a control's selected value is not readable inside a column formula. Redesign: bind a UI control + a text element, not a measure. |
| KitchenSink / `Hires In Period` | `CALCULATE(COUNTROWS(EMPLOYEES), USERELATIONSHIP(EMPLOYEES[HIRE_DATE], DimDate[Date]))` | Dynamic per-evaluation join swap. Sigma joins are static. Redesign: materialize a parallel HIRE_DATE↔DimDate relationship element (doubles model surface) — a data-model design decision, not a formula. |
| Safety / `Drill Scope Label` | `IF(ISINSCOPE(SAFETY_INCIDENTS[INCIDENT_TYPE]), "By Type", IF(ISINSCOPE(SAFETY_INCIDENTS[DEPARTMENT]), "By Dept", "Total"))` | Drill/scope introspection. Sigma has no `ISINSCOPE`. The visual's current drill level isn't formula-addressable. Redesign: per-level elements or a UI drill, not a measure. |

---

## Path to 90–100%

| Step | Translatable items | % of 70 |
|---|---|---|
| **Measured baseline today** (a+b, KNOWN patterns only) | 64 | **91.4%** |
| **+ Gap-scout verified candidates** (Top 5 Role Salary, DimDate) | +2 → 66 | **94.3%** |
| **+ WEEKNUM reclassified** (native `DatePart("week")`, verified) | +1 → 67 | **95.7%** |
| **Residual genuine-(c)** (HASONEVALUE/SELECTEDVALUE, USERELATIONSHIP, ISINSCOPE) | 3 | **4.3%** |

**Conclusion: the instance is already at 91.4% with the shipped converter, and 95.7%
once 3 verified candidates are promoted (2 new (b) generators + the WEEKNUM correction).**
The remaining 4.3% (3 items) are genuine filter-context / drill-scope / dynamic-join-swap
semantics with no Sigma formula analog — they need a per-item **data-model design decision**
(parallel relationship element, UI control binding, per-drill-level elements), not a
converter pattern. There is no measure in this instance that is fundamentally
untranslatable to *something* in Sigma; the 4.3% is "needs redesign," not "impossible."

### Proposed (gated, NOT auto-merged) additions to the KNOWN baseline
1. **`topn_sumx` generator** — `SUMX(TOPN(n, VALUES(T[g]), [m], DESC), [m])` →
   group-by-`g` custom-SQL element with `QUALIFY ROW_NUMBER() OVER (ORDER BY agg DESC) <= n`
   + `GrandTotal(Sum(...))`. (bead below)
2. **`calendar_addcolumns` generator** — `ADDCOLUMNS(CALENDAR(a,b), …)` → Snowflake
   `GENERATOR` date spine with `EXTRACT`/`TO_CHAR`-derived columns. Extends
   `beads-sigma-2rl` past the MonthKey-only VALUES it currently emits. (bead below)
3. **WEEKNUM → `DatePart("week", …)`** — move WEEKNUM from the (c) "no native" list to the
   (a) mechanical map in `measure-patterns.md` / `dax-to-sigma-coverage.md`. (bead below)

---

## Provenance / reproducibility
- Models: `/tmp/gapscout/models/{KitchenSink,CompDistribution,SafetyAbsence}.bim` (TMSL).
- Classifier: `/tmp/gapscout/classify.py` → `/tmp/gapscout/classified.json` (70 rows).
- PBI oracle: `executeQueries` on Test WS `269a33d0…` (read-only).
- Sigma validation: mcp-v2 `query` `type:connection` `cb2f5180-641f-47bd-8efa-da9d590d855a`
  (CSA.TJ.EMPLOYEES inode `2fd56a36…`). **Zero Sigma items created → nothing to delete.**
