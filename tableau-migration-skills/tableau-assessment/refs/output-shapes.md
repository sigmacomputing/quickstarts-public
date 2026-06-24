# Output shapes

Three JSON files + one markdown emitted to `<out>/`. Renderer reads the three
JSON files to produce `readout.md`; downstream skills (e.g. `tableau-to-sigma`)
read whichever they need.

## `inventory.json`

Always written (MCP-only or MCP+PAT). Sections that require Admin Insights are
present with `null` value if the user lacked Site Admin access.

```json
{
  "site": {
    "name": "<site contentUrl>",
    "url": "<root URL>",
    "generated_at": "YYYY-MM-DD",
    "mode": "MCP-only" | "MCP + Admin Insights" | "MCP + Admin Insights + PAT"
  },
  "environment_overview": {
    "workbooks":   <int>,
    "views":       <int>,
    "datasources": <int>,
    "projects":    <int>,
    "flows":       <int>,
    "metrics":     <int>,
    "metric_definitions": <int>
  },
  "view_type_breakdown": { "dashboard": <int>, "view_sheet": <int>, "story": <int> },
  "licenses": {
    "users_total": <int>,
    "by_type": [{ "license": "Creator|Explorer|Viewer|Unlicensed", "site_role": "...", "users": <int>, "avg_days_since_login": <float> }, ...],
    "notes": "<string>"
  } | null,
  "content_ownership": [
    { "owner": "<email>", "workbooks": <int>, "datasources": <int>, "views": <int>, "flows": <int> }, ...
  ] | null,
  "datasource_types": {
    "published_extract": [{ "db_type": "<str>", "n": <int> }, ...],
    "published_live":    [{ "db_type": "<str>", "n": <int> }, ...],
    "embedded":          [{ "db_type": "<str>", "n": <int> }, ...],
    "summary": { "published_total": <int>, "embedded_total": <int>, "extract_total": <int>, "live_total": <int> }
  } | null,
  "refresh_jobs": {
    "total": <int>,
    "by_type_result": [{ "job_type": "<str>", "result": "Succeeded|Failed", "n": <int>, "avg_duration_s": <float> }, ...],
    "notes": "<string>"
  } | null,
  "audit_summary_all_time": {
    "total_events": <int>,
    "by_event_type": [{ "event": "Access|Publish|Update|Create|Delete", "n": <int>, "actors": <int> }, ...],
    "by_item_type":  [{ "item": "View|Data Source|Workbook|(other)", "accesses": <int> }, ...]
  } | null,
  "workbook_usage": [
    { "name": "<workbook name>", "accesses": <int>, "actors": <int> }, ...
  ] | null,
  "workbook_inventory": [
    {
      "name": "<workbook name>",
      "luid": "<workbook luid>",
      "owner": "<email>",
      "project": "<top-level project name>",
      "size_mb": <float>,
      "is_extract": <bool>,
      "last_accessed": "YYYY-MM-DD" | null,
      "url": "<full URL>"
    }, ...
  ]
}
```

## `complexity.json` (PAT mode only)

One row per workbook with non-null `.twb` content. Keyed by workbook LUID.

```json
{
  "<workbook-luid>": {
    "name": "<workbook name>",
    "twb_size_kb": <int>,
    "n_features":  <int>,
    "n_auto":      <int>,
    "n_hint":      <int>,
    "n_manual":    <int>,
    "n_unhandled": <int>,
    "features": [
      { "name": "<feature>", "status": "auto|hint|manual|unhandled", "count": <int> }, ...
    ]
  }, ...
}
```

`status` semantics (from `tableau-to-sigma/scripts/scan-workbook-gaps.rb`):
- `auto` — translated by the skill end-to-end, no human intervention
- `hint` — WARN with a copy-paste-ready Sigma formula
- `manual` — needs post-publish wiring by the customer
- `unhandled` — needs gap-scout subagent escalation

## `shortlist.json` (PAT mode only)

Array, sorted by `score` descending. Each row:

```json
{
  "name": "<workbook name>",
  "luid": "<workbook luid>",
  "url":  "<full URL>",
  "accesses": <int>,
  "actors":   <int>,
  "auto":  <int>,
  "hint":  <int>,
  "manual": <int>,
  "unhandled": <int>,
  "value":  <float>,
  "cost":   <int>,
  "score":  <float>,
  "tag":    "migrate-first" | "easy-win" | "moderate" | "needs-gap-scout" | "retire"
}
```

Tag rules:
- `accesses == 0`                                            → `retire`
- `unhandled >= 1`                                           → `needs-gap-scout`
- `score >= 20 and (manual + unhandled) == 0`                → `migrate-first`
- `score >= 10`                                              → `easy-win`
- otherwise                                                  → `moderate`

## `consolidation-candidates.json` (Phase 6b, PAT mode only)

Workbook-variant groups that could collapse into one Sigma workbook + control.

```json
{
  "generated_at": "YYYY-MM-DD",
  "params": { "emit_floor": 0.45, "consolidate_min_field_overlap": 0.7,
              "consolidate_min_sheet_jaccard": 0.6, "review_min_score": 0.55 },
  "summary": { "workbooks_analyzed": <int>, "groups_total": <int>,
               "consolidate": <int>, "review": <int>, "keep_separate": <int>,
               "conversions_avoidable": <int> },
  "groups": [{
    "group_id": "consolidation-NN",
    "recommendation": "consolidate" | "review" | "keep-separate",
    "recommendation_reason": "<string>",
    "workbooks": [{ "workbookId": "<luid>", "name": "...", "accesses": <int>,
                    "sheets": <int>, "dashboards": <int>, "used_fields": <int>,
                    "priority_tier": "<shortlist tag>", "recommended_path": "<plan path>" }],
    "primary": { "workbookId": "<luid>", "name": "..." },
    "shared_datasource": { "warehouse_tables": [...], "published_ids": [...] },
    "field_overlap_pct": <int>,
    "field_basis": "used" | "schema",
    "similarity_drivers": ["<evidence string>", ...],
    "differences": ["<evidence string>", ...],
    "proposed_controls": [{ "column": "<field>", "kind": "list-control|date-range-control",
                            "values_observed": [...] }],
    "pairwise": [{ "a_name": "...", "b_name": "...", "score": <float>,
                   "field_overlap": <float>, "field_basis": "...",
                   "sheet_jaccard": <float>, "name_similarity": <float>,
                   "filter_similarity": <float>, "feature_cosine": <float|null>,
                   "differing_filter_values": [...] }],
    "estimated_savings": { "conversions_avoided": <int> } | null
  }]
}
```

After `--decide`, `migration-plan.json` gains a top-level `consolidation` block
(`decided_at` + `decisions[]`) and per-workbook keys: merged members get
`recommended_path: "consolidate-into-primary"`, `consolidate_into`,
`pre_consolidation_path`, `consolidation_group`, `consolidation_role: "merged"`;
the primary gets `consolidation_role: "primary"` + `consolidation_controls`.

## `readout.md`

12-section markdown. See `refs/readout-template.md` for the exact section
ordering and placeholders. Composition is deterministic — `render-readout.rb`
takes the three JSON files and a template, fills in placeholders, writes file.
