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
#   --page-rows N    visible rows (default 32)
#   --chart-y0 PCT   top of the chart band as Tableau %  (default 29.7)
#   --chart-y1 PCT   bottom of the chart band as Tableau % (default 100.0)
#   --chart-row0 N   first grid row of the chart band     (default 6)

require 'json'
require 'optparse'

opts = { page_cols: 24, page_rows: 32, chart_y0: 29.7, chart_y1: 100.0, chart_row0: 6 }
OptionParser.new do |p|
  p.on('--layout PATH')        { |v| opts[:layout] = v }
  p.on('--wb-ids PATH')        { |v| opts[:wb_ids] = v }
  p.on('--out PATH')           { |v| opts[:out] = v }
  p.on('--page-cols N',  Integer) { |v| opts[:page_cols] = v }
  p.on('--page-rows N',  Integer) { |v| opts[:page_rows] = v }
  p.on('--chart-y0 PCT', Float)   { |v| opts[:chart_y0] = v }
  p.on('--chart-y1 PCT', Float)   { |v| opts[:chart_y1] = v }
  p.on('--chart-row0 N', Integer) { |v| opts[:chart_row0] = v }
end.parse!
%i[layout wb_ids out].each { |k| abort("missing --#{k.to_s.tr('_','-')}") unless opts[k] }

dash_layout = JSON.parse(File.read(opts[:layout]))
wb_ids      = JSON.parse(File.read(opts[:wb_ids]))

# Page lookups
data_page  = wb_ids['pages'].find { |p| p['name'] == 'Data' }
abort('no "Data" page in wb-ids') unless data_page
master_el  = data_page['elements'].first

overview   = wb_ids['pages'].find { |p| p['name'] != 'Data' && !p['name'].nil? } || wb_ids['pages'][1]
abort('no overview page (non-Data) in wb-ids') unless overview

els_by_name = overview['elements'].each_with_object({}) { |e, h| h[e['name']] = e if e['name'] }
title_el = overview['elements'].find { |e| e['kind'] == 'text' }
ctl_els  = overview['elements'].select { |e| e['kind'] == 'control' }

# Chart zones from the Tableau dashboard (first dashboard)
dashboard = dash_layout.first
chart_zones = dashboard['zones'].select { |z| z['kind'] == 'chart' && z['caption'] }

def chart_pos(z, opts)
  y0 = z['y_pct'] || 0
  h  = z['h_pct'] || 0
  y1 = y0 + h
  remaining_rows = opts[:page_rows] - (opts[:chart_row0] - 1)
  row_start = (opts[:chart_row0] + (y0 - opts[:chart_y0]) / (opts[:chart_y1] - opts[:chart_y0]) * remaining_rows).round
  row_end   = (opts[:chart_row0] + (y1 - opts[:chart_y0]) / (opts[:chart_y1] - opts[:chart_y0]) * remaining_rows).round
  row_end   = row_start + 1 if row_end <= row_start
  col_start = [1,  (1 + (z['x_pct'] || 0) / 100.0 * opts[:page_cols]).round].max
  col_end   = [opts[:page_cols] + 1, (1 + ((z['x_pct'] || 0) + (z['w_pct'] || 0)) / 100.0 * opts[:page_cols]).round].min
  col_end   = col_start + 1 if col_end <= col_start
  [col_start, col_end, row_start, row_end]
end

# Compute initial positions
chart_layouts = chart_zones.map do |z|
  el = els_by_name[z['caption']]
  warn "WARN: no Sigma element matched zone caption #{z['caption'].inspect}" if el.nil?
  next nil unless el
  c1, c2, r1, r2 = chart_pos(z, opts)
  { el_id: el['id'], c1: c1, c2: c2, r1: r1, r2: r2 }
end.compact

# Close horizontal gaps within each row (Tableau dashboards often have separate
# legend/filter zones between chart tiles that Sigma doesn't render — without
# this, the dashboard has visible empty columns between adjacent charts).
rows = chart_layouts.group_by { |c| [c[:r1], c[:r2]] }
rows.each_value do |row_charts|
  row_charts.sort_by! { |c| c[:c1] }
  row_charts.each_with_index do |c, i|
    next_c1 = i + 1 < row_charts.length ? row_charts[i + 1][:c1] : (opts[:page_cols] + 1)
    c[:c2] = next_c1
  end
end

# Render
lines = ['<?xml version="1.0" encoding="utf-8"?>']
lines << %(<Page type="grid" gridTemplateColumns="repeat(#{opts[:page_cols]}, 1fr)" gridTemplateRows="auto" id="page-data">)
lines << %(  <LayoutElement elementId="#{master_el['id']}" gridColumn="1 / #{opts[:page_cols] + 1}" gridRow="1 / 21"/>)
lines << '</Page>'

lines << %(<Page type="grid" gridTemplateColumns="repeat(#{opts[:page_cols]}, 1fr)" gridTemplateRows="auto" id="#{overview['id']}">)
if title_el
  lines << %(  <LayoutElement elementId="#{title_el['id']}" gridColumn="1 / #{opts[:page_cols] + 1}" gridRow="1 / 3"/>)
end

# Distribute controls evenly across the top row (cols 1, 1+W, 1+2W, ... where W = total/n)
n = ctl_els.length
if n > 0
  col_width = (opts[:page_cols].to_f / n).round
  ctl_els.each_with_index do |c, i|
    col_start = 1 + i * col_width
    col_end   = i == n - 1 ? opts[:page_cols] + 1 : col_start + col_width
    lines << %(  <LayoutElement elementId="#{c['id']}" gridColumn="#{col_start} / #{col_end}" gridRow="3 / 6"/>)
  end
end

chart_layouts.each do |c|
  lines << %(  <LayoutElement elementId="#{c[:el_id]}" gridColumn="#{c[:c1]} / #{c[:c2]}" gridRow="#{c[:r1]} / #{c[:r2]}"/>)
end

lines << '</Page>'

File.write(opts[:out], lines.join("\n") + "\n")
puts "wrote #{opts[:out]} (#{chart_layouts.length} charts, #{ctl_els.length} controls, gap-closing applied)"
