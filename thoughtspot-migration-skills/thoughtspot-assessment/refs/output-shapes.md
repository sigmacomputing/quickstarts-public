# Output shapes

One JSON file + one rendered HTML emitted to `~/thoughtspot-migration/` (or the
`--out` directory). `scripts/scan.py` writes `assessment.json`;
`scripts/render-readout-html.rb` reads it to produce `readout.html`.

## `assessment.json`

Always written. Usage-dependent fields are present but zero/empty when
`TS: BI Server` is absent (`usage_available: false`).

```json
{
  "instance": {
    "host": "<TS_HOST>",
    "generated_at": "YYYY-MM-DD"
  },
  "environment_overview": {
    "liveboards":  <int>,
    "answers":     <int>,
    "models":      <int>,
    "tables":      <int>,
    "connections": <int>
  },
  "profiles": [
    {
      "id":   "<liveboard guid>",
      "name": "<liveboard name>",
      "author": "<author name/email>",
      "exportable": <bool>,
      "note": "<reason>",                  // only when exportable=false
      "viz":  <int>,                       // exportable only ↓
      "chart_types": { "<TYPE>": <int>, ... },
      "models": ["<model name>", ...],
      "n_formula": <int>,                  // TML formulas referenced
      "n_filter":  <int>,                  // viz + liveboard filters
      "unsupported": ["<TYPE>", ...],      // chart kinds w/o 1:1 Sigma mapping
      "complexity": <int>,
      "views": <int>,                      // from TS: BI Server (0 if no usage)
      "users": <int>,
      "value_cost": <float>,               // views / (1 + complexity)
      "tag": "migrate-first|easy-win|moderate|needs-gap-scout|retire"
    }, ...
  ],
  "shortlist": [ <profile subset, ranked> ],   // exportable, value/cost desc (or effort asc)
  "ownership": [ { "author": "<name>", "liveboards": <int> }, ... ],
  "connections": [
    { "id": "<guid>", "name": "<name>", "author": "<name>",
      "connection_type": "<RDBMS_*>", "class": "embrace|falcon|unknown" }, ...
  ],
  "tables": [
    { "id": "<guid>", "name": "<name>", "author": "<name>",
      "type": "<header type>", "file_uploaded": <bool> }, ...
  ],
  "datasource_summary": {
    "embrace": <int>, "falcon": <int>, "unknown": <int>,
    "file_uploaded_tables": <int>, "tables_total": <int>
  },
  "usage_by_user": [ { "user": "<name>", "actions": <int> }, ... ],  // [] if no usage
  "coverage": <float>,                    // % viz with a supported chart type
  "chart_types": { "<TYPE>": <int>, ... },          // across all exportable LBs
  "unsupported_chart_types": { "<TYPE>": <int>, ... },
  "models_used": ["<model name>", ...],
  "usage_available": <bool>,
  "usage_note": "<string>" | null,        // single graceful note when usage absent
  "total_views": <int>
}
```

## Complexity scoring

```
complexity = viz_count
           + 2 × distinct_chart_kinds
           + 3 × models_touched
           + 2 × tml_formulas
           +     filters
```

A relative effort proxy, not a time estimate.

## Tag rules (per exportable Liveboard)

- `views == 0` and usage available                     → `retire`
- any unsupported chart type                           → `needs-gap-scout`
- `complexity < 20` and usage available                → `migrate-first`
- `complexity < 30`                                    → `easy-win`
- otherwise                                            → `moderate`

## `readout.html`

Sigma-branded HTML. See `refs/readout-template.md` for the section ordering and
what each section renders. Composition is deterministic — the renderer takes
`assessment.json` and emits the file; no template-fill step.
