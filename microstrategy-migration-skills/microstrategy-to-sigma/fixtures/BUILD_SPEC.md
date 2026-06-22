# "Orders Analytics Workbench" — dossier build spec (Library UI)

Goal: one big dossier exercising every visualization type the Library gallery
offers, all on live Snowflake data, as the migration-converter fixture.
REST cannot author visualizations, so this is ~30 min of drag-and-drop.

**Dataset:** every page uses the report **`Orders Wide Dataset`**
(Public Objects → Reports). When creating the dossier: ⊕ New Dashboard →
Add Data → Existing Dataset → Orders Wide Dataset.
It has 15 attributes (Region, State, Store, Store Type, Category, Subcategory,
Brand, Customer Segment, Loyalty Tier, Year, Month, Day, Order Channel,
Ship Method, Order Status) and 12 metrics (Total Net Revenue, Total Gross
Profit, Profit Margin Pct, Units Sold, Order Count, Avg Unit Price, Total
Discount, Total Shipping, Units Returned, Customer Count, Avg Order Value,
Return Rate).

Name the dossier **Orders Analytics Workbench**, save into Public Objects → Reports.

If a viz type below isn't in your gallery, skip it and note which.

## Page 1 — Revenue Overview
| # | Viz type | Slots |
|---|----------|-------|
| 1 | KPI | Metric: Total Net Revenue |
| 2 | Multi-Metric KPI | Metrics: Total Net Revenue, Order Count, Units Sold, Avg Order Value |
| 3 | Bar (vertical clustered) | Vertical: Total Net Revenue · Horizontal: Region · Color By: Category |
| 4 | Bar (stacked) | Vertical: Total Net Revenue · Horizontal: Order Channel · Color By: Category (Stacked) |
| 5 | Line | Vertical: Total Net Revenue · Horizontal: Month (sorted by ID) · Break By: Year |
| 6 | Area | Vertical: Units Sold · Horizontal: Month |

## Page 2 — Product & Mix
| # | Viz type | Slots |
|---|----------|-------|
| 7 | Pie | Angle: Total Net Revenue · Slice: Category |
| 8 | Ring/Donut | Angle: Order Count · Slice: Loyalty Tier |
| 9 | Heat Map | Grouping: Category, Subcategory · Size By: Total Net Revenue · Color By: Profit Margin Pct |
| 10 | Combo | Vertical L: Total Net Revenue (bar) · Vertical R: Profit Margin Pct (line) · Horizontal: Month |
| 11 | Grid | Rows: Brand · Metrics: all 12 — then add a **threshold** (e.g. Profit Margin Pct < 0.5 red) |

## Page 3 — Statistical
| # | Viz type | Slots |
|---|----------|-------|
| 12 | Scatter | X: Avg Unit Price · Y: Units Sold · Group/point: Product? not in dataset — use Subcategory · Color: Category |
| 13 | Bubble | X: Total Net Revenue · Y: Profit Margin Pct · Size: Units Sold · Group: Store · Color: Region |
| 14 | Histogram | Metric: Avg Order Value · binning default (per Store) |
| 15 | Box Plot | Y: Total Net Revenue · Group: Region · point = Store |
| 16 | Waterfall | Vertical: Total Net Revenue · Horizontal: Category |

## Page 4 — Geo, Flow & Text
| # | Viz type | Slots |
|---|----------|-------|
| 17 | Map (Geospatial / ESRI) | Geo attribute: State (set Geo Role → State when prompted) · Color: Total Net Revenue |
| 18 | Sankey (if present) | From: Region · To: Order Channel · Weight: Units Sold |
| 19 | Network (if present) | From: Category · To: Brand · Weight: Order Count |
| 20 | Funnel (if present) | Stage: Order Status · Metric: Order Count |
| 21 | Word Cloud (if present) | Word: Brand · Size: Total Net Revenue |
| 22 | Text box + Image | any title text + any image (free-form `fields` coverage) |

## Dossier-level features (converter coverage beyond viz types)
- **Chapter filter:** add Year as a filter (All / 2026).
- **Selector/panel:** put vizzes 7–8 in a Panel Stack with a panel selector.
- **Attribute selector** targeting viz 3 (e.g. element selector on Region).
- Rename chapters: "Overview", "Product", "Statistical", "Geo & Flow".

When done, tell Claude — extraction + Sigma migration take it from there.
