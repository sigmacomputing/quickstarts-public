---
name: hex-to-sigma
description: Convert a Hex project (SQL cells, single-value/METRIC cells, EXPLORE charts, app layout) into a Sigma data model and matching workbook. Discovery via a Hex project export file (Hex's REST API does not expose cell content), calc translation, DM + workbook creation via REST, layout, and warehouse parity verification.
user-invocable: true
---

# Hex → Sigma

> **Status: live-validated through Phase 6 (2026-07-30).** DM POST + readback,
> workbook POST + readback, layout lint, the deeper compiled-SQL check
> (`sigma-workbooks/scripts/verify-workbook.sh`), a visual PNG export, AND
> numeric parity all passed clean against Phil's real Sigma org — 8/8 DM
> columns, 10/10 workbook columns, 6/6 elements, zero `type=error`, zero
> unresolved/circular formula refs, KPI values confirmed exact
> (`$39,759,625.52` / `91,206`), and the visual layout matches the original
> Hex app (verified via PNG export, not just Phil eyeballing the live UI).
> `corpus/hex/commerce/` covers the structural regression test (no live org
> needed to re-run it).

> Phase numbering is local to this skill; the canonical Assess→Discover→
> Reuse→Convert→Post-DM→Build→Layout→Parity→Security→Enhance arc and this
> skill's mapping live in
> [`docs/phase-schema.md`](../../../../docs/phase-schema.md).

> Read `refs/hex-file-schema.json` (the vendored public JSON Schema for
> Hex's `.hex.yaml` format) before relying on a cell shape not covered
> below — it's the actual source of truth, not this document.

---

## Why discovery is different here

Hex's public REST API (`learn.hex.tech/docs/api/api-overview`) covers
projects/runs/users/collections/data-connections — **it does not return
cell content** (no SQL text, no chart config). There is no endpoint
equivalent to Metabase's `GET /api/card/{id}` or Cognos's data-module JSON.

The actual source of truth for a project's full logic is Hex's **`.hex.yaml`
project export** — a full-fidelity file (every cell + the app layout),
obtained via a one-click manual `Export` from the project dropdown (any
plan, no credentials) or continuous **Git Sync** (Team/Enterprise — same
format, synced to a repo instead of a one-off download). There's a public,
versioned JSON Schema for it at `https://static.hex.site/hex-file-schema.json`
(registered on SchemaStore), vendored locally at `refs/hex-file-schema.json`.

**Practical effect**: no Hex API credentials are needed to run this skill.
The user exports their target project and hands you the file path.

## Prerequisites

- **A `.hex.yaml` export** of the target Hex project (`Export` from the
  project's dropdown menu in Hex).
- **Sigma** API token (via `~/.sigma-migration/env` / `scripts/get-token.sh`
  or `scripts/get_token.py`) to POST the data model + workbook.
- **The same warehouse on both sides.** Sigma reads the warehouse live;
  parity only means something when the Sigma connection reaches the
  database the Hex project's SQL cells query.
- **`Python 3.10+` with PyYAML** (`pip install pyyaml`) for the converter —
  same dependency `looker-to-sigma` and `microstrategy-to-sigma` already
  carry for their own YAML-parsing scripts. `Ruby` (any recent) for
  `post-and-readback.rb` and the vendored shared gates.

**Auth gotcha (found 2026-07-30, unresolved — flag before assuming
`get_token.py`/`get-token.sh` just work):** this family's shared auth
scripts (`sigma_rest.rb`/`.py`, `get_token.py`, `get-token.sh`) exchange
client credentials via an HTTP **Basic Auth header**. Against a freshly
created API client in Phil's org, that got a `400 {"code":"invalid_request",
"message":"Invalid access/refresh token"}` on every attempt (three separate
fresh key pairs, all formatted correctly — 64/128-char id/secret, no
whitespace/encoding issues). Sigma's own official Postman guide
(`quickstarts.sigmacomputing.com/guide/sigma_api_with_postman`) documents
`client_id`/`client_secret` as **body form params** with **No Auth**
instead — switching to that shape got `200` immediately with the exact same
credentials. Not yet determined whether this is org-specific or affects the
whole family; **not fixed in the canonical shared scripts** (that's a
cross-cutting decision beyond this skill — see corpus MANIFEST for the raw
finding). If `get_token.py --print-token` 400s with that exact message,
this is almost certainly why — mint by hand with body-form params as a
workaround rather than assuming the credentials themselves are bad.

## Phase 0 — Assess (C1)

Defer full-estate scanning to the `hex-assessment` skill (scoped stub — see
its own `SKILL.md`). For a single-project conversion, skip straight to
Phase 1.

## Phase 1 — Discover (C2)

```bash
cd converter
python3 -c "import hex_yaml, json; d = hex_yaml.load_project('<project>.hex.yaml'); \
  cells, warnings = hex_yaml.parse_cells(d); \
  print(f'{len(cells)} convertible cells, {len(warnings)} skipped'); \
  [print('WARN:', w) for w in warnings]"
```

`hex_yaml.py` parses the export and reports every cell it can't convert
(never silently drops one). Confirmed cell types (from a real export):
`SQL`, `METRIC` (single-value/KPI), `EXPLORE` (chart). Everything else —
`CODE` (Python), `INPUT`, `MARKDOWN`, `TABLE_DISPLAY`, `TEXT`, `MAP`,
`WRITEBACK`, `PIVOT`, `FILTER`, `DBT_METRIC`, `COMPONENT_IMPORT`, `BLOCK`,
`COLLAPSIBLE` — is flagged as a warning, not converted. Python cells in
particular need hand review: their transform logic has no automatic Sigma
translation.

`hex_yaml.data_connection_ids(doc)` lists every Hex data-connection uuid
referenced — Hex only carries the uuid (the human-readable connection name
is a YAML *comment*, unparseable). Get the target `SIGMA_CONNECTION_ID`
from the user directly, same as every sibling skill's kickoff prompt.

## Phase 1.5 — Reuse-check (C3)

Before creating a DM, score existing Sigma DMs and reuse on a strong match
(avoid sprawl). Mirrors tableau Phase 1.5:
`ruby scripts/find-or-pick-dm.rb --workbook-signature <sig.json>`.

## Phase 2 — Convert (C4)

Two scripts, matching this repo's flat-script convention (`sisense-to-sigma`,
`gooddata-to-sigma`) rather than a single unified CLI:

```bash
python3 converter/convert_dm.py <project>.hex.yaml \
  --connection <SIGMA_CONNECTION_ID> > dm.json
```

Every Hex `SQL` cell is raw SQL with no query DSL (unlike Metabase's MBQL),
so it always takes the "native SQL element" path — wrap the cell's `source`
verbatim into `{kind:'table', source:{kind:'sql', statement}}`, same shape
metabase-to-sigma uses for ITS native-SQL fallback (there's no Metabase-style
"auto-remodel a simple SELECT into a structured model" path here — nothing
to remodel into). Column discovery uses the SQL cell's own
`tableDisplayConfig.columnProperties[]` (Hex's stand-in for a
`result_metadata` list — the export never states a SQL cell's output schema
any other way). Hex's column aliases are already human-authored display
names (`"Visit ID"`, `"Category"`, ...), so — unlike Metabase's
machine-generated aliases — they're used **verbatim**, not reprocessed
through a display-name deriver.

```bash
python3 converter/convert_workbook.py <project>.hex.yaml \
  --dm-id <dataModelId> --dm-element-id <element id> \
  --columns-map <columns_by_variable from dm.json> > wb.json
```

- `METRIC` cells → `kpi-chart` elements (`value:{columnId}`), Hex's own
  `displayFormat` → a Sigma number/currency format.
- `EXPLORE` cells → `bar-chart` / `line-chart` / `area-chart` /
  `scatter-chart` / `pie-chart`, keyed off the cell's series `type`.
  Channel → Sigma shape: `base-axis`→`xAxis`, `cross-axis`→`yAxis`
  (cartesian) or `value` (pie), `color`→`color` (pie). `tooltip` fields and
  Hex's synthetic `_HEX_COUNT_STAR_ARG_` token are not carried over in v1.
- **Hex's `lump` (Top-N) is NOT a flagged gap** — Sigma has a native
  `filters: [{kind: top-n, ...}]` chart filter
  (`sigma-workbooks/reference/specification/charts.md`) that maps onto it
  directly. This was corrected during design after initially assuming (like
  most source-tool constructs with no obvious Sigma analog) it would need
  flagging — check the target skill's own reference docs before assuming
  something is unsupported.
- Multi-series/combo `EXPLORE` cells and any series `type` outside
  bar/line/area/scatter/pie (e.g. `histogram`) are skipped with a loud
  warning — never faked.

**Formula prefix — confirmed, not just assumed (live-verified 2026-07-30):**
column formulas are qualified `[Custom SQL/<column>]`, matching
metabase-to-sigma's finding that "Sigma does NOT honor sql-element names
(all read back 'Custom SQL')" for SQL-sourced elements. This applies even to
the DM element's OWN columns referencing their OWN SQL source — a bare
`[<column>]` self-reference was tried first and compiles to a **`Ref Cycle`**
error (a column named `Brand` with formula `[Brand]` is looking itself up by
name; confirmed via `GET /v2/dataModels/{id}/columns`). `Custom SQL/` is
Sigma's fixed sentinel for "this element's own raw SQL output," not a
cross-element name — don't read `sigma-workbooks`' "bare `[col]` = same
element's own columns" rule as applying to a sql-source element's own
output columns.

**Stale-column guard (live-verified 2026-07-30):** Hex's cached
`tableDisplayConfig.columnProperties[]` can list a column that isn't
actually in the SQL cell's `SELECT` output — e.g. a join key referenced only
in a `JOIN ... ON` clause, left over in the cache from an earlier query
edit. Posting a DM column for it 400s ("dependency not found"). `convert_dm.py`
now cross-checks `columnProperties` against the SELECT clause's quoted
identifiers (everything before the first top-level `FROM`) and drops
anything not genuinely selected, with a loud warning — see
`_select_clause_output_names()`.

**Both DM and workbook specs require `schemaVersion` and `folderId`**
(`convert_dm.py --folder <id>`, `convert_workbook.py --folder <id>`) — POST
400s with `"schemaVersion: Invalid 1: undefined"` without it. `1` is
accepted for a fresh CREATE; the `sigma-workbooks` docs warn against
hardcoding it for an UPDATE (re-fetch from the existing spec instead).

**`layout` is a TOP-LEVEL spec field, not a page field** (live-verified
2026-07-30): nesting it under `pages[].layout` (what the `sigma-workbooks`
docs' phrasing "`layout` is a page-level property" reads as, at first
glance) is silently ignored — no error, Sigma just falls back to its own
auto-arrange (a single stacked column, every element full-width). The XML
string itself still wraps each page's elements in a `<Page id="...">` tag;
it's the JSON *placement* of that string that must be `spec.layout`, a
sibling of `pages`, not `spec.pages[N].layout`.

**Chart axes need an explicit `sort`, or Sigma defaults to alphabetical**
(live-verified 2026-07-30): without `xAxis.sort` (cartesian) or
`color.sort` (pie), a "Top 10 by revenue" chart rendered its dimension
alphabetically (Australia, Canada, France, ... — missing the actual largest
country, United States, entirely from the visible rows) instead of sorted
by the measure. `convert_workbook.py`'s `_axis_sort()` maps Hex's
`sort.mode` (`cross-axis-descending` → sort by the paired measure;
`value-ascending` → sort by the axis field's own value, e.g. a
chronological Year axis) to Sigma's `{by: <colId>, direction: ascending|
descending}`. The underlying Top-N SQL (`rank() over (...) qualify rank <=
10`) was correct the whole time — this was purely a display-order bug, not
a data bug, but it looked exactly like one at first (missing categories) until
the compiled SQL was inspected directly.

## Phase 3 — Post the data model + read back (C5) ← HARD GATE

```bash
eval "$(python3 scripts/get_token.py --print-export)"
ruby scripts/post-and-readback.rb --type datamodel --spec dm.json --out dm-map.json
```

POSTs to `/v2/dataModels/spec`, reads it back, and **fails on any
`type=error` column** — a spec can POST 200 yet have formulas that don't
resolve at query time. `dm-map.json` carries the real `dataModelId` +
element/column ids (Sigma reassigns them on POST) — re-run
`convert_workbook.py` with those, not the client-side ids from Phase 2.

## Phase 4 — Build the workbook (C6)

```bash
ruby scripts/post-and-readback.rb --type workbook --spec wb.json --out wb-map.json
```

Each `METRIC`/`EXPLORE` cell became the matching Sigma element in Phase 2,
already wired to the DM. This POST also runs the layout lint (below) inline.

## Phase 5 — Layout (C7)

Unlike Metabase (whose Phase 5 needs a separate post-creation `apply-layout`
pass because dashcard hints must be remapped to server-assigned element
ids), **Hex's full `appLayout` is known upfront and baked directly into the
workbook spec `convert_workbook.py` emits** — no separate `put-layout.rb`
step for this skill. `appLayout.tabs[].rows[].columns[].{start,end}` is on a
**0–120 scale** (confirmed from a real export — not Metabase's 24-col grid);
`build_layout_xml()` maps it proportionally onto Sigma's 24-column
`<Page>`/`<LayoutElement>` grammar. This is a first-pass proportional
mapping — verify against a readback + PNG export
(`scripts/sigma-export-png.py`, `refs/layout-visual-qa.md`) before treating
it as final, same as every sibling skill's layout gate.

## Phase 6 — Verify parity (C8) ← HARD GATE, never skip

Compare Hex values vs Sigma vs the shared warehouse. Since both sides read
the same tables, re-run the SQL cell's query directly against the warehouse
and diff against each Sigma element's value — same pattern as the rest of
the family (not via Hex's Runs API, which only triggers/monitors published
app refreshes, not something this skill needs).

**Before the numeric check**, run the deeper compiled-SQL verify (catches
what the readback's `type=error` guard can miss — Sigma accepts some bad
specs at POST and only surfaces the failure as a string literal baked into
the compiled query, e.g. `select 'Unknown column "[X]"' ...`):

```bash
bash ../sigma-authoring/skills/sigma-workbooks/scripts/verify-workbook.sh <workbookId>
```

Then the numeric gate:

```bash
ruby scripts/assert-phase6-ran.rb --workdir <workdir> --workbook-id <id>
```

## Security: RLS / CLS (C9)

Not yet implemented. Hex's own permission model (workspace roles, project
sharing) is app/workspace-level, not the row/column-level security the
family's `apply_sigma_rls.py` engine targets — confirm whether a given
customer's Hex estate uses row-level patterns (e.g. per-user filtered SQL
cells) before assuming there's nothing to port.

## Gaps

Unsupported source features → `python3 scripts/escalate-gap.py` (opt-in
issue filer). Never fake a feature; flag it. Known gaps as of this skill's
first pass: Python (`CODE`) cells, multi-series/combo `EXPLORE` charts,
`histogram` series, `INPUT`/`FILTER`/`WRITEBACK`/`PIVOT`/`DBT_METRIC`/
`COMPONENT_IMPORT`/`BLOCK`/`COLLAPSIBLE` cell types, Git-Sync-based
discovery (v1 is single manual-export only).
