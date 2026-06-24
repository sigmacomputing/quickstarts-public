#!/usr/bin/env ruby
# Regression test for the container-fidelity layout path — Tableau dashboards
# that group filters/parameters into a (often nested) layout container, e.g. a
# left vertical rail beside the chart area. Before this fix the layout builder
# discarded the container tree and lumped every control into one top strip
# (build_page_for_dashboard's single control band).
#
# Asserts, end-to-end through the ACTUAL parse-twb-layout.rb +
# build-dashboard-layout.rb (no Tableau/Sigma calls):
#   1. The parser preserves the nested zone tree (a layout-flow rail INSIDE a
#      layout-basic root, holding a filter zone + a paramctrl zone).
#   2. The layout builder emits NESTED Sigma GridContainers (a container inside
#      a container), not a flat band stack.
#   3. The filter control AND the parameter control both land INSIDE the same
#      rail container — i.e. filters/params are laid out within their Tableau
#      container — while the chart sits OUTSIDE that rail.
#
# Usage:  ruby scripts/test-container-layout.rb

require 'json'
require 'rexml/document'
require 'tmpdir'

DIR    = __dir__
PARSER = File.join(DIR, 'parse-twb-layout.rb')
BUILD  = File.join(DIR, 'build-dashboard-layout.rb')

fails = []
def check(cond, msg, fails)
  fails << msg unless cond
  puts "  #{cond ? 'PASS' : 'FAIL'}  #{msg}"
end

# A dashboard whose <zones> root is a layout-basic container holding:
#   - a layout-flow VERTICAL rail (left) with a filter zone (on "Region") and a
#     paramctrl zone (parameter "Metric Switch")
#   - a chart zone ("Sales by Region") filling the right
TWB = <<~XML
  <?xml version='1.0' encoding='utf-8' ?>
  <workbook>
    <datasources>
      <datasource caption='Params' name='Parameters'>
        <column param-domain-type='list' caption='Metric Switch' name='[Parameter 1]' datatype='string' value='&quot;Revenue&quot;'>
          <members><member value='&quot;Revenue&quot;' /><member value='&quot;Profit&quot;' /></members>
        </column>
      </datasource>
      <datasource caption='Sales' name='federated.x'>
        <column caption='Region' name='[Region]' datatype='string' role='dimension' />
      </datasource>
    </datasources>
    <worksheets>
      <worksheet name='Sales by Region'><table><view><datasource-dependencies datasource='federated.x' /></view></table></worksheet>
    </worksheets>
    <dashboards>
      <dashboard name='Pipeline'>
        <zones>
          <zone id='1' type-v2='layout-basic' x='0' y='0' w='100000' h='100000'>
            <zone id='2' type-v2='layout-flow' param='vert' x='0' y='0' w='25000' h='100000'>
              <zone id='3' type-v2='filter' param='[federated.x].[none:Region:nk]' x='0' y='0' w='25000' h='40000' />
              <zone id='4' type-v2='paramctrl' param='[Parameters].[Parameter 1]' x='0' y='40000' w='25000' h='40000' />
            </zone>
            <zone id='5' name='Sales by Region' x='25000' y='0' w='75000' h='100000' />
          </zone>
        </zones>
      </dashboard>
    </dashboards>
  </workbook>
XML

layout = nil
xml_doc = nil
build_log = ''
Dir.mktmpdir do |d|
  twb = File.join(d, 'wb.twb')
  lay = File.join(d, 'layout.json')
  File.write(twb, TWB)
  abort 'parse-twb-layout failed' unless system('ruby', PARSER, twb, lay, out: File::NULL, err: File::NULL)
  layout = JSON.parse(File.read(lay))

  # Synthetic workbook readback: a Data page + the dashboard page with a chart
  # element (named like the worksheet), two controls (named like the filter
  # column + the parameter caption), and a title text element.
  wb_ids = {
    'pages' => [
      { 'name' => 'Data', 'elements' => [{ 'id' => 'master', 'kind' => 'table', 'name' => 'Data' }] },
      { 'name' => 'Pipeline', 'elements' => [
        { 'id' => 'el-chart', 'kind' => 'bar-chart', 'name' => 'Sales by Region' },
        { 'id' => 'el-region', 'kind' => 'control', 'name' => 'Region' },
        { 'id' => 'el-metric', 'kind' => 'control', 'name' => 'Metric Switch' },
        { 'id' => 'el-title', 'kind' => 'text', 'name' => nil }
      ] }
    ]
  }
  wbf = File.join(d, 'wb-ids.json')
  out = File.join(d, 'layout.xml')
  File.write(wbf, JSON.dump(wb_ids))
  build_log = `ruby #{BUILD} --layout #{lay} --wb-ids #{wbf} --out #{out} 2>&1`
  if File.exist?(out)
    # The layout file has multiple top-level <Page> roots; wrap for REXML.
    body = File.read(out).sub(/\A<\?xml[^>]*\?>\s*/, '')
    xml_doc = REXML::Document.new("<Root>#{body}</Root>")
  end
end

# ---- 1. parser preserved the nested tree -----------------------------------
dash = (layout || []).find { |x| x['dashboard'] == 'Pipeline' }
tree = dash && dash['zone_tree']
root = tree && tree.first
rail = root && (root['children'] || []).find { |c| c['kind'] == 'container' }
check(!root.nil? && root['kind'] == 'container', 'parser: <zones> root is a container node', fails)
check(rail && rail['direction'] == 'vert', "parser: nested vertical rail container preserved (direction=#{rail && rail['direction'].inspect})", fails)
rail_kids = rail ? (rail['children'] || []).map { |c| c['kind'] } : []
check(rail_kids.include?('filter') && rail_kids.include?('parameter'),
      "parser: rail holds the filter + parameter zones (got #{rail_kids.inspect})", fails)
fcap = rail && (rail['children'] || []).find { |c| c['kind'] == 'filter' }&.dig('filter_column_caption')
check(fcap == 'Region', "parser: filter zone resolves column caption 'Region' (got #{fcap.inspect})", fails)

# ---- 2 + 3. builder nested the containers and placed controls in the rail ---
gcs = xml_doc ? xml_doc.elements.to_a('//GridContainer') : []
nested = gcs.any? { |g| !g.elements.to_a('.//GridContainer').empty? }
check(nested, 'builder: emitted NESTED GridContainers (container inside container)', fails)

# Find the container whose descendants include BOTH control element ids.
def descendant_el_ids(gc)
  gc.elements.to_a('.//LayoutElement').map { |le| le.attributes['elementId'] }
end
rail_gc = gcs.find do |g|
  ids = descendant_el_ids(g)
  ids.include?('el-region') && ids.include?('el-metric') &&
    g.elements.to_a('.//GridContainer').empty? # innermost container = the rail
end
check(!rail_gc.nil?, 'builder: both controls (Region + Metric Switch) live INSIDE one rail container', fails)
chart_in_rail = rail_gc && descendant_el_ids(rail_gc).include?('el-chart')
check(rail_gc && !chart_in_rail, 'builder: the chart is NOT inside the control rail', fails)
chart_placed = gcs.any? { |g| descendant_el_ids(g).include?('el-chart') }
check(chart_placed, 'builder: the chart element is placed in the layout', fails)
check(build_log.include?('container-tree layout'), 'builder: took the container-tree path (not the banded fallback)', fails)

puts
if fails.empty?
  puts 'ALL PASS — container-fidelity layout: nested Tableau containers → nested Sigma containers; filters/params placed within their container'
  exit 0
else
  puts "FAILURES (#{fails.length}):"
  fails.each { |f| puts "  - #{f}" }
  puts "\n--- build log (tail) ---"
  puts build_log.to_s.lines.last(15).join
  exit 1
end
