#!/usr/bin/env ruby
# Parse Tableau view CSVs (already on disk) into a signals manifest.
# In production this script would also CALL the Tableau REST API to fetch
# the CSVs with the parallel-then-solo-retry dance for VizQL 401 contention.
#
# Usage:
#   ruby fetch-view-data.rb <views-dir> <out-signals.json>

require 'csv'
require 'json'

VIEWS_DIR = ARGV[0] || abort('usage: fetch-view-data.rb <views-dir> <out-signals.json>')
OUT       = ARGV[1] || abort('usage: fetch-view-data.rb <views-dir> <out-signals.json>')

def parse_num(s)
  s = s.to_s.strip.delete(',')
  return nil if s.empty?
  Float(s) rescue nil
end

# Type-check a column's values; date only if values look like real dates
# (not bare integers that happen to contain 4 digits).
def column_kind(values)
  non_null = values.compact.reject(&:empty?)
  return 'dimension' if non_null.empty?

  numeric_ratio = non_null.count { |v| parse_num(v) }.to_f / non_null.size
  date_like_ratio = non_null.count { |v|
    v.match?(/\d{4}-\d{2}-\d{2}/) ||                                          # ISO
    v.match?(/^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}$/) ||  # "May 2026"
    v.match?(/\d{1,2}\/\d{1,2}\/\d{2,4}/)                                     # 1/2/26
  }.to_f / non_null.size

  return 'date'    if date_like_ratio >= 0.6
  return 'numeric' if numeric_ratio   >= 0.8
  'dimension'
end

# Tableau CSV headers carry the agg type as a prefix when the display alias
# wasn't customized: "Sum of Gross Revenue", "Distinct count of Order Id",
# etc. When the user gave the field a display alias ("Gross Revenue"), the
# header is just that alias and the agg has to be inferred from elsewhere
# (defaultAggregation in the datasource metadata).
AGG_PREFIX = %w[
  Sum Avg Min Max Median Count\ distinct Distinct\ count
  Std Var Year\ of Month\ of Quarter\ of Day\ of Week\ of
].map { |p| Regexp.escape(p) }.join('|')
AGG_RX = /\A(#{AGG_PREFIX}) of (.+)\z/i

def detect_aggregation(header)
  return nil unless (m = header.match(AGG_RX))
  agg = m[1].downcase.gsub(' ', '_')
  agg = 'count_distinct' if agg == 'distinct_count'
  { agg: agg, of: m[2].strip }
end

signals = {}
Dir["#{VIEWS_DIR}/*.csv"].sort.each do |path|
  view_id = File.basename(path, '.csv')
  csv     = CSV.read(path, headers: true)
  headers = csv.headers.map { |h| h.strip }

  by_col = {}
  agg_hint = {}
  headers.each do |h|
    col_vals = csv.map { |r| r[h] }.compact
    kind = column_kind(col_vals)
    by_col[h] = {
      kind: kind,
      distinct_count: col_vals.uniq.size,
      sample: col_vals.first(5),
      distinct: (kind == 'dimension' ? col_vals.uniq.sort_by(&:to_s) : nil),
      numeric_range: (kind == 'numeric' ?
        [col_vals.map { |v| parse_num(v) }.compact.min,
         col_vals.map { |v| parse_num(v) }.compact.max] : nil)
    }
    if (d = detect_aggregation(h))
      agg_hint[h] = d
    end
  end

  signals[view_id] = {
    headers: headers,
    row_count: csv.size,
    columns: by_col,
    aggregation_hints: agg_hint.empty? ? nil : agg_hint
  }
end

File.write(OUT, JSON.pretty_generate(signals))
puts "wrote #{OUT}  (#{signals.size} views, total " \
     "#{signals.values.sum { |v| v[:row_count] || 0 }} rows)"
