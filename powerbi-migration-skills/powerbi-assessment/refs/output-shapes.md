# Output shapes

Four JSON files + one markdown emitted to `<out>/`, plus decoded `raw-tmsl/`
and `raw-pbir/`. `render-readout.rb` reads the JSON to produce `readout.md`;
`powerbi-to-sigma` reads `migration-plan.json`.

Parallel to `tableau-assessment/refs/output-shapes.md` — the renderer and
shortlist scoring share that skill's vocabulary so the markdown sections line
up. The key difference: Power BI splits complexity across the **semantic model**
(DAX) and the **report** (visuals); Tableau packs both into one `.twb`.

## `inventory.json` (written by `fabric-inventory.py`)

```json
{
  "tenant": {
    "generated_at": "YYYY-MM-DD",
    "fabric_aud": "https://api.fabric.microsoft.com",
    "refresh_history_available": true,
    "workspace_count": <int>
  },
  "workspaces": [
    { "id": "...", "name": "...", "on_capacity": <bool>,
      "capacityId": "..."|null, "item_type_counts": { "Report": N, "SemanticModel": N, ... } }
  ],
  "semantic_models": [
    {
      "id": "...", "name": "...", "workspace": "...", "workspace_id": "...",
      "on_capacity": <bool>,
      "table_count": <int>, "calc_table_count": <int>,
      "measure_count": <int>, "calc_column_count": <int>,
      "rls_role_count": <int>,
      "import_tables": <int>, "directquery_tables": <int>,
      "warehouse_sources": ["Snowflake:<host>", ...],   // parsed from M
      "dax_buckets": { "a": <int>, "b": <int>, "c": <int> },
      "measures": [{ "name": "...", "bucket": "a|b|c", "chars": <int>, "funcs": [...] }],
      "measure_total_chars": <int>, "max_measure_chars": <int>,
      "refresh_history": [{ "status": "...", "startTime": "...", "endTime": "...", "refreshType": "..." }] | null
    }
  ],
  "reports": [
    {
      "id": "...", "name": "...", "workspace": "...", "workspace_id": "...",
      "dataset_id": "..."|null,        // links report → semantic_model; from PBI REST /reports
      "page_count": <int>, "visual_count": <int>,
      "visual_kinds": { "barChart": N, "lineChart": N, ... },
      "custom_visuals": [ "<type token>", ... ]
    }
  ],
  "environment_overview": {
    "workspaces": <int>, "on_capacity_workspaces": <int>,
    "semantic_models": <int>, "reports": <int>, "dashboards": <int>,
    "dataflows": <int>, "lakehouses": <int>, "warehouses": <int>,
    "notebooks": <int>, "other_items": <int>
  }
}
```

`dax_buckets` semantics (from `research/dax-to-sigma-coverage.md` +
`powerbi-to-sigma/fixtures/MANIFEST.md`): `a` = mechanical rewrite, `b` =
needs data-model/element restructuring, `c` = no Sigma equivalent.

## `complexity.json` (written by `score-complexity.rb`)

Keyed by **report id**. The report inherits its model's DAX burden via
`dataset_id`. The four `n_*` tiers map onto tableau-assessment's vocabulary so
the renderer is shared: `a → auto`, `b → manual`, `c → unhandled`, no `hint`
tier (DAX bucket-a is already mechanical).

```json
{
  "<report-id>": {
    "name": "...", "workspace": "...", "model_name": "...",
    "pages": <int>, "visuals": <int>, "visual_kinds": {...},
    "measure_count": <int>, "calc_column_count": <int>, "calc_table_count": <int>,
    "rls_role_count": <int>, "directquery_tables": <int>,
    "warehouse_sources": [...],
    "dax_buckets": { "a": <int>, "b": <int>, "c": <int> },
    "twb_size_kb": 0,                        // n/a for PBI; renderer-compat
    "n_features": <int>, "n_auto": <int>, "n_hint": 0,
    "n_manual": <int>,                       // b + calc_tables + rls_roles
    "n_unhandled": <int>,                    // c + custom_visuals
    "features": [{ "name": "...", "status": "auto|manual|unhandled", "count": <int> }]
  }
}
```

## `usage.json` (optional — only when Fabric-admin is available)

The agent fires the Activity Events API per `SKILL.md` Phase 2 and writes:

```json
{
  "available": true,
  "by_report": { "<report-id>": { "views": <int>, "users": <int> } }
}
```

If admin is unavailable, this file is absent and `build-shortlist.rb` falls back
to the complexity-only proxy.

## `shortlist.json` (written by `build-shortlist.rb`)

```json
{
  "usage_available": <bool>,
  "value_basis": "activity-events (views × √users)" | "complexity-only proxy (pages + visuals/4)",
  "reports": [
    {
      "name": "...", "id": "...", "workspace": "...", "model_name": "...",
      "views": <int>|null, "users": <int>|null,
      "pages": <int>, "visuals": <int>,
      "auto": <int>, "hint": <int>, "manual": <int>, "unhandled": <int>,
      "dax_buckets": {...},
      "value": <float>, "cost": <int>, "score": <float>,
      "tag": "migrate-first"|"easy-win"|"moderate"|"needs-gap-scout"|"retire"
    }
  ]
}
```

Tag rules (mirror tableau-assessment):
- usage available AND `views == 0`               → `retire`
- `unhandled >= 1`                               → `needs-gap-scout`
- `score >= 20 and (manual + unhandled) == 0`    → `migrate-first`
- `score >= 10`                                  → `easy-win`
- else                                           → `moderate`

## `migration-plan.json` (written by `migration-plan.rb`)

The hand-off contract for `powerbi-to-sigma`. Per-report `recommended_path`
(`powerbi-to-sigma` / `powerbi-to-sigma-with-scout` / `retire` / `blocked`) plus
DM clusters. Clustering primary key is the **shared semantic model** — reports
off the same model share a Sigma data model by construction (cleaner than
Tableau's `.twb`-table Jaccard). See `migration-plan.rb` header for the full
shape.

## `readout.md`

12-section markdown. See `refs/readout-template.md` for section ordering and
placeholders. Deterministic composition from the JSON files above.
