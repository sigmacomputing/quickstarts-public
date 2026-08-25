# Shared helpers for the Domo→Sigma build scripts (build-dm.rb, build-workbook.rb).
# Kept in one place so display-name derivation is IDENTICAL across the DM columns
# and the workbook column references — a mismatch compiles Sigma columns to type
# "error" (case-sensitive same-element refs).

module DomoSigma
  module_function

  # Clean a raw identifier to a Sigma display name (mirrors the converter's
  # sigmaDisplayName). Idempotent: display_name(display_name(x)) == display_name(x).
  def display_name(raw)
    s = raw.to_s
           .gsub(/([a-z])([A-Z])/, '\1_\2')
           .gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
           .gsub(/([A-Za-z])([0-9])/, '\1_\2')
           .gsub(/([0-9])([A-Za-z])/, '\1_\2')
    s.split(%r{[_\s/]+}).reject(&:empty?).map { |w|
      (w =~ /\A[A-Z0-9]+\z/) ? w : w.capitalize
    }.join(' ')
  end

  B62 = (('0'..'9').to_a + ('a'..'z').to_a + ('A'..'Z').to_a).freeze

  # Client-side id. Sigma preserves client IDs on CREATE (feedback_sigma_spec_id_stability).
  def rand_id(len = 10)
    Array.new(len) { B62.sample }.join
  end

  def inode_id(col)
    "inode-#{rand_id(22)}/#{col.to_s.upcase}"
  end

  # Master-column id from a display name — MUST match build-workbook-spec.rb's
  # auto-master slug (m-<slug>) so control filters can target the master column.
  def mcol_id(display)
    "m-#{display.to_s.downcase.gsub(/\W+/, '-').sub(/-$/, '')}"
  end

  # Domo number-format object → Sigma column format. Falls back to a name heuristic
  # (the same precedence the Tableau KPI emitter uses) ONLY to pick a category
  # (currency/percent/number) — never to build a format string.
  #
  # Field-proven shape only: {kind:"number", decimalPlaces:N} POSTs cleanly
  # (a d3/Excel formatString can 400). Sigma's documented format schema
  # (sigma-workbooks/reference/specification/formatting.md) has no distinct
  # currency/percent `kind` — just `kind: number` with an optional raw
  # formatString or structured fields (currencySymbol, prefix, …) that have
  # NOT been field-verified in combination with decimalPlaces. So currency
  # and percent are classified (for future use) but, absent a documented/
  # verified currency|percent shape, both fall back to the same proven
  # {kind:"number", decimalPlaces:prec} rather than guessing.
  def sigma_format(domo_fmt, name = nil)
    prec = (domo_fmt.is_a?(Hash) && (domo_fmt['precision'] || domo_fmt['decimals'])) || 0
    type = domo_fmt.is_a?(Hash) ? (domo_fmt['type'] || domo_fmt['format']).to_s.upcase : ''
    category =
      case type
      when 'CURRENCY', 'MONEY'                            then :currency
      when 'PERCENT', 'PERCENTAGE'                        then :percent
      when 'COMMA', 'NUMBER', 'DECIMAL', 'LONG', 'DOUBLE'  then :number
      else
        n = name.to_s.downcase
        if    n =~ /revenue|sales|profit|cost|amount|budget|price|\$/ then :currency
        elsif n =~ /rate|percent|pct|%|margin|ratio|share/            then :percent
        elsif !type.empty? || domo_fmt.is_a?(Hash)                    then :number
        end
      end
    return nil unless category
    { 'kind' => 'number', 'decimalPlaces' => prec }
  end

  # Does this column name look like a row-key / id (the Domo table-summary COUNT trap)?
  def id_like?(name)
    n = name.to_s.downcase
    n == 'id' || n =~ /(^|[_ ])id$/ || n =~ /\bkey$/ || n =~ /\buuid\b/
  end

  # C9: extract Domo PDP (personalized data permission) policies from a DataSet
  # metadata object (fetched with parts=core,permission). Returns [] when none —
  # the caller (build-dm.rb) must warn + stub, never silently drop row-level security.
  def detect_pdp(dataset)
    perm = dataset['permission'] || dataset['pdp'] || {}
    (perm['policies'] || []).map do |p|
      { 'id' => p['id'].to_s, 'name' => (p['name'] || p['id']).to_s,
        'predicates' => Array(p['predicates']) }
    end
  end

  # Merge Domo page-layout geometry onto each card record by id — ports
  # domo-capture-visuals.rb's normalize_layout coordinate extraction so
  # domo-discover.rb's --pages path (not just the OPTIONAL capture-visuals
  # script) hands build-domo-layout.rb real layout instead of forcing it to
  # auto-stack every card.
  #
  # Bug 5 (P0, refs/live-validation-2026-07-30.md): CLASSIC Domo pages carry NO
  # x/y/w/h pixel geometry anywhere. What a live `GET
  # /api/content/v3/stacks/{pageId}/cards` response (Domo.cards_for_page, the
  # PRIMARY card-enumeration route — see domo-discover.rb's
  # enumerate_page_cards) actually gives you for layout is:
  #
  #   sizes[]       = [{"id"=>"<cardId>", "size"=>"medium"}, ...]
  #                   — a T-SHIRT-SIZE TOKEN per card (small/medium/large/...),
  #                   NOT pixels or a column span number.
  #   collections[] = [{"id"=>.., "title"=>"Section Name", "description"=>..,
  #                      "minimized"=>false, "cardIndices"=>[0,1,2,3]}, ...]
  #                   — titled sections that group cards BY INDEX into the
  #                   stacks response's OWN `cards[]` array (NOT by card id).
  #                   An API-created page has collections: [] and just an
  #                   ordered `sizes[]` entry per card — no sections at all.
  #
  # This method merges BOTH kinds of geometry onto each card record by id, and
  # keeps them independent so either can be present, absent, or both:
  #
  #   - legacy 'x'/'y'/'w'/'h' (mason / Domo-App pages, pixel-ish grid coords)
  #     — sourced from `page_layout`, UNCHANGED behavior from before this fix.
  #   - '_size'        — the T-shirt token, from `stacks['sizes']`, keyed by
  #                       card id.
  #   - '_collection'  — {'id','title','index'} for the collection (if any)
  #                       this card falls in. `index` is the card's 0-based
  #                       position in the `cards` ARGUMENT passed to this
  #                       method (NOT its id) — domo-discover.rb guarantees
  #                       that position matches the stacks response's own
  #                       `cards[]` order, since it builds the card list by
  #                       walking that same array in order. Omitted (never
  #                       defaulted) when the card's index isn't inside any
  #                       collection's `cardIndices` (e.g. collections: [] on
  #                       an API-created page).
  #   - '_pageOrder'   — that same 0-based index, ALWAYS attached whenever
  #                       `stacks` is given (regardless of collection
  #                       membership), so the layout builder has an explicit
  #                       ordering signal even on a page with zero collections.
  #
  # build-domo-layout.rb (owned by another agent) is the consumer of all of
  # this — this method only DEFINES and documents the shape on discovery's
  # output; it does not lay anything out itself.
  #
  # Pure/side-effect-free in both passes: returns a NEW array; a card with no
  # matching entry in a given source is left unchanged by that source's pass —
  # 'x'/'y'/'w'/'h' are OMITTED, never defaulted to 0 (0 is a valid top-left
  # coordinate and must not be confused with "unknown").
  def merge_geometry(cards, page_layout, stacks: nil)
    out = Array(cards)
    out = merge_xywh_geometry(out, page_layout)
    out = merge_stacks_geometry(out, stacks)
    out
  end

  # --- x/y/w/h pass (mason / Domo-App pages) — unchanged from before Bug 5 --
  def merge_xywh_geometry(cards, page_layout)
    return cards unless page_layout.is_a?(Hash)

    raw_cards = page_layout['cards'] || page_layout.dig('pageLayoutV4', 'cards') || []
    geom_by_id = {}
    Array(raw_cards).each do |c|
      next unless c.is_a?(Hash)
      id = c['id'] || c['cardId'] || c['urn']
      next unless id
      geom = c['layout'].is_a?(Hash) ? c['layout'] : c # geometry sometimes nested under "layout"
      geom_by_id[id.to_s] = {
        'x' => geom['x']     || geom['col']    || geom['gridX'],
        'y' => geom['y']     || geom['row']    || geom['gridY'],
        'w' => geom['w']     || geom['width']  || geom['colSpan'] || geom['sizeX'],
        'h' => geom['h']     || geom['height'] || geom['rowSpan'] || geom['sizeY'],
      }
    end

    cards.map do |card|
      next card unless card.is_a?(Hash)
      geom = geom_by_id[card['id'].to_s]
      next card unless geom
      coords = geom.each_with_object({}) { |(k, v), h| h[k] = v.to_i unless v.nil? }
      coords.empty? ? card : card.merge(coords)
    end
  end

  # --- sizes[] / collections[] pass (classic pages) — Bug 5 -----------------
  def merge_stacks_geometry(cards, stacks)
    return cards unless stacks.is_a?(Hash)

    size_by_id = {}
    Array(stacks['sizes']).each do |s|
      next unless s.is_a?(Hash) && s['id']
      size_by_id[s['id'].to_s] = s['size']
    end

    collection_by_index = {}
    Array(stacks['collections']).each do |col|
      next unless col.is_a?(Hash)
      Array(col['cardIndices']).each do |idx|
        collection_by_index[idx] = { 'id' => col['id'], 'title' => col['title'], 'index' => idx }
      end
    end

    cards.each_with_index.map do |card, idx|
      next card unless card.is_a?(Hash)
      extra = {}
      size = size_by_id[card['id'].to_s]
      extra['_size'] = size if size
      coll = collection_by_index[idx]
      extra['_collection'] = coll if coll
      extra['_pageOrder'] = idx
      extra.empty? ? card : card.merge(extra)
    end
  end
end
