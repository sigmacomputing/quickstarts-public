<!-- Shared Phase E (opt-in) contract — vendored into every converter skill. -->

## Phase E (opt-in) — Enhance

**OFF by default, everywhere.** Phase E never runs in batch/headless mode
without the explicit `--enhance` flag, and it only ever starts from a
**parity-verified** workbook. It is powered by the shared engine vendored
byte-identically into each converter (`scripts/enhance-scan.rb`,
`enhance-select.rb`, `enhance-app-plan.rb`, `enhance-apply.rb` plus
`scripts/lib/enhance_options.rb` — md5 discipline, same as `escalate-gap.py`).

Today **tableau-to-sigma** and **powerbi-to-sigma** wire `--enhance` /
`--enhance-accept` on their orchestrators. Other converters vendor the same
scripts; adopt the flag convention when wiring C10 (see
`docs/phase-schema.md`).

```bash
# After parity is green (orchestrator --finalize / equivalent):
#   --enhance                       # scan only → exit 14 with proposals
ruby scripts/enhance-scan.rb --workbook-id <parityWorkbookId> \
  --workdir <migration-workdir> --source <tableau|powerbi|qlik|...> \
  --out <workdir>/enhancements.json

# Design interview (below), then record the answer:
ruby scripts/enhance-select.rb --enhancements <workdir>/enhancements.json \
  --option option-interactive-dashboard \
  --out <workdir>/enhance-selection.json

# Apply exactly what the human chose (orchestrator re-run with accept, or):
ruby scripts/enhance-apply.rb --workbook-id <parityWorkbookId> \
  --enhancements <workdir>/enhancements.json \
  --accept "$(ruby scripts/enhance-select.rb \
    --enhancements <workdir>/enhancements.json \
    --option option-interactive-dashboard --print-accept)" \
  --out <workdir>/enhance-report.json
```

### The design interview (MANDATORY in interactive runs)

Exit 14 means *proposals pending*, *not* "pick from a list of fifteen
patches". A human does not want to adjudicate `polish-null-label-el7`; they
want to decide **what this app should be**. `enhancements.json` therefore also
carries `app_options[]` — a handful of data-derived app shapes rolled up from
the same detector evidence — plus a `signals` block explaining why.

Do this, in order:

1. **Read `app_options[]`** from `enhancements.json`. Each app entry has
   `{id, label, archetype, score, confidence, summary, evidence_items,
   modules, optional_modules, requires, manual_refs, recommended}`. Patch-only
   options continue to carry `candidate_ids`.
2. **Ask the human with ONE question**, options taken verbatim from
   `app_options[]` — lead with the `recommended: true` one and quote its
   `evidence` so the recommendation is visibly grounded in their data, not a
   template. Always include `option-parity-only`; declining is a legitimate,
   respectable answer.
3. **Confirm medium-risk items individually.** An option may bundle
   `risk: medium` candidates (formula rewrites, heuristic pairings). Never let
   an option choice imply consent for those — `enhance-select.rb` drops any
   unconfirmed medium item and reports it. Re-run with
   `--confirm-medium <ids>` only after the human confirms each by name.
4. **Record patch acceptance** with `enhance-select.rb`, which writes
   `enhance-selection.json` (`selected_option_ids`, `declined_option_ids`,
   `accepted_candidate_ids`, `dropped_unconfirmed_medium`, `manual_followups`).
   That artifact is the audit trail for what was offered and what was approved.
5. **For an app archetype, ask only architecture-changing follow-ups:**
   what users edit (`drivers|line-values|both|none`), approvals, scenarios,
   agent authority, **unit of work**, and **write mode** (`append` default —
   overwrite only when the human explicitly wants destructive updates). Then
   write the build contract:

   ```bash
   ruby scripts/enhance-app-plan.rb \
     --enhancements <workdir>/enhancements.json \
     --option <selected-option-id> \
     --editable <mode> --approval <yes|no> --scenarios <yes|no> \
     --agent <mode> \
     [--unit-of-work "<grain description>"] [--write-mode append|overwrite] \
     --out <workdir>/app-plan.json
   ```

   Validate it against `schemas/app-plan.schema.json` before authoring.
   **STOP:** summarize the plan back and get explicit human confirmation
   before any `sigma-authoring` writeback work.
6. **Report `manual_followups` and `descoped_notes`** in the same summary,
   alongside any skill-local post-publish / UI-only residue.

App archetypes are multi-label. The detector scores scenario planning,
allocation/capacity, approval workflow, and exception command center from
exported dimension members + field/formula structure + stable-key readiness;
vocabulary is supporting evidence only. The highest score is primary and other
qualified archetypes contribute optional modules. See
`app-recommendation-signals.md`.

App options carry **no `candidate_ids`** because Phase E has no generic
write-back patch ops. They are scoped follow-up work built with the
`sigma-authoring` recipes, never something `enhance-apply.rb` can execute.

### Rails before agents (L1 → L2 → L3)

Writeback archetypes inherit BUILD's maturity ladder:

| Level | Meaning |
|---|---|
| L1 | Governed workflow: stable key, write connection, state tracked |
| L2 | L1 + AI-compressed tasks |
| L3 | L2 + agents (semi-autonomous) |

`enhance-app-plan.rb` **refuses** `--agent write-after-approval` unless L1
readiness is green (stable-key candidates present and no open
write-connection prerequisite). `recommend` without L1 emits a warning —
keep the agent read-only until the rails exist.

When `--write-mode append` (the default) and the surface is editable, the
plan emits ledger + `CURRENT_*` view manual steps. Prefer append-only unless
the human explicitly chooses overwrite.

### Related: greenfield BUILD / Design Pack

Phase E starts from a **parity-green analytics workbook**. If the human
actually wants a greenfield process → app design (actors, handoffs, OLTP
input-table model from a discovery transcript), hand off to the separate
**sigma-app-design** / BUILD Design Pack skill — do not stretch Phase E into
a full process-design interview. Phase E's `app-plan.json` is the thin
migration-side contract; BUILD's Design Pack is the full PRD.

Before offering writeback as build-ready, require:

- a stable entity/composite key;
- a write-enabled connection;
- a declared editable grain with uniqueness/cardinality proof;
- workbook-owned controls for workbook formulas (never reference a control
  owned by a separate data-model document);
- a plan for how rows arrive (a linked child inheriting a parent element, or
  supported Sigma UI/warehouse loading — bulk row-load APIs are not a supported
  migration path);
- a runtime verification plan.

> **Data entry is not spec-authorable.** If the human picks the write-back
> direction, the resulting input tables are editable **only in draft** until
> someone flips each element's *kebab → "Set data entry permission" → "Only in
> published version"* in the UI. That setting does not exist in the workbook
> spec. Say so explicitly at handoff — see
> `sigma-workbooks/reference/specification/input-tables.md`.

The contract (trial-validated, 2026-06-10):

1. **Clone-first.** `enhance-apply.rb` GETs the parity workbook's spec and
   POSTs it as `"<name> — Enhanced"`. The 1:1 parity artifact is **never
   written** (the report records its `updatedAt` before/after as proof).
2. **Scan-then-propose.** `enhance-scan.rb` reads source signals (workdir
   artifacts — tool-specific files such as Tableau `calc-fields.json` /
   `dashboard-layout.json`, Power BI `signals.json`, plus `migrate-state.json`
   when present) + the built spec + live element exports, and emits
   `enhancements.json` — each candidate `{id, category, evidence, proposed,
   risk, verdict_hint, patch}`, plus `signals` and the `app_options[]` rollup
   that drives the design interview. **Nothing applies without acceptance**:
   interactive runs run the interview above and record it with
   `enhance-select.rb`; headless runs pass `--enhance-accept id1,id2` or
   `--enhance-accept all-low-risk`.
3. **Apply + parity-unchanged gate.** Accepted items apply **one at a time**
   to the clone; after each, 2-3 untouched elements are spot-queried on the
   clone AND the original at the same instant (live-drift-proof) — any shift
   auto-reverts that item and flags it in `enhance-report.json`
   (applied/skipped/reverted + evidence).

Detector catalog (trial-validated; nothing speculative):

- **comparison-enrichment** — date-grouped master + revenue-like measure →
  latest-period KPI + delta-% KPI pair. KPI value columns INLINE the full
  `Sum(If(D = Max(D), v, Null))` expression — cross-column aggregate refs
  silently misevaluate in kpi-charts.
- **interactivity-recovery** — (a) list **selection controls** on
  reasonable-cardinality dims wired to the shared master (empty default =
  identical render); (b) **grain switcher** — segmented control + DateTrunc
  switch, default = parity grain; (c) **drill switcher** — segmented control +
  `If()` dimension switch where a finer dim exists (medium risk: heuristic
  hierarchy pairing); (d) **map restoration** (PBI signals) — point-map with
  `Switch()` centroid synthesis (medium risk: centroids must be filled into
  the patch before apply).
- **fidelity-polish** — null-bucket labeling (`Coalesce → "No <Dim>"`),
  month/date axis canonicalization (`MakeDate`; medium risk on multi-year
  sources — intentionally un-pools), stale-source freshness note (time-boxed
  wording), title corrections from source captions.

**Descoped — emitted as propose-in-UI notes, never spec changes** (all
trial-proven spec-unsupported): chart-as-filter (`useAsFilter` silently dropped
on readback), pie percent labels (`valueFormat:'percent'` silently dropped).
DM-metric promotion is not an enhancement candidate: the normal workbook build
already binds formula-equivalent, readback-confirmed metrics through
`[Metrics/<metric name>]`. `[Master/<metric>]` is an invalid column lookup, not
evidence that data-model metrics are unavailable.

### Prerequisites for apply

`enhance-apply.rb` needs `scripts/lib/{sigma_rest,code_rep,layout_lint,control_lint}.rb`.
Layout banding/placement also needs `scripts/lib/layout.rb` (lazy-loaded). Skills
without `layout.rb` can still run scan/select/app-plan; apply aborts with a clear
message if a patch needs banding and layout is missing. Spec-only patches
(formula / rename / prop) do not require `layout.rb`.

### Phase E layout placement + HARD screenshot checklist

Every applied item lands in the **container system** — never appended at the
page foot (that was the "PHASEE PBI Employee Dashboard" regression):

- selection controls → the **control band** (created under the header if the
  clone lacks one);
- comparison KPIs → the **KPI band**;
- grain/drill switchers → a slim row **inside the container of the chart they
  drive**;
- migration/freshness notes → a **slim note band directly under the header**.

If the cloned parity workbook predates container layouts (no `<Container>`
in its layout), `enhance-apply.rb` **regenerates a banded layout** for the
clone first (builder machinery, `scripts/lib/layout.rb`), then applies items.
The finalize runs the shared layout lint (`scripts/lib/layout_lint.rb`: no
raw-id display names, no controls outside containers, no dead zones, no
generic header-band title — "Page 1"/"Sheet N"/"Dashboard N" never titles a
dashboard; the header carries the promoted source title → source display
name → workbook name — and no band whose elements fill <60% of the grid
columns, KPI bands of ≤4 tiles exempt) and
**exits 4 on violations** — a lint-failing clone must be fixed and re-PUT
before the run may be declared done.

**HARD screenshot checklist (mandatory at finalize).** The lint is mechanical;
your eyes are the last gate. Export the clone's **full-page PNG**
(`scripts/sigma-export-png.py`) and verify EVERY item, listing each with
pass/fail in your report:

- [ ] every chart/control title is human-readable (no raw element ids)
- [ ] the page has a header band (dark, full-width, carrying the SOURCE title
      or display name — never a generic "Page 1")
- [ ] selection controls sit together in a control band near the top
- [ ] every control is adjacent to / inside the container of what it filters
      (grain/drill switchers INSIDE their chart's container)
- [ ] no orphan elements below the fold (nothing dumped at the page foot)
- [ ] no dead zones; row heights look even across each band
