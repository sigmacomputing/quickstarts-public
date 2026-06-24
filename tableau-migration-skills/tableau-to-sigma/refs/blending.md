# Tableau data blending → Sigma

**Disposition: documented decision tree + scripted detection
(beads-sigma-iq8).** Tableau *blending* joins two published/embedded
datasources at query time on same-named "linking fields". Sigma's equivalent
is a data model with both sources as elements plus a relationship — but only
when both sources are reachable from ONE Sigma connection. The router below
keeps that honest.

## Detection (Phase 0a — automatic)

`scripts/scan-workbook-gaps.rb` detects blends per worksheet — ALL must hold:

- the worksheet's `<view>` lists **2+ real datasources** (defined at
  `/workbook/datasources/datasource`, `Parameters` excluded)
- a `<datasource-dependencies datasource='<secondary>'>` block under the
  worksheet pulls **fields from the secondary**
- a `<join>` inside a single `<datasource>` is a JOIN, not a blend — it never
  produces a secondary dependencies block, so it never matches

**Linking fields** are approximated as the captions present in BOTH the
primary's and the secondary's dependency blocks (Tableau's default link is
same-named fields). Output: `blend-plan.json` next to the gaps report —
`datasources[]` (name, caption, connection class/server/dbname/schema) and
`blends[]` (worksheet, primary, secondary, linking_fields, secondary_fields,
route, recommendation) — plus a per-route row in the gap report.

## Decision tree (the `route` field)

```
Is the secondary's <connection> the same warehouse as the primary's
(class + server match, dbname compatible)?
├── YES → (a) same-warehouse-repoint           [hint — convertible]
│         ONE Sigma DM: both Tableau datasources as elements
│         (warehouse-table or kind:sql), a `relationships` entry on the
│         primary keyed on the linking fields (composite keys supported).
│         Workbook refs `[Secondary.Field]` → cross-element refs
│         `[Secondary Element/Field]`.
│         ⚠ When repointing connectionId on an existing spec, DEEP-WALK it:
│         connectionId nests inside join sources (`joins[].left/right`,
│         recursively) and control `source.source` — a top-level-only swap
│         silently leaves stale connections (see
│         feedback_sigma_spec_connectionid_nesting; manager import bug PR #45).
└── NO → is the secondary a file / extract / published source
         (textscan, csv, msexcel, excel-direct, hyper, webdata-direct,
         google-sheets, salesforce, sqlproxy)?
    ├── YES → (b) materialize-via-vds           [manual — two-step]
    │         Run the **tableau-vds-to-cdw** skill FIRST to land the
    │         secondary in the primary's warehouse (Snowflake Part A /
    │         Databricks Part B), grant the Sigma connection's role SELECT +
    │         schema-sync the connection, then convert as (a).
    └── NO → (c) flag-unreachable               [manual — report only]
              The secondary is a different live system (another warehouse /
              server) the conversion can neither repoint nor land. The blend
              stays manual: use blend-plan.json's linking_fields +
              secondary_fields to wire a workbook-level join or a second DM
              post-publish, and record the decision in the conversion report.
```

Route (a) was live-verified in the 2026-05-04 blending spike (Orders ×
Region_Targets, one DM + relationship, attainment ratio matched Snowflake for
all 16 region-year cells).

## Gotchas

- The **primary** is the first datasource in the worksheet's `<view>` list;
  Tableau aggregates the secondary to the linking-field grain before joining.
  In Sigma, reproduce that grain with a grouped helper element when the
  secondary is finer-grained than the link (same pattern as nested-LOD
  helpers).
- Empty `linking_fields` in blend-plan.json means the blend links on
  RENAMED field pairs (Tableau allows custom link mappings) — read the
  worksheet XML by hand; the report can't infer those.
- Never cap or filter the shared master to "fix" blend parity — element
  filters propagate to every chart sourcing it
  (feedback_sigma_source_element_filter_propagates).
