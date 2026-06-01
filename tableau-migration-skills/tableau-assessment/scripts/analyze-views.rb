#!/usr/bin/env ruby
# Phase 3: Per-view (dashboard/sheet) usage + performance analysis.
#
# Reads:
#   <out>/raw-ts-events-per-view.json     (per-view × per-workbook access counts)
#   <out>/raw-ts-events-per-datasource.json (per-user × per-datasource access)
#   <out>/raw-viz-load-times.json         (per-view load duration)
#   <out>/raw-ts-events-per-user.json     (per-user × per-workbook — for top-users-per-workbook)
#   <out>/users.json                      (for unique-to-user enrichment)
# Writes:
#   <out>/views.json — per-view usage + per-workbook top-views rollup
#   <out>/performance.json — slow-view ranked list
#   <out>/datasource-usage.json — per-DS access counts and top users
#   <out>/workbook-users.json — per-workbook top users
#
# Usage: ruby scripts/analyze-views.rb --out /tmp/assessment-<site>

require 'json'
require 'optparse'

opts = {}
OptionParser.new do |p|
  p.on('--out DIR') { |v| opts[:out] = v }
end.parse!
abort('--out required') unless opts[:out]

def read_data(out, name)
  path = File.join(out, name)
  return [] unless File.exist?(path)
  JSON.parse(File.read(path))['data'] || []
end

views_events = read_data(opts[:out], 'raw-ts-events-per-view.json')
ds_events    = read_data(opts[:out], 'raw-ts-events-per-datasource.json')
load_times   = read_data(opts[:out], 'raw-viz-load-times.json')
user_events  = read_data(opts[:out], 'raw-ts-events-per-user.json')

# ----- VIEWS ----------------------------------------------------------------
# Roll up: per workbook, list of views with access counts; top-3 views by access
by_wb = Hash.new { |h, k| h[k] = [] }
total_views_accesses = 0
views_events.each do |e|
  wb = e['Workbook Name'] || '(no workbook)'
  view = e['Item Name'] || '(unnamed)'
  acc = e['accesses'].to_i
  by_wb[wb] << { 'view' => view, 'accesses' => acc, 'actors' => e['actors'].to_i }
  total_views_accesses += acc
end

view_rollup = by_wb.map do |wb, items|
  items = items.sort_by { |i| -i['accesses'].to_i }
  total = items.sum { |i| i['accesses'].to_i }
  top = items.first(5)
  most_used_pct = total.zero? ? 0.0 : (items.first['accesses'].to_f / total * 100).round
  named = items.count { |i| i['view'] != '(unnamed)' }
  {
    'workbook'         => wb,
    'total_view_accesses' => total,
    'view_count'       => items.size,
    'top_views'        => top,
    'concentration_pct'=> most_used_pct,
    'unused_views'     => items.select { |i| i['accesses'].zero? }.map { |i| i['view'] }
  }
end.sort_by { |r| -r['total_view_accesses'].to_i }

File.write(File.join(opts[:out], 'views.json'), JSON.pretty_generate({
  'summary' => {
    'total_view_access_events' => total_views_accesses,
    'distinct_views_accessed'  => views_events.size,
    'workbooks_with_views'     => view_rollup.size
  },
  'by_workbook' => view_rollup
}))

# ----- PERFORMANCE ----------------------------------------------------------
# Sort by avg load time × loads (i.e., total time spent waiting on this view)
perf = load_times.map do |r|
  avg = r['avg_load'].to_f
  loads = r['loads'].to_i
  {
    'workbook'   => r['Workbook Name'],
    'view'       => r['Item Name'],
    'avg_load_s' => avg.round(2),
    'max_load_s' => r['max_load'].to_f.round(2),
    'loads'      => loads,
    'total_wait_s' => (avg * loads).round(1),
    'severity'   => avg >= 10 ? 'red' : avg >= 5 ? 'amber' : avg >= 2 ? 'yellow' : 'green'
  }
end.sort_by { |r| -r['total_wait_s'] }

perf_summary = {
  'total_loads' => perf.sum { |r| r['loads'].to_i },
  'p_red'   => perf.count { |r| r['severity'] == 'red' },
  'p_amber' => perf.count { |r| r['severity'] == 'amber' },
  'avg_load_s' => perf.empty? ? 0 : (perf.sum { |r| r['avg_load_s'] * r['loads'] } / perf.sum { |r| r['loads'] }.to_f).round(2)
}

File.write(File.join(opts[:out], 'performance.json'), JSON.pretty_generate({
  'summary' => perf_summary,
  'views'   => perf
}))

# ----- DATASOURCE USAGE -----------------------------------------------------
# Per DS: total accesses + top users
ds_rollup = Hash.new { |h, k| h[k] = { 'accesses' => 0, 'users' => Hash.new(0) } }
ds_events.each do |e|
  name = e['Item Name'] || '(unnamed)'
  ds_rollup[name]['accesses'] += e['accesses'].to_i
  ds_rollup[name]['users'][e['Actor User Name']] += e['accesses'].to_i
end

ds_usage = ds_rollup.map do |name, r|
  top_users = r['users'].sort_by { |_, n| -n }.first(5).map { |u, n| { 'user' => u, 'accesses' => n } }
  {
    'datasource' => name,
    'total_accesses' => r['accesses'],
    'distinct_users' => r['users'].size,
    'top_users' => top_users
  }
end.sort_by { |r| -r['total_accesses'].to_i }

File.write(File.join(opts[:out], 'datasource-usage.json'), JSON.pretty_generate({
  'summary' => {
    'total_accesses' => ds_usage.sum { |r| r['total_accesses'].to_i },
    'distinct_datasources' => ds_usage.size
  },
  'datasources' => ds_usage
}))

# ----- WORKBOOK → TOP USERS -------------------------------------------------
wb_users = Hash.new { |h, k| h[k] = Hash.new(0) }
user_events.each do |e|
  wb_users[e['Workbook Name']][e['Actor User Name']] += e['accesses'].to_i
end
workbook_users = wb_users.map do |wb, users|
  ranked = users.sort_by { |_, n| -n }
  total = users.values.sum
  {
    'workbook' => wb,
    'total_accesses' => total,
    'distinct_users' => users.size,
    'top_users' => ranked.first(5).map { |u, n| { 'user' => u, 'accesses' => n, 'share_pct' => total.zero? ? 0 : (n.to_f / total * 100).round } }
  }
end.sort_by { |r| -r['total_accesses'].to_i }

File.write(File.join(opts[:out], 'workbook-users.json'), JSON.pretty_generate({
  'workbooks' => workbook_users
}))

puts "wrote views.json (#{view_rollup.size} workbooks, #{total_views_accesses} view accesses)"
puts "wrote performance.json (#{perf.size} views, #{perf_summary['p_red']} red, #{perf_summary['p_amber']} amber)"
puts "wrote datasource-usage.json (#{ds_usage.size} datasources)"
puts "wrote workbook-users.json (#{workbook_users.size} workbooks)"
