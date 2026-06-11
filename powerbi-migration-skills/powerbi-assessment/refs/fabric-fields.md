# Fabric / Power BI API field cheat-sheet

The PBI-side analog of `tableau-assessment/refs/admin-insights-fields.md`.
Field names and endpoint quirks that silently bite. Verified 2026-05-31 against
the `sigmacomputing.com` tenant (Fabric trial).

## Two audiences, two tokens

Power BI surfaces split across two API audiences. The well-known PowerBI Desktop
public client (`ea0616ba-638b-4df5-95b9-636659ae5121`) can mint a token for
either via two scope requests against the **same** device-code session / cache:

| Surface | Base | Token scope (`.default`) |
|---|---|---|
| Workspaces, items, semantic-model & report **getDefinition** | `https://api.fabric.microsoft.com/v1` | `https://api.fabric.microsoft.com/.default` |
| Report → dataset linkage, **refresh history**, **Activity Events**, **Scanner** | `https://api.powerbi.com/v1.0/myorg` | `https://analysis.windows.net/powerbi/api/.default` |

`fabric-inventory.py` acquires both up front (silently from
`/tmp/pbiauth/cache.bin`). If the Power BI token can't be obtained, refresh
history degrades to `null` and dataset linkage falls back to the Fabric value
(usually absent → `dataset_id: null`).

## Endpoint gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `getDefinition` returns **202**, not 200 | It's a long-running operation (LRO) | Poll the `Location` header, respect `Retry-After`, GET `Location/result` when `status == "Succeeded"`. Implemented in `get_definition_tmsl` / `get_report_pbir`. |
| Report `dataset_id` is `null` | The **Fabric** `/workspaces/{ws}/reports` endpoint omits `datasetId` | Recover it from the **Power BI REST** `/groups/{ws}/reports` endpoint (`datasetId` field). `fabric-inventory.py` does this via `fetch_report_dataset_map`. |
| `dataset_id` still `null` for *My workspace* reports | PBI REST `/groups/{ws}/reports` doesn't cover the per-user My-workspace; it uses the no-group `/reports` route | Acceptable — the report still inventories; it just won't link DAX complexity. Rare in real tenants (shared content lives in named workspaces). |
| `CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain` | Corp network MITM-inspects `api.fabric.microsoft.com` | `import truststore; truststore.inject_into_ssl()` as the FIRST import (uses the macOS keychain which trusts the corp root CA). MANDATORY. |
| Activity Events / Scanner return **403** | Signed-in user lacks the **Fabric Administrator** role | Expected for most users. Degrade to complexity-only shortlist (`probe-admin.py`/`.rb` handle this). |
| Activity Events returns 400 "startDateTime required" | The endpoint needs an explicit single-UTC-day window | `?startDateTime='YYYY-MM-DDT00:00:00.000Z'&endDateTime='...T23:59:59.999Z'` — note the **single quotes around the ISO strings** are part of the OData syntax. |

## TMSL (TOM) shape — what the complexity scan reads

`getDefinition?format=TMSL` returns `definition.parts[]`; the model part
(`model.bim` / `*.tmsl`) base64-decodes to TOM JSON:

```
model.tables[]
  .partitions[].mode           // "import" | "directQuery"
  .partitions[].source.type    // "calculated" ⇒ calculated table
  .partitions[].source.expression  // M (Power Query) — parsed for warehouse host
  .measures[].expression       // DAX — classified into a/b/c buckets
  .columns[].type == "calculated"  // calc columns; .expression is DAX
model.roles[]                  // RLS roles — rls_role_count
```

Warehouse host parsing regex matches `Snowflake.Databases("host"...)`,
`Sql.Database(...)`, `AmazonRedshift.*`, `GoogleBigQuery.*`, `Databricks.*`,
`PostgreSQL.*`, `Oracle.*`. Extend `analyze_tmsl` in `fabric-inventory.py` for
more connectors.

## PBIR shape — what the report scan reads

`getDefinition` (no format flag) on a report returns PBIR parts. Two layouts
exist in the wild:

- **Enhanced report format (PBIR)**: pages at
  `definition/pages/<page>/page.json`, visuals at `.../visuals/<id>/visual.json`
  with a `"visualType": "..."` key. `analyze_pbir` counts page dirs and
  histograms `visualType`.
- **Legacy inlined `report.json`**: `sections[].visualContainers[].config`
  (a JSON-encoded string) with `singleVisual.visualType`. `analyze_pbir` falls
  back to this when no `pages/` dirs are present.

Custom visuals show up as a non-standard `visualType` token (long GUID-ish
string or `PBI_CV_*`); they're collected into `custom_visuals` and scored as
`unhandled` (no automatic Sigma equivalent).

## DAX function → bucket classification

The function-name lists live in `fabric-inventory.py` (`DAX_BUCKET_A/B/C`).
Worst bucket present in a measure wins (`c` > `b` > `a`). Source of truth for
the mapping is `research/dax-to-sigma-coverage.md` (the 70% mechanical finding)
and the worked rubric in `powerbi-to-sigma/fixtures/MANIFEST.md`. When the
converter gains coverage for a currently-`b`/`c` pattern, move the function name
to the lower bucket here.
