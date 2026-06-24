#!/usr/bin/env ruby
# Regression test for the empty-view-CSV recovery — a worksheet gated behind a
# dashboard ACTION filter renders fine in Tableau but its headless data export
# returns ZERO rows. The builder used to DROP the tile (shipping N-1 charts);
# it must instead reconstruct the view headers from the .twb shelf signals and
# BUILD the chart (Sigma sources the same warehouse, so it populates). Parity
# for that one tile is downgraded to manual. Principle: never skip anything in
# the .twb.
#
# Deterministic + offline: synthesizes a minimal .twb (a line chart of
# Month(Order Date) × SUM(Gross Revenue) gated by an action filter), runs the
# ACTUAL parse-twb-layout.rb + build-charts-from-signals.rb with an EMPTY view
# CSV, and asserts the chart element was built (not dropped).
#
# Usage:  ruby scripts/test-empty-csv-build-from-signals.rb

require 'json'
require 'tmpdir'

DIR    = __dir__
PARSER = File.join(DIR, 'parse-twb-layout.rb')
BUILD  = File.join(DIR, 'build-charts-from-signals.rb')

fails = []
def check(cond, msg, fails)
  fails << msg unless cond
  puts "  #{cond ? 'PASS' : 'FAIL'}  #{msg}"
end

# Line chart: cols = Month-Trunc(Order Date), rows = SUM(Gross Revenue), with a
# dashboard action filter on Region (the reason the data export comes back empty).
TWB = <<~XML
  <?xml version='1.0' encoding='utf-8' ?>
  <workbook>
    <datasources>
      <datasource caption='ORDER_FACT' name='federated.fact'>
        <connection class='federated'>
          <named-connections>
            <named-connection name='snow'><connection class='snowflake' dbname='CSA' schema='TJ' /></named-connection>
          </named-connections>
          <relation connection='snow' name='ORDER_FACT' table='[TJ].[ORDER_FACT]' type='table' />
        </connection>
        <column caption='Gross Revenue' name='[33b6c718-9b55-3dc0-9698-d1d57fac0f90]' datatype='real' role='measure' type='quantitative' />
        <column caption='Order Date ' name='[c2ec6b07-897e-39ab-9422-aa895d35a627]' datatype='date' role='dimension' type='ordinal' />
        <column caption='Region' name='[d73055c0-9ed1-347d-8f8e-05a48ce2c8a8]' datatype='string' role='dimension' type='nominal' />
      </datasource>
    </datasources>
    <worksheets>
      <worksheet name='Monthly Revenue Trend'>
        <table>
          <view>
            <datasource-dependencies datasource='federated.fact'>
              <column caption='Gross Revenue' name='[33b6c718-9b55-3dc0-9698-d1d57fac0f90]' datatype='real' role='measure' type='quantitative' />
              <column caption='Order Date ' name='[c2ec6b07-897e-39ab-9422-aa895d35a627]' datatype='date' role='dimension' type='ordinal' />
              <column-instance column='[c2ec6b07-897e-39ab-9422-aa895d35a627]' derivation='Month-Trunc' name='[tmn:c2ec6b07-897e-39ab-9422-aa895d35a627:qk]' pivot='key' type='quantitative' />
              <column-instance column='[33b6c718-9b55-3dc0-9698-d1d57fac0f90]' derivation='Sum' name='[sum:33b6c718-9b55-3dc0-9698-d1d57fac0f90:qk]' pivot='key' type='quantitative' />
            </datasource-dependencies>
          </view>
          <rows>[federated.fact].[sum:33b6c718-9b55-3dc0-9698-d1d57fac0f90:qk]</rows>
          <cols>[federated.fact].[tmn:c2ec6b07-897e-39ab-9422-aa895d35a627:qk]</cols>
          <pane><mark class='Line' /></pane>
        </table>
      </worksheet>
    </worksheets>
    <dashboards>
      <dashboard name='Dash'>
        <zones><zone id='1' name='Monthly Revenue Trend' x='0' y='0' w='100000' h='100000' /></zones>
      </dashboard>
    </dashboards>
  </workbook>
XML

MASTER_MAP = {
  '(?i)^Gross Revenue$' => { 'id' => 'm-gr',   'name' => 'Gross Revenue' },
  '(?i)^Order Date $'   => { 'id' => 'm-od',   'name' => 'Order Date ' },
  '(?i)^Order Date$'    => { 'id' => 'm-od',   'name' => 'Order Date ' },
  '(?i)^Region$'        => { 'id' => 'm-reg',  'name' => 'Region' }
}

build_out = nil
build_log = ''
Dir.mktmpdir do |d|
  twb = File.join(d, 'wb.twb')
  lay = File.join(d, 'layout.json')
  mm  = File.join(d, 'master-map.json')
  File.write(twb, TWB)
  File.write(mm, JSON.dump(MASTER_MAP))
  # get-workbook view list + an EMPTY view CSV (the action-filter-gated export).
  File.write(File.join(d, 'get-workbook.json'),
             JSON.dump('views' => { 'view' => [{ 'id' => 'v1', 'name' => 'Monthly Revenue Trend' }] }))
  Dir.mkdir(File.join(d, 'views'))
  File.write(File.join(d, 'views', 'v1.csv'), '')   # 0 bytes — the whole point
  abort 'parse-twb-layout failed' unless system('ruby', PARSER, twb, lay, out: File::NULL, err: File::NULL)
  out = File.join(d, 'specs.json')
  build_log = `ruby #{BUILD} --tableau-dir #{d} --layout #{lay} --meta #{lay.sub(/\.json$/, '-meta.json')} --master-map #{mm} --master-element-id master --title Dash --out #{out} 2>&1`
  build_out = JSON.parse(File.read(out)) if File.exist?(out)
  vv_path = File.join(d, 'visual-verify-tiles.json')
  $vv_sidecar = File.exist?(vv_path) ? JSON.parse(File.read(vv_path)) : nil
end

els = build_out ? (build_out.is_a?(Array) ? build_out : (build_out['elements'] || (build_out['pages'] || []).flat_map { |p| p['elements'] || [] })) : []
trend = els.find { |e| e['name'].to_s.casecmp?('Monthly Revenue Trend') }

check(!trend.nil?, 'chart BUILT from signals despite empty CSV (not dropped)', fails)
check(trend && trend['kind'] == 'line-chart', "built element is a line-chart (got #{trend && trend['kind'].inspect})", fails)
cols = trend ? (trend['columns'] || []) : []
xcol = trend && cols.find { |c| c['id'] == trend.dig('xAxis', 'columnId') }
ycol = trend && cols.find { |c| trend.dig('yAxis', 'columnIds')&.include?(c['id']) }
check(xcol && xcol['formula'].to_s =~ /DateTrunc\("month"/i,
      "x-axis is Month DateTrunc of Order Date (got #{xcol && xcol['formula'].inspect})", fails)
check(ycol && ycol['formula'].to_s =~ /Sum\(/i,
      "y-axis is Sum(Gross Revenue) (got #{ycol && ycol['formula'].inspect})", fails)
check(build_log.include?('BUILT FROM .twb SIGNALS'),
      'builder logged the empty-CSV → build-from-signals recovery (not a ZONE DROPPED)', fails)
check(!build_log.include?('ZONE DROPPED'), 'no ZONE DROPPED warning emitted', fails)

# ---- visual-verify sidecar: the tile routes to IMAGE verification -----------
vv = $vv_sidecar
check(vv.is_a?(Array) && vv.length == 1,
      "builder wrote visual-verify-tiles.json with the empty-export tile (got #{vv.inspect})", fails)
entry = vv && vv.first
check(entry && entry['worksheet'] == 'Monthly Revenue Trend' && entry['view_id'] == 'v1' &&
      entry['element_id'] == (trend && trend['id']),
      "sidecar entry carries worksheet + view_id + the built element id (got #{entry.inspect})", fails)

puts
if fails.empty?
  puts 'ALL PASS — empty action-filter-gated CSV: chart rebuilt from .twb signals, nothing skipped'
  exit 0
else
  puts "FAILURES (#{fails.length}):"
  fails.each { |f| puts "  - #{f}" }
  puts "\n--- build log (tail) ---"
  puts build_log.to_s.lines.last(20).join
  exit 1
end
