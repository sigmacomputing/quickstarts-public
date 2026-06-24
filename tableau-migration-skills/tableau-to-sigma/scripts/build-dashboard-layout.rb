#!/usr/bin/env ruby
# Build a Sigma layout XML that mirrors a Tableau dashboard's zone grid for
# dashboard-fidelity conversion mode (Phase 0b).
#
# Output: a layout XML with two pages —
#   1. <Page id="page-data">: hidden master element spanning the page
#   2. <Page id="<overview-page-id>">: title + N controls + N chart tiles
#      positioned at grid cells derived from each Tableau zone's x/y/w/h%.
#
# Crucially: walks each chart row left-to-right and STRETCHES each chart's
# right edge to meet the next chart's left edge so there are no empty columns
# between adjacent tiles (Tableau dashboards often have separate legend/filter
# zones between two tiles that Sigma doesn't render; without this step, those
# gaps stay visible).
#
# Usage:
#   ruby scripts/build-dashboard-layout.rb \
#     --layout /tmp/<name>/dashboard-layout.json \
#     --wb-ids /tmp/<name>/wb-ids.json \
#     --out /tmp/<name>/layout.xml
#
# Optional:
#   --page-cols N    Sigma grid columns (default 24)
#   --page-rows N    visible rows BEFORE row scaling (default 32)
#   --row-scale F    multiply the chart band's row count (default 1.5).
#                    Tableau zone h% mapped 1:1 onto a 32-row Sigma page makes
#                    tiles too short — Sigma suppresses axis labels / pie slice
#                    labels below ~5-6 grid rows (bead tkkv; the looker builder
#                    uses ROW_SCALE=2, tableau E2E found 1.43× sufficient —
#                    default 1.5 preserves proportions while clearing the
#                    label-suppression threshold). Pass --row-scale 1 to get
#                    the old un-scaled mapping.
#   --rename PAIR    "Tableau name=Sigma name" (repeatable) — same flag as the
#                    parity scripts. A chart tile renamed during conversion
#                    otherwise fails the zone→element name match and silently
#                    drops out of the layout (bead ddbq).
#   --chart-y0 PCT   top of the chart band as Tableau %  (default 29.7)
#   --chart-y1 PCT   bottom of the chart band as Tableau % (default 100.0)
#   --chart-row0 N   first grid row of the chart band     (default 6)

require 'json'
require 'optparse'
require_relative 'lib/layout'
include SigmaLayout

opts = { page_cols: 24, page_rows: 32, row_scale: 1.5, chart_y0: 29.7,
         chart_y1: 100.0, chart_row0: 6, renames: {} }
OptionParser.new do |p|
  p.on('--layout PATH')        { |v| opts[:layout] = v }
  p.on('--wb-ids PATH')        { |v| opts[:wb_ids] = v }
  p.on('--out PATH')           { |v| opts[:out] = v }
  p.on('--page-cols N',  Integer) { |v| opts[:page_cols] = v }
  p.on('--page-rows N',  Integer) { |v| opts[:page_rows] = v }
  p.on('--row-scale F',  Float, 'row-height multiplier (default 1.5; min label-safe ~1.43)') { |v| opts[:row_scale] = v }
  p.on('--rename PAIR', 'Tableau-name=Sigma-name (repeat) — matches the parity scripts\' flag') do |v|
    from, to = v.split('=', 2)
    abort("--rename expects 'Tableau name=Sigma name', got #{v.inspect}") if from.nil? || to.nil? || from.empty? || to.empty?
    opts[:renames][from] = to
  end
  p.on('--chart-y0 PCT', Float)   { |v| opts[:chart_y0] = v }
  p.on('--chart-y1 PCT', Float)   { |v| opts[:chart_y1] = v }
  p.on('--chart-row0 N', Integer) { |v| opts[:chart_row0] = v }
  p.on('--no-containers', 'force the geometry-banded layout even when the dashboard nests a filter/parameter rail') { opts[:no_containers] = true }
end.parse!
%i[layout wb_ids out].each { |k| abort("missing --#{k.to_s.tr('_','-')}") unless opts[k] }

# Row scaling (bead tkkv): scale the page's row count so each chart band tile
# gets proportionally more rows. Title (rows 1-3) and controls (rows 3-6) keep
# their fixed positions; only the chart band [chart_row0..page_rows] stretches.
opts[:page_rows] = (opts[:page_rows] * opts[:row_scale]).round if opts[:row_scale] != 1.0

dash_layout = JSON.parse(File.read(opts[:layout]))
wb_ids      = JSON.parse(File.read(opts[:wb_ids]))

# Page lookups
data_page  = wb_ids['pages'].find { |p| p['name'] == 'Data' }
abort('no "Data" page in wb-ids') unless data_page
master_el  = data_page['elements'].first

# Multi-dashboard workbooks (bead ptrt): ONE Sigma page per Tableau dashboard,
# each with its own container-banded layout. Pair each dashboard to the page
# with the same name; when the workbook has a single non-Data page (legacy
# single-dashboard flow), pair the first dashboard to it.
content_pages = wb_ids['pages'].reject { |p| p['name'] == 'Data' || p['name'].nil? }
content_pages = [wb_ids['pages'][1]].compact if content_pages.empty?
abort('no overview page (non-Data) in wb-ids') if content_pages.empty?

page_for_dash = {}
dash_layout.each do |d|
  pg = content_pages.find { |p| p['name'] == d['dashboard'] }
  pg ||= content_pages.first if dash_layout.length == 1
  if pg.nil?
    warn "WARN: no Sigma page matched dashboard #{d['dashboard'].inspect} — dashboard skipped from layout"
    next
  end
  page_for_dash[d['dashboard']] = pg
end
abort('no dashboard↔page pairs resolved') if page_for_dash.empty?

def chart_pos(z, opts)
  y0 = z['y_pct'] || 0
  h  = z['h_pct'] || 0
  y1 = y0 + h
  remaining_rows = opts[:page_rows] - (opts[:chart_row0] - 1)
  span = (opts[:chart_y1] - opts[:chart_y0]).to_f
  span = 1.0 if span <= 0
  row_start = (opts[:chart_row0] + (y0 - opts[:chart_y0]) / span * remaining_rows).round
  row_end   = (opts[:chart_row0] + (y1 - opts[:chart_y0]) / span * remaining_rows).round
  # Sigma rejects non-positive grid positions ("Invalid element position").
  # Clamp into the legal band [chart_row0 .. page_rows+1] and guarantee a span.
  max_row   = opts[:page_rows] + 1
  row_start = [[row_start, opts[:chart_row0]].max, max_row - 1].min
  row_end   = [[row_end,   row_start + 1].max,      max_row].min
  row_end   = row_start + 1 if row_end <= row_start
  col_start = [1,  (1 + (z['x_pct'] || 0) / 100.0 * opts[:page_cols]).round].max
  col_end   = [opts[:page_cols] + 1, (1 + ((z['x_pct'] || 0) + (z['w_pct'] || 0)) / 100.0 * opts[:page_cols]).round].min
  col_end   = col_start + 1 if col_end <= col_start
  [col_start, col_end, row_start, row_end]
end

# ---- Faithful container-tree layout (preferred when a control rail exists) --
# Mirror Tableau's nested zone tree as nested Sigma GridContainers so each
# filter / parameter / chart lands INSIDE the container it lives in — preserving
# the left-rail / sidebar idiom and arbitrary nesting — instead of re-banding by
# raw geometry (which lumps every control into one top strip). Activates only
# when the dashboard actually nests a filter/parameter zone; otherwise the
# proven banded path runs. Any failure falls back to bands (rescued in caller).

def clampc(v, lo, hi)
  [[v, lo].max, hi].min
end

# True when the zone tree contains a filter/parameter zone at any depth — the
# case the banded path mishandles and the container path fixes.
def tree_has_controls?(tree)
  (tree || []).any? do |n|
    %w[filter parameter].include?(n['kind']) || tree_has_controls?(n['children'])
  end
end

# Place a child within its parent container's internal 24-col grid from pct
# bounds. parent_rows = grid row-lines the parent spans internally.
def place_in_parent(ch, p, parent_rows)
  pw = (p['w_pct'] || 100).to_f; pw = 1.0 if pw <= 0
  ph = (p['h_pct'] || 100).to_f; ph = 1.0 if ph <= 0
  px = (p['x_pct'] || 0).to_f;   py = (p['y_pct'] || 0).to_f
  cx = (ch['x_pct'] || 0).to_f;  cy  = (ch['y_pct'] || 0).to_f
  cw = (ch['w_pct'] || 0).to_f;  chh = (ch['h_pct'] || 0).to_f
  c0 = clampc(1 + ((cx - px) / pw * 24).round, 1, 24)
  c1 = clampc(1 + ((cx + cw - px) / pw * 24).round, c0 + 1, 25)
  r0 = [1, 1 + ((cy - py) / ph * parent_rows).round].max
  r1 = [r0 + 1, 1 + ((cy + chh - py) / ph * parent_rows).round].max
  [c0, c1, r0, r1]
end

# Resolve a leaf zone to an existing workbook element id (chart by caption,
# filter/param control by target-column / caption, title text to the page
# title). Returns nil for zones Sigma renders inline (legend) or drops (spacer).
def resolve_leaf(node, ctx)
  case node['kind']
  when 'chart'
    name = ctx[:renames][node['caption']] || node['caption']
    el = ctx[:els_by_name][name]
    el && el['id']
  when 'filter', 'parameter'
    # Pre-assigned by build_page_from_tree (caption match, then rail-fill) so a
    # control lands in its container even when its target column didn't resolve.
    ctx[:zone_to_ctl][node['id']]
  when 'text', 'title'
    if ctx[:title_el] && !ctx[:title_used]
      ctx[:title_used] = true
      ctx[:title_el]['id']
    end
  end
end

# Recursively emit a zone node as Sigma layout XML at grid cell (c0,c1,r0,r1)
# RELATIVE to its parent container. Container nodes become GridContainers whose
# children are placed in the container's own 24-col internal grid; empty
# containers (no resolvable children) are dropped. Appends new container spec
# placeholders to ctx[:extra]; records placed element ids in ctx[:placed].
def emit_node(node, c0, c1, r0, r1, ctx)
  if node['kind'] == 'container'
    kids = node['children'] || []
    my_rows = [r1 - r0, 2].max
    inner = kids.map do |ch|
      kc0, kc1, kr0, kr1 = place_in_parent(ch, node, my_rows)
      emit_node(ch, kc0, kc1, kr0, kr1, ctx)
    end.compact
    return nil if inner.empty?
    cid = "tc-#{ctx[:page_id]}-#{node['id']}"
    ctx[:extra] << container_el(cid)
    gc(cid, c0, c1, r0, r1, inner.join("\n"))
  else
    eid = resolve_leaf(node, ctx)
    return nil unless eid && !ctx[:placed].include?(eid)
    ctx[:placed] << eid
    le(eid, c0, c1, r0, r1)
  end
end

# Container-tree page builder. Same return shape as build_page_for_dashboard.
def build_page_from_tree(dashboard, page, opts)
  tree        = dashboard['zone_tree'] || []
  els_by_name = page['elements'].each_with_object({}) { |e, h| h[e['name']] = e if e['name'] }
  ctl_by_name = page['elements'].select { |e| e['kind'] == 'control' && e['name'] }
                    .each_with_object({}) { |e, h| h[e['name'].to_s.downcase] = e }
  title_el    = page['elements'].find { |e| e['kind'] == 'text' }

  ctx = { page_id: page['id'], renames: opts[:renames], els_by_name: els_by_name,
          ctl_by_name: ctl_by_name, title_el: title_el, title_used: false,
          extra: [], placed: [], zone_to_ctl: {} }

  # Assign workbook control elements to control zones (filter/parameter), in
  # document order: caption match first, then fill the remaining control zones
  # with leftover controls. This puts a rail's controls INSIDE the rail even
  # when a zone's target column didn't resolve to a caption.
  control_zones = []
  collect = lambda { |ns| (ns || []).each { |n| control_zones << n if %w[filter parameter].include?(n['kind']); collect.call(n['children']) } }
  collect.call(tree)
  all_ctls = page['elements'].select { |e| e['kind'] == 'control' }
  used = {}
  control_zones.each do |z|
    nm = (z['filter_column_caption'] || z['caption']).to_s.downcase
    el = nm.empty? ? nil : ctl_by_name[nm]
    next unless el && !used[el['id']]
    ctx[:zone_to_ctl][z['id']] = el['id']; used[el['id']] = true
  end
  leftover = all_ctls.reject { |e| used[e['id']] }
  control_zones.each do |z|
    next if ctx[:zone_to_ctl][z['id']]
    el = leftover.shift or next
    ctx[:zone_to_ctl][z['id']] = el['id']; used[el['id']] = true
  end

  children  = []
  extra_els = ctx[:extra]
  page_rows = opts[:page_rows]
  body_rows = [page_rows - HEADER_ROWS, 4].max
  page_pseudo = { 'x_pct' => 0.0, 'y_pct' => 0.0, 'w_pct' => 100.0, 'h_pct' => 100.0 }

  # Header band (dark title strip), same chrome as the banded path.
  hdr_id = "tc-#{page['id']}-hdr"
  extra_els << container_el(hdr_id, HEADER_STYLE.dup)
  if title_el
    children << header_band_xml(hdr_id, title_el['id'])
    ctx[:title_used] = true
  else
    txt_id = "tc-#{page['id']}-hdrtext"
    extra_els << header_text_el(txt_id, page['name'])
    children << header_band_xml(hdr_id, txt_id)
  end

  # Top-level zones → page children, shifted below the header band.
  tree.each do |node|
    c0, c1, r0, r1 = place_in_parent(node, page_pseudo, body_rows)
    r0 += HEADER_ROWS; r1 += HEADER_ROWS
    xml = emit_node(node, c0, c1, r0, r1, ctx)
    children << xml if xml
  end

  # Safety net: any chart/control element NOT placed by the tree (an unmatched
  # zone, or a control with no dashboard zone) lands in a bottom band so nothing
  # silently drops from the layout.
  unplaced = page['elements'].select do |e|
    %w[chart control].include?(e['kind']) && e['name'] && !ctx[:placed].include?(e['id'])
  end
  unless unplaced.empty?
    n = unplaced.length
    cw = 24.0 / n
    inner = unplaced.each_with_index.map do |e, i|
      cs = 1 + (cw * i).round
      ce = i == n - 1 ? 25 : [1 + (cw * (i + 1)).round, cs + 1].max
      le(e['id'], cs, ce, 1, 5)
    end.join("\n")
    bid = "tc-#{page['id']}-extra"
    extra_els << container_el(bid)
    children << gc(bid, 1, 25, [page_rows - 4, HEADER_ROWS + 1].max, page_rows + 1, inner)
    warn "WARN: #{n} element(s) had no Tableau zone — appended in a bottom band: #{unplaced.map { |e| e['name'] }.join(', ')}"
  end

  [page_xml(page['id'], *children), extra_els, ctx[:placed].size, tree.length, ctl_by_name.size]
end

# Build one container-banded page for a single dashboard. Returns
# [page_xml_string, extra_spec_elements, n_charts, n_bands, n_controls].
def build_page_for_dashboard(dashboard, page, opts)
  chart_zones = dashboard['zones'].select { |z| z['kind'] == 'chart' && z['caption'] }
  els_by_name = page['elements'].each_with_object({}) { |e, h| h[e['name']] = e if e['name'] }
  title_el = page['elements'].find { |e| e['kind'] == 'text' }
  ctl_els  = page['elements'].select { |e| e['kind'] == 'control' }

  # Per-dashboard copy of the band tuning — auto-fit must not leak between
  # dashboards (bead ptrt: the old script used dash_layout.first only).
  o = opts.dup

  # Auto-fit the chart band to the ACTUAL zone extents. The default
  # chart_y0=29.7 assumes a title/filter band at the top; a dashboard whose
  # charts start near y=0 would otherwise map to negative grid rows.
  zone_y0s = chart_zones.map { |z| (z['y_pct'] || 0).to_f }
  zone_y1s = chart_zones.map { |z| (z['y_pct'] || 0).to_f + (z['h_pct'] || 0).to_f }
  unless zone_y0s.empty?
    fit_y0 = zone_y0s.min
    fit_y1 = [zone_y1s.max, fit_y0 + 1].max
    if fit_y0 < o[:chart_y0]
      o[:chart_y0] = fit_y0
      o[:chart_y1] = fit_y1
    end
  end

  chart_layouts = chart_zones.map do |z|
    lookup_name = o[:renames][z['caption']] || z['caption']
    el = els_by_name[lookup_name]
    if el.nil?
      warn "WARN: no Sigma element matched zone caption #{z['caption'].inspect} on page #{page['name'].inspect}" \
           "#{lookup_name == z['caption'] ? " — if the tile was renamed, pass --rename #{z['caption'].inspect}'=<Sigma name>'" : " (renamed to #{lookup_name.inspect})"} — tile DROPPED from layout"
    end
    next nil unless el
    c1, c2, r1, r2 = chart_pos(z, o)
    { el_id: el['id'], c1: c1, c2: c2, r1: r1, r2: r2 }
  end.compact

  # Close horizontal gaps within each row (Tableau dashboards often have
  # separate legend/filter zones between chart tiles that Sigma doesn't render).
  rows = chart_layouts.group_by { |c| [c[:r1], c[:r2]] }
  rows.each_value do |row_charts|
    row_charts.sort_by! { |c| c[:c1] }
    row_charts.each_with_index do |c, i|
      next_c1 = i + 1 < row_charts.length ? row_charts[i + 1][:c1] : (o[:page_cols] + 1)
      c[:c2] = next_c1
    end
  end

  children = []
  extra_els = []
  ov_prefix = "band-#{page['id']}"

  # Header band: reuse the page's existing title text if present, else add one
  # (sidecar) named after the page (= the Tableau dashboard name).
  hdr_id = "#{ov_prefix}-hdr"
  extra_els << container_el(hdr_id, HEADER_STYLE.dup)
  if title_el
    children << header_band_xml(hdr_id, title_el['id'])
  else
    txt_id = "#{ov_prefix}-hdrtext"
    extra_els << header_text_el(txt_id, page['name'])
    children << header_band_xml(hdr_id, txt_id)
  end

  # Control band: dashboard-global controls side-by-side under the header.
  n = ctl_els.length
  ctl_rows = 0
  if n > 0
    ctl_rows = 3
    col_width = (o[:page_cols].to_f / n).round
    inner = ctl_els.each_with_index.map do |c, i|
      col_start = 1 + i * col_width
      col_end   = i == n - 1 ? o[:page_cols] + 1 : col_start + col_width
      le(c['id'], col_start, col_end, 1, 1 + ctl_rows)
    end.join("\n")
    ctl_id = "#{ov_prefix}-ctl"
    extra_els << container_el(ctl_id)
    children << gc(ctl_id, 1, o[:page_cols] + 1, 1 + HEADER_ROWS, 1 + HEADER_ROWS + ctl_rows, inner)
  end

  # Chart bands: cluster the zone-derived positions into row bands and shift
  # the whole chart area under the header + control bands.
  chart_items = chart_layouts.map { |c| [c[:el_id], c[:c1], c[:c2], c[:r1], c[:r2]] }
  bands = cluster_bands(chart_items)
  content_start = 1 + HEADER_ROWS + ctl_rows
  band_offset = bands.empty? ? 0 : content_start - bands.first.map { |i| i[3] }.min
  bands.each_with_index do |band, i|
    cid = "#{ov_prefix}-#{i + 1}"
    extra_els << container_el(cid)
    children << band_container_xml(cid, band, row_offset: band_offset)
  end

  [page_xml(page['id'], *children), extra_els, chart_layouts.length, bands.length, ctl_els.length]
end

data_page_xml = page_xml('page-data',
                         le(master_el['id'], 1, opts[:page_cols] + 1, 1, 21))

page_xmls = [data_page_xml]
sidecar = {}
totals = { charts: 0, bands: 0, controls: 0 }
dash_layout.each do |d|
  page = page_for_dash[d['dashboard']]
  next unless page
  use_tree = !opts[:no_containers] && tree_has_controls?(d['zone_tree'])
  if use_tree
    begin
      pxml, extra_els, n_charts, n_bands, n_ctls = build_page_from_tree(d, page, opts)
      warn "container-tree layout: #{d['dashboard'].inspect} → nested Sigma containers (filters/params placed in their Tableau container)"
    rescue StandardError => e
      warn "WARN: container-tree layout failed for #{d['dashboard'].inspect} (#{e.class}: #{e.message}) — falling back to banded layout"
      pxml, extra_els, n_charts, n_bands, n_ctls = build_page_for_dashboard(d, page, opts)
    end
  else
    pxml, extra_els, n_charts, n_bands, n_ctls = build_page_for_dashboard(d, page, opts)
  end
  page_xmls << pxml
  sidecar[page['id']] = extra_els
  totals[:charts] += n_charts
  totals[:bands] += n_bands
  totals[:controls] += n_ctls
end

File.write(opts[:out], assemble(*page_xmls) + "\n")
File.write("#{opts[:out]}.elements.json", JSON.pretty_generate(sidecar))
puts "wrote #{opts[:out]} (#{page_for_dash.size} dashboard page(s): #{totals[:charts]} charts in #{totals[:bands]} band container(s), " \
     "#{totals[:controls]} controls, header bands, gap-closing applied, row-scale #{opts[:row_scale]}× → #{opts[:page_rows]} rows)"
puts "wrote #{opts[:out]}.elements.json (#{sidecar.values.sum(&:length)} container/header spec element(s) — put-layout.rb injects these)"
