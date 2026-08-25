#!/usr/bin/env ruby
# Phase 1 discovery for domo-to-sigma.
#
#   ruby scripts/domo-discover.rb --probe              # detect extraction tier (A/B)
#   ruby scripts/domo-discover.rb --pages 123,456      # discover specific dashboards
#   ruby scripts/domo-discover.rb --datasets           # list all DataSets
#
# Writes discovery/*.json. PUBLIC-API paths follow Domo's documented API. PRIVATE
# card-definition shapes are confirmed against Domo's OpenAPI ("Get Chart Card
# Definition") + three production reference impls (jsade/domo-query-cli,
# brycewc/domo-toolkit, newli5737/domo-chousa); do a final field-path check on
# first contact with a live instance.
#
# Domo returns a card definition in TWO different shapes with different field
# names; normalize_card() below detects and flattens both into ONE record that the
# build steps (build-dm.rb / build-workbook.rb) consume:
#   Shape A — official "CardDefinition": chartBody/summaryNumber Components,
#             chartType, calculatedFields, conditionalFormats.
#   Shape B — internal analyzer def (definition.subscriptions.main.*,
#             definition.formulas[]); beast-mode refs are "calculation_<uuid>" ids.
#
# Prereqs (see refs/connection.md):
#   export DOMO_CLIENT_ID=... DOMO_CLIENT_SECRET=... DOMO_INSTANCE=acme
#   export DOMO_DEV_TOKEN=...        # omit for Tier B (public only)
#   eval "$(scripts/get-domo-token.sh)"   # sets DOMO_ACCESS_TOKEN

require 'json'
require 'fileutils'
require 'optparse'
require_relative 'lib/domo_rest'
require_relative 'lib/domo_sigma_util'
include DomoSigma   # merge_geometry — shared with build-domo-layout.rb

OUT = ENV['DOMO_DISCOVERY_DIR'] || File.expand_path('../discovery', __dir__)
FileUtils.mkdir_p(OUT)

def dump(name, obj)
  path = File.join(OUT, name)
  File.write(path, JSON.pretty_generate(obj))
  warn "  wrote #{path} (#{obj.is_a?(Array) ? obj.size : obj.keys.size} entries)"
end

# ---------------------------------------------------------------------------
# Beast Mode id prefix that card columns/filters use to reference a calc field.
CALC_PREFIX = 'calculation_'

# Map a Domo chartType token (a FREE STRING — no enum) to a Sigma element kind by
# substring. Returns nil when the token is unknown; the build step then reads the
# card PNG (refs/card-to-element.md: the render is authoritative). A summary-number
# card is decided as KPI in the build step, not here.
def sigma_kind_hint(chart_type)
  t = chart_type.to_s.downcase
  return 'kpi-chart'    if t.include?('singlevalue') || t.include?('summary') ||
                           t.include?('gauge') || t == 'badge'
  return 'pivot-table'  if t.include?('pivot')
  return 'table'        if t.include?('datagrid') || t.include?('table')
  return 'bar-chart'    if t.include?('bar')
  return 'line-chart'   if t.include?('line')
  return 'area-chart'   if t.include?('area')
  return 'donut-chart'  if t.include?('pie') || t.include?('donut')
  return 'scatter-chart' if t.include?('scatter') || t.include?('bubble')
  return 'combo-chart'  if t.include?('combo') || t.include?('barline')
  nil
end

# Function-CALL-shape regexes (Bug C): an identifier immediately followed by
# an open paren, never a bare substring match. Domo columns are BACKTICK-quoted
# (MySQL dialect) — `` `SUMMARY` `` — so a column literally named e.g. SUMMARY
# can never satisfy "SUM" + "(" immediately after; a real function call always
# has the paren right there (optionally with whitespace: "SUM (x)" is valid
# SQL). Case-insensitive — Domo's SQL is not case-normalized.
AGGREGATE_FN_RE = /\b(SUM|COUNT|AVG|MIN|MAX|MEDIAN|STDDEV|STDDEV_POP|STDDEV_SAMP|VARIANCE|
                      VAR_POP|VAR_SAMP|CEILING|FLOOR|APPROXIMATE_COUNT_DISTINCT)\s*\(/ix
WINDOW_FN_RE     = /\bOVER\s*\(|\b(RANK|DENSE_RANK|ROW_NUMBER|LAG|LEAD|NTILE|PERCENT_RANK|CUME_DIST)\s*\(/i

def sql_has_aggregate_call?(sql)
  !!(sql.to_s =~ AGGREGATE_FN_RE)
end

def sql_has_window_construct?(sql)
  !!(sql.to_s =~ WINDOW_FN_RE)
end

# Classify a Beast Mode as aggregate | window | lod | projection. `template`
# may be EITHER an inline formula entry (Bug 4: definition.formulas[] on the
# card, or a dataset's properties.formulas.formulas map value — keyed
# isAnalytic/isAggregatable, confirmed live) OR a standalone function-template
# fetch (keyed analytic/aggregated — the older, pre-live-validation field
# names). Both are accepted here so callers can pass whichever they have.
#
# BUG C (live-validated 2026-07-30, refs/live-validation-2026-07-30.md):
# Domo's OWN isAnalytic/isAggregatable flags are NOT trustworthy — all 4 Beast
# Modes on a live run reported isAggregatable:false, isAnalytic:false (this
# appears to be a Domo quirk specific to card-local calcs created via the
# public write API — see the "calculatedFields are referenced by name"
# section of the live-validation doc) despite formulas like
#   (CASE WHEN (SUM(`x`) = 0) THEN 0 ELSE (SUM(`y`) / SUM(`x`)) END )
#   (SUM(`x`) / COUNT(DISTINCT `y`))
# being plainly aggregates. The OLD code trusted a *present* flag pair
# absolutely and never looked at the SQL at all once template.is_a?(Hash) was
# true, so all four were misclassified 'projection' — silently wrong
# downstream (a calc column instead of a metric/aggregate expression).
#
# Fix: ALWAYS scan the SQL for a function-call-shaped aggregate/window
# construct, and let a positive SQL match override a `false` flag. A flag that
# says "yes" but the SQL scan can't corroborate is still honored (Domo may
# recognize constructs — e.g. a bucketed histogram — this regex heuristic
# can't see). Most-specific class wins: lod > window > aggregate > projection.
def classify_beast_mode(sql, template = nil)
  return 'lod' if sql.to_s =~ /\bFIXED\s*\(/i          # Domo LOD → Sigma LOD

  window_hint    = template.is_a?(Hash) && (template['isAnalytic'] || template['analytic'])
  aggregate_hint = template.is_a?(Hash) && (template['isAggregatable'] || template['aggregated'])

  return 'window'    if sql_has_window_construct?(sql) || window_hint
  return 'aggregate' if sql_has_aggregate_call?(sql) || aggregate_hint
  'projection'
end

# Bug 4: an inline Beast Mode entry ALREADY carries isAnalytic/isAggregatable
# — Domo's own classification of it — so PREFER that over an extra standalone
# function-template HTTP round-trip. Only fall back to fetch_template (the
# old behavior, still needed for a calc id a card references but that isn't
# inlined anywhere reachable) when NEITHER flag key is present on `f` at all
# (checked with key?, not truthiness — both flags legitimately being `false`
# still reaches classify_beast_mode, which (Bug C) cross-checks the SQL rather
# than taking a `false`/`false` pair as a settled "projection").
def classify_beast_mode_for(f, template_cache)
  sql = f['formula'] || f['expression']
  if f.key?('isAnalytic') || f.key?('isAggregatable')
    classify_beast_mode(sql, f)
  else
    tmpl = fetch_template(f['templateId'] || f['id'], template_cache)
    classify_beast_mode(sql, tmpl)
  end
end

# Normalize a Component's column list ({column,alias,aggregation,format,mapping})
# — used for chartBody, summaryNumber, groupBy, orderBy (Shape A DataSetColumn[])
# and Shape B's subscriptions.main/big_number columns.
#
# `mapping` is the VISUAL-ROLE binding (confirmed live, 10-value vocabulary:
# ITEM=category/x, VALUE=measure, SERIES=split, XTIME, BUBBLESIZE, CATEGORY,
# CURRENT, TARGET, DATE, EVENT). It used to be dropped entirely; surfacing it
# here is what lets build-workbook.rb bind axes/series instead of guessing
# column order.
# Resolve the DataSet a card is bound to.
#
# LIVE-VALIDATED FIX (2026-07-30): this used to read only `raw['dataSetId']` and
# `raw.dig('dataProvider','dataSourceId')`. NEITHER of those exists on a live
# response. The real binding is the `datasources` PART:
#   "datasources": [{"dataSourceId":"021e123b-…","dataSourceName":"Orders Fact",
#                    "displayType":"api","providerType":"api", …}]
# Consequence of getting this wrong was severe and silent: datasetId came back
# nil for 15/15 cards, and because dataset-level enrichment is keyed on it, the
# run skipped dataset Beast Modes, C9/PDP detection, AND the column-schema fetch
# — leaving build-dm.rb with no columns to build from at all.
#
# `card_meta` is the enumeration record (from the stacks/adminsummary route),
# which also carries `datasources` when fetched with parts=datasources — so a
# card def missing the part can still resolve.
def resolve_dataset_id(raw, card_meta = nil)
  sources = []
  [raw, card_meta].each do |h|
    next unless h.is_a?(Hash)
    sources.concat(Array(h['datasources']))
    sources.concat(Array(h['dataSources']))
  end
  from_part = sources.find { |s| s.is_a?(Hash) && (s['dataSourceId'] || s['id']) }
  (from_part && (from_part['dataSourceId'] || from_part['id'])) ||
    (raw.is_a?(Hash) && (raw['dataSetId'] || raw['dataSourceId'] ||
                         raw.dig('dataProvider', 'dataSourceId'))) ||
    (card_meta.is_a?(Hash) && (card_meta['dataSetId'] || card_meta['dataSourceId']))
end

def norm_columns(component, formulas: nil)
  by_id = {}
  Array(formulas).each { |f| by_id[f['id'].to_s] = f if f.is_a?(Hash) && f['id'] }

  Array(component && component['columns']).map do |c|
    raw = c['column'] || c['dataColumn'] || c['field']
    calc_id = raw.to_s.start_with?(CALC_PREFIX) ? raw : c['formulaId']

    # LIVE-VALIDATED FIX (2026-07-30): a chart-body column bound to a Beast Mode
    # carries `formulaId` and NO `column` — the same shape norm_summary_number
    # already handles. Left unresolved, `column` stayed nil and build-workbook
    # emitted a formula with an empty reference:
    #   pages[N].elements[M].columns[K].formula: Invalid formula: 'Sum([Master/])'
    # which Sigma rejects, taking down the ENTIRE workbook POST — one
    # Beast-Mode-bound axis/series column kills every other element too. Resolve
    # the id to the Beast Mode's NAME (that is the display name the DM calc
    # column gets) and flag it so downstream can tell a calc from a warehouse
    # column and skip it honestly when the formula never translated.
    if raw.to_s.empty? && calc_id && (f = by_id[calc_id.to_s])
      raw = f['name']
    end

    {
      'column'      => raw,
      'alias'       => c['alias'],                 # display label override (fixes raw-name bug)
      'aggregation' => c['aggregation'] || c['aggr'],
      # Domo expresses a DISTINCT count as aggregation:'COUNT' + distinct:true —
      # there is no COUNT_DISTINCT aggregation in its enum. Dropping this flag
      # silently turns CountDistinct into Count: live run showed Orders=877
      # (row count) where Domo showed 872 (distinct orders). A plausible-looking
      # WRONG number, which is worse than a hard failure.
      'distinct'    => (c['distinct'] ? true : nil),
      'format'      => c['format'] || c['numberFormat'],
      'order'       => c['order'],
      'mapping'     => c['mapping'],                # visual-role binding (Bug 2)
      # `calendar: true` marks a SYNTHETIC Domo grain pseudo-column
      # (CalendarMonth/CalendarWeek/...) that does NOT exist in the dataset —
      # the real column + grain live on the component's dateGrain. Preserve the
      # flag so build-workbook can emit a Sigma DateTrunc instead of a
      # reference to a column that isn't there.
      'calendar'    => (c['calendar'] ? true : nil),
      'beastModeId' => calc_id,
      '_isCalc'     => (calc_id ? true : nil),
    }.compact
  end
end

# Parse a JSON-encoded string with a rescue guard (Bug 3: metadata.
# SummaryNumberFormat / .columnAliases / .columnFormats are STRINGS containing
# JSON, not objects — they need a *second* JSON.parse). Returns nil for
# anything that isn't a non-empty String, or that fails to parse (malformed
# JSON on a live instance should degrade to "no data", never raise and abort
# discovery for one bad card).
def parse_json_string(s)
  return nil unless s.is_a?(String) && !s.strip.empty?
  JSON.parse(s)
rescue JSON::ParserError
  nil
end

# Read the parts-read card object's `metadata` block (Bug 3). `metadata.
# chartType` — NOT the card root — is where chartType actually lives on that
# endpoint; `columnAliases`/`columnFormats`/`SummaryNumberFormat` are
# JSON-encoded strings needing the second parse above.
#
# `card_meta` is whichever raw record the CALLER already has that might carry
# this `metadata` block — either the enumeration route's own per-card object
# (Domo.cards_for_page's `cards[]` entries carry full metadata inline, so on
# the common path this costs zero extra HTTP calls — see
# domo-discover.rb's enumerate_page_cards) or, when that's unavailable, `raw`
# itself in case the definition fetch fell back to the Shape-A parts read.
def parse_card_metadata(card_meta)
  md = card_meta.is_a?(Hash) ? card_meta['metadata'] : nil
  return {} unless md.is_a?(Hash)
  {
    'chartType'           => md['chartType'],
    'columnAliases'       => parse_json_string(md['columnAliases']),
    'columnFormats'       => parse_json_string(md['columnFormats']),
    'summaryNumberFormat' => parse_json_string(md['SummaryNumberFormat']),
  }.compact
end

# Resolve chartType across every confirmed location, most-authoritative first
# (Bug 3). `metadata.chartType` (from whichever source has it) wins; Shape B's
# OWN `definition.charts.main.chartType` is a same-call fallback (no extra
# HTTP — reliable on every card where the v3 analyzer fetch succeeded, even
# when the enumeration route didn't supply `metadata` — see
# enumerate_page_cards route 2/3); root-level `chartType` is kept last for the
# create-body shape (offline tests / any future write-body reuse).
def resolve_chart_type(raw, defn, meta)
  meta['chartType'] ||
    raw.dig('metadata', 'chartType') ||
    (defn && defn.dig('charts', 'main', 'chartType')) ||
    raw['chartType'] ||
    (defn && defn['chartType'])
end

# Normalize a card definition (either shape) into one record. `card_meta` is
# an OPTIONAL enumeration-route record for this card (see parse_card_metadata
# above) — pass it when the caller has one; omit it and this still degrades
# gracefully (chartType/mapping/etc. fall back to whatever `raw` itself has).
def normalize_card(raw, card_id, card_meta: nil)
  # The parts-form (Shape A) endpoint can return an array of card objects.
  raw = raw.first if raw.is_a?(Array)
  raw ||= {}
  defn = raw['definition']
  meta = parse_card_metadata(card_meta || raw)
  chart_type = resolve_chart_type(raw, defn, meta)

  if defn.is_a?(Hash) && (defn['subscriptions'] || defn['formulas'])
    # ---- Shape B (internal analyzer definition) ----
    main = defn.dig('subscriptions', 'main') || {}
    # LIVE-VALIDATED FIX (2026-07-30): none of the old fallbacks resolve against a
    # live Shape-B response, so EVERY card came back title-less and every migrated
    # chart was unnamed (KPIs only looked fine because their label comes from the
    # summary number's `alias`). A null element name then made Sigma reject the
    # whole workbook POST with a MISLEADING error —
    #   pages[N].elements[M]: Invalid kind: "bar-chart"
    # — because the element stopped matching the bar-chart schema and the
    # validator blames the `kind` discriminator rather than the null field.
    # Real locations: Shape B keeps the title at definition.title, and the
    # enumeration record from /stacks carries `title` at its ROOT, not under
    # metadata.
    title = defn.dig('dynamicTitle', 'text')&.map { |t| t['text'] }&.join ||
            raw['title'] || defn['title'] || raw.dig('metadata', 'title') ||
            (card_meta.is_a?(Hash) &&
             (card_meta['title'] || card_meta['cardTitle'] ||
              card_meta.dig('metadata', 'title')))
    columns = norm_columns((main.empty? ? nil : { 'columns' => main['columns'] }),
                           formulas: defn['formulas'])
    filters = Array(main['filters']).map do |f|
      { 'column' => f['column'], 'operator' => f['filterType'] || f['operator'],
        'values' => f['values'] }.compact
    end
    {
      'id'                 => card_id,
      'title'              => title,
      'chartType'          => chart_type,
      'sigmaKindHint'      => sigma_kind_hint(chart_type),
      'datasetId'          => resolve_dataset_id(raw, card_meta),
      'columns'            => columns,
      # Bug 2 (P0): the summary number lives at subscriptions.big_number on a
      # live instance — NOT defn['summaryNumber'] or main['summaryNumber']
      # (neither of which exist there), so this used to be nil for 31/36
      # cards and Rule 0 (summary number -> kpi-chart) never fired. Old paths
      # kept as a fallback for compatibility / other Domo versions.
      'summaryNumber'      => norm_summary_number(
        defn.dig('subscriptions', 'big_number') || defn['summaryNumber'] || main['summaryNumber'],
        formulas: defn['formulas'], card_id: card_id
      ),
      # The real date column + grain behind any `calendar: true` pseudo-column.
      'dateGrain'          => main['dateGrain'],
      'dateRangeFilter'    => main['dateRangeFilter'],
      'groupBy'            => Array(main['groupBy']).map { |c| c['column'] }.compact,
      'orderBy'            => Array(main['orderBy']).map { |c| c['column'] }.compact,
      'limit'              => main['limit'],
      'filters'            => filters,
      'conditionalFormats' => Array(defn['conditionalFormats']),
      'cardFormulas'       => Array(defn['formulas']),  # {id,name,columnPositions,...}
      '_metadata'          => (meta.empty? ? nil : meta),
      '_shape'             => 'B',
    }.compact
  else
    # ---- Shape A (official CardDefinition) ----
    body = raw['chartBody'] || {}
    filters = Array(body['filters']).map do |f|
      { 'column' => f['column'], 'operator' => f['operand'] || f['operator'],
        'values' => f['values'] }.compact
    end
    {
      'id'                 => card_id,
      # Same title-resolution fix as Shape B above — also consult the /stacks
      # enumeration record, whose `title` sits at the root.
      'title'              => raw['title'] || raw.dig('metadata', 'title') ||
                              (card_meta.is_a?(Hash) &&
                               (card_meta['title'] || card_meta['cardTitle'] ||
                                card_meta.dig('metadata', 'title'))) || nil,
      'chartType'          => chart_type,
      'sigmaKindHint'      => sigma_kind_hint(chart_type),
      'datasetId'          => resolve_dataset_id(raw, card_meta),
      'columns'            => norm_columns(body, formulas: raw['calculatedFields']),
      'summaryNumber'      => norm_summary_number(raw['summaryNumber'], formulas: raw['calculatedFields'], card_id: card_id),
      'dateGrain'          => body['dateGrain'],
      'dateRangeFilter'    => body['dateRangeFilter'],
      'groupBy'            => norm_columns({ 'columns' => body['groupBy'] }).map { |c| c['column'] },
      'orderBy'            => norm_columns({ 'columns' => body['orderBy'] }).map { |c| c['column'] },
      'limit'              => body['limit'],
      'filters'            => filters,
      'conditionalFormats' => Array(raw['conditionalFormats']),
      'cardFormulas'       => Array(raw['calculatedFields']),  # {formula,id,name,saveToDataSet}
      '_metadata'          => (meta.empty? ? nil : meta),
      '_shape'             => 'A',
    }.compact
  end
end

# Extract the card's Summary Number — the single big value Domo shows at the top of
# EVERY viz card (column + aggregation + label + number format). This is what a
# table-that-looks-like-a-KPI is built from; the build step maps it to a Sigma
# kpi-chart (refs/card-to-element.md Rule 0), NOT a table.
#
# CONFIRMED path (official "Get Chart Card Definition"): summaryNumber.columns[]
# with {column, aggregation, alias, format}. A Domo TABLE card's summary number
# DEFAULTS to COUNT of the bound (often id/first) column — so a faithful read can
# emit Count([id]). We flag that so build-workbook.rb prefers the authored measure.
#
# BUG A (live-validated 2026-07-30, refs/live-validation-2026-07-30.md): when the
# summary number's MEASURE IS A BEAST MODE, live Domo binds that columns[] entry
# by `formulaId` and supplies NEITHER `column` NOR `aggregation` — the aggregation
# is baked into the Beast Mode's own SQL (e.g. "(CASE WHEN (SUM(`x`) = 0) THEN 0
# ELSE (SUM(`y`) / SUM(`x`)) END )"). Before this fix, `col['column'] ||
# col['dataColumn'] || col['field']` had nothing to read there, so both `column`
# and `aggregation` silently came back nil — a Sigma KPI with NO bound measure at
# all, and no warning that anything was wrong. Observed on a live 15-card run: 3
# of 15 cards had summaryNumber.column == nil / aggregation == nil, and every one
# of those three was a Beast Mode summary number.
#
# `formulas` is this card's OWN definition.formulas[] (Shape B) / calculatedFields[]
# (Shape A) — the caller passes it in so this stays a pure function (no HTTP, no
# global card registry). Resolution is strictly by `id` match (never by name —
# Beast Mode names are not guaranteed unique on a page).
def norm_summary_number(sn, formulas: [], card_id: nil)
  return nil unless sn.is_a?(Hash)
  col = sn['columns'].is_a?(Array) ? sn['columns'].first : sn
  return nil unless col.is_a?(Hash)
  agg    = col['aggregation'] || col['aggr'] || col['func']
  column = col['column'] || col['dataColumn'] || col['field']
  formula_id = col['formulaId']
  is_calc = false

  if column.nil? && formula_id
    match = Array(formulas).find { |f| f.is_a?(Hash) && f['id'] == formula_id }
    if match
      # The Beast Mode's NAME becomes the measure. Do NOT invent an
      # `aggregation` on top of it: the SQL already aggregates, so wrapping it
      # in another Agg(...) in the build step would double-aggregate and
      # silently produce a wrong number. `_isCalc` tells build-workbook.rb this
      # is a calc/formula reference, not a raw warehouse column.
      column  = match['name']
      is_calc = true
    else
      # Never silently produce a nil measure: name the card so this is
      # discoverable, and fall back to the raw formulaId as the "column" so
      # downstream at least has a non-nil, traceable value instead of an
      # inexplicably empty KPI.
      warn "  WARNING: card #{card_id.inspect}: summary number references " \
           "formulaId #{formula_id.inspect} but no matching entry was found " \
           "in this card's own formulas[] — summary number measure NOT resolved."
      column = formula_id
    end
  end

  {
    'column'               => column,
    'aggregation'          => agg,
    # See norm_columns: Domo encodes a distinct count as COUNT + distinct:true.
    'distinct'             => (col['distinct'] ? true : nil),
    'label'                => col['alias'] || col['label'] || col['title'],
    'format'               => col['format'] || col['numberFormat'],
    'beastModeId'          => (is_calc ? formula_id : nil),
    '_isCalc'              => (is_calc || nil),
    # Domo's default for a table card is COUNT — scrutinize in the build step so a
    # KPI shows the intended measure, not a distinct/row count of the row key.
    '_defaultCountSuspect' => (agg.to_s.upcase == 'COUNT'),
    '_raw'                 => sn,
  }.compact
end

# Collect + classify every Beast Mode reachable from a normalized card:
#   - dataset-level formulas  (properties.formulas.formulas — a MAP keyed by id)
#   - card-local formulas     (Shape A calculatedFields / Shape B definition.formulas)
# Joins card column/filter refs via the "calculation_<uuid>" id, tags each with
# scope (dataset|card) and class (aggregate|projection|window|lod).
#
# Bug 4: both formula sources are INLINE — definition.formulas[] already
# carries the full formula object (isAnalytic/isAggregatable included), no
# standalone template fetch required to get the SQL or classify it. See
# classify_beast_mode_for for the prefer-inline / fall-back-to-fetch logic.
def dig_beast_modes(card, ds_formula_map, template_cache)
  out = []
  # 1. Dataset-level Beast Modes (map → values).
  (ds_formula_map || {}).each_value do |f|
    sql = f['formula'] || f['expression']
    next unless sql
    out << { 'id' => f['id'], 'name' => f['name'], 'sql' => sql,
             'scope' => 'dataset', 'class' => classify_beast_mode_for(f, template_cache),
             'dataSourceId' => card['datasetId'], 'cardId' => card['id'] }
  end
  # 2. Card-local Beast Modes.
  Array(card['cardFormulas']).each do |f|
    sql = f['formula'] || f['expression']
    next unless sql
    out << { 'id' => f['id'], 'name' => f['name'], 'sql' => sql,
             'scope' => 'card', 'class' => classify_beast_mode_for(f, template_cache),
             'cardId' => card['id'] }
  end
  out
end

def fetch_template(fn_id, cache)
  return nil if fn_id.nil? || Domo.dev_token.nil?
  cache[fn_id] ||= (Domo.beast_mode_template(fn_id) rescue nil)
end

# Fetch a card definition, trying Shape B (v3 analyzer def, what production tools
# use) then Shape A (parts form). Returns the raw response or nil.
def fetch_card_def(card_id)
  b = (Domo.card_definition_v3(card_id) rescue nil)
  return b if b.is_a?(Hash) && b['definition']
  Domo.card_definition(card_id) rescue nil
end

# Bug 1 (P0): GET /v1/pages/{id} (Domo.page) returns cardIds: [] even for a
# page with dozens of cards on a live instance — discovery used to derive its
# card list from exactly that field, so it silently produced ZERO cards. This
# tries the three confirmed-working routes in preference order, degrading
# gracefully to the next when one comes back empty:
#
#   1. Domo.cards_for_page   (private, richest — full card objects + sizes[]/
#                             collections[] for Bug 5 layout, in ONE call)
#   2. Domo.cards_adminsummary (private, instance-wide; paginated via skip/limit
#                             query params, scoped to this page via pageIds)
#   3. Domo.list_cards       (PUBLIC — the only route reachable on Tier B;
#                             limit capped at 100 inside the REST wrapper;
#                             paginated via offset; filtered here to this page)
#
# Returns [card_ids, meta_by_id, stacks]:
#   card_ids   — ordered array of card ids/urns for this page.
#   meta_by_id — card id (String) => whatever per-card record that route
#                supplied (full card object for route 1, the lighter
#                adminsummary/public-list record for routes 2/3). Passed into
#                normalize_card as `card_meta` (Bug 3 chartType/metadata).
#   stacks     — the FULL route-1 response (nil for routes 2/3) — passed to
#                DomoSigma.merge_geometry for the sizes[]/collections[] merge
#                (Bug 5). Only route 1 carries this; routes 2/3 have no
#                layout information at all, which is fine — merge_geometry
#                treats a nil `stacks` as a no-op.
def enumerate_page_cards(pid)
  # Route 1 — private, single call, full fidelity (cards + sizes + collections).
  stacks = (Domo.cards_for_page(pid) rescue nil)
  cards = Array(stacks && stacks['cards'])
  if cards.any?
    meta_by_id = {}
    ids = cards.map do |c|
      next nil unless c.is_a?(Hash) && c['id']
      meta_by_id[c['id'].to_s] = c
      c['id']
    end.compact
    return [ids, meta_by_id, stacks]
  end

  # Route 2 — private, instance-wide sweep filtered server-side to this page.
  if Domo.dev_token
    ids = []
    meta_by_id = {}
    skip = 0
    loop do
      resp  = (Domo.cards_adminsummary(pid, skip: skip, limit: 100) rescue nil)
      batch = Array(resp && resp['cardAdminSummaries'])
      break if batch.empty?
      batch.each do |c|
        next unless c.is_a?(Hash) && c['id']
        ids << c['id']
        meta_by_id[c['id'].to_s] = c
      end
      skip += 100
      break if batch.size < 100
    end
    return [ids, meta_by_id, nil] if ids.any?
  end

  # Route 3 — PUBLIC, the only route reachable on Tier B. `pages` is filtered
  # client-side since this endpoint isn't page-scoped server-side. An empty
  # result here (this list is documented as eventually-consistent right after
  # bulk mutations) is the LAST fallback, so we can only warn, not degrade
  # further — never silently report it as "confirmed zero cards".
  ids = []
  meta_by_id = {}
  offset = 0
  loop do
    resp  = (Domo.list_cards(limit: 100, offset: offset) rescue nil)
    batch = Array(resp && resp['cards'])
    break if batch.nil? || batch.empty?
    batch.each do |c|
      next unless c.is_a?(Hash)
      on_page = Array(c['pages']).any? do |p|
        (p.is_a?(Hash) ? (p['id'] || p['pageId']) : p).to_s == pid.to_s
      end
      next unless on_page
      urn = c['cardUrn'] || c['id']
      next unless urn
      ids << urn
      meta_by_id[urn.to_s] = c
    end
    offset += 100
    break if batch.size < 100
  end
  if ids.empty?
    warn "  cards: all 3 enumeration routes returned zero for page #{pid} — " \
         'public /v1/cards is eventually-consistent right after bulk mutations; ' \
         'treat as UNKNOWN, not "confirmed no cards" (re-run if unexpected).'
  end
  [ids, meta_by_id, nil]
end

# C9 wiring: merge each dataset's `permission` block — captured below from the
# ALREADY-FETCHED Domo.dataset_formulas response (parts=core,permission,formulas),
# no extra HTTP call — onto the matching datasets.json record, so build-dm.rb's
# DomoSigma.detect_pdp() can actually see it live. Pure/side-effect-free (returns
# a new array) so this is unit-testable offline without a network stub.
#
# Defensive: `permission_cache` values are attached as-is, whatever top-level
# `permission` the response carried. detect_pdp already tolerantly reads
# dataset['permission']['policies'] || dataset['pdp'] and returns [] (never
# raises) if the real nesting differs — this function does not assert or guess
# any deeper shape.
def merge_dataset_permissions(datasets, permission_cache)
  return [0, Array(datasets)] if permission_cache.nil? || permission_cache.empty?
  merged = 0
  out = Array(datasets).map do |d|
    next d unless d.is_a?(Hash)
    perm = permission_cache[d['id']]
    next d unless perm
    merged += 1
    d.merge('permission' => perm)
  end
  [merged, out]
end

# Merge real column schemas onto datasets.json.
#
# LIVE-VALIDATED FIX (2026-07-30): the PUBLIC LIST endpoint (GET /v1/datasets),
# which is what populates datasets.json, does NOT return a schema — its
# `columns` field is an Integer COUNT:
#   {"id":"...","name":"Orders Fact","rows":877,"columns":29}
# Only the per-dataset DETAIL endpoint (GET /v1/datasets/{id}) carries
#   schema.columns[] = [{"name":"ORDER_ID","type":"STRING"}, ...]
# (types seen live: STRING, LONG, DECIMAL, DOUBLE, DATE, DATETIME).
# Without this enrichment build-dm.rb had nothing to build columns FROM — it
# crashed on `29.each`, and a naive guard would instead have posted a data model
# with zero columns. Same shape as merge_dataset_permissions so both merges
# compose over one datasets.json.
def merge_dataset_schemas(datasets, schema_cache)
  return [0, Array(datasets)] if schema_cache.nil? || schema_cache.empty?
  merged = 0
  out = Array(datasets).map do |d|
    next d unless d.is_a?(Hash)
    sch = schema_cache[d['id']]
    next d unless sch.is_a?(Hash) && sch['columns'].is_a?(Array)
    merged += 1
    d.merge('schema' => sch)
  end
  [merged, out]
end

# ---------------------------------------------------------------------------

opts = {}
OptionParser.new do |o|
  o.on('--probe')            { opts[:probe] = true }
  o.on('--datasets')         { opts[:datasets] = true }
  o.on('--pages IDS', Array) { |v| opts[:pages] = v }
end.parse!(ARGV)

# --- Tier probe -------------------------------------------------------------
# Tier A = private API reachable (full fidelity). Tier B = public only.
if opts[:probe]
  public_ok = begin
    Domo.list_datasets(limit: 1); true
  rescue => e
    warn "PUBLIC API: FAIL — #{e.message}"; false
  end
  warn "PUBLIC API: OK" if public_ok

  if Domo.dev_token.nil?
    warn "PRIVATE API: skipped (DOMO_DEV_TOKEN unset) => TIER B (public only)."
    warn "  Card defs, Beast Modes, and layout will NOT be auto-extractable."
    warn "  Fall back to PNG-read per card (see feedback_phase1d_dashboard_png)."
  else
    # Private-API reachability check.
    #
    # LIVE-VALIDATED FIX (2026-07-30): this used to probe
    #   /api/content/v1/cards?urns=PROBE
    # with the literal string "PROBE" as a card id and treat ANY exception as
    # "unreachable". A live instance rejects that fake id with **400 Bad
    # Request** — the token was fine, the id was not — so a fully working Tier A
    # instance was misdetected as Tier B and the run silently threw away card
    # defs, Beast Modes, and layout. Probe an **id-free** endpoint instead, and
    # only treat an AUTH failure (401/403) as Tier B; a 4xx that isn't auth means
    # the credential was accepted, i.e. the surface is reachable.
    private_ok = begin
      Domo.private_get('/api/content/v2/users/me')
      true
    rescue => e
      if e.message =~ /\b(401|403)\b/
        warn "PRIVATE API: FAIL (auth) — #{e.message}"
        false
      else
        # Reachable: the token was accepted, the request shape was the problem.
        warn "PRIVATE API: reachable (non-auth error on probe: #{e.message[0, 120]})"
        true
      end
    end
    warn(private_ok ? "PRIVATE API: OK => TIER A (full fidelity)" : "PRIVATE API: unreachable => TIER B")
  end
  exit 0
end

# --- DataSet inventory ------------------------------------------------------
# Domo.list_datasets hits the PUBLIC /v1/datasets endpoint, which does NOT
# carry a `permission`/`pdp` block by itself. The --pages branch below already
# fetches each used dataset's `permission` part as a side effect of pulling
# Beast Mode formulas (Domo.dataset_formulas requests parts=core,permission,
# formulas) — after that loop we merge the captured permission data onto the
# matching datasets.json record (see merge_dataset_permissions above). NO
# extra HTTP call is added. `datasets_snapshot` lets that merge target this
# run's in-memory list when --datasets and --pages are invoked together in one
# process; otherwise it falls back to reading discovery/datasets.json off disk
# (run --datasets first so it exists). TODO(on-access): the exact `permission`
# nesting is still unconfirmed against a live instance — detect_pdp() in
# lib/domo_sigma_util.rb tolerates whatever shape actually comes back.
datasets_snapshot = nil
if opts[:datasets]
  all = []
  offset = 0
  loop do
    batch = Domo.list_datasets(limit: 50, offset: offset)
    break if batch.nil? || batch.empty?
    all.concat(batch)
    offset += 50
    break if batch.size < 50
  end
  datasets_snapshot = all
  dump('datasets.json', all)
end

# --- Per-page discovery -----------------------------------------------------
if opts[:pages]
  pages_out = []
  cards_out = []
  beast_out = []
  ds_formula_cache    = {}   # datasetId → formulas map
  ds_permission_cache = {}   # datasetId → raw `permission` value (C9 PDP wiring)
  ds_schema_cache     = {}   # datasetId → PUBLIC detail `schema` (columns[]) — build-dm needs this
  template_cache      = {}   # templateId → standalone Beast Mode (for classification)

  opts[:pages].each do |pid|
    page = Domo.page(pid) # PUBLIC: page title/hierarchy — do NOT trust
                          # page['cardIds']/['cards'] (confirmed empty even on
                          # a live 36-card page; see enumerate_page_cards, Bug 1).
    pages_out << page

    # PRIVATE, pixel-ish x/y/w/h geometry — present only on mason/Domo-App
    # pages. Classic pages return none of this (Bug 5); their layout signal
    # (sizes[]/collections[]) comes from `stacks` below instead. Both are
    # independent and merge_geometry tolerates either/both/neither being nil.
    layout = (Domo.page_layout(pid) rescue nil)

    # Bug 1 fix: enumerate cards via the three confirmed routes instead of the
    # empty page['cardIds']. `stacks` (non-nil only when route 1 supplied it)
    # also carries this page's sizes[]/collections[] for the Bug 5 geometry
    # merge below.
    card_ids, card_meta_by_id, stacks = enumerate_page_cards(pid)
    page_cards = []

    card_ids.each do |cid|
      if Domo.dev_token
        raw = fetch_card_def(cid)
        if raw.nil?
          page_cards << { 'id' => cid, '_error' => 'card definition unavailable' }
          next
        end
        card = normalize_card(raw, cid, card_meta: card_meta_by_id[cid.to_s])

        # Fetch + cache dataset-level Beast Modes for this card's dataset. This
        # SAME response (parts=core,permission,formulas) also carries the C9
        # PDP `permission` block — capture it too, no extra HTTP call.
        dsid = card['datasetId']
        if dsid && !ds_formula_cache.key?(dsid)
          det = (Domo.dataset_formulas(dsid) rescue nil)
          ds_formula_cache[dsid] = det&.dig('properties', 'formulas', 'formulas') || {}
          ds_permission_cache[dsid] = det['permission'] if det.is_a?(Hash) && det['permission']

          # The PRIVATE detail above does NOT carry the documented column schema,
          # and the PUBLIC LIST endpoint only reports a column COUNT — so fetch
          # the PUBLIC per-dataset detail once per USED dataset to get
          # schema.columns[]. build-dm.rb hard-fails without it rather than
          # posting a column-less data model (see merge_dataset_schemas).
          pub = (Domo.dataset(dsid) rescue nil)
          ds_schema_cache[dsid] = pub['schema'] if pub.is_a?(Hash) && pub['schema'].is_a?(Hash)
        end

        card['beastModes'] = dig_beast_modes(card, ds_formula_cache[dsid], template_cache)
        beast_out.concat(card['beastModes'])
        page_cards << card
      else
        # Tier B: still no private API, but card_meta_by_id now carries a real
        # id + title (route 3, public /v1/cards) instead of nothing — this is
        # what "Tier B can produce a card inventory" (Bug 1) means in practice;
        # chart classification still requires a human to read the PNG.
        meta = card_meta_by_id[cid.to_s] || {}
        page_cards << {
          'id' => cid, '_tierB' => true,
          'title' => meta['cardTitle'] || meta['title'],
          '_note' => 'no private API — capture PNG + transcribe Beast Modes manually',
        }.compact
      end
    end

    cards_out.concat(merge_geometry(page_cards, layout, stacks: stacks))
  end

  # De-dupe Beast Modes by id (a dataset formula shared by many cards appears once).
  beast_out.uniq! { |b| [b['id'], b['scope']] }

  # C9/PDP: merge captured `permission` data onto datasets.json (this run's
  # in-memory list if --datasets ran too, else re-read the file from a prior
  # --datasets run) so DomoSigma.detect_pdp can see it in build-dm.rb.
  # Both merges compose over ONE datasets.json, so do them together and dump once.
  # `schema` is not optional: build-dm.rb hard-fails without it (the PUBLIC LIST
  # endpoint only gives a column COUNT — see merge_dataset_schemas).
  if ds_permission_cache.any? || ds_schema_cache.any?
    ds_path  = File.join(OUT, 'datasets.json')
    existing = datasets_snapshot || (JSON.parse(File.read(ds_path)) rescue nil)

    # `--pages` without a prior `--datasets` leaves no merge target. Rather than
    # emit an un-buildable discovery set, synthesize minimal records for exactly
    # the datasets this page set actually uses.
    unless existing.is_a?(Array)
      ids = (ds_schema_cache.keys + ds_permission_cache.keys).uniq
      if ids.any?
        existing = ids.map { |i| { 'id' => i } }
        warn "  datasets.json absent — synthesized #{existing.size} record(s) for the " \
             'dataset(s) used by these pages so the schema/permission merge has a target.'
      end
    end

    if existing.is_a?(Array)
      sch_merged, datasets = merge_dataset_schemas(existing, ds_schema_cache)
      perm_merged, datasets = merge_dataset_permissions(datasets, ds_permission_cache)
      dump('datasets.json', datasets)
      warn "  schema: merged column schemas into #{sch_merged} datasets.json record(s) " \
           '(build-dm.rb requires these).' if sch_merged > 0
      warn "  C9/PDP: merged permission data into #{perm_merged} datasets.json record(s) " \
           '(see DomoSigma.detect_pdp).' if perm_merged > 0
      missing = datasets.select { |d| d.is_a?(Hash) && !d.dig('schema', 'columns').is_a?(Array) }
      warn "  ⚠ #{missing.size} dataset(s) still have NO schema.columns — build-dm.rb will " \
           "refuse to build them: #{missing.map { |d| d['id'] }.join(', ')}" if missing.any?
    else
      warn "  ⚠ fetched schema/permission data but discovery/datasets.json is missing and " \
           'no dataset ids were captured — run --datasets (before or with --pages).'
    end
  end

  dump('pages.json', pages_out)
  dump('cards.json', cards_out)
  dump('beast-modes.json', beast_out)
  warn "\nNext: ruby scripts/convert-beast-modes.rb   (translate Beast Mode SQL -> Sigma formulas)"
end
