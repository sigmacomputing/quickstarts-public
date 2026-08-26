# Workbook-as-code release mappings and gaps

Domo mappings for the Aug-2026 Sigma workbook code representation:

| Domo semantic | Sigma release surface | Converter status |
|---|---|---|
| Waterfall card | `waterfall-chart` | Gap: no confirmed Domo `chartType` token and role payload in discovery. The released target is not enough to justify guessing source intent. |
| Card legend | chart `legend`; `controlType:legend` | Gap: normalized card definitions do not expose a grounded visibility/position or shared-legend binding. Keep Sigma defaults; do not invent a legend control. |
| `allowTableDrill` / `drillPath` | `controlType:drill` | Gap: drill intent is captured, but no complete ordered hierarchy plus target wiring is grounded. Retain the base chart and warn. |
| Domo pages | metadata pages + `navigation` + view-mode page tabs | Native for multiple discovered pages: auto navigation is emitted on every content page. |
| `pageLayoutV4` `PAGE_BREAK` | `page-break` | Native only for an explicit authored template entry. Geometry alone never becomes a print break. |
| Filled gauge with `CURRENT` + `TARGET` roles | `progress` | Native ring progress with zero minimum when both roles exist and no card-local filter/date window must be preserved; otherwise KPI fallback with a loud gap. |
| Page filter-bar chrome | document `panels` | Gap: `showFilterBar` provides no filter definitions or panel binding. No empty panel/control is fabricated. |
| Literal canvas/palette signals | `settings.theme.overrides` | Native only for literal discovered colors. Dynamic or inferred styling remains a visual-review gap. |
| `pageLayoutV4` `HEADER` | text element + layout | Native for non-empty authored header content at captured geometry. |
| Tabbed alternate views | `tabbed-container` | Source gap: discovery has no grounded tab labels and child membership. Domo pages remain pages, not tabs in a container. |
| Data-bound repeated cards | `repeated-container` | Source gap: ordinary Domo cards/collections are static layout and must not be reinterpreted as repeaters. |
| Box-and-whisker | `box-chart` | Release-gated and source-ungrounded. Never emit until workspace entitlement and the Domo token/roles are verified. |

Workbook requests use outer metadata plus a nested `document`. Workbook pages
are metadata-only, elements are document-global, and `document.layout` is
required and authoritative for page membership. Domo layout emitters write the
live `<Element>` and `<Container>` tags. `LayoutElement` and `GridContainer`
exist only as read compatibility for old artifacts and must be canonicalized
before verify, POST, or PUT. Data-model code representation is unchanged and
continues to use nested `pages[].elements`.
