# Sigma workbook code-representation capabilities

Re-audited against the compiled public OpenAPI in October 2026. Run
`scripts/audit-openapi.py` before relying on this matrix; it fails when the
operation-scoped contract drifts.

## Current lifecycle

| Operation | Endpoint / body |
|---|---|
| validate create | `POST /v2/workbooks` with metadata, `contents`, `dryRun: true` |
| create | `POST /v2/workbooks` with metadata and `contents` |
| read | `GET /v2/workbooks/{id}?includeContents=true` |
| update | `PUT /v2/workbooks/{id}/contents` with `contents` and optional `documentVersion` |

The older `/v2/workbooks/spec` and `/spec/verify` endpoints are deprecated.
Data-model specs remain on `/v2/dataModels/.../spec`; never wrap them in
workbook `contents`.

Create body:

```json
{
  "name": "Workbook name",
  "folderId": "folder-id",
  "contents": {
    "schemaVersion": 1,
    "kind": "workbook",
    "pages": [{"id": "page", "name": "Page"}],
    "elements": [],
    "layout": "<Page id=\"page\">...</Page>"
  }
}
```

A successful dry run returns HTTP 200 with `dryRun: true` and `warnings`; it
does not promise `valid: true`. Failure is HTTP 400 with `valid: false`,
`errors`, and `warnings`.

## Authorable primitives

- Tables, pivots, KPI/bar/line/area/pie/donut/scatter/combo/waterfall/Sankey/
  treemap/funnel/gauge/box charts and maps.
- Controls including list, date/range, number/range, slider, hierarchy, file,
  segmented, drill, legend, and synced controls.
- Input tables with `edit`, `explore`, or `view` write modes.
- Input validation via literal `values`, `valuesFrom`, inclusive `range`, and
  file count/size/type constraints.
- Element actions for API calls, stored procedures, input-table insert/update/
  delete, Python execution, navigation, exports, controls, refresh, plugins,
  and conditional effects.
- Python `kind: code` elements and table sources with `kind: code-output`.
- Document automated actions with scheduled or webhook triggers. Their current
  effect surface is narrower than element actions; do not assume every element
  effect is legal in an automated action.

Schema authorability is not runtime proof. Connector auth, stored-procedure
signatures, Python packages, write permissions, action side effects, and linked
input-table behavior still require live tests.

## Input-table cautions

Data-entry column types are `text`, `number`, `datetime`, `checkbox`,
`multi-select`, and `file`. `values` and `valuesFrom` are mutually exclusive;
`valuesFrom` is incompatible with `range`.

The code schema accepts linked input tables, but previous live tests found
inherited columns rendering “multiple values.” Continue to treat linked mode as
review/UI-only until a create/read/query regression proves otherwise.
