# Layered / derived LookML — patterns and how the converter handles them

Real Looker projects are rarely flat `sql_table_name:` views. Mature customers
layer derived tables on derived tables, persist them as PDTs, and work around
Looker's circular-reference rules with hand-written CTE fragments. This doc
catalogs those patterns and exactly what `convert_lookml_to_sigma` (MCP +
`scripts/convert_dm.mjs`) does with each — including what it CANNOT do and the
warning you'll see instead. Nothing in this class of LookML is ever dropped
silently: every lossy translation emits a 🔶 (action required) or ⚠ (review)
warning, and `migrate-looker.py` prints those in a banner after Phase 3.

**Golden rule: always convert the WHOLE LookML directory, not one file.**
Cross-view references only resolve against the views in the parse set.
`migrate-looker.py --lookml-dir <dir>` and `convert_dm.mjs` both glob every
`*.view.lkml` in the directory (or its `views/` subdir) for exactly this
reason.

---

## 1. View-only input (no `.model.lkml`)

Customers usually hand over a few `.view.lkml` files, not the model. The
converter no longer requires an explore: with no model file it converts **every
view as a standalone element** (derived tables → Custom SQL elements, plain
views → warehouse-table elements) and warns:

> ℹ No explore/model file provided — converted N standalone view element(s)…

Joins live in the model's explores, so view-only output has **no
relationships**. If you later receive the model file, re-run with it included.

## 2. `derived_table` with multi-table SQL

A `derived_table: { sql: … }` becomes a Sigma **Custom SQL element**
(`source.kind: "sql"`). The SQL is carried through verbatim (multi-CTE, window
functions, `REGEXP_REPLACE`, `SELECT * EXCLUDE (…)`, `MAX_BY`, `LISTAGG`,
`QUALIFY` — all fine: Sigma sends it to the warehouse as-is). Dimensions on the
view become columns referencing the SQL output aliases
(`[Custom SQL/COL_NAME]`); measures become metrics.

## 3. Cross-view `${other_view.SQL_TABLE_NAME}` references

Looker substitutes these with the referenced view's scratch table (or inlines
its SQL). The converter resolves them three ways, in order of preference:

| Referenced view | Result |
|---|---|
| Plain view (`sql_table_name:`) — incl. N-hop alias chains | Literal warehouse path substituted (e.g. `CSA.TJ.ORDER_FACT`) |
| Derived view **in the parse set** | Inlined as a **named `WITH` CTE** (`WITH other_view AS (…)`), recursively for its own refs, cycle-guarded; the reference becomes the CTE name, so existing SQL aliases (`… t`, `… a/b` self-joins) are preserved |
| View **NOT in the parse set** | Placeholder table `LOOKER_SCRATCH.<VIEW>` + **🔶 UNRESOLVED VIEW** warning naming the view. The SQL parses but will NOT run — either add `<view>.view.lkml` to the input and re-run, or repoint the placeholder at the real warehouse table (the Looker scratch-schema PDT or its underlying source) |

## 4. CTE-continuation fragments (the circular-reference workaround)

Derived SQL that **starts with a comma** —

```sql
, base AS (
    SELECT … FROM ${upstream.SQL_TABLE_NAME} …
)
SELECT … FROM base
```

— is deliberate: the author expects Looker to prepend the inlined SQL of
referenced PDTs as leading CTEs (this is how customers inline upstream logic to
avoid circular view references). The converter:

- if it inlined CTEs for the view's refs (§3), the generated `WITH …` prelude
  **completes the fragment** (`WITH ref AS (…)\n, base AS (…) …`);
- otherwise it **promotes the leading `,` to `WITH `** so the statement parses
  standalone, with an ℹ warning telling you to verify the first CTE no longer
  depends on a missing upstream CTE.

A referenced view whose own SQL is itself a fragment cannot be wrapped in a
CTE — it falls back to the `LOOKER_SCRATCH` placeholder + 🔶 warning.

## 5. Persistence (PDTs) → Sigma materialization handoff

Sigma has no incremental/persisted derived tables in the spec — the equivalent
is **scheduled materialization on the element** (DM UI → Materialization tab,
or the API). Persistence config is therefore converted-but-flagged, never
silent:

| LookML | Converter behaviour |
|---|---|
| `datagroup_trigger` / `sql_trigger_value` / `persist_for` | Element converts normally + ℹ warning recommending a materialization schedule |
| `increment_key` / `increment_offset` | Element converts (full-SQL semantics) + **🔶 warning**: re-computes in full each refresh; enable materialization |
| `{% incrementcondition %} col {% endincrementcondition %}` (Liquid in the SQL) | Replaced with `1=1 /* comment preserving the column */` + **🔶 warning** — Looker expands this to `col >= watermark` on incremental builds; Sigma always full-scans |
| `cluster_keys` / `sortkeys` / `distribution` / `partition_keys` / `persist_with` | ℹ warning — warehouse-side hints, configure in the warehouse if still needed |

**Handoff:** after `post_dm.py` succeeds, take every element with a 🔶/ℹ
materialization warning and set up a materialization schedule matching the old
datagroup cadence. The `sigma-materialization-advisor` skill can rank which of
these actually deserve materialization by credit spend.

## 6. `dimension_group` expansion

`type: time` groups expand into a folder of timeframe columns: raw/time → the
physical column, date/week/month/quarter/year → `DateTrunc("…", col)`.
Hardened edge cases (all regression-tested):

- `sql: CAST(${TABLE}."COL" AS TIMESTAMP_NTZ)` — the CAST wrapper is unwrapped
  to the physical column (common tz-handling idiom), not skipped.
- `timeframes:` lists **without** `raw`/`time` still emit the base physical
  column once (named "… Raw") so measures and the column order stay valid.
- Two dimension_groups (or a dimension + a group) over the **same physical
  column** share one base column — no duplicate columns/ids.
- Every timeframe name (`group_raw`, `group_date`, …) is registered so measure
  SQL can reference it (§7).
- Truly complex group SQL (expressions beyond a CAST) is skipped with a ⚠ —
  re-add as a Sigma calc column.

## 7. Measures — complex / filtered / formatting

- **Simple aggregates** (`sum`, `count_distinct`, `average`, …, over `${dim}`
  or `${TABLE}.col`) → Sigma metrics.
- **Filtered measures** (`filters: [field: …]`) → `SumIf`/`CountIf`/… 
- **Computed/ratio measures** (`${measure_a} / ${measure_b}`, `NULLIF`, …) →
  metrics with the referenced measures' formulas substituted inline.
- **`type: date_time` / `date` measures** like `MAX(${group_raw})` →
  `Max([COL])` metrics (previously fabricated a phantom column).
- **Formatting measures** — `type: string` CASE blocks wrapping values in
  `TO_CHAR(x, '$FM999,…')`, `||` concatenation, `::` casts — have **no Sigma
  formula equivalent**. The converter emits a ⚠ naming the measure and quoting
  the exact untranslatable fragment. Recreate as: keep the underlying numeric
  metric (it converts fine) + apply a Sigma **column format** for the display
  treatment. A broken metric is never emitted silently.

## 8. What you'll see in `migrate-looker.py`

Phase 3 writes `dm-spec-warnings.json` next to the spec and prints:

```
   ════════ 🔶 ACTION REQUIRED — N converter warning(s) ════════
   🔶 UNRESOLVED VIEW "x": …
   🔶 View "y": incremental PDT (increment_key: …) … materialization …
   ► UNRESOLVED VIEW: … add the named .view.lkml file(s) to --lookml-dir …
   ► MATERIALIZATION HANDOFF: … enable a materialization schedule …
```

Treat 🔶 as a gate: a DM whose Custom SQL contains `LOOKER_SCRATCH.*`
placeholders will POST but its element will error at query time — fix the
placeholder (or supply the missing view files) before Phase 6 parity.
