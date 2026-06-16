# Readout layout — `readout.html`

`scripts/render-readout-html.rb` emits a Sigma-branded HTML report whose theme
(palette, fonts, `.brand-bar` masthead, table/bar/risk-chip/tag CSS) is
byte-identical to the `tableau-assessment` gold standard. ThoughtSpot vocabulary
throughout: Liveboard / Answer, model / worksheet, table, connection, Embrace vs
Falcon, TML formula.

## Masthead + hero

- **Brand masthead** — `sigma` brand-mark + "Migration Assessment" tag.
- **Doc header** — eyebrow "ThoughtSpot Environment Report", instance host as
  title, generated date.
- **Hero headline finding** — the single most actionable sentence. On a populated
  instance: top-5 pilot usage share + count of Liveboards needing chart-type
  review. Without usage: count of readable Liveboards ranked by effort.

## Sections

| # | Title | Content |
|---|---|---|
| 01 | Environment overview | KPI tiles: Liveboards (readable / system-locked), Answers, models/worksheets, tables (file-uploaded count), connections (Embrace / Falcon), total views |
| 02 | Liveboard priority & usage | Top-10 usage-ranked with bars from `TS: BI Server`; author, distinct users, viz count; cold / zero-view detection note. Falls back to listed order + a note if usage absent |
| 03 | Ownership & concentration | Liveboards by author with bars; top-author concentration % |
| 04 | Data-source patterns | Stat tiles Embrace / Falcon / file-uploaded; connection table with connector-class badges; file-uploaded tables flagged for warehouse landing |
| 05 | User activity | Per-user action volume bars — **only rendered when `TS: BI Server` usage is present** (renumbers subsequent sections) |
| 06* | Migration to Sigma — recommended sequence | Stat tiles (top-5 usage share, chart types to review, needs-review · retire counts); value/cost shortlist with risk chips + tag pills; per-Liveboard complexity table (viz, chart kinds, models, TML formulas, complexity, review); chart-type coverage bars; referenced-models note; unsupported-chart callout |
| 07* | Data handling | Two-column privacy: read-by-scanner vs never-left-environment |
| 08* | Recommended next steps | Numbered: pilot top-5, migrate referenced models first, land Falcon/file sources in warehouse, plan review time, retire cold Liveboards |

\* Section numbers shift down by one when the optional User activity section (05)
is absent — the renderer computes the numbering so the sequence is always
contiguous.

## Conversion-risk legend (shortlist)

- **No issues** — every chart type and field converts automatically
- **N formulas** — converts automatically; TML formulas translate to Sigma
  formulas with a quick check
- **N chart types to review** — uses a chart kind without a 1:1 Sigma mapping yet

## Tag pills (recommendation column)

`migrate-first` (go) · `easy-win` (blue) · `moderate`/Standard (gray) ·
`needs-gap-scout`/Needs review (warn) · `retire` (mute) — same `TAG_LABELS` /
`TAG_CLASSES` mapping as the other assessment renderers.
