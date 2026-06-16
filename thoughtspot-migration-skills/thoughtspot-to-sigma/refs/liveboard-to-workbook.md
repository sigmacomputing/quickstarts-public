# ThoughtSpot Liveboard → Sigma workbook — spec shapes

The exact Sigma workbook-spec shapes the builder (`ts_common.py` /
`migrate.py`) emits, all live-verified (POST → readback). Get these wrong and
Sigma either 400s at POST or **silently degrades** (pivot collapses to one
cell, KPI fails validation only at POST, sorts dropped).

## Chart-kind map

| ThoughtSpot | Sigma | Notes |
|---|---|---|
| KPI | `kpi-chart` | value is `{"columnId": c}` — NOT `{"id": c}` |
| COLUMN / BAR / STACKED_* | `bar-chart` | `orientation` enum is `"horizontal"`-only; omit for vertical |
| LINE | `line-chart` | |
| PIE / DONUT | `donut-chart` | TS renders pies as donuts; `value`/`color` use `{"id": c}` — NOT `{"columnId": c}` |
| AREA / STACKED_AREA | `area-chart` | |
| SCATTER / BUBBLE | `scatter-chart` | two measures x/y + optional category `color` |
| LINE_COLUMN | `combo-chart` | first measure bare string in `yAxis.columnIds`, rest `{"columnId", "type": "line"}` |
| GEO_AREA / GEO_BUBBLE | `region-map` | `region: {id, regionType}`; regionType inferred from the geo field name |
| PIVOT_TABLE | `pivot-table` | see below |
| TABLE / ADVANCED_COLUMN | grouped `table` | see below |
| funnel / waterfall / treemap / heat-map / sankey | `bar-chart` fallback | flagged in the assessment |

## The asymmetric column-ref shapes (the #1 trap)

- **KPI**: `"value": {"columnId": cid}` (kpis.md docs are stale; `{id}` fails at POST,
  validate-spec misses it).
- **Donut/pie**: `"value": {"id": vid}, "color": {"id": cid}` (the opposite convention).
- **Pivot**: `rowsBy`/`columnsBy` are arrays of **`{id}` objects**, `values` is an
  array of **bare column-id strings**. Omitting rowsBy/columnsBy silently collapses
  the pivot to a single grand-total cell.
- **Grouped table**: `"groupings": [{"id", "groupBy": [dimId], "calculations": [measureIds]}]`.

## Column ORDER (tables)

Use the answer's **`table.ordered_column_ids`** for column order — `answer_columns`
is alphabetical and `chart.chart_columns` follows the chart axes, both of which
scramble multi-measure tables. (`ts_common.parse_ts_viz` reorders by
`ordered_column_ids`; the converter's chart_columns order is wrong for tables.)

## Sorts

TML sorts come from `sort by [Col] desc/asc` tokens in `search_query` and
`sortInfo` entries in `client_state(_v2)` (`ts_common.parse_sorts`). Verified
Sigma shapes (same as looker-to-sigma, live POST + readback + render):

- bar/line/area/scatter/combo: `xAxis.sort = {by: <colId>, direction}`
- pie/donut: `color.sort = {by: <colId>, direction}`
- ungrouped table: element-level `sort = [{columnId, direction}]`
- grouped table: `groupings[0].sort = [{columnId, direction}]` — element-level
  sort on a grouped table 400s with "Sort column not found".

## Master-element pattern

Each workbook gets a "Data" page with one master `table` sourced from the DM's
denormalized View (`source: {dataModelId, elementId, kind: "data-model"}`);
every chart sources `{elementId: <master id>, kind: "table"}` and references
columns as `[<master name>/<friendly>]`. Never put an element filter / top-N cap
on the master — it propagates into every chart that sources it.

## Layout: TML tiles → Sigma grid

`liveboard.layout.tiles[]` carries `{visualization_id, x, y, width, height}` on a
**12-column** grid. Sigma layout is XML on a **24-column** grid:

- columns: ×2 → `gridColumn="{x*2+1} / {(x+width)*2+1}"`
- rows: ×`ROW_SCALE` (min **2**) → `gridRow="{y*RS+1} / {(y+height)*RS+1}"`.
  1:1 rows make bands too short: Sigma suppresses axis category labels and hides
  KPI titles below ~5 grid rows (~150px) — same fix as looker's `ROW_SCALE=2`.

Apply layout as the **LAST** write — a bare spec PUT wipes `spec.layout`
(strip `workbookId/url/ownerId/created*/updated*/latestDocumentVersion` before
the PUT; see `apply_layouts.py`).

## Rename gotcha

`PATCH /v2/workbooks/{id}` **silently no-ops for renames** (200, name unchanged).
Rename through the files API instead:

```
PATCH /v2/files/{workbookId}   {"name": "New Name"}
```

(Workbook delete is also files-side: `DELETE /v2/files/{id}`; and unarchive is
`{"restore": true}`.)

## Misc verified gotchas

- Workbook POST/spec GET respond in **YAML** even with `Accept: application/json`
  — parse both.
- Show value labels on bar/donut via `dataLabel: {labels: "shown"}` (defaults OFF).
- Search-query filters `[Col] = 'val'` → element list-filters
  `{kind: "list", mode: include|exclude, columnId, values}`; TS lowercases string
  literals in the query (best-effort Title Case for case-sensitive warehouses).
- Sigma has no `IsIn` — silently errors the column and blanks the chart; use `or` chains.
- `CountOver`/`SumOver` window functions silently error in master/DM calc columns.
