# NEW_FIXTURES — untested-DAX semantic models + styled reports

Created 2026-05-31 in the **Test** workspace (`269a33d0-98c4-476f-890d-612ea8072f9a`).
Both models live-bound to Snowflake **CSA.TJ** (`ymb68310`, conn `cb2f5180-641f-47bd-8efa-da9d590d855a`)
via key-pair creds (legacy Update-Datasource PATCH, `encryptionAlgorithm:"NONE"`, `passphrase:""`,
gateway `e707d522…`, datasource `0890727e…`). Both refreshed to **Completed** and verified via `executeQueries`.
Source tables used ONLY: `EMPLOYEES`, `ABSENCE_RECORDS`, `SAFETY_INCIDENTS`.

These complement `fixture_06_kitchen_sink` (already-covered DAX). The novelty here is (a) **untested DAX**
and (b) **un-charted angles** of the workforce data (salary dispersion/percentiles, role text-parsing,
month-over-month windowed safety trends, fatigue-vs-headcount).

> **Convertibility note:** every report visual type is in the converter's supported `visualType → Sigma kind`
> mapping (`research/powerbi-visual-layout.md` §4e). No `ribbonChart`/`funnel`/`treemap`/`map` (no Sigma
> equivalent — these only "approximate or skip with warning"). New types used = `gauge`, `donutChart`,
> `scatterChart` (all map cleanly). Each report also carries **2 `slicer` visuals** (→ Sigma `control`) so
> filter conversion can be exercised.

---

## Model A — Workforce Comp & Distribution (untested DAX)

- **Semantic model id:** `92a0f3a0-9bdd-42ab-b575-58269283177f`
  - URL: https://app.powerbi.com/groups/269a33d0-98c4-476f-890d-612ea8072f9a/datasets/92a0f3a0-9bdd-42ab-b575-58269283177f
  - .bim: `fixtures/fixture_07_comp_distribution.bim`
- **Report id:** `8271b4d7-cd81-4b92-9468-fd06716bbb26`
  - URL: https://app.powerbi.com/groups/269a33d0-98c4-476f-890d-612ea8072f9a/reports/8271b4d7-cd81-4b92-9468-fd06716bbb26
- Tables: `EMPLOYEES` (+ richer cols: ROLE, EMAIL, STATE, CITY, MANAGER_ID, SHIFT), `ABSENCE_RECORDS`, calc table `SalaryBands`.
- Refresh: **Completed**. Verify highlights: Median 73,000 · P90 121,440 · StdDev 31,634 · GeoMean 72,597 · 30 distinct roles · Top-5-role salary 8,694,311.

### Measures / calc-cols / calc-table → DAX → untested pattern → expected Sigma

| # | Object (type) | DAX | Untested pattern | Expected Sigma translation |
|---|---|---|---|---|
| 1 | Median Salary (M) | `MEDIANX(EMPLOYEES, EMPLOYEES[ANNUAL_SALARY])` | `MEDIANX` | `Median([Annual Salary])` |
| 2 | P90 Salary (M) | `PERCENTILEX.INC(EMPLOYEES, EMPLOYEES[ANNUAL_SALARY], 0.9)` | `PERCENTILEX.INC` | `PercentileInc([Annual Salary], 0.9)` |
| 3 | P10 Salary (M) | `PERCENTILEX.INC(…, 0.1)` | `PERCENTILEX.INC` | `PercentileInc([Annual Salary], 0.1)` |
| 4 | Salary StdDev (M) | `STDEVX.P(EMPLOYEES, EMPLOYEES[ANNUAL_SALARY])` | `STDEVX.P` | `StdevP([Annual Salary])` |
| 5 | Salary Variance (M) | `VARX.P(EMPLOYEES, EMPLOYEES[ANNUAL_SALARY])` | `VARX.P` | `VarP([Annual Salary])` |
| 6 | Salary GeoMean (M) | `GEOMEANX(EMPLOYEES, EMPLOYEES[ANNUAL_SALARY])` | `GEOMEANX` | unknown — new (no native GeoMean; `Exp(Avg(Ln([x])))` workaround) |
| 7 | Salary Spread P90-P10 (M) | `[P90 Salary] - [P10 Salary]` | measure arithmetic of percentiles | subtraction of two percentile measures |
| 8 | Distinct Roles (M) | `DISTINCTCOUNTNOBLANK(EMPLOYEES[ROLE])` | `DISTINCTCOUNTNOBLANK` | `CountDistinct([Role])` (blanks already excluded) |
| 9 | Roles In Dept (M) | `CONCATENATEX(VALUES(EMPLOYEES[ROLE]), EMPLOYEES[ROLE], ", ", …, ASC)` | `CONCATENATEX` | unknown — new (`ListAgg`-style; needs grouped context) |
| 10 | Top 5 Role Salary (M) | `SUMX(TOPN(5, VALUES(EMPLOYEES[ROLE]), [Total Salary], DESC), [Total Salary])` | `TOPN` | unknown — new (no row-set TOPN; rank-filter + Sum, e.g. `Sum(If(Rank≤5,…))`) |
| 11 | Selected Dept Label (M) | `IF(HASONEVALUE(…), SELECTEDVALUE(EMPLOYEES[DEPARTMENT]), "All Departments")` | `HASONEVALUE` + `SELECTEDVALUE` | control/label; `If(CountDistinct=1, Min([Dept]), "All Departments")` |
| 12 | Salary vs Company Median (M) | `VAR DeptMed=MEDIANX(...) VAR CoMed=CALCULATE(MEDIANX(...), REMOVEFILTERS(EMPLOYEES)) RETURN DIVIDE(DeptMed-CoMed, CoMed)` | `REMOVEFILTERS` (whole table) | grand-total ref: `(Median - PercentOfTotal-style grand Median)/grand` |
| 13 | Pct In Selected Bands (M) | `…TREATAS(Picked, SalaryBands[Band])… / …REMOVEFILTERS(SalaryBands)…` with `KEEPFILTERS` + `CALCULATETABLE` | `TREATAS`, `KEEPFILTERS`, `CALCULATETABLE` | unknown — new (TREATAS = synthetic relationship; no direct Sigma form) |
| 14 | Mgmt Headcount (M) | `COALESCE(CALCULATE([Headcount], KEEPFILTERS(SEARCH("Manager", EMPLOYEES[ROLE],1,0)>0)), 0)` | `COALESCE`, `KEEPFILTERS`, measure-level `SEARCH` | `Coalesce(…, 0)` + `Contains([Role],"Manager")` filter |
| 15 | Email Domain (CC) | `MID(EMPLOYEES[EMAIL], SEARCH("@", EMPLOYEES[EMAIL])+1, LEN(EMPLOYEES[EMAIL]))` | `SEARCH` (calc col) | `Right([Email], Length-Find("@"))` / `Split` |
| 16 | Role Family (CC) | `SUBSTITUTE(SUBSTITUTE(EMPLOYEES[ROLE], "Sr. ", ""), "Manager", "Mgmt")` | `SUBSTITUTE` (nested) | `Replace(Replace([Role],"Sr. ",""),"Manager","Mgmt")` |
| 17 | Dept-Role Key (CC) | `COMBINEVALUES(" | ", EMPLOYEES[DEPARTMENT], EMPLOYEES[ROLE])` | `COMBINEVALUES` | `Concat([Dept], " | ", [Role])` |
| 18 | Salary Rank In Dept (CC) | `COUNTROWS(FILTER(EMPLOYEES, …[DEPARTMENT]=EARLIER([DEPARTMENT]) && …[SALARY]>EARLIER([SALARY])))+1` | `EARLIER`-based calc column | `RankDense` window partitioned by Dept (Sigma has no EARLIER; row-context rank) |
| 19 | Absence Hours (High Earners) (M) | `…TREATAS(HighEarners, ABSENCE_RECORDS[EMPLOYEE_ID])…` over `FILTER(ALL(EMPLOYEES), …≥[P90 Salary])` | `TREATAS` (cross-table id push) | unknown — new (virtual relationship via id list) |
| 20 | SalaryBands (calc TABLE) | `ADDCOLUMNS(SELECTCOLUMNS(GENERATESERIES(40000,200000,40000),"BandFloor",[Value]), "Band", "$"&FORMAT([BandFloor]/1000,"0")&"k+")` | `GENERATESERIES` + `SELECTCOLUMNS` + `ADDCOLUMNS` calc table | unknown — new (no native series gen; warehouse VALUES table or inline list) |

Verified by `executeQueries`:
- stat measures (row 1–8): all return real numbers.
- context measures by dept (9, 12, 13, 14, 19): `Roles In Dept` lists 10–11 roles/dept; `Salary vs Company Median` ranges -17.8%…+41.8%; `Mgmt Headcount` 10–15/dept; `Absence Hours (High Earners)` 4.7k–8.7k.
- calc columns (15–18): Email Domain `acmecorp.com`, Role Family strips `Sr.`, Dept-Role Key joined, Salary Rank In Dept up to 82.
- calc table (20): 5 bands `$40k+…$200k+`.

---

## Model B — Safety & Absence Patterns (window DAX)

- **Semantic model id:** `82786904-9405-4b56-af99-f6da6003a1c9`
  - URL: https://app.powerbi.com/groups/269a33d0-98c4-476f-890d-612ea8072f9a/datasets/82786904-9405-4b56-af99-f6da6003a1c9
  - .bim: `fixtures/fixture_08_safety_absence_patterns.bim`
- **Report id:** `f0e8ceb8-fc09-43c3-b0c2-bebf10cae242`
  - URL: https://app.powerbi.com/groups/269a33d0-98c4-476f-890d-612ea8072f9a/reports/f0e8ceb8-fc09-43c3-b0c2-bebf10cae242
- Tables: `SAFETY_INCIDENTS`, `ABSENCE_RECORDS`, `EMPLOYEES`, disconnected calc table `DimMonth`.
- Note: the DAX **window functions** (`OFFSET`/`WINDOW`/`INDEX`/`RANK`) sort over the fact's own `MonthKey` int calc column — DimMonth is intentionally **disconnected** (relating fact calc-columns to a calc-table dim failed Fabric import with `invalid column ID`).
- **Axis design:** DAX window functions only evaluate correctly when the visual **groups by the same column the window orders by** (`MonthKey`). So the window measures live in the **"Monthly Trend (OFFSET/WINDOW/RANK)" table grouped by `MonthKey`** (where prev/MoM/rolling/rank are all correct). The **line chart** instead groups by a clean `Month Start` date calc column (`Incident Count` + `Avg Fatigue Hours`) — readable dates, no fragile window navigation. (Earlier the line chart used raw `MonthKey` like `202507`, which looked wrong; fixed.)
- Refresh: **Completed**. Verify highlights: 36 DimMonth rows (Apr 2024–end 2026), month rank/rolling-3mo/worst-month all evaluate.

### Measures / calc-cols / calc-table → DAX → untested pattern → expected Sigma

| # | Object (type) | DAX | Untested pattern | Expected Sigma translation |
|---|---|---|---|---|
| 1 | Incidents Prev Month (M) | `CALCULATE([Incident Count], OFFSET(-1, ALLSELECTED(SAFETY_INCIDENTS[MonthKey]), ORDERBY(SAFETY_INCIDENTS[MonthKey], ASC)))` | `OFFSET` (new window fn) | `Lag(Sum/Count, 1)` ordered by month |
| 2 | Incident MoM Delta (M) | `[Incident Count] - [Incidents Prev Month]` | window-measure arithmetic | current − lag |
| 3 | Incident Rolling 3mo (M) | `CALCULATE([Incident Count], WINDOW(-2, REL, 0, REL, ALLSELECTED(…[MonthKey]), ORDERBY(…[MonthKey], ASC)))` | `WINDOW` (new window fn) | `SumOver`/windowed sum, trailing-3 frame |
| 4 | Month Rank By Incidents (M) | `RANK(DENSE, ALLSELECTED(…[MonthKey]), ORDERBY([Incident Count], DESC))` | `RANK` (new window fn) | `RankDense(...)` over months |
| 5 | Worst Month Incidents (M) | `CALCULATE([Incident Count], INDEX(1, ALLSELECTED(…[MonthKey]), ORDERBY([Incident Count], DESC)))` | `INDEX` (new window fn) | unknown — new (pick Nth ordered row; `First` of sorted) |
| 6 | Overtime Incident Rate (M) | `DIVIDE(CALCULATE([Incident Count], KEEPFILTERS(SAFETY_INCIDENTS[OVERTIME_ON_DAY]=TRUE())), [Incident Count])` | `KEEPFILTERS` | `Divide(CountIf([OT]), Count())` |
| 7 | Incident Pct of All Depts (M) | `DIVIDE([Incident Count], CALCULATE([Incident Count], REMOVEFILTERS(SAFETY_INCIDENTS[DEPARTMENT])))` | `REMOVEFILTERS` (single column) | `PercentOfTotal(...,"parent_grouping")` or grand-total ref |
| 8 | Drill Scope Label (M) | `IF(ISINSCOPE(SAFETY_INCIDENTS[INCIDENT_TYPE]), "By Type", IF(ISINSCOPE(…[DEPARTMENT]), "By Dept", "Total"))` | `ISINSCOPE` | unknown — new (no scope introspection; grouping-level label) |
| 9 | Weighted Severity (M) | `SUMX(SAFETY_INCIDENTS, SAFETY_INCIDENTS[Severity Weight])` | SUMX over calc-col weight | `Sum([Severity Weight])` |
| 10 | Avg Fatigue Hours (M) | `AVERAGE(SAFETY_INCIDENTS[HOURS_WORKED_BEFORE_INCIDENT])` | (covered AVERAGE; new column/angle) | `Avg([Hours Worked Before Incident])` |
| 11 | Absence Hours Prev Month (M) | `CALCULATE([Total Absence Hours], OFFSET(-1, ALLSELECTED(ABSENCE_RECORDS[MonthKey]), ORDERBY(…, ASC)))` | `OFFSET` on a 2nd fact | `Lag(Sum([Hours]),1)` ordered by month |
| 12 | Absence Hours In Incident Depts (M) | `VAR IncDepts=CALCULATETABLE(VALUES(SAFETY_INCIDENTS[DEPARTMENT]), ALL(SAFETY_INCIDENTS)) RETURN CALCULATE([Total Absence Hours], TREATAS(IncDepts, ABSENCE_RECORDS[DEPARTMENT]))` | `TREATAS` + `CALCULATETABLE` (cross-table) | unknown — new (virtual relationship on Department) |
| 13 | Incidents Per 100 Heads (M, EMPLOYEES) | `DIVIDE([Incident Count], [Headcount]) * 100` | cross-table ratio (via active rel) | `Divide([Incident Count],[Headcount])*100` |
| 14 | MonthKey (CC) | `YEAR([DATE])*100 + MONTH([DATE])` | int month key calc col (sort/window key) | `Year([Date])*100 + Month([Date])` |
| 14b | Month Start (CC) | `DATE(YEAR([DATE]), MONTH([DATE]), 1)` | month-truncation date calc col (clean chart axis) | `DateTrunc("month", [Date])` |
| 15 | Week Of Year (CC) | `WEEKNUM(SAFETY_INCIDENTS[DATE], 2)` | `WEEKNUM` (Mon-start) | `Week([Date])` |
| 16 | Severity Weight (CC) | `SWITCH(…[SEVERITY], "Critical",4,"High",3,"Medium",2,"Low",1,0)` | SWITCH 4-way weight col | `Switch`/nested `If` |
| 17 | DimMonth (calc TABLE) | `SELECTCOLUMNS(ADDCOLUMNS(GENERATESERIES(0,35,1), "_d", EDATE(DATE(2024,1,1),[Value])), "MonthKey", YEAR([_d])*100+MONTH([_d]), "MonthLabel", FORMAT([_d],"MMM YYYY"), "MonthEnd", EOMONTH([_d],0))` | `GENERATESERIES` + `EDATE` + `EOMONTH` calc table (disconnected) | unknown — new (month-spine table; `DateAdd`/`EndOfMonth` over a generated series) |

Verified by `executeQueries`:
- window measures (1–5) by month: e.g. 202509 → inc 33, prev 29, MoM +4, rolling-3 99, rank 4, worst 42 (INDEX constant).
- pattern measures (6–8, 12) by dept: Overtime rate 25–45%, Pct-of-depts 16–26%, Drill Scope = "Total" at grand total, Absence-in-incident-depts 34,047.5.
- calc table (17): 36 months, `MonthLabel` "Apr 2024", `MonthEnd` 2026-12-31 (EOMONTH).

---

## Styled-`objects` recipe for NEW visual types

All visuals share the base styled `objects`: bold left-aligned `title` (accent `#118DFF` for charts, dark for cards),
white `background` (`show:true`), light `border` (`#E1E1E1`, `radius:6`). Literal encoding:
`{"expr":{"Literal":{"Value":"<v>"}}}` — strings wrapped in single quotes, numbers suffixed `D`, colors as `{"solid":{"color":<lit>}}`.

| Visual type | queryState roles | NEW per-type `objects` |
|---|---|---|
| `gauge` | `Y`: [measure] | `dataPoint.fillColor` (accent), `labels.show:true` |
| `donutChart` | `Category`: [column], `Y`: [measure] | `labels.show:true` + `labelStyle:'Category, percent of total'`; `legend.show:true` + `position:'Right'` |
| `scatterChart` | `Category`: [detail column], `X`: [measure], `Y`: [measure] | `dataPoint.fill` (accent2 `#E66C37`), `legend.show:false` |
| `slicer` (filter) | `Values`: [column] | `general.outlineColor` (border) |
| `card` (KPI) | `Values`: [measure] | `labels` (accent, 28pt bold), `categoryLabels.show:true` |
| `clusteredColumnChart`/`lineChart`/`clusteredBarChart` | `Category`: [column], `Y`: [measures] | `dataPoint.fill`, `labels.show:true`, `legend.show` (true if multi-series) |
| `tableEx` | `Values`: [cols + measures, ordered] | base only |
| `pivotTable` (matrix) | `Rows`: [column], `Columns`: [column], `Values`: [measures] | base only |

All 23 visuals across the two reports (11 in Report A, 12 in Report B) round-tripped via `getDefinition` with `visualType`, bindings, roles, and `objects` intact. Report B's line chart groups by `Month Start` (`Incident Count` + `Avg Fatigue Hours`); the windowed measures sit in a `MonthKey`-grouped table.

## Reproduction scripts (in /tmp/pbiauth)
- `deploy_new.py <bim> <name>` — create semantic model (LRO, transient-DNS-resilient poll).
- `bind_refresh.py <datasetId>` — key-pair cred bind + refresh-to-Completed.
- `exec2.py <datasetId>` — pipe DAX to `executeQueries`.
- `report_lib.py` + `build_report_a.py` / `build_report_b.py` — styled PBIR generators (1280×720, M=24/G=16 grid).
- `create_report.py <root> <name>` — create report item (live-bound).
- `verify_report.py <reportId>` — round-trip getDefinition + dump visualType/roles/objects.

---

## Migration note — Model B end-to-end (2026-05-31, validated)

Migrated Model B ("Safety & Absence Patterns") fully into tj-wells-1989:
- **DM:** `a5242e18-6d60-49b1-b3fc-62c6a5de2875` (3 warehouse-table elements + 1 SQL `Monthly Window Trend` element; 0 error columns)
- **Workbook:** `bbfa6279-8115-45a1-8b97-49a74d110da4` (12 visuals + 4 hidden masters, 24-col layout applied last, 44 cols clean)
- **Phase 6:** 11/11 strict PASS vs PBI executeQueries; assert-phase6-ran 4/4 GREEN.

### Window functions (OFFSET/WINDOW/INDEX/RANK) — ALL reproduced (bucket b)
The DAX window measures error in plain Sigma DM calc columns AND as DM metrics
(the converter even emitted `RANK(DENSE, ALLSELECTED(...), ORDERBY(...))` verbatim,
which is invalid Sigma). The reproducible shape that matched PBI to the unit:
materialize them in a **custom-SQL DM element** that groups SAFETY_INCIDENTS by
MonthKey and computes the windows with Snowflake window fns, then group-by MonthKey
+ `Max()` in the workbook table. Exact SQL→DAX mapping (verified vs PBI 202507–202605):
- **OFFSET(-1, ORDERBY ASC)** → `LAG(inc,1) OVER (ORDER BY monthkey)`  (Incidents Prev Month: null,37,29,33,34,33,42,10,12,3,25 ✓)
- **WINDOW(-2 REL, 0 REL)** → `inc + COALESCE(LAG(inc,1),0) + COALESCE(LAG(inc,2),0)`. **NOT** `SUM(...) OVER (ORDER BY ...)` — that is an unbounded cumulative sum (wrong) and Sigma's mcp-v2 query layer rejects bounded `ROWS BETWEEN N PRECEDING` frames, so the LAG-sum form is required.  (Rolling 3mo: 37,66,99,96,100,109,85,64,25,40,56 ✓)
- **RANK(DENSE, ORDERBY DESC)** → `DENSE_RANK() OVER (ORDER BY inc DESC)`. Plain `RANK()` diverges (gives 6 where PBI DENSE gives 5).  (2,5,4,3,4,1,9,8,10,7,6 ✓)
- **INDEX(1, ORDERBY DESC)** → `FIRST_VALUE(inc) OVER (ORDER BY inc DESC)` = 42 constant ✓
- Edge case: PBI `Incident MoM Delta` at the first month = `Incident Count` (prev=blank→0); Sigma LAG gives null there. Benign single-cell difference.

### Other DAX
- **ISINSCOPE / Drill Scope Label**: FLAGGED (bucket c). No Sigma scope-introspection;
  the converter emitted raw `ISINSCOPE(...)` which is invalid. Dropped from the DM
  (would have been an error column); it is a grouping-level label with no faithful scalar form.
- **REMOVEFILTERS(single col) / Incident Pct of All Depts** → `PercentOfTotal(CountDistinct([Incident Id]), "grand_total")` ✓ exact.
- **KEEPFILTERS / Overtime Incident Rate** → `CountIf([Overtime on Day]) / CountDistinct([Incident Id])` ✓ exact.
- **TREATAS / Absence Hours In Incident Depts**: degenerate (same trap as Model A row 19).
  `ALL(SAFETY_INCIDENTS)` → IncDepts = all 6 depts; every absence dept is in that set
  (verified: NOT-IN query returns empty), so the measure = `[Total Absence Hours]` =
  `GrandTotal(Sum([Hours]))`. PBI value 34047.5 vs live-Snowflake 34062.9 — the 15.4 gap
  is a **source-snapshot difference** (PBI import vs live table), confirmed because PBI's
  own grand-total `[Total Absence Hours]` = 34047.5 too.
- **Incidents Per 100 Heads** (cross-table ratio): in the SAFETY_INCIDENTS[DEPARTMENT]
  context PBI's `[Headcount]` is the GLOBAL headcount (no SAFETY.dept↔EMP.dept rel), so
  `Incident Count / 363 * 100`. Reproduced with the **constant-denominator** form
  (`CountDistinct([Incident Id]) / 363 * 100`); grand-total = 78.79 matches PBI exactly.
  Caveat: PBI `COUNTROWS(EMPLOYEES)` = 363 but live EMPLOYEES = 365 (snapshot drift) — flagged.
- **DimMonth** (GENERATESERIES+EDATE+EOMONTH calc table): the converter's w9s fix DID emit
  a `sql` element (not a 404 table), but only the MonthKey VALUES column has real SQL;
  MonthLabel/MonthEnd reference non-existent `[Month Label]`/`[Month End]` (would error).
  DimMonth is a **disconnected** dim and **no report visual binds to it**, so it was dropped
  from the migration (flagged) with zero parity impact. The window measures order over the
  fact's own MonthKey, not DimMonth.
- **Calc cols**: MonthKey `Year([Date])*100+Month([Date])` ✓, Month Start `MakeDate(...)` ✓,
  Severity Weight `Switch(...)` ✓ (Weighted Severity SUMX→`Sum([Severity Weight])` = 471 ✓),
  Week Of Year: Sigma has no `WeekNumber`/`Week` fn — used `DateDiff("week", DateTrunc("year",[Date]), [Date]) + 1` (not bound in any visual; approximate vs WEEKNUM Mon-start).

### Converter/script gaps observed (candidate beads)
- Converter emits invalid Sigma for window/rank/scope DAX (`RANK(DENSE,...)`, `ISINSCOPE(...)`)
  as DM metrics rather than dropping or flagging them — these become error columns if posted.
- DimMonth ADDCOLUMNS-derived columns (MonthLabel/MonthEnd) point at non-existent SQL columns.
- `convert-model.rb` MODE B does not auto-name base elements when the converter already names
  them (it did here — 0 added — fine), but the window-element generator is not yet in
  `dax-restructure-patterns.rb` (OFFSET/WINDOW/INDEX/RANK → grouped-SQL element). Worth adding.
- Workbook builder emits `controlType: list-values` + `columnId`; spec POST requires
  `controlType: list` + `controlId` + `source:{kind:source,...}` + `filters[]`.
