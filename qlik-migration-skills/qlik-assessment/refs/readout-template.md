# Qlik Cloud Assessment — readout section template

`render-readout-html.rb` composes `readout.html` deterministically from
`inventory.json`. Sections below match the gold-standard `tableau-assessment` /
`powerbi-assessment` HTML readouts so the look is byte-identical; only the
vocabulary is Qlik-specific. Placeholders in `{{ }}` come straight from the JSON.

The masthead is always `sigma · Migration Assessment` with the eyebrow
`Qlik Cloud Environment Report` and the tenant name as the H1.

---

## Hero — Headline finding

One sentence. If the top-5 pilot has zero unhandled features and at least one
`migrate-first` app: "Pilot migration is low-risk…". Else if any unhandled
features exist: names the count of apps needing review (Set Analysis, Aggr(),
alternate states). Else a neutral summary.

---

## 01. Environment overview

Six KPI tiles: **Apps**, **Sheets**, **Master measures**, **Spaces**,
**Data connections**, **Total app views** (sub-label: `28-day rolling window`).

---

## 02. App priority & usage

Top 10 apps ranked by `itemViews`, with a bar cell, owner, and a Flags cell
(Section Access / DirectQuery inline pills). Always followed by the note that
`itemViews` is a **28-day rolling window**, not all-time. Cold apps (zero views)
are listed as retirement candidates.

---

## 03. Ownership & concentration

Apps-by-owner table (bar on apps; views + master measures as numeric columns).
Note line states the top-owner concentration percentage — a governance signal.

---

## 04. Data sources & load-script patterns

Three stat tiles: **DirectQuery apps** (drop-in to a Sigma connection),
**In-memory apps** (reload from QVD/file/warehouse extract), **File-based
connections** (QVD/CSV/Excel — land in warehouse first). Then a connection-type
table (warehouse/live vs file-based badges). A callout fires when any app uses
**Section Access** (row-level security → Sigma column/row-level security).

---

## 05. Reload activity

Reload-status table (succeeded/failed/unknown counts) plus average and max
last-reload duration. Frames reloads as migration motivation: Sigma queries the
warehouse live and removes the reload step.

---

## 06. Migration to Sigma — recommended sequence  *(shortlist mode only)*

Three stat tiles: **Top-5 tenant usage share** (`{{top5_pct}}%`), **Top-5
conversion complexity** (`{{sl_top5_unhandled}}` features to review), **Needs
review · Retire** counts. Then the shortlist table (App, Views bar, Conversion
risk chip, Score, Recommendation pill) with the risk legend, an optional callout
when unhandled features exist, and a **Per-app complexity** sub-table (master
measures, charts, Auto / Setup / Review counts).

Risk chip + recommendation tags use the shared `TAG_LABELS` / `TAG_CLASSES` /
risk-chip helpers: `migrate-first`→Migrate first (green), `easy-win`→Easy win
(blue), `moderate`→Standard (gray), `needs-gap-scout`→Needs review (amber),
`retire`→Retire (mute).

---

## 07. Data handling

Two-column privacy grid. **Read by the scanner**: aggregate counts, app/owner
names, space IDs, reload + `itemViews`, and (deep mode) master-measure
expressions + chart definitions. **Never left your environment**: warehouse
rows, QVD/in-memory extracts, credentials, Section Access rules verbatim.

---

## 08. Recommended next steps

Numbered list. Shortlist mode: pilot the top 5, plan review time for
`needs-gap-scout` apps, retire zero-view apps, hand off to `qlik-to-sigma`
(feed it the Qlik *model*, not the warehouse). Inventory-only mode: re-run with
`--deep`, then hand off.

Section numbering: 06–08 in shortlist mode; collapses to 06–07 (data handling +
next steps) when no shortlist is present.
