# Sample readout — synthetic QuickSight account fixture

A committed end-to-end run of `quicksight-assessment` against a **synthetic**
`inventory.json` (account `153722385948`), so the skill's output shape is
reviewable without an AWS account. The `inventory.json` here is hand-authored to
exercise the three complexity profiles; the four downstream artifacts
(`complexity.json`, `shortlist.json`, `migration-plan.json`, `readout.md`) are
the **real** output of the Ruby pipeline run over it.

Regenerate with:

```bash
ruby scripts/score-quicksight-complexity.rb --out fixtures/sample-readout
ruby scripts/build-shortlist.rb            --out fixtures/sample-readout
ruby scripts/migration-plan.rb             --out fixtures/sample-readout
ruby scripts/render-readout.rb             --out fixtures/sample-readout
```

## What this run shows

- **3 analyses, 2 datasets, 1 Snowflake data source.** Enterprise edition (the
  definition APIs succeeded), so complexity is fully scored.
- **`Orders Overview`** — the happy path: 5 built visuals (KPI/bar/line/pie), 3
  mechanical calc fields, no window funcs → ranks highest, `recommended_path:
  quicksight-to-sigma`.
- **`Sales Deep Dive`** — mid-catalog visuals (table, pivot, combo), a join +
  transforms, 1 window calc, RLS dataset → `needs-gap-scout`.
- **`Exec ML Board`** — the hard case: InsightVisual (ML) + geospatial map +
  sankey + 3 window calcs + free-form layout → mostly unhandled,
  `needs-gap-scout`.
- **Complexity-only mode** (no `usage.json`), so the readout carries the
  limited-mode banner and the value basis is the `sheets + visuals/4` proxy.
- **DM clustering** unions all three analyses into one cluster: they transitively
  share `ds-orders-enriched` (Orders Overview + Exec ML Board reference it
  directly; Sales Deep Dive references it alongside Customers), so they belong on
  one Sigma data model.

This validates the shared scoring + tag vocabulary, the Standard-edition /
limited-mode banner logic, and the shared-dataset clustering.
