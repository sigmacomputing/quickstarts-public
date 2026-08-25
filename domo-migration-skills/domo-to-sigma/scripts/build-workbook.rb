#!/usr/bin/env ruby
# Phase 5 — Workbook chart layer (the Domo analog of Tableau's
# build-charts-from-signals.rb). Turns normalized Domo cards into Sigma workbook
# ELEMENTS that source a hidden "master" table, then the reused
# build-workbook-spec.rb assembles master + pages into the POST-ready spec.
#
# Every element references DM columns as [Master/<Display Name>] so it composes
# with the auto-master build-workbook-spec.rb emits. This script bakes in the
# fixes from the field migration feedback:
#   #1 KPI value = summary number's aggregation of its MEASURE (source-prefixed);
#      a COUNT of a row-key/id (Domo table default) is flagged, not shipped silently.
#   #2 page filters → controls that fan out to EVERY element via the shared master.
#   #5 long-text table columns get style.textWrap:"wrap".
#   #7 a Domo bar chart → a real bar-chart element, never a table+dataBars.
#   #8 chart axes default to gridlines-off (format.marks:"none").
#
#   ruby scripts/build-workbook.rb            # → discovery/chart-specs.json (+ warnings.json)
#   # then reuse: build-workbook-spec.rb --chart-specs chart-specs.json --dm-ids dm-ids.json ...
#
# Optional sidecar discovery/kpi-overrides.json  { "<cardId>": {"column":"...","aggregation":"SUM"} }
# lets the migrator correct a wrong KPI measure deterministically and re-run.

require 'json'
require 'fileutils'
require 'base64'
require_relative 'lib/domo_sigma_util'
include DomoSigma

OUT = ENV['DOMO_DISCOVERY_DIR'] || File.expand_path('../discovery', __dir__)

AGG = { 'SUM' => 'Sum', 'AVG' => 'Avg', 'AVERAGE' => 'Avg', 'COUNT' => 'Count',
        'COUNT DISTINCT' => 'CountDistinct', 'DISTINCT_COUNT' => 'CountDistinct',
        'COUNT_DISTINCT' => 'CountDistinct', 'MIN' => 'Min', 'MAX' => 'Max' }.freeze
# Domo has NO distinct-count aggregation — it sends aggregation:'COUNT' plus a
# separate distinct:true flag. Honour that flag or a CountDistinct silently
# degrades to Count and the KPI shows a WRONG-but-plausible number (live run:
# Orders 877 rows vs 872 distinct orders).
def sigma_agg(a, distinct = false)
  base = AGG[a.to_s.upcase] || 'Sum'
  return 'CountDistinct' if distinct && base == 'Count'
  base
end

def mref(display) "[Master/#{display}]" end

$warnings = []
def warn_card(card, msg) $warnings << { 'card' => card['title'] || card['id'], 'warning' => msg } end

$companion_elements = [] # bead 08sf — Task 5 populates this
$sub_masters = {}        # bead ziht — datasetId => sub-master element Hash

# bead ziht: dm-spec.json is build-dm.rb's PRE-post spec (already at this
# script's own OUT dir — build-dm.rb writes it to discovery/, same as
# cards.json/pages.json). It carries `_datasetId` on every DM element
# (build-dm.rb) — a client-assigned tag Sigma neither knows nor round-trips.
# dm-ids.json is the POST-readback (client ids are preserved by Sigma on
# CREATE, but only the readback carries the real `dataModelId` + confirms the
# element actually posted) — it lives in migrate-domo.rb's OUT, a DIFFERENT
# directory than DISCOVERY, so it needs its own env var.
DM_SPEC_PATH = File.join(OUT, 'dm-spec.json')
DM_IDS_PATH  = ENV['DOMO_DM_IDS_PATH']

# Which live DM element serves each Domo DataSet, keyed by datasetId. Both
# inputs are optional — a hand run of build-workbook.rb alone, or a unit test,
# has neither, and this degrades to {} (the caller's existing warn+SKIP path
# for a card whose DataSet doesn't match the workbook's dominant master).
def dataset_element_map
  return $ds_element_map if $ds_element_map
  unless DM_IDS_PATH && File.exist?(DM_SPEC_PATH.to_s) && File.exist?(DM_IDS_PATH.to_s)
    return $ds_element_map = {}
  end
  dm_spec = (JSON.parse(File.read(DM_SPEC_PATH)) rescue nil)
  dm_ids  = (JSON.parse(File.read(DM_IDS_PATH)) rescue nil)
  return $ds_element_map = {} unless dm_spec && dm_ids

  ds_by_el_id = {}
  # LIVE-VALIDATED FIX (2026-07-31): build-dm.rb never sets an element-level
  # `name` (rule 3), so the live readback's own `name` is null for both the
  # primary master AND every other DM element. build-workbook-spec.rb already
  # resolves this fallback for the ONE element it picks as the primary master
  # (server assigns a name by kind: the warehouse table's last path segment,
  # else "Custom SQL") — sub_master_for needs the identical resolution for
  # every OTHER element, or its column formulas emit "[/Col]" (an empty table
  # name — verified live against a nameless Customer Dim element: Sigma
  # rejected "[/Phone]" as an invalid formula, which would 400 the whole
  # workbook POST).
  name_by_el_id = {}
  (dm_spec['pages'] || []).each do |p|
    (p['elements'] || []).each do |e|
      ds_by_el_id[e['id']] = e['_datasetId'] if e['_datasetId']
      src = e['source'] || {}
      name_by_el_id[e['id']] =
        if src['kind'] == 'warehouse-table' && !Array(src['path']).empty?
          Array(src['path']).last
        else
          'Custom SQL'
        end
    end
  end
  map = {}
  (dm_ids['pages'] || []).flat_map { |p| p['elements'] || [] }.each do |e|
    ds_id = ds_by_el_id[e['id']]
    next unless ds_id && !map.key?(ds_id)
    resolved = e.dup
    resolved['name'] = name_by_el_id[e['id']] if e['name'].to_s.strip.empty?
    map[ds_id] = resolved
  end
  $ds_element_map = map
end

def dm_id
  return $dm_id if defined?($dm_id) && $dm_id
  return $dm_id = nil unless DM_IDS_PATH && File.exist?(DM_IDS_PATH.to_s)
  ids = (JSON.parse(File.read(DM_IDS_PATH)) rescue nil)
  $dm_id = ids && ids['dataModelId']
end

# A hidden sub-master for a non-dominant DataSet — the same auto-passthrough
# shape build-workbook-spec.rb builds for the primary `master` (every column of
# the named DM element, by name), reimplemented here rather than shared because
# that file is VENDORED and must not diverge (see its header). nil when the
# DataSet has no resolvable live element yet (caller falls back to the existing
# warn+SKIP stopgap).
def sub_master_for(ds_id)
  return $sub_masters[ds_id] if $sub_masters[ds_id]
  live_el = dataset_element_map[ds_id]
  return nil unless live_el
  cols = (live_el['columnLabels'] || live_el['columns'] || []).map do |c|
    nm = c.is_a?(String) ? c : (c['name'] || c['id'])
    next nil if nm.to_s.empty?
    { 'id' => mcol_id(nm), 'name' => nm, 'formula' => "[#{live_el['name']}/#{nm}]" }
  end.compact
  return nil if cols.empty?
  $sub_masters[ds_id] = {
    'id' => "master-#{ds_id.to_s.downcase.gsub(/\W+/, '-')}", 'kind' => 'table',
    'name' => "Master (#{live_el['name'] || ds_id})", 'visibleAsSource' => false,
    'source' => { 'kind' => 'data-model', 'dataModelId' => dm_id, 'elementId' => live_el['id'] },
    'columns' => cols, 'order' => cols.map { |c| c['id'] },
  }
end

# ---- Domo chartType -> Sigma element kind (refs/card-to-element.md Problems 1-3) --
#
# `chartType` is a STRICT Domo enum, not a free-form string — substring matching
# on it is actively harmful (`badge_line_bar` is a COMBO chart but contains
# "badge_line"; `badge_symbol_bar` contains "_bar" but isn't a plain bar chart).
# EXACT-match the full token against CHART_TYPE_MAP below; a token this map
# hasn't seen falls back to `card['sigmaKindHint']` (upstream's own best-effort
# guess) and, failing that, to the existing "unknown chartType" bar-chart
# default at the bottom of build_element — never a silent drop.
#
# Four tokens the map used to carry (`badge_datagrid`, `badge_pivottable`,
# `badge_stackedarea`, `badge_line`) are NOT valid Domo ChartType values —
# probing card creation returned "No enum constant ... ChartType.<token>" for
# each. They're kept here only so a card carrying one is flagged as an upstream
# extraction bug (a real Domo instance will never produce them), not silently
# mis-mapped.
FABRICATED_CHART_TYPES = {
  'badge_datagrid'    => 'badge_table',
  'badge_pivottable'  => nil, # no confirmed-valid Domo pivot-table token observed yet
  'badge_stackedarea' => nil, # no confirmed-valid Domo stacked-area token observed yet
  'badge_line'        => 'badge_symbolline (or badge_curved_symbolline)',
}.freeze

# Every chartType this converter has actually seen accepted by Domo — either by
# creating a card with it, or observed live on `metadata.chartType` of a real
# card on a real instance (2026-07-30 validation) — mapped to the Sigma element
# `kind` string that best represents it. Kind strings are verified against the
# sigma-workbooks skill (plugins/sigma-authoring/skills/sigma-workbooks); values
# here are the CLOSEST HONEST kind, not always an exact visual match — see
# NO_NATIVE_EQUIVALENT below for the subset where Sigma has no true equivalent.
CHART_TYPE_MAP = {
  'badge_vert_bar'            => 'bar-chart',
  'badge_horiz_bar'           => 'bar-chart',
  'badge_vert_stackedbar'     => 'bar-chart',   # + stacking: stacked (bar_stacking_for)
  'badge_vert_multibar'       => 'bar-chart',   # + stacking: none (grouped/clustered)
  'badge_horiz_multibar'      => 'bar-chart',   # + orientation: horizontal, stacking: none
  'badge_horiz_100pct'        => 'bar-chart',   # + orientation: horizontal, stacking: normalized
  'badge_vert_nestedbar'      => 'bar-chart',   # approximated (no 2-level nested axis) — see warning
  'badge_treemap'             => 'bar-chart',   # NO_NATIVE_EQUIVALENT — sorted desc by measure
  'badge_symbolline'          => 'line-chart',
  'badge_curved_symbolline'   => 'line-chart',
  'badge_trendline'           => 'line-chart',
  'badge_two_trendline'       => 'line-chart',
  'badge_xyscatterplot'       => 'scatter-chart',
  'badge_bubble'              => 'scatter-chart',  # + size channel from a BUBBLESIZE-mapped column
  'badge_pie'                 => 'pie-chart',
  'badge_donut'               => 'donut-chart',
  'badge_singlevalue'         => 'kpi-chart',
  'badge_filledgauge'         => 'kpi-chart',   # NO_NATIVE_EQUIVALENT — no gauge kind in Sigma
  'badge_table'               => 'table',
  'badge_word_cloud'          => 'table',       # NO_NATIVE_EQUIVALENT — term + frequency table
  'badge_calendar'            => 'table',       # NO_NATIVE_EQUIVALENT — flat date + value table
  'badge_map'                 => 'region-map',  # default; build_map falls back to a table when the
                                                 # geography column can't be classified
  'badge_line_bar'            => 'combo-chart',
  'badge_line_stackedbar'     => 'combo-chart',
  'badge_symbol_bar'          => 'combo-chart',
  'badge_pop_bar_line'        => 'combo-chart', # NO_NATIVE_EQUIVALENT — no POP comparison primitive
  'badge_vert_symbol_overlay' => 'combo-chart', # NO_NATIVE_EQUIVALENT — no actual-vs-target overlay
}.freeze

# Sigma has no true equivalent for these — CHART_TYPE_MAP above still names the
# closest honest degradation (never silently substituted for a bar chart with
# no explanation), but build_element ALSO emits a loud, specific warning naming
# the card and the gap. Per refs/card-to-element.md, actually closing this gap
# is tracked as a Sigma CUSTOM PLUGIN follow-up (see the sigma-plugin-development
# skill) — building one is NOT this converter's job today.
NO_NATIVE_EQUIVALENT = {
  'badge_treemap' => 'Domo treemap — no treemap `kind` was found in the Sigma workbook spec ' \
                      '(verified against the sigma-workbooks skill); degraded to a bar-chart sorted ' \
                      'descending by measure, which loses the area-proportional hierarchy.',
  'badge_word_cloud' => 'Domo word cloud — no word-cloud `kind` exists in Sigma; degraded to a flat ' \
                         'term + frequency table.',
  'badge_calendar' => 'Domo calendar heatmap — no calendar `kind` exists in Sigma; degraded to a flat ' \
                       'date + value table.',
  'badge_filledgauge' => 'Domo gauge/dial — `gauge` is a CONFIRMED-INVALID Sigma kind (rejected ' \
                          '`400 Invalid kind` — not part of the workbook spec API); degraded to ' \
                          'kpi-chart. Bind the TARGET column as a KPI comparison if present.',
  'badge_pop_bar_line' => 'Domo period-over-period bar+line — combo-chart approximates the visual ' \
                           '(bar = current period, line = prior period) but Sigma has no automatic ' \
                           'prior-period comparison; the two periods must be modeled as two explicit measures.',
  'badge_vert_symbol_overlay' => 'Domo bar + actual/target symbol overlay — combo-chart (bar + a ' \
                                  'scatter marker series) is the closest native shape; a true ' \
                                  'actual-vs-target dial is not representable.',
}.freeze

# Exact-match chartType tokens (never substring) whose Sigma bar-chart needs a
# non-default orientation. Anything not listed renders Sigma's default (vertical).
HORIZONTAL_CHART_TYPES = %w[badge_horiz_bar badge_horiz_multibar badge_horiz_100pct].freeze

def bar_stacking_for(chart_type)
  case chart_type.to_s.downcase
  when 'badge_vert_stackedbar' then 'stacked'
  when 'badge_horiz_100pct'    then 'normalized'
  else 'none'
  end
end

# Which shape the secondary (non-bar) series takes on a combo-chart, by exact
# chartType token — Domo's ChartType alone doesn't say which measure is which,
# so build_combo also documents/flags the first-measure-is-bar heuristic.
COMBO_SECONDARY_TYPE = {
  'badge_line_bar'            => 'line',
  'badge_line_stackedbar'     => 'line',
  'badge_pop_bar_line'        => 'line',
  'badge_symbol_bar'          => 'scatter',
  'badge_vert_symbol_overlay' => 'scatter',
}.freeze

# Resolve a card's Sigma element kind from its chartType via EXACT match
# (never substring — see the header comment above). Returns nil — the
# documented, explicit fallback — for a fabricated token (flagged separately,
# via FABRICATED_CHART_TYPES) or a token this map hasn't seen; the caller
# falls back to sigmaKindHint, then to the unknown-chartType bar-chart default.
def chart_kind_for(card)
  ct = card['chartType'].to_s.downcase
  return nil if ct.empty?
  if FABRICATED_CHART_TYPES.key?(ct)
    real = FABRICATED_CHART_TYPES[ct]
    warn_card(card, "chartType '#{card['chartType']}' is not a valid Domo ChartType value " \
                    "(confirmed invalid by probing card creation)#{real ? " — the real token is #{real}" : ''} " \
                    '— check the upstream extraction; falling back.')
    return nil
  end
  CHART_TYPE_MAP[ct]
end

# A page whose cards carry no grid geometry (Task 1's merge_geometry 'x'/'y'
# fields, sourced from domo-discover's --pages capture) has nothing for
# build-domo-layout.rb/build-dashboard-layout.rb to place — it silently falls
# back to a single-column stack. Warn loudly instead of shipping that quietly.
def warn_missing_geometry(pname, pcards)
  return if pcards.empty?
  return if pcards.any? { |c| c['x'] || c['y'] }
  warn_card(pcards.first, "no grid geometry for page '#{pname}' — layout will fall back to a " \
                          'single-column stack; ensure domo-discover captured x/y/w/h')
end

# Split a card's columns into dimensions (grouped / non-aggregated) and measures.
#
# Prefers Domo's own column->visual-role `mapping` vocabulary when a column
# carries one (live-verified 2026-07-30: ITEM/CATEGORY/XTIME/DATE/SERIES bind
# to the axis/series side, VALUE/CURRENT/TARGET/BUBBLESIZE are measures) —
# more reliable than guessing from `aggregation`/`groupBy` alone. Falls back to
# the aggregation/groupBy heuristic when no column carries a `mapping` (Tier B,
# or an extraction pass that hasn't captured it yet).
DIM_MAPPINGS = %w[ITEM CATEGORY XTIME DATE].freeze
MEASURE_MAPPINGS = %w[VALUE CURRENT TARGET BUBBLESIZE].freeze

# SERIES is AMBIGUOUS and must be disambiguated by whether the column carries an
# aggregation — it used to sit in DIM_MAPPINGS unconditionally, which silently
# produced charts with ZERO measures.
#
# LIVE EVIDENCE (2026-07-30):
#   * badge_line_bar / combo + two-axis cards bind every MEASURE via SERIES
#     (mapping=SERIES with aggregation=SUM/AVG, date on ITEM+calendar:true) —
#     verified against 3 real combo cards. Treating those as dimensions yielded
#     "combo-chart: expected a bar measure + a line measure but found 0" and then
#     a workbook POST rejection ("Invalid kind: combo-chart").
#   * badge_vert_stackedbar / badge_vert_multibar bind a SPLIT DIMENSION via
#     SERIES (a plain string column, NO aggregation).
# So: SERIES + aggregation => measure; SERIES without => split dimension.
SERIES_MAPPING = 'SERIES'

def split_cols(card)
  cols = card['columns'] || []
  gb = Array(card['groupBy'])
  dims = []
  meas = []
  # Per-column: prefer Domo's own `mapping` when THIS column carries one (it's
  # the more reliable signal); fall back to the aggregation/groupBy heuristic
  # for any column that doesn't (Tier B, or an extraction pass that hasn't
  # captured `mapping` yet) — mixing the two per-column, rather than an
  # all-or-nothing switch, so a partially-tagged column set still classifies
  # correctly instead of silently losing the untagged columns.
  cols.each do |c|
    m = c['mapping'].to_s.upcase
    if m == SERIES_MAPPING
      # Ambiguous by design — see SERIES_MAPPING above.
      c['aggregation'].to_s.empty? ? dims << c : meas << c
    elsif DIM_MAPPINGS.include?(m)
      dims << c
    elsif MEASURE_MAPPINGS.include?(m)
      meas << c
    elsif gb.include?(c['column']) || c['aggregation'].to_s.empty?
      dims << c
    else
      meas << c
    end
  end
  dims = cols.reject { |c| meas.include?(c) } if dims.empty? && !meas.empty?
  [dims, meas]
end

def col_label(c) (c['alias'] && !c['alias'].to_s.strip.empty?) ? c['alias'] : display_name(c['column']) end

# A measure element column: <Agg>([Master/<disp>]) with a clean label + format.
def measure_col(c, card = nil)
  # An aggregate/window Beast Mode is inlined un-wrapped — see
  # inline_beast_mode_measure for why Sum([Master/<BM name>]) would be wrong.
  inlined = c['_isCalc'] ? inline_beast_mode_measure(card || {}, c) : nil
  return inlined if inlined

  disp = display_name(c['column'])
  { 'id' => "m-#{c['column'].to_s.downcase.gsub(/\W+/, '-')}",
    'name' => col_label(c),
    'formula' => "#{sigma_agg(c['aggregation'], c['distinct'])}(#{mref(disp)})",
    'format' => sigma_format(c['format'], col_label(c)) }.compact
end

# Domo dateTimeElement -> Sigma DateTrunc unit.
DATE_GRAIN_UNIT = {
  'YEAR' => 'year', 'QUARTER' => 'quarter', 'MONTH' => 'month', 'WEEK' => 'week',
  'DAY' => 'day', 'DATE' => 'day', 'HOUR' => 'hour', 'MINUTE' => 'minute',
}.freeze

# A dimension element column: [Master/<disp>].
#
# LIVE-VALIDATED FIX (2026-07-30): when a Domo card applies a date grain, the
# component's column list contains a SYNTHETIC pseudo-column — `CalendarMonth`,
# `CalendarWeek`, `CalendarYear`, … flagged `calendar: true` — which does NOT
# exist in the DataSet. The real column and grain live on the component's
# `dateGrain`:
#   columns:   [{"column":"CalendarMonth","calendar":true,"mapping":"ITEM"}, ...]
#   groupBy:   [{"column":"CalendarMonth","calendar":true}]
#   dateGrain: {"column":"ORDER_DATE","dateTimeElement":"MONTH"}
# Emitting the pseudo-column verbatim produced
#   pages[N].elements[M]: Dependency not found: 'master/calendar month'
# which fails the ENTIRE workbook POST. Translate it to a Sigma truncation of the
# real column instead: DateTrunc("month", [Master/Order Date]).
def dim_col(c, card = nil)
  grain = card && card['dateGrain']
  is_cal = c['calendar'] || c['column'].to_s =~ /\ACalendar/i
  if is_cal && grain.is_a?(Hash) && !grain['column'].to_s.empty?
    unit = DATE_GRAIN_UNIT[grain['dateTimeElement'].to_s.upcase]
    if unit
      disp = display_name(grain['column'])
      return { 'id' => "d-#{c['column'].to_s.downcase.gsub(/\W+/, '-')}",
               'name' => col_label(c),
               'formula' => %(DateTrunc("#{unit}", #{mref(disp)})) }.compact
    end
  end
  { 'id' => "d-#{c['column'].to_s.downcase.gsub(/\W+/, '-')}",
    'name' => col_label(c), 'formula' => mref(display_name(c['column'])) }.compact
end

AXIS_OFF = { 'marks' => 'none' }.freeze # gridlines off (bug #8); labels left to source

def eid(card, suffix = '') "el-#{(card['id'] || rand_id).to_s.gsub(/\W+/, '-')}#{suffix}" end

# ---- per-kind builders -----------------------------------------------------

def build_kpi(card, overrides)
  sn = card['summaryNumber'] || {}
  ov = overrides[card['id']]
  col = ov && ov['column'] || sn['column']
  agg = ov && ov['aggregation'] || sn['aggregation'] || 'SUM'
  # #1 guard: Domo table cards default the summary number to COUNT of the bound
  # (usually id/row-key) column. Ship it, but flag loudly so wrong numbers surface.
  if !ov && sn['_defaultCountSuspect'] && id_like?(col)
    warn_card(card, "KPI counts the row-key '#{col}' (Domo table default) — likely NOT the intended metric. " \
                    "Set discovery/kpi-overrides.json {\"#{card['id']}\":{\"column\":\"<measure>\",\"aggregation\":\"SUM\"}} and re-run.")
  end
  return nil unless col
  disp = display_name(col)
  label = (sn['label'] && !sn['label'].to_s.strip.empty?) ? sn['label'] : disp
  vid = mcol_id(disp).sub(/\Am-/, 'v-')
  # LIVE-VALIDATED FIX (2026-07-31): an aggregate/window Beast Mode summary
  # number is not a data-model column — mirrors measure_col's own
  # inline_beast_mode_measure handling. Without this, a KPI (or bead 08sf's
  # companion KPI, which calls build_kpi for a card whose summary is bound to
  # an aggregate calc like "Margin Pct") emitted Sum([Master/Margin Pct]), a
  # column that does not exist, 400ing the ENTIRE workbook POST. Only applies
  # when NOT overridden — a kpi-overrides.json entry points at a real column.
  value_col = (!ov && sn['_isCalc'] && inline_beast_mode_measure(card, sn)) ||
              { 'id' => vid, 'name' => label,
                'formula' => "#{sigma_agg(agg, sn['distinct'])}(#{mref(disp)})",
                'format' => sigma_format(sn['format'], label) }.compact
  {
    'id' => eid(card), 'kind' => 'kpi-chart', 'name' => label,
    'source' => { 'kind' => 'table', 'elementId' => 'master' },
    'columns' => [value_col],
    'value' => { 'columnId' => value_col['id'] },   # ⚠ columnId, NOT id (feedback_sigma_kpi_value_columnid)
  }
end

# bead 08sf: Domo prints a Summary Number above EVERY viz card, not just KPI
# cards — a bar chart, a table, a combo all show one. Sigma's chart/table
# elements have no summary slot, so the fix is a separate companion kpi-chart
# element, reusing build_kpi (identical measure/format resolution, including
# the #1 COUNT-of-row-key guard) with a distinct id so it never collides with
# the primary element's own id. build-domo-layout.rb synthesizes this
# companion its own layout zone in the page's KPI band (kind-aware
# composition) — it is NOT guaranteed to land immediately adjacent to its own
# primary chart/table (that band groups ALL of a page's KPI-kind elements
# together, regardless of which card produced them); see refs/card-to-
# element.md's "Companion KPI" section for the honest placement description.
#
# build_kpi's own "return nil unless col" guard is a bare truthiness check —
# it only trips on a literal nil/false column, so an explicitly blank ''
# column (as opposed to an absent one) sails through it and build_kpi would
# happily emit a broken Count([Master/]) reference. Re-check for blank here,
# scoped only to this new function (build_kpi itself is untouched), using the
# same .to_s.strip.empty? convention prune_unresolvable_columns! already uses
# elsewhere in this file for "no resolvable column".
def build_summary_companion(card, overrides)
  sn = card['summaryNumber'] || {}
  ov = overrides[card['id']]
  col = ov && ov['column'] || sn['column']
  return nil if col.to_s.strip.empty?
  kpi = build_kpi(card, overrides)
  return nil unless kpi
  kpi['id'] = eid(card, '-summary')
  kpi
end

def build_axis_chart(card, kind)
  dims, meas = split_cols(card)
  if dims.empty? || meas.empty?
    # LIVE-VALIDATED FIX (2026-07-30): this used to WARN and then build the
    # element anyway. Sigma requires `yAxis` on an axis chart, so an element with
    # no measure is structurally invalid and the API rejects it with the
    # misleading `Invalid kind: "bar-chart"` — which fails the WHOLE workbook
    # POST, losing every other element too. The common trigger is a card whose
    # only measure is an untranslated Beast Mode (see prune_unresolvable_columns!).
    # Skipping the element keeps the rest of the workbook postable; the caller
    # .compact's nils and this warning names exactly what was dropped.
    warn_card(card, "#{kind}: SKIPPED — could not resolve both a dimension and a measure " \
                    "(dims=#{dims.size}, measures=#{meas.size}). Sigma requires yAxis on an " \
                    'axis chart, so emitting it would fail the entire workbook POST. Verify ' \
                    'against the card PNG and re-add by hand.')
    return nil
  end
  ct = card['chartType'].to_s.downcase
  xcol = dims.first
  dcols = dims.map { |d| dim_col(d, card) }
  mcols = meas.map { |m| measure_col(m, card) }
  el = {
    'id' => eid(card), 'kind' => kind, 'name' => card['title'],
    'source' => { 'kind' => 'table', 'elementId' => 'master' },
    'columns' => dcols + mcols,
  }
  if xcol
    xa = { 'columnId' => dcols.first['id'], 'format' => AXIS_OFF }
    # Sort by the first measure if the card ordered by a measure, OR if this is
    # the badge_treemap degradation (no native treemap kind — see
    # NO_NATIVE_EQUIVALENT — sorting descending by size is the closest a flat
    # bar-chart gets to the area-proportional hierarchy).
    is_treemap = ct == 'badge_treemap'
    xa['sort'] = { 'by' => mcols.first['id'], 'direction' => 'descending' } if mcols.first && (Array(card['orderBy']).any? || is_treemap)
    el['xAxis'] = xa
  end
  el['yAxis'] = { 'columnIds' => mcols.map { |m| m['id'] }, 'format' => AXIS_OFF } unless mcols.empty?
  if kind == 'bar-chart'
    # #2/#3: orientation/stacking keyed on the EXACT chartType token, not a
    # `.include?('horiz')` substring check (the same class of bug this whole
    # map fix addresses — see refs/card-to-element.md Problem 2).
    el['orientation'] = 'horizontal' if HORIZONTAL_CHART_TYPES.include?(ct)
    el['stacking'] = bar_stacking_for(ct)
    if ct == 'badge_vert_nestedbar'
      warn_card(card, 'badge_vert_nestedbar: Sigma has no 2-level nested-category axis — ' \
                      'approximated as a flat grouped bar chart (the outer grouping tier is lost).')
    end
  end
  if kind == 'scatter-chart'
    # badge_bubble: bind the BUBBLESIZE-mapped column (if the extraction
    # captured `mapping`) to the scatter's optional size channel.
    bubble = (card['columns'] || []).find { |c| c['mapping'].to_s.upcase == 'BUBBLESIZE' }
    el['size'] = { 'id' => measure_col(bubble, card)['id'] } if bubble
  end
  el
end

# ---- pie-chart / donut-chart --------------------------------------------
# Both use `value` (the measure, referenced by `id` — NOT `columnId`, the
# opposite of a KPI) + `color` (the dimension) instead of xAxis/yAxis. The
# previous implementation reused build_axis_chart and just overwrote `kind`,
# which shipped an xAxis/yAxis-shaped element with no `value`/`color` at all —
# not a valid pie/donut spec. `pie-chart` is the same shape as `donut-chart`
# minus the donut-only hole/holeValue/innerRadius fields (verified against the
# sigma-workbooks skill's charts.md).
def build_pie_or_donut(card, kind)
  dims, meas = split_cols(card)
  warn_card(card, "#{kind}: could not resolve both a dimension (color) and a measure (value) — " \
                  'verify against the card PNG.') if dims.empty? || meas.empty?
  dcol = dims.first ? dim_col(dims.first, card) : nil
  mcol = meas.first ? measure_col(meas.first, card) : nil
  {
    'id' => eid(card), 'kind' => kind, 'name' => card['title'],
    'source' => { 'kind' => 'table', 'elementId' => 'master' },
    'columns' => [dcol, mcol].compact,
    'value' => mcol ? { 'id' => mcol['id'] } : nil,   # ⚠ donut/pie use value.id, NOT columnId
    'color' => dcol ? { 'id' => dcol['id'] } : nil,
  }.compact
end

# ---- combo-chart (badge_line_bar / badge_line_stackedbar / badge_pop_bar_line /
# badge_symbol_bar / badge_vert_symbol_overlay) ------------------------------
# Domo's ChartType alone doesn't say WHICH measure is the bar vs. the secondary
# series, so this uses a documented, honest heuristic: the FIRST measure is the
# primary (bar) series; every other measure takes the secondary shape (line or
# scatter, per COMBO_SECONDARY_TYPE). Flagged for review when the measure count
# isn't the expected 2.
def build_combo(card)
  dims, meas = split_cols(card)
  ct = card['chartType'].to_s.downcase
  secondary = COMBO_SECONDARY_TYPE[ct] || 'line'
  if meas.size != 2
    warn_card(card, "combo-chart: expected a bar measure + a #{secondary} measure (2 total) but found " \
                    "#{meas.size} — verify the series assignment against the card PNG.")
  end
  dcols = dims.map { |d| dim_col(d, card) }
  mcols = meas.map { |m| measure_col(m, card) }
  series = mcols.each_with_index.map { |m, i| { 'columnId' => m['id'], 'type' => i.zero? ? 'bar' : secondary } }
  el = {
    'id' => eid(card), 'kind' => 'combo-chart', 'name' => card['title'],
    'source' => { 'kind' => 'table', 'elementId' => 'master' },
    'columns' => dcols + mcols,
  }
  el['xAxis'] = { 'columnId' => dcols.first['id'], 'format' => AXIS_OFF } if dcols.first
  el['yAxis'] = { 'columnIds' => series, 'format' => AXIS_OFF } unless series.empty?
  el['stacking'] = 'stacked' if ct == 'badge_line_stackedbar'
  el
end

# ---- badge_map -> Sigma region-map -----------------------------------------
# Sigma's real map kinds are geography-map / point-map / region-map (a bare
# "map" kind is confirmed INVALID — verified against the sigma-workbooks
# skill's docs/sigma-trellis-chart-support.md). This converter only attempts
# region-map (Domo's geo cards are overwhelmingly country/state/zip choropleths,
# not lat/long point plots) and degrades honestly to a table — with a loud
# warning, never a silent substitution — when the geography column can't be
# classified into one of Sigma's regionType values.
REGION_TYPE_HINTS = [
  [/zip|postal/i, 'us-zipcode'],
  [/county/i,     'us-county'],
  [/cbsa|metro/i, 'us-cbsa'],
  [/province/i,   'ca-province'],
  [/state/i,      'us-state'],
  [/country/i,    'country'],
].freeze

def infer_region_type(dim)
  name = (dim && (dim['alias'] || dim['column'])).to_s
  hit = REGION_TYPE_HINTS.find { |(re, _)| name =~ re }
  hit && hit[1]
end

def build_map(card)
  dims, meas = split_cols(card)
  geo = dims.first
  region_type = infer_region_type(geo)
  unless region_type
    geo_name = geo && (geo['alias'] || geo['column'])
    warn_card(card, "badge_map: could not classify the geography column '#{geo_name}' into a Sigma " \
                    'regionType (country/us-state/us-county/us-zipcode/us-cbsa/ca-province) — no ' \
                    'native Sigma equivalent for this geography; emitted a table instead (candidate ' \
                    'for a Sigma custom plugin — see refs/card-to-element.md).')
    return build_table(card)
  end
  gcol = dim_col(geo, card)
  mcol = meas.first ? measure_col(meas.first, card) : nil
  {
    'id' => eid(card), 'kind' => 'region-map', 'name' => card['title'],
    'source' => { 'kind' => 'table', 'elementId' => 'master' },
    'columns' => [gcol, mcol].compact,
    'region' => { 'id' => gcol['id'], 'regionType' => region_type },
    'color' => mcol ? { 'by' => 'scale', 'column' => mcol['id'] } : nil,
  }.compact
end

def build_table(card)
  dims, meas = split_cols(card)
  mcols = meas.map { |m| measure_col(m, card) }
  cols = dims.map { |d| dim_col(d, card).merge('style' => { 'textWrap' => 'wrap' }) } + mcols
  cols = (card['columns'] || []).map { |c| dim_col(c, card).merge('style' => { 'textWrap' => 'wrap' }) } if cols.empty?
  el = {
    'id' => eid(card), 'kind' => 'table', 'name' => card['title'],
    'source' => { 'kind' => 'table', 'elementId' => 'master' },
    'columns' => cols, 'order' => cols.map { |c| c['id'] },
  }

  # A Sigma `table` with NO `groupings` shows raw DETAIL rows — the
  # sigma-workbooks spec calls this "the #1 migration bug for aggregated source
  # vizzes" (reference/specification/tables.md § groupings). A Domo table card
  # with a dimension + an aggregated measure IS an aggregated query, so it MUST
  # carry a groupings entry; without one the dimension repeats per warehouse row
  # and each measure cell shows a ROW value instead of the group total.
  #
  # Caught live by the anchors oracle (2026-07-30): the source card printed
  # 58,494.90 gross profit for Online, and the migrated table's closest value was
  # 487.96 — a single row — because groupBy was dropped. Charts don't need this
  # (they aggregate by their axis/value binding); only `table` does.
  #
  # `calculations` must be AGGREGATE expressions, which measure_col already emits
  # (Sum(...)/CountDistinct(...)/an inlined aggregate Beast Mode). A grouped
  # table's SORT must nest inside the grouping — an element-level sort 400s.
  unless dims.empty? || meas.empty?
    grouping = {
      'id' => "grp-#{eid(card)}",
      'groupBy' => dims.map { |d| dim_col(d, card)['id'] },
      'calculations' => mcols.map { |m| m['id'] },
    }
    el['groupings'] = [grouping]
  end

  # #7: in-cell data bars belong ONLY to a real Domo table card that declared them.
  bars = Array(card['conditionalFormats']).select { |cf| cf.to_s.downcase.include?('databar') || cf.dig('format', 'dataBar') }
  unless bars.empty?
    el['conditionalFormats'] = [{ 'type' => 'dataBars', 'columnIds' => mcols.map { |m| m['id'] } }]
  end

  # bead 2ef7: a Domo card's row LIMIT (e.g. limit:25 on a "Top 25" table) has no
  # query-level analog in Sigma — without a translation the table just renders
  # every warehouse row (872 instead of 25, live-validated 2026-07-30). The Sigma
  # analog is an element-level top-n FILTER: `rowCount` takes a number literal
  # only (reference/specification/tables.md "top-N, element-level row filters") —
  # it cannot be bound to a control, so this is a direct, static translation.
  # Ranks by the FIRST measure (mirrors the existing "sort by first measure"
  # convention in build_axis_chart's xa['sort']) — Sigma's top-n ranks
  # DESCENDING only; an ascending Domo orderBy has no equivalent here and is left
  # alone rather than silently reversed. No measure column -> nothing to rank by
  # -> no filter emitted (never a columnId: nil filter).
  limit = card['limit'].to_i
  if limit.positive? && mcols.any?
    el['filters'] = [{
      'id' => "topn-#{el['id']}", 'columnId' => mcols.first['id'],
      'kind' => 'top-n', 'rankingFunction' => 'rank', 'mode' => 'top-n', 'rowCount' => limit,
    }]
  end
  el
end

def build_pivot(card)
  dims, meas = split_cols(card)
  warn_card(card, 'pivot-table: rowsBy/columnsBy split inferred — verify against the card PNG.') if dims.size < 2
  {
    'id' => eid(card), 'kind' => 'pivot-table', 'name' => card['title'],
    'source' => { 'kind' => 'table', 'elementId' => 'master' },
    'columns' => (dims + meas).map { |c| meas.include?(c) ? measure_col(c, card) : dim_col(c, card) },
    'rowsBy' => dims.first(1).map { |d| dim_col(d, card)['id'] },
    'columnsBy' => dims.drop(1).map { |d| dim_col(d, card)['id'] },   # pivot REQUIRES both (feedback_sigma_pivot_rowsby_columnsby)
    'values' => meas.map { |m| measure_col(m, card)['id'] },
  }
end

# ---- image / logo / drawing cards (tableau build-charts-from-signals.rb:6655 pattern) ----
# Inline data-URI — no hosting required. PNG/JPEG data-URIs POST + render cleanly
# (only base64-SVG is WAF-blocked; Domo logos are raster PNG).
# NOTE: 'richtext' is deliberately excluded — it overlaps the text/title row
# (refs/card-to-element.md); richtext stays a text element, not an image.
IMAGE_CHART_TYPE_RE = /image|logo|drawing|picture/i

# The staged capture path capture_card (domo-capture-visuals.rb) writes to, or
# the card's own override if the caller already resolved one.
def png_path(card)
  card['_pngPath'] || File.join(OUT, 'png', 'cards', "#{card['id']}.png")
end

# True ONLY for a card whose chartType explicitly names it as a static
# image/logo/drawing asset. Do NOT also key off "no data columns + a staged
# PNG exists" — domo-capture-visuals.rb's capture_card renders a PNG for
# EVERY card on a page (filter widgets, text/title cards included), so that
# combination is not a useful discriminator and silently misroutes cards that
# belong on the control path (chartType 'filter') or the text path (chartType
# 'text'/'title') into a flat raster image with no warning. An image-ish card
# that doesn't match this chartType check falls through to the existing
# placeholder path + warn_card below — the honest fidelity-discipline default.
def image_card?(card)
  card['chartType'].to_s =~ IMAGE_CHART_TYPE_RE ? true : false
end

# build_image(card) -> {id, kind:'image', url:"data:image/png;base64,<b64>"} or
# nil when no PNG was captured (Tier B / not captured) — the caller falls back
# and warns; NEVER emit an image element with an empty/broken url.
def build_image(card)
  path = png_path(card)
  return nil unless path && File.exist?(path.to_s)
  { 'id' => eid(card), 'kind' => 'image',
    'url' => "data:image/png;base64,#{Base64.strict_encode64(File.binread(path))}" }
end

# Translated Beast Mode ids (those that actually produced a sigmaFormula and so
# EXIST as DM calc columns). convert-beast-modes.rb --lint deliberately DROPS
# untranslated formulas rather than shipping bad SQL, so a card bound to one is
# referencing a column the data model does not have.
def translated_beast_modes
  return $translated_bms if defined?($translated_bms) && $translated_bms
  path = File.join(OUT, 'formulas.json')
  list = (JSON.parse(File.read(path)) rescue nil)
  by_id = {}
  Array(list).each do |f|
    next unless f.is_a?(Hash)
    next if f['sigmaFormula'].to_s.strip.empty?
    by_id[f['id'].to_s] = f
    by_id[f['name'].to_s] = f unless f['name'].to_s.empty?
  end
  $translated_bms = by_id
end

def translated_beast_mode_ids
  translated_beast_modes
end

# Rewrite bare column refs in a Sigma formula to the shared-master namespace.
# A translated Beast Mode comes back referencing bare columns — [Net Revenue] —
# but every element here sources the hidden `master` table, so its formulas must
# read [Master/Net Revenue]. Already-qualified refs (any "<something>/") are left
# alone so this is idempotent.
def masterize_formula(formula)
  formula.to_s.gsub(/\[([^\[\]\/]+)\]/) { "[Master/#{Regexp.last_match(1)}]" }
end

# An AGGREGATE (or window) Beast Mode cannot be a data-model column — build-dm
# only promotes PROJECTION (row-level) Beast Modes to DM calc columns, because an
# aggregate expression has no row-level value. So for an aggregate Beast Mode the
# correct Sigma shape is to INLINE its translated expression as the element's
# measure formula, un-wrapped:
#
#   Domo  "Margin Pct" = (CASE WHEN (SUM(`NET_REVENUE`) = 0) THEN 0
#                         ELSE (SUM(`GROSS_PROFIT`) / SUM(`NET_REVENUE`)) END )
#   Sigma element column formula:
#         If(Sum([Master/Net Revenue]) = 0, 0,
#            Sum([Master/Gross Profit]) / Sum([Master/Net Revenue]))
#
# NOT Sum([Master/Margin Pct]) — that column does not exist, and wrapping an
# already-aggregating expression in another aggregate is wrong anyway. Before this
# existed, an aggregate Beast Mode had NOWHERE to go: build-dm skipped it (not
# projection) and build-workbook dropped the column, so the card lost its measure.
def inline_beast_mode_measure(card, c)
  bm = translated_beast_modes[c['beastModeId'].to_s] ||
       translated_beast_modes[c['column'].to_s]
  return nil unless bm.is_a?(Hash)
  return nil unless %w[aggregate window].include?(bm['class'].to_s)
  { 'id' => "m-#{c['column'].to_s.downcase.gsub(/\W+/, '-')}",
    'name' => col_label(c),
    'formula' => masterize_formula(bm['sigmaFormula']),
    'format' => sigma_format(c['format'], col_label(c)) }.compact
end

# Drop columns that CANNOT resolve to a real DM column, loudly.
#
# LIVE-VALIDATED FIX (2026-07-30): two ways a column silently became invalid —
#   1. a Beast-Mode-bound column whose id never resolved to a name emitted
#        Sum([Master/])            -> Sigma: "Invalid formula"
#   2. a Beast-Mode-bound column whose formula never TRANSLATED emitted
#        Sum([Master/Avg Order Value])  -> Sigma: "dependency not found"
#      HISTORICAL CONTEXT for why this path exists: when this was written, 74%
#      of real Beast Modes failed the SQL->Sigma converter (CASE WHEN and
#      COUNT(DISTINCT) both mistranslated; see refs/live-validation-2026-07-30.md).
#      That's fixed now (sigma-data-model-mcp PR #115 then #116) — re-measured,
#      37/74 distinct Beast Modes match a converter rule exactly, and the rest
#      no longer come back corrupted, just not fully translated (e.g. an infix
#      `LIKE` with no Sigma equivalent). This path stays: convert-beast-modes.rb
#      still correctly DROPS a Beast Mode it can't translate rather than
#      shipping bad SQL, so a bound column with no sigmaFormula is still a real,
#      if now much rarer, case this guard must keep catching.
# Either way Sigma rejects the request and the ENTIRE workbook POST fails — one
# bad column takes down every other element. Dropping the column (and, if it
# leaves nothing to plot, the element) keeps the rest of the migration postable
# while naming exactly what was lost. Never silent: each drop is a warning the
# Phase-5e gate surfaces.
def prune_unresolvable_columns!(card)
  cols = card['columns']
  return card unless cols.is_a?(Array)
  ok = []
  cols.each do |c|
    if c['column'].to_s.strip.empty?
      warn_card(card, "dropped a column with no resolvable name (Beast Mode id " \
                      "#{c['beastModeId'].inspect} did not resolve) — would have emitted " \
                      'an empty [Master/] reference that Sigma rejects.')
      next
    end
    # An aggregate/window Beast Mode with a translated formula is legitimately
    # NOT a data-model column — it gets inlined as the element's measure formula
    # instead (inline_beast_mode_measure), so do not prune it here.
    if c['_isCalc'] && inline_beast_mode_measure(card, c)
      ok << c
      next
    end
    if c['_isCalc'] && c['beastModeId'] && !translated_beast_modes[c['beastModeId'].to_s] &&
       !translated_beast_modes[c['column'].to_s]
      warn_card(card, "dropped column #{c['column'].inspect}: its Beast Mode did not " \
                      'translate to a Sigma formula, so no such data-model column exists. ' \
                      'Hand-author the formula (see the Beast Mode section of ' \
                      'refs/live-validation-2026-07-30.md) and re-run.')
      next
    end
    ok << c
  end
  card['columns'] = ok
  card
end

# The dataset the single shared `master` element is built from — every element
# emitted here sources `master`, and build-workbook-spec.rb builds that master
# from ONE data-model element. Cards bound to any OTHER DataSet would reference
# columns the master does not have.
#
# LIVE-VALIDATED (2026-07-30): a page mixing two DataSets failed the whole
# workbook POST with
#   pages[N].elements[M]: Dependency not found: 'master/region'
# (a customer-dim card on a page whose master is the order fact). Multi-dataset
# pages are normal in Domo — cards are independently dataset-bound. Properly
# supporting them means one master per used DataSet (bead ziht); until then,
# SKIP the off-master cards loudly so the rest of the workbook still posts.
def dominant_dataset_id(cards)
  counts = {}
  Array(cards).each do |c|
    id = c['datasetId'].to_s
    next if id.empty?
    counts[id] = (counts[id] || 0) + 1
  end
  return nil if counts.empty?
  counts.max_by { |_, n| n }.first
end

# Deep-rewrite every "[Master/" formula ref + the element's own source to point
# at a per-DataSet sub-master instead of the shared primary master (bead ziht).
# gsub (not sub) — an inlined aggregate Beast Mode formula can reference
# [Master/...] more than once in a single string (e.g. an If() with two Sum()s).
#
# M1 (final review): guard the `source` rewrite — build_image's element has NO
# `source` key at all (it's a bare data-URI), and unconditionally setting one
# would fabricate a bogus source binding on an image element that never had
# one. Every other element kind here (chart/table/kpi/pivot/map) always
# carries `source`, so this only ever actually skips for an image.
def retarget_to_submaster!(el, sm)
  el['source'] = { 'kind' => 'table', 'elementId' => sm['id'] } if el.key?('source')
  walk = lambda do |n|
    case n
    # LIVE-VALIDATED FIX (2026-07-31): AXIS_OFF ({'marks'=>'none'}.freeze) is a
    # shared frozen constant referenced by every axis-chart element's
    # xAxis/yAxis 'format' — mutating it in place raised FrozenError the first
    # time this routed an axis-chart card (Domo page 'Orders Executive',
    # "Customers by Region"). A frozen Hash/Array in this codebase is always
    # static shared config, never a dynamic [Master/...] reference, so it's
    # always safe to leave it untouched rather than walk into it.
    when Hash   then (n.frozen? ? n : n.each { |k, v| n[k] = walk.call(v) })
    when Array  then (n.frozen? ? n : n.map! { |v| walk.call(v) })
    when String then n.gsub('[Master/', "[#{sm['name']}/")
    else n
    end
  end
  walk.call(el)
  el
end

def build_element(card, overrides, master_ds = nil)
  ds = card['datasetId'].to_s
  routed = master_ds && !ds.empty? && ds != master_ds
  sm = nil
  if routed
    sm = sub_master_for(ds)
    unless sm
      warn_card(card, "SKIPPED — card is bound to DataSet #{ds} but this workbook's shared " \
                      "master is built from #{master_ds}, and no live data-model element is " \
                      'resolvable yet for its own DataSet (bead ziht). Rebuild this card by ' \
                      'hand against its own source, or re-run once the data model has posted.')
      return nil
    end
  end

  before = $companion_elements.length
  el = build_element_body(card, overrides)
  if el.nil?
    # C1 (final review, promoted from a deferred Task-5 minor to BLOCKING): a
    # card whose primary element failed to build must not leave behind an
    # orphaned companion KPI. build_element_body itself now defers pushing a
    # companion onto $companion_elements until it knows the primary built (see
    # below) — so in the ordinary case this slice is a no-op — but truncate
    # here too, defensively, at the one call site that actually decides
    # whether this card's build succeeded: a companion that somehow reached
    # $companion_elements during a failed attempt must never survive it. For
    # the ROUTED (non-dominant-dataset) case specifically, surviving here
    # would mean a companion still sourcing the SHARED master's namespace
    # instead of the sub-master's — reintroducing the exact "Dependency not
    # found" whole-workbook-POST failure bead ziht exists to prevent.
    $companion_elements.slice!(before..-1)
    return nil
  end

  if routed
    retarget_to_submaster!(el, sm)
    $companion_elements[before..-1].each { |c| retarget_to_submaster!(c, sm) }
    warn_card(card, "routed to sub-master '#{sm['name']}' for DataSet #{ds} (bead ziht) — " \
                    'verify column coverage against the card PNG; the sub-master passes through ' \
                    "every column of #{sm['name']}, not just the ones this card uses.")
  end
  el
end

def build_element_body(card, overrides)
  card = prune_unresolvable_columns!(card)
  # Rule 0: a summary-number card with no real grouping → KPI, never a table.
  kind = card['sigmaKindHint']
  is_kpi = kind == 'kpi-chart' ||
           (card['summaryNumber'] && Array(card['groupBy']).empty? && (card['columns'] || []).size <= 1)
  return build_kpi(card, overrides) if is_kpi

  # Domo prints a Summary Number at the top of EVERY viz card, not just KPI
  # cards. Sigma's chart/table elements have no summary slot, so this
  # RESOLVES a companion KPI element (bead 08sf) here, but does NOT push it
  # onto $companion_elements (or warn about it) until the primary element
  # below is confirmed to have actually built — see the bottom of this
  # method. M3/C1 (final review): a companion pushed before that point would
  # outlive a primary that then fails to build, leaving an orphaned KPI with
  # no chart/table beside it and a warning claiming it "represents" a card
  # that was actually dropped.
  sn = card['summaryNumber']
  companion = nil
  if sn.is_a?(Hash) && !sn['column'].to_s.empty?
    companion = build_summary_companion(card, overrides)
    unless companion
      agg = sn['aggregation'].to_s.empty? ? '(calc)' : sn['aggregation']
      warn_card(card, "source Summary Number NOT represented: Domo prints " \
                      "#{agg}(#{sn['column']}) above this card, but a Sigma " \
                      "#{kind || 'chart'} element has no summary slot, and a companion KPI " \
                      'could not be built (no resolvable column) — the headline value is dropped.')
    end
  end

  el =
    if image_card?(card)
      img = build_image(card)
      if img
        img
      else
        # PNG absent (Tier B / not captured) — honest fallback: fall through
        # to the existing placeholder path below (unchanged) + flag it so it
        # gets fixed by hand rather than shipping a broken/empty image element.
        warn_card(card, "image card #{card['id']}: no captured PNG — export from Domo UI and embed manually.")
        nil
      end
    end

  if el.nil?
    # #2/#3: chartType is a STRICT Domo enum — EXACT-match it (never substring)
    # against the known-token table before falling back to any upstream hint.
    mapped = chart_kind_for(card)
    kind = mapped || kind
    ct = card['chartType'].to_s.downcase
    if mapped && NO_NATIVE_EQUIVALENT.key?(ct)
      warn_card(card, "no native Sigma equivalent for chartType '#{card['chartType']}' — " \
                      "#{NO_NATIVE_EQUIVALENT[ct]} Tracked as a Sigma custom-plugin follow-up " \
                      '(sigma-plugin-development skill) — not handled by this converter today.')
    end

    el = case kind
         when 'bar-chart', 'line-chart', 'area-chart', 'scatter-chart'
           build_axis_chart(card, kind)
         when 'combo-chart' then build_combo(card)
         when 'pie-chart', 'donut-chart' then build_pie_or_donut(card, kind)
         when 'pivot-table'  then build_pivot(card)
         when 'table'        then build_table(card)
         when 'region-map'   then build_map(card)
         when 'kpi-chart'
           # badge_filledgauge (and any other kpi-mapped chartType) may reach
           # here without a summaryNumber — never silently drop the card;
           # degrade to a table + warn rather than emit nil.
           build_kpi(card, overrides) || begin
             warn_card(card, "kpi-chart: chartType '#{card['chartType']}' has no summaryNumber to build a " \
                             'value from — emitted a table instead so the card is not silently dropped.')
             build_table(card)
           end
         else
           warn_card(card, "unknown chartType '#{card['chartType']}' → emitted bar-chart; verify against the PNG.")
           build_axis_chart(card, 'bar-chart')
         end
  end

  if companion
    if el
      $companion_elements << companion
      warn_card(card, "source Summary Number ALSO represented as a companion KPI element " \
                      "'#{companion['name']}' alongside this #{el['kind'] || kind || 'chart'} element " \
                      '(bead 08sf) — see build-domo-layout.rb for where it lands on the page.')
    else
      warn_card(card, "source Summary Number's companion KPI element '#{companion['name']}' was NOT " \
                      "emitted: the primary #{kind || 'chart'} element for this card failed to build, " \
                      'and a standalone companion with no primary chart/table beside it would be ' \
                      'confusing, not helpful (bead 08sf / C1).')
    end
  end

  el
end

# ---- controls (bug #2: fan out to EVERY element via the shared master) ------
def build_controls(cards, master_ds = nil)
  seen = {}
  controls = []
  cards.each do |card|
    ds = card['datasetId'].to_s
    Array(card['filters']).each do |f|
      col = f['column']; next if col.nil? || seen[col]
      if master_ds && !ds.empty? && ds != master_ds
        warn_card(card, "control filter on '#{col}' SKIPPED — its card is bound to DataSet " \
                        "#{ds}, not this workbook's shared master (#{master_ds}); binding it to " \
                        'master would 400 the whole workbook POST. Per-sub-master controls are ' \
                        'not yet supported (bead ziht follow-up).')
        next
      end
      seen[col] = true
      disp = display_name(col)
      controls << {
        'id' => "ctl-#{col.to_s.downcase.gsub(/\W+/, '-')}",
        'kind' => 'control',
        'controlId' => disp.gsub(/\s+/, ''),
        'controlType' => 'list',
        'name' => disp,
        # Bind to the shared master column ONCE — every element sourcing master
        # inherits it, so the filter no longer falls off after the first element.
        'filters' => [{ 'source' => { 'kind' => 'table', 'elementId' => 'master' },
                        'columnId' => mcol_id(disp) }],
      }
    end
  end
  controls
end

if $PROGRAM_NAME == __FILE__
  cards = JSON.parse(File.read(File.join(OUT, 'cards.json'))) rescue []
  pages = JSON.parse(File.read(File.join(OUT, 'pages.json'))) rescue []
  overrides = (JSON.parse(File.read(File.join(OUT, 'kpi-overrides.json'))) rescue {}) || {}

  cards = cards.reject { |c| c['_error'] || c['_tierB'] }
  # Group cards by page (fall back to a single page when page membership is absent).
  by_page = Hash.new { |h, k| h[k] = [] }
  card_page = {}
  pages.each do |p|
    Array(p['cardIds'] || p['cards']).each { |cid| card_page[cid.to_s] = p['title'] || p['name'] || p['id'] }
  end
  cards.each { |c| by_page[card_page[c['id'].to_s] || 'Overview'] << c }
  master_ds = dominant_dataset_id(cards)
  by_page.each { |pname, pcards| warn_missing_geometry(pname, pcards) }

  out_pages = by_page.map do |pname, pcards|
    before = $companion_elements.length
    els = pcards.map { |c| build_element(c, overrides, master_ds) }.compact
    els += $companion_elements[before..]
    els += build_controls(pcards, master_ds)
    { 'name' => pname, 'elements' => els }
  end

  FileUtils.mkdir_p(OUT)
  File.write(File.join(OUT, 'chart-specs.json'),
             JSON.pretty_generate('pages' => out_pages, 'data_elements' => $sub_masters.values))
  File.write(File.join(OUT, 'warnings.json'), JSON.pretty_generate($warnings))
  warn "  wrote #{File.join(OUT, 'chart-specs.json')} (#{out_pages.sum { |p| p['elements'].size }} elements across #{out_pages.size} page(s), #{$sub_masters.size} sub-master(s))"
  warn "  wrote #{File.join(OUT, 'warnings.json')} (#{$warnings.size} warning(s))"
  $warnings.first(20).each { |w| warn "    ⚠ #{w['card']}: #{w['warning']}" }
  warn "\n  Next: build-workbook-spec.rb --chart-specs discovery/chart-specs.json --dm-ids discovery/dm-ids.json ..."
end
