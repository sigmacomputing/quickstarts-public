# Domo page layout — the v4 grid

**Status:** confirmed against two independent live Domo instances (2026-07-30). The
second was validated by a partner SE against their own tenant with a dev token, which
is why the page-style taxonomy below is broader than a single-tenant sample.

Supersedes the claim in `refs/live-validation-2026-07-30.md` that layout geometry is
UI-only. It is not. It is readable, and on a v4 page it is exact.

## Three page styles

| Style | How to tell | Where geometry lives |
|---|---|---|
| **v4-inline** (newer pages) | `pageLayoutV4` present in the stacks response when `includeV4PageLayouts=true` | `pageLayoutV4.standard.template[]` |
| **legacy** (older pages) | no `pageLayoutV4` | `sizes[]` — ordered `{id, size}`, `size` is `""` / `"large"` / `"full"`; cards flow in array order |
| **v4-separate** | no inline `pageLayoutV4`, but a layoutId exists | `GET /api/content/v4/pages/layouts/{layoutId}` |

Only the first two are observed live. v4-separate appears in Domo's own Postman
collection; treat it as real but unverified until we see one.

## The shape

```json
{
  "pageLayoutV4": {
    "layoutId": 1039237476,
    "isDynamic": false,
    "content": [ { "contentKey": 1, "cardId": 757225475, "type": "CARD" } ],
    "standard": {
      "width": 60,
      "template": [
        { "contentKey": 4, "x": 0,  "y": 5, "width": 11, "height": 14, "type": "CARD" },
        { "contentKey": 0, "x": 11, "y": 5, "width": 8,  "height": 14, "type": "CARD" }
      ]
    },
    "compact": { "width": 12, "template": [] }
  }
}
```

- `content[]` maps `contentKey` → `cardId`.
- `standard.template[]` maps `contentKey` → `x` / `y` / `width` / `height`.
- **Join them on `contentKey`.** Neither array alone gives you card-id + position.
- **Grid is 60 wide** (`standard.width`). `compact` is the 12-wide mobile grid — use
  `standard`. Domo 60 → Sigma 24 is **×0.4**.
- `content[]` entries with `type: "HEADER"` carry a `text` field and NO `cardId` —
  these are Domo's named section dividers, and they get x/y/w/h in
  `standard.template` like anything else. `pagelayoutv4_content` preserves them
  as authored text elements at their real positions.
- `PAGE_BREAK` entries also appear in `standard.template`; they map to the
  released Sigma `page-break` element and are fixed to one grid row in the
  authoritative layout. No page break is inferred from geometry alone.

## Two defects — fixed

Both verified by reading the source, not assumed, and now fixed (`Domo.cards_for_page`
requests `includeV4PageLayouts=true`; `DomoSigma.merge_pagelayoutv4_geometry` performs the
join below):

1. **`scripts/lib/domo_rest.rb`, `cards_for_page`** — used to send only `parts`.
   Without `includeV4PageLayouts=true` a v4-inline page returned no `pageLayoutV4`
   at all, so every such page fell through to the default-composition rung
   unnecessarily.

2. **`scripts/lib/domo_sigma_util.rb`, was at the top of what is now
   `merge_xywh_geometry`** — used to read
   `page_layout['cards'] || page_layout.dig('pageLayoutV4', 'cards')`.
   There is no `cards` key under `pageLayoutV4`; the geometry is under
   `standard.template`. **That dig could never match**, so the v4 branch was dead
   code that silently yielded nothing. It also read from the separate layout
   endpoint's response, whereas the v4 data arrives on the *stacks* response.

The join, once both are fixed:

```ruby
content_map = {}
Array(stacks.dig('pageLayoutV4', 'content')).each do |c|
  content_map[c['contentKey']] = c['cardId'].to_s if c['cardId']
end

Array(stacks.dig('pageLayoutV4', 'standard', 'template')).each do |t|
  card_id = content_map[t['contentKey']]
  next unless card_id
  geom_by_id[card_id] = { 'x' => t['x'], 'y' => t['y'],
                          'w' => t['width'], 'h' => t['height'] }
end
```

## Endpoints

```
GET /api/content/v3/stacks/{pageId}/cards
      ?includeV4PageLayouts=true
      &parts=metadata,datasources,...
      &stackLoadContext=Page&stackLoadContextId={pageId}&stackLoadTrigger=page-view

GET /api/content/v4/pages/layouts/{layoutId}                  # v4-separate style
GET /api/content/v4/pages/layouts/{layoutId}/sectionState     # seen in HAR; purpose TBD
```

## Why this matters

Pages that would otherwise fall through to kind-aware default composition get
real coordinates, widths, section headers, and authored print breaks. The
screenshot / `layout-observed.json` rung stays, but becomes the fallback for
genuinely legacy pages rather than the only route to fidelity.
