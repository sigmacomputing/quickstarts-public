# Data Model Spec Reference

## Endpoint

```
POST /v2/dataModels/spec
```

**Not** `/v2/workbooks/spec`. These create completely different object types.

## Top-level shape

```json
{
  "name": "My Data Model",
  "folderId": "<folder-id>",
  "schemaVersion": 1,
  "pages": [
    {
      "id": "page-1",
      "name": "Page 1",
      "elements": [ ... ]
    }
  ]
}
```

## Element shape (warehouse-table)

```json
{
  "id": "orders-el",
  "kind": "table",
  "name": "Orders",
  "source": {
    "connectionId": "<connection-id>",
    "kind": "warehouse-table",
    "path": ["SCHEMA", "CATALOG", "TABLE_NAME"]
  },
  "columns": [
    {"id": "col-sales", "name": "Sales", "formula": "[TABLE_NAME/SALES]"}
  ],
  "order": ["col-sales"],
  "metrics": [
    {"id": "met-sales", "formula": "Sum([Sales])", "name": "Total Sales",
     "format": {"kind": "number", "formatString": "$,.2f", "currencySymbol": "$"}}
  ],
  "relationships": [ ... ]
}
```

### Column formula prefix rule

The prefix in a column formula is the **last segment of the `path` array**, exactly as written:
- `path: ["CSA", "Tableau Test", "ORDERS"]` → prefix is `ORDERS`
- Formula: `"[ORDERS/SALES]"`

## Element shape (Custom SQL)

Use a Custom SQL element whenever the source data is a SQL query — including any Tableau workbook that uses Custom SQL **and** any DM that needs window aggregates (`SUM() OVER`, `RANK()`, `RUNNING_SUM`, etc.) which Sigma's calc-column functions cannot express.

```json
{
  "id": "el-orders-sql",
  "kind": "table",
  "name": "Orders SQL",
  "source": {
    "connectionId": "<connection-id>",
    "kind": "sql",
    "statement": "SELECT o.ORDER_ID, o.REGION, o.SALES,\n  SUM(o.SALES) OVER (PARTITION BY o.REGION) AS REGION_TOTAL_SALES,\n  RANK() OVER (PARTITION BY o.REGION ORDER BY o.SALES DESC) AS SALES_RANK_IN_REGION\nFROM ANALYTICS.PUBLIC.ORDERS o\nLEFT JOIN ANALYTICS.PUBLIC.CUSTOMERS c ON o.CUSTOMER_ID = c.CUSTOMER_ID"
  },
  "columns": [
    {"id": "c-order-id",      "name": "Order Id",             "formula": "[Custom SQL/ORDER_ID]"},
    {"id": "c-region",        "name": "Region",               "formula": "[Custom SQL/REGION]"},
    {"id": "c-sales",         "name": "Sales",                "formula": "[Custom SQL/SALES]"},
    {"id": "c-region-total",  "name": "Region Total Sales",   "formula": "[Custom SQL/REGION_TOTAL_SALES]"},
    {"id": "c-sales-rank",    "name": "Sales Rank in Region", "formula": "[Custom SQL/SALES_RANK_IN_REGION]"}
  ],
  "order": ["c-order-id","c-region","c-sales","c-region-total","c-sales-rank"]
}
```

### Custom SQL element rules

1. `source.kind` is `"sql"`. `path` is absent.
2. `source.statement` is the raw SQL text in the warehouse's native dialect (Snowflake, BigQuery, etc.). Newlines in the JSON string are fine; the API parses them. **The field name is `statement`, not `sql`** — POSTing with `"sql": "…"` returns `"source.statement: Invalid string: undefined"` even though `kind: "sql"` is correct.
3. **Column formula prefix is the literal string `Custom SQL`** — not the table name, not a path segment, not the element's `name`. Every column on the element uses `"[Custom SQL/<SELECT_ALIAS>]"`.
4. `<SELECT_ALIAS>` is whatever you wrote as the column alias in the SELECT (`SELECT x AS NAME`). **Use UPPERCASE aliases** — Snowflake's default identifier casing is uppercase, and Sigma's column lookup is case-sensitive against the SQL result set. `[Custom SQL/region_total_sales]` will fail if the SELECT wrote `AS REGION_TOTAL_SALES`.
5. Every column you want to expose in the DM needs both a SELECT-list entry AND a `columns[]` entry with the matching prefix.
6. Metrics work the same as on a warehouse-table element: bare refs to sibling column names (`Sum([Sales])`).
7. Relationships work the same — point at another element by `targetElementId` and match column IDs.

### When to use a Custom SQL element vs a warehouse-table element

Use a Custom SQL element when:
- The Tableau source workbook uses Custom SQL (detected by `extract-custom-sql.rb` in Phase 1f).
- The DM needs **window aggregates** (`SUM() OVER`, `RANK()`, `ROW_NUMBER()`, `LAG/LEAD`, etc.). Sigma's calc-column window functions (`SumOver`, `RankOver`, `CumulativeSum`, etc.) silently produce `error` type columns and the chart that references them renders blank. The validator hard-fails on these — see `scripts/validate-spec.rb`.
- The DM needs **LOD-equivalent pre-aggregation**. Tableau `{FIXED [Dim] : SUM([X])}` becomes `SUM(X) OVER (PARTITION BY Dim)` in the Custom SQL or a pre-aggregated subquery joined back.
- The customer's data model is already SQL-shaped in Tableau (CTEs, joins, derived columns) and breaking it apart into raw warehouse tables would lose semantics.

Use a `warehouse-table` element when the source is a single physical table and all derived columns can be expressed as Sigma calc columns (scalar `If`/`Case`/`Lookup`/etc. — no window aggregates).

You can mix both kinds of elements in the same DM. A common pattern: warehouse-table elements for the dimension tables (Customer Dim, Product Dim, Date Dim), Custom SQL element for the fact table when it needs window aggregates.

### Tableau Custom SQL → Sigma SQL — common rewrites

| Tableau | Sigma SQL (inside `source.statement`) |
|---|---|
| `RUNNING_SUM(SUM([X]))` | `SUM(X) OVER (ORDER BY <time> ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` |
| `WINDOW_SUM(SUM([X]))` | `SUM(X) OVER (<partition / order>)` |
| `RANK(SUM([X]))` | `RANK() OVER (PARTITION BY <p> ORDER BY <X> DESC)` |
| `RANK_DENSE(SUM([X]))` | `DENSE_RANK() OVER (...)` |
| `INDEX()` | `ROW_NUMBER() OVER (PARTITION BY <p> ORDER BY <expr>)` |
| `LOOKUP(SUM([X]), -1)` | `LAG(X) OVER (ORDER BY <time>)` |
| `LOOKUP(SUM([X]), +1)` | `LEAD(X) OVER (ORDER BY <time>)` |
| `{FIXED [Dim] : SUM([X])}` | `SUM(X) OVER (PARTITION BY Dim)` — or pre-aggregated subquery joined back |
| `{INCLUDE [Dim] : SUM([X])}` | Subquery pre-aggregated at view-grain + Dim, joined to the view |
| `{EXCLUDE [Dim] : SUM([X])}` | `SUM(X) OVER (PARTITION BY <view-dims-minus-excluded>)` |
| `TOTAL(SUM([X]))` | `SUM(X) OVER (PARTITION BY <view-dims>)` |
| `SIZE()` | `COUNT(*) OVER (PARTITION BY <p>)` |

### Metric formula rule

Metrics reference column `name` values (not IDs) without a table prefix:
- `"Sum([Sales])"` — references the column named "Sales" in the same element
- Never `"Sum([ORDERS/Sales])"` inside a metric

## Relationships

Relationships belong on the **source** element, not the target. They link a source column to a target column on another element.

```json
"relationships": [
  {
    "id": "rel-orders-people",
    "targetElementId": "<target-element-id>",
    "keys": [
      {
        "sourceColumnId": "<source-col-id>",
        "targetColumnId": "<target-col-id>"
      }
    ],
    "name": "Orders to People"
  }
]
```

- `targetElementId` — the `id` of the element being joined to
- `sourceColumnId` / `targetColumnId` — the `id` values of the specific join key columns
- Multiple keys supported for composite joins
- One relationship per join pair; n-way joins use multiple relationship entries

## Denormalizing dim columns onto a fact element — use `Lookup()`, not bare refs

Relationships enable query-time joins, but they do **not** auto-resolve cross-element references inside calc-column formulas. A formula like `[Customer Dim/Region]` on an `Order Fact` calc column compiles cleanly, GET round-trips it, and `describe` reports the column type as `text` — but every row returns `NULL`. There is no error.

To pull a dim column onto a fact element, use `Lookup()`:

```json
{
  "id": "of-region",
  "name": "Region",
  "formula": "Lookup([Customer Dim/Region], [Customer Key], [Customer Dim/Customer Key])"
}
```

`Lookup(<value-from-other-element>, <local-key>, <other-element-key>)`. The local key column (`[Customer Key]`) must already exist on the fact element. The other-element columns are referenced with the standard `[Element Name/Column Name]` prefix.

Use this pattern whenever the workbook needs to slice the fact by a dim attribute (Region, Category, Tier, etc.) — denormalize once on the data-model element so the workbook master table sees a flat row.

**Null-tolerance for Tableau-style ELSE catches:** Tableau's `IF x >= 5000 THEN "Platinum" … ELSE "Bronze"` collapses NULL `x` into the ELSE branch (`NULL >= 5000` is NULL → falls through). Sigma's `If(NULL >= ..., ...)` returns NULL, not the false-arm — so orphan-joined rows where the lookup returns NULL produce a NULL bucket instead of joining the default category. To match Tableau, wrap the lookup: `Coalesce(Lookup([Customer Dim/Customer Value Tier], ...), "Bronze")`. Equivalent fix: `If(Coalesce([Lifetime Revenue], -1) >= 5000, ...)` if computing the bucket directly from the looked-up base column.

> **Apply the Coalesce wrap at the workbook master, not the DM, when possible.** Editing the DM after the workbook is built reassigns all element IDs and breaks the workbook's `source.elementId`. Wrapping the column on the master table (`Coalesce([Order Fact/Customer Value Tier], "Bronze")`) gets the same null-collapse result with one workbook PUT and no DM churn. Use the DM-level wrap only when the DM is being built fresh OR when multiple workbooks need the fix and you'd rather centralize. Validated 2026-05-18 on Orders Conversion Test (REST v2): workbook-master-level Coalesce took chart from `DIVERGE [null tier 0.66]` to strict-mode PASS without touching the DM.

## Format objects

```json
{"kind": "number", "formatString": "$,.2f", "currencySymbol": "$"}   // currency
{"kind": "number", "formatString": ",.0f"}                           // integer
{"kind": "number", "formatString": ",.2%"}                           // percent
```

## Response

The POST response is **YAML** and contains only `success` and `dataModelId` — **no element IDs**.

```bash
ruby -r yaml -r date -e \
  "d=YAML.safe_load(File.read('/tmp/dm-response.yaml'),permitted_classes:[Date,Time]); \
   puts 'dataModelId: ' + d['dataModelId'].to_s"
```

Record the `dataModelId`, then **immediately GET the spec** to retrieve server-assigned element IDs:

```bash
curl -s -H "Authorization: Bearer $SIGMA_API_TOKEN" \
  "$SIGMA_BASE_URL/v2/dataModels/<dataModelId>/spec" \
  -o /tmp/dm-get.yaml

ruby -r yaml -r date - <<'EOF'
require 'date'
d = YAML.safe_load(File.read('/tmp/dm-get.yaml'), permitted_classes: [Date, Time])
puts "dataModelId: #{d['dataModelId']}"
d['pages'].each do |pg|
  puts "page: #{pg['id']} #{pg['name']}"
  (pg['elements'] || []).each { |e| puts "  elementId: #{e['id']}  name: #{e['name']}" }
end
EOF
```

## Workbook source reference to a data model element

```json
{
  "kind": "data-model",
  "dataModelId": "<dataModelId>",
  "elementId": "<server-assigned-element-id>"
}
```

The `elementId` here is the element ID from the data model response, **not** the ID you assigned in the spec.

## Validation checklist before POSTing

1. No column `name` contains `/`
2. Column formula prefix matches last segment of `path`, exact case
3. Metric formulas use bare column refs (no table prefix)
4. Relationship `targetElementId` matches an element `id` defined in the same spec
5. Relationship key column IDs match column `id` values in their respective elements
6. `order` array contains exactly the column IDs defined in `columns`
