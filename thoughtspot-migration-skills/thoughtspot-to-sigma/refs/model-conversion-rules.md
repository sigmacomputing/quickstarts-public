# ThoughtSpot model TML → Sigma data model — conversion rules

What `convert_thoughtspot_to_sigma` (MCP tool / `CONVERTER_PATH` build) does with a
model TML, and the conventions every downstream script relies on.

## Input shape (the `model:` format)

ThoughtSpot exports models with:

- `model_tables[]` — one entry per physical table; the **fact (root) table is the
  one carrying `joins[]`** (joins are inline, not a separate section):
  ```yaml
  model_tables:
  - name: ORDER_FACT
    fqn: 7ccc4d3c-...            # a ThoughtSpot guid, NOT the warehouse FQN
    joins:
    - with: CUSTOMER_DIM
      'on': '[ORDER_FACT::CUSTOMER_KEY] = [CUSTOMER_DIM::CUSTOMER_KEY]'
      type: LEFT_OUTER
      cardinality: MANY_TO_ONE
  ```
- `formulas[]` — `[TABLE::COL]` refs, TS functions (`safe_divide`, `if … then … else`,
  `count`, `in { … }`).
- `columns[]` — `column_id: TABLE::PHYSICAL_COL` (physical) or `formula_id:` (formula),
  with `properties.column_type` (`ATTRIBUTE`/`MEASURE`), `aggregation`,
  `format_pattern`, `currency_type`.

Older worksheets use `worksheet:` + `worksheet_columns[]` with `ALIAS::column`
separators and `table_paths` — the converter handles both.

## Warehouse path: TS_DB / TS_SCHEMA are REQUIRED

`model_tables[].fqn` is a ThoughtSpot guid, so the warehouse `database`/`schema`
cannot be recovered from the TML. Pass `TS_DB` + `TS_SCHEMA` (converter args
`database`/`schema`); the source path becomes `[TS_DB, TS_SCHEMA, <table name>]`.

## Output conventions (what the scripts depend on)

- **One element per table** plus a denormalized **"`<root>` View"** element that
  surfaces joined-dim columns via cross-element refs `[<fact element>/REL/Field]`.
  The workbook master reads from this View element. When the model has no joins
  there is no View — fall back to the element with the most columns
  (`migrate.py::build_dm`).
- **Display names**: `SNAKE_CASE`/`camelCase` → Title Case with small connector
  words (`of`, `to`, `and`, …) kept lowercase (`ts_common.sigma_display_name`
  replicates this). On the View element, joined-dim columns get a
  **`(TABLE)` suffix** (`Category (PRODUCT_DIM)`); fact columns don't.
  `ts_common.build_resolver` derives the TS-name → View-name map from the model
  TML itself — never hardcode it.
- **Relationship keys**: the denormalized View must NOT re-surface the join key
  column of the relationship itself — a cross-element passthrough of a join key
  compiles to a `type: error` column in Sigma.
- **Formulas** on the fact element keep their TS name; aggregate formulas
  (`sum(x)/sum(y)`, `sqrt(sum(...))`) become DM **metrics**, not columns.
- **Formats**: `format_pattern` (Java DecimalFormat, e.g. `#,##0.00`, `0.0%`) +
  `currency_type.iso_code` map to Sigma `format` objects
  (`ts_common.ts_format_to_sigma`). The pattern never carries a currency symbol —
  only emit one when `currency_type` is set.

## Converter invocation

MCP tool `mcp__sigma-data-model__convert_thoughtspot_to_sigma`:
`{tml_yaml, connection_id, database, schema}` (empty string = omit). Returns
`{sigmaDataModel, stats, warnings}` (the local `CONVERTER_PATH` build returns the
same spec under `model`) — the spec POSTs to `/v2/dataModels/spec` (add
`folderId`). `migrate.py` emits this exact request to
`<workdir>/convert-request.json` when no local build is configured, and resumes
from the tool's saved output via `--converted <file>`.

## Gotchas

- TML export embeds raw control chars in JSON strings → `json.loads(..., strict=False)`.
- The TS trial REST API rejects short id prefixes — use full guids.
- System/sample objects are FORBIDDEN to export (only own content).
- Security: `rls_rules` are detected and reported in `result.security[]`, never
  injected into the spec — see SKILL.md "Row- & Column-Level Security".
