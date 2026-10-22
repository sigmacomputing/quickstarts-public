# Excel → Sigma — Quickstart

End-to-end on the bundled sample fixture. ~10 min; three of the steps are clicks.

## 0. Setup
```bash
cd <this skill>/scripts
python3 -m venv .venv && .venv/bin/pip install -r ../requirements.txt
# Sigma creds in ~/.sigma-migration/env  (SIGMA_BASE_URL / SIGMA_CLIENT_ID / SIGMA_CLIENT_SECRET)
```

## 1. Make (or bring) an Excel model
```bash
.venv/bin/python make-sample-forecast.py        # writes "Sample Forecast.xlsx" (540-row formal Table + dims + 3 charts)
```
Or point the next steps at a real `.xlsx`.

To generate three smaller chart-focused fixtures:
```bash
.venv/bin/python make-chart-examples.py
```
This writes `chart-examples/Sales Performance.xlsx`, `Expense Planning.xlsx`,
and `Headcount Planning.xlsx`. Each has an editable formal Table plus three
charts that map directly to Sigma visualizations.

## 2. Audit, then discover
```bash
.venv/bin/python audit-xlsx.py "Sample Forecast.xlsx" --out /tmp/forecast-audit.json
# REVIEW_REQUIRED (exit 0) is expected for charts/formatting: route every issue before --post.
# (--strict exits 1 for it, for a production gate; `migrate.py plan <file>` runs audit + discovery
#  and prints the archetype, refs to read, and next commands.)
.venv/bin/python audit-openapi.py --out /tmp/sigma-code-rep-audit.json
.venv/bin/python xlsx-discover.py "Sample Forecast.xlsx"
```
The audit is the no-silent-loss gate; discovery then lists formal Tables, their
grain, each chart's type/title/anchor, pivots, and formulas. Confirm the fact
Table + grain and resolve every audit issue with the user.

## 3. Extract the paste-ready seed
```bash
.venv/bin/python xlsx-to-input-csv.py "Sample Forecast.xlsx" --table tblForecast --out forecast_input_paste.csv
```
Entry columns only, UPPER_SNAKE_CASE headers, dates as ISO. (System columns are
excluded — Sigma auto-populates them.)

## 4. Build the input-table structure  (API)
```bash
.venv/bin/python build-input-table-wb.py --name "Forecast Entry" --connection cb2f5180-… \
  --columns REGION:text,BRANCH:text,SUB_BRANCH:text,MONTH_DATE:datetime,CATEGORY_CODE:number,FORECAST_AMOUNT:number
```
> Builds the empty input-table **structure** through REST. The CLI stops there;
> seed the resulting table through Sigma MCP Code Mode or use UI CSV paste.
> **Don't use `--linked` for a shippable
> table** — linked context columns don't resolve via POST ("multiple values");
> use the established UI path, or validate MCP `add_linked_input_table()`
> end-to-end before shipping. See `refs/input-tables.md`.

## 5. Load data + view  (MCP + UI — see refs/input-tables.md)

Preferred when the Sigma MCP connector is available: `describe` and `query` the
new input table. First run `scripts/input-sync.py architecture --workflow ...`
and `stage` so the source audit, immutable architecture, reviewed seed, and
target document/page/version are bound. Emit construction and native join
fragments from that receipt. After assigned element/column IDs are reviewed and
re-staged, run `plan` with the queried rows. Review and submit its Code Mode
chunks, then re-query the table and a downstream element. The CLI plans and
emits programs; it does not call MCP. Use `complete` only after every approved
feature has edit/restore and persistence readback evidence.

UI fallback: open the workbook → the input table → paste
`forecast_input_paste.csv` → **Publish**.

Then use the input-table element menu → **Warehouse views → Create new** → copy the
   `database.schema.view` path.

## 6. Build the DM on the view  (API)
```bash
.venv/bin/python build-dm-on-view.py --view SIGMA_WRITE_DB.SIGMA_WRITE.FORECAST_ENTRY \
  --connection cb2f5180-… --categories-from "Sample Forecast.xlsx"
# prints the dataModelId
```

## 7. Verify parity
Query the DM's report element grouped by Statement Section (Sigma MCP) and compare
to the targets the discover step computed. The fixture's targets:
Revenue **10,902,533** · Contract Costs **−5,603,043** · Admin **−2,221,185** ·
Allocation **−415,557** · Net Contribution **2,662,748**.

> Validated run (2026-06-08): exact parity on all sections. workbook
> `cb6c53ef-…`, view `SIGMA_WRITE_DB.SIGMA_WRITE.FORECAST_ENTRY`, DM `04e462d8-…`.

---

# Worked example B — actuals + driver-grown + manual P&L (one-shot builder)

For a "report drawn in cells" planning model (live actuals + assumption-driven
forecast + manual cells) — the FP&A case. `xlsx-discover.py` now prints a
**cell-level model map** (ACTUAL / DRIVER_GROWTH / MANUAL /
DEPENDENCY_LINK / DERIVED). Preserve direct cell references as live
dependencies, including cash roll-forwards; `=prior` is not evidence for a
constant `flat` forecast. After confirming intent and that the source has the
expected actuals, drivers, sections, and periods (see `refs/model-taxonomy.md`),
route -> draft the **model-plan JSON** -> dry run -> post:

```bash
# 1. route: audit + discovery + archetype + next commands (JSON)
.venv/bin/python migrate.py plan "Original Model.xlsx" --out-dir work
# 2. draft the plan from the workbook (fails loudly on shapes it cannot map; verifies every
#    line-month and GL month against Excel's cached values before writing)
.venv/bin/python draft-forecast-plan.py "Original Model.xlsx" --intent what-if \
    --connection <writeConn> --folder <folderId> --out work/plan.json
# 3. dry run (draft mode): local parity vs the workbook's totals + dm_spec.json / wb_spec.json / seed CSVs
.venv/bin/python build-forecast-model.py work/plan.json --out-dir work/build
# 4. build live (DM + workbook with union[actuals,forecast], KPIs, Actual|Forecast pivot, trend,
#    editable rate+manual tables); production keeps the strict dispositions contract
.venv/bin/python build-forecast-model.py work/plan.json --post --review-dispositions work/review.json
```

The plan records the source workbook's `sourceSha256`; `sourcePath` is saved in the
plan, or pass `--source`. Plans without a source hash must be regenerated because their
parity claims cannot be tied to the workbook being migrated. Step 3 reports pending
review issues (`DRAFT MODE: ...`, including the drafter's `FLAT_CARRY_POLICY` for
`=prior` lines) without blocking; step 4 needs every code dispositioned in
`review.json` (format in `refs/coverage-contract.md`; `migrate.py` writes
`review.template.json`). The local parity check compares the plan to the workbook's
FY totals (`--parity-tolerance`, default 0.01) and exits 1 on any mismatch.
Source binding alone does not make this builder general. If discovery finds
unknown sheets, tables, sections, periods, or dependency behavior, use
source-specific MCP construction or explicit review. Do not map the workbook
into the bundled sample profile or freeze formula caches to obtain baseline
parity; validate live behavior before claiming completion.

The forecast is computed (`base × (1+rate)^n`); editable rate/manual input tables
override via `Coalesce(input, default)`, so **parity holds before any seeding**
(verified: Revenue 6,961,218.48 · EBITDA 62,327.16 · **Net Income −135,372.84**).
Then seed `rate_seed.csv` / `manual_seed.csv` through Sigma MCP Code Mode
(`InputTable.upsert_rows()` after a preflight query), or paste them through the UI
and Publish. A live regression seeded 6 rate rows and 30 manual rows through MCP,
then changed and restored one rate and one zero-valued manual row; the P&L and
trend recalculated and returned exactly to baseline with no duplicate keys. Run
the generated layout and render; use the workbook refinement tooling only when
the explicit KPI, trend, and pivot layout needs further adjustment. See
`refs/forecast-recipes.md`.

If `.xlsm`: run `macro-classify.py` first (`refs/macro-handling.md`) — surface
FLAG/ACTION macros before building.

> Note: delete a test workbook/DM via `DELETE /v2/files/{inodeId}` (not
> `/v2/workbooks/{id}`, which 404s).

---

## Worked example C — equity-research model (broker / FactSet house template)

For a sell-side research model (line-items × YEARS, statement sections; e.g. a FactSet-style broker model). Generate the synthetic fixture, then convert it:

```bash
# fake, no-customer-data fixture (Acme Widgets NV): plug-cycle + %-literal + Lag + #REF! + MIXED
.venv/bin/python make-sample-research-model.py                       # -> scripts/Sample Research Model.xlsx

# infer the two-layer plan (hard-coded grid + ONE canonical formula per derived line)
.venv/bin/python infer-canonical-formulas.py "Sample Research Model.xlsx" \
    --sheet="FY results" --first-row=7 --last-row=45 --out plan.json \
    --review-dispositions review.json

# build DM (data page) + workbook (computation + transpose + display pivot)
.venv/bin/python build-research-model.py plan.json --conn <writeConn> --folder <id> \
    --review-dispositions review.json --post
```

The report shows `input / derived / ratio` counts, live-verified vs frozen formula
cells, and resolved anchors. A nonzero frozen count adds the review issue
`CACHED_FORMULA_FALLBACK`; preserving the cached display value does not establish
a live-formula migration. Put that code, a named owner, the implemented
disposition, and `verified: true` in the source-bound review file. The plan stores
`sourcePath` and `sourceSha256`; use `--source` only when the saved path moved.
See `refs/research-recipes.md`.

**A fleet of similar files** (the ~850-file case) → `batch-convert.py` fingerprints,
maps to the chart-of-accounts (`coa.json`), converts, parity-gates, and emits a triage
manifest (AUTO_PARITY / NEEDS_REVIEW / BLOCKED / FAILED), full audit details, and
the top unmapped labels to grow the COA:

```bash
.venv/bin/python batch-convert.py /path/to/models/ --sheet="FY results" --out manifest.json
```
Reviewed sources require `--review-dispositions review.json`, or a directory with
one `<sourceSha256>.json` per reviewed workbook. `--post-review` alone never posts
a reviewed source, and `BLOCKED` sources are never inferred or posted.
See `refs/research-template-coa.md`.
