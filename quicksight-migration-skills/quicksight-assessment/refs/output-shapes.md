# Output shapes

Three JSON files + one markdown emitted to `<out>/`, plus decoded `raw-defs/`
and `raw-datasets/`. `render-readout.rb` reads the JSON to produce `readout.md`;
`quicksight-to-sigma` reads `migration-plan.json`.

Parallel to `powerbi-assessment/refs/output-shapes.md` — the renderer and
shortlist scoring share that skill's vocabulary so the markdown sections line
up. The key difference: QuickSight splits complexity across the **analysis**
(visuals, calc fields, parameters, layout) and its **datasets** (source type,
custom-sql, joins, data-prep, RLS/CLS).

## `inventory.json` (written by `quicksight-inventory.py`)

```json
{
  "account": {
    "account_id": "...", "region": "us-east-1",
    "generated_at": "YYYY-MM-DD",
    "edition": "Enterprise" | "Standard? (definition API rejected)" | null,
    "enterprise": true | false | null
  },
  "analyses": [
    {
      "id": "...", "name": "...", "last_updated": "...",
      "sheet_count": <int>, "visual_count": <int>,
      "visual_kinds": { "BarChartVisual": N, "KPIVisual": N, ... },
      "visuals_built": <int>, "visuals_mid": <int>, "visuals_unhandled": <int>,
      "calc_field_count": <int>,
      "calc_buckets": { "a": <int>, "b": <int>, "c": <int> },
      "window_calc_count": <int>,
      "parameter_count": <int>, "filter_group_count": <int>,
      "free_form_sheets": <int>, "section_based_sheets": <int>,
      "dataset_identifiers": [...], "dataset_ids": ["<dataSetId>", ...]
      // OR, on a Standard account / no perms:  "def_error": "..."
    }
  ],
  "datasets": [
    {
      "id": "...", "name": "...",
      "import_mode": "SPICE" | "DIRECT_QUERY",
      "physical_kinds": ["RelationalTable" | "CustomSql" | "S3Source", ...],
      "has_custom_sql": <bool>, "has_joins": <bool>, "transform_count": <int>,
      "rls_enabled": <bool>, "cls_enabled": <bool>, "column_count": <int>
    }
  ],
  "data_sources": [ { "id": "...", "name": "...", "type": "SNOWFLAKE" | "REDSHIFT" | "ATHENA" | "S3" | ... } ],
  "environment_overview": {
    "analyses": <int>, "dashboards": <int>, "datasets": <int>, "data_sources": <int>
  }
}
```

`calc_buckets` semantics (from `refs/migration-test-slate.md`): `a` = mechanical
rewrite, `b` = needs restructuring, `c` = window / table-calc function with no
clean Sigma equivalent (converter degrades to a `/* TODO */` placeholder).

## `complexity.json` (written by `score-quicksight-complexity.rb`)

Keyed by **analysis id**. The analysis inherits its datasets' burden via
`dataset_ids`. The four `n_*` tiers map onto the shared vocabulary: easy → auto,
medium → manual, hard → unhandled, no `hint` tier.

```json
{
  "<analysis-id>": {
    "name": "...", "sheets": <int>, "visuals": <int>, "visual_kinds": {...},
    "calc_field_count": <int>, "window_calc_count": <int>,
    "parameter_count": <int>, "filter_group_count": <int>,
    "dataset_count": <int>, "dataset_source_types": [...],
    "has_custom_sql": <bool>, "has_joins": <bool>,
    "rls_role_count": <int>, "cls_count": <int>,
    "calc_buckets": { "a": <int>, "b": <int>, "c": <int> },
    "twb_size_kb": 0,                       // n/a; renderer-compat
    "n_features": <int>, "n_auto": <int>, "n_hint": 0,
    "n_manual": <int>,                      // restructure calc + mid visuals + joins + transforms + params + RLS/CLS
    "n_unhandled": <int>,                   // window calc + exotic visuals + free-form/section layout + FilterGroups + S3 source
    "features": [{ "name": "...", "status": "auto|manual|unhandled", "count": <int> }]
  }
}
```

## `usage.json` (optional — only if the agent supplies it)

QuickSight has no per-analysis view-count API on the standard surface. If the
agent derives views from CloudTrail / CloudWatch (optional, out of scope for the
default run) it can drop a file in this shape and `build-shortlist.rb` will use
the usage-weighted value formula:

```json
{
  "available": true,
  "by_analysis": { "<analysis-id>": { "views": <int>, "users": <int> } }
}
```

If absent, `build-shortlist.rb` falls back to the complexity-only proxy.

## `shortlist.json` (written by `build-shortlist.rb`)

```json
{
  "usage_available": <bool>,
  "value_basis": "usage (views × √users)" | "complexity-only proxy (sheets + visuals/4)",
  "analyses": [
    {
      "name": "...", "id": "...", "sheets": <int>, "visuals": <int>,
      "views": <int>|null, "users": <int>|null,
      "auto": <int>, "hint": <int>, "manual": <int>, "unhandled": <int>,
      "calc_buckets": {...}, "dataset_source_types": [...],
      "value": <float>, "cost": <int>, "score": <float>,
      "tag": "migrate-first"|"easy-win"|"moderate"|"needs-gap-scout"|"retire"
    }
  ]
}
```

Tag rules (mirror powerbi/tableau-assessment):
- usage available AND `views == 0`               → `retire`
- `unhandled >= 1`                               → `needs-gap-scout`
- `score >= 20 and (manual + unhandled) == 0`    → `migrate-first`
- `score >= 10`                                  → `easy-win`
- else                                           → `moderate`

## `migration-plan.json` (written by `migration-plan.rb`)

The hand-off contract for `quicksight-to-sigma`. Per-analysis `recommended_path`
(`quicksight-to-sigma` / `quicksight-to-sigma-with-scout` / `retire` /
`blocked`) plus DM clusters. Clustering key is the **shared dataset** — analyses
that reference the same QuickSight dataset (or transitively overlap) share a
Sigma data model by construction. See `migration-plan.rb` header for the full
shape.

## `readout.md`

Markdown readout. See `refs/readout-template.md` for section ordering and
placeholders. Deterministic composition from the JSON files above.
