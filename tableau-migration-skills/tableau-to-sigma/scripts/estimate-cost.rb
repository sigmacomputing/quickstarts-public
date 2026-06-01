#!/usr/bin/env ruby
# Estimate the agent token cost of converting a Tableau workbook to Sigma,
# given pre-fetched workbook + datasource metadata.
#
# In production this script would itself call:
#   - mcp__tableau__get-workbook       (views/sheets/dashboards count)
#   - mcp__tableau__get-datasource-metadata  (calc fields, custom SQL)
# and emit the estimate. For this demo it takes pre-fetched JSON.
#
# Cost model (calibrate against your real measurements):
#
#   base                              = 25,000 input tokens
#   per dashboard view                = 4,000 input tokens
#   per worksheet (sheet) view        = 2,500 input tokens
#   per datasource                    = 5,000 input tokens
#   per calc field (simple)           = 3,000 input tokens
#   per calc field (LOD or chained)   = 8,000 input tokens
#   per 1KB of custom SQL             = 1,200 input tokens
#
#   output ≈ input × 0.45
#   $ ≈ input × $3/1M + output × $15/1M   (Sonnet 4.6 rates — adjust)
#
# After running ~10 calibration workbooks with measured costs, regress the
# coefficients above against actual usage. The model is intentionally simple
# (linear regression on features) — sophisticated isn't worth the effort
# until calibration data exists.
#
# Usage:
#   ruby estimate-cost.rb --workbook <get-workbook.json> --datasource <metadata.json>
#   ruby estimate-cost.rb --workbook <get-workbook.json>   (no datasource)

require 'json'
require 'optparse'

opts = { rate_in: 3.0, rate_out: 15.0, model: 'sonnet-4.6' }
OptionParser.new do |p|
  p.on('--workbook PATH')   { |v| opts[:wb] = v }
  p.on('--datasource PATH') { |v| opts[:ds] = v }
  p.on('--rate-in DOLLAR_PER_1M_INPUT',   Float) { |v| opts[:rate_in]  = v }
  p.on('--rate-out DOLLAR_PER_1M_OUTPUT', Float) { |v| opts[:rate_out] = v }
end.parse!
abort('--workbook required') unless opts[:wb]

wb = JSON.parse(File.read(opts[:wb]))
views = wb.dig('views', 'view') || wb['views'] || []
dashboard_count = views.count { |v| (v['sheetType'] || '').downcase.include?('dashboard') }
sheet_count     = views.size - dashboard_count

calc_count_simple = 0
calc_count_complex = 0
custom_sql_bytes  = 0
datasource_count  = 0

if opts[:ds]
  meta = JSON.parse(File.read(opts[:ds]))
  datasource_count = 1
  # Accept either MCP shape (fieldGroups[].fields[]) or REST VDS shape (data[])
  fields = if meta['fieldGroups']
             meta['fieldGroups'].flat_map { |g| g['fields'] || [] }
           else
             meta['data'] || []
           end
  fields.each do |f|
    next unless f['columnClass'] == 'CALCULATION'
    if (f['formula'] || '').match?(/\{\s*(FIXED|INCLUDE|EXCLUDE)|\bIF\b[\s\S]+\bELSEIF\b[\s\S]+\bELSEIF\b/i)
      calc_count_complex += 1
    else
      calc_count_simple += 1
    end
  end
  # Custom SQL is reported in the metadata for textOfRawSql sources; not always present
  custom_sql_bytes = (meta['customSql'] || '').to_s.bytesize
end

features = {
  dashboards: dashboard_count, sheets: sheet_count, datasources: datasource_count,
  calc_fields_simple: calc_count_simple, calc_fields_complex: calc_count_complex,
  custom_sql_bytes: custom_sql_bytes
}

input_tokens = 25_000 +
               (dashboard_count        * 4_000) +
               (sheet_count            * 2_500) +
               (datasource_count       * 5_000) +
               (calc_count_simple      * 3_000) +
               (calc_count_complex     * 8_000) +
               ((custom_sql_bytes / 1024.0) * 1_200).to_i
output_tokens = (input_tokens * 0.45).to_i
cost = (input_tokens / 1_000_000.0) * opts[:rate_in] +
       (output_tokens / 1_000_000.0) * opts[:rate_out]

complexity =
  if input_tokens < 50_000 then 'small'
  elsif input_tokens < 150_000 then 'medium'
  elsif input_tokens < 350_000 then 'large'
  else                              'very-large'
  end

puts JSON.pretty_generate({
  workbook: wb['name'] || File.basename(opts[:wb], '.json'),
  features: features,
  estimate: {
    complexity: complexity,
    input_tokens: input_tokens,
    output_tokens: output_tokens,
    total_tokens: input_tokens + output_tokens,
    estimated_cost_usd: cost.round(2),
    model: opts[:model],
    note: 'Cost model is heuristic. Calibrate coefficients against ~10 real conversions to tighten the range.'
  }
})
