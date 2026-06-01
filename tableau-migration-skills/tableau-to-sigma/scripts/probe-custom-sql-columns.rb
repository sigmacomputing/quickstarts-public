#!/usr/bin/env ruby
# Probe the column names + types of a warehouse table when discover-columns.rb
# returns 404 (table not in Sigma's catalog).
#
# Strategy: build a one-shot probe workbook with a Custom SQL element that
# SELECTs against INFORMATION_SCHEMA (Snowflake / Postgres / Redshift / SQL
# Server / BigQuery all support it). CSV-export the element. Parse the result.
# Delete the probe workbook.
#
# This works around Sigma's static-catalog visibility issue: the connection
# still executes arbitrary SQL fine, only the catalog index is stale.
#
# Use when:
#   - `discover-columns.rb` returned 404 (table not in catalog)
#   - You need column names + types BEFORE writing the real DM
#   - You'd otherwise be POST-fail-cleanup-retrying on 30+ column-name
#     permutations (CUSTOMER_ID vs CUST_ID vs ID vs RECORD_ID...)
#
# Saves ~120s on every Custom SQL fallback. Validated against
# TJ.PUBLIC.SUPERSTORE_ORDERS on connection bc0319f8-9fe0-4315-aea3-6a2d1eef0623
# during Superstore's standalone conversion (2026-05-24).
#
# Usage:
#   eval "$(scripts/get-token.sh)"
#   ruby scripts/probe-custom-sql-columns.rb \
#     --connection-id <id> \
#     --table-path <db>.<schema>.<table>          # Snowflake / Postgres / Redshift
#     [--dialect snowflake|postgres|bigquery]     # default: snowflake
#     [--folder-id <id>]                          # required if no default
#     [--out <file>.json]
#
# Output (stdout, or to --out):
#   { "connection_id": "...",
#     "table_path": "DB.SCHEMA.TABLE",
#     "columns": [ { "name": "...", "type": "..." }, ... ] }

require 'net/http'
require 'uri'
require 'json'
require 'csv'
require 'optparse'
require 'securerandom'

opts = { dialect: 'snowflake' }
OptionParser.new do |p|
  p.on('--connection-id ID')  { |v| opts[:conn]    = v }
  p.on('--table-path PATH')   { |v| opts[:path]    = v }
  p.on('--dialect D')         { |v| opts[:dialect] = v }
  p.on('--folder-id ID')      { |v| opts[:folder]  = v }
  p.on('--out PATH')          { |v| opts[:out]     = v }
end.parse!
abort 'missing --connection-id' unless opts[:conn]
abort 'missing --table-path (DB.SCHEMA.TABLE)' unless opts[:path]

parts = opts[:path].split('.', 3)
abort "--table-path must be DB.SCHEMA.TABLE (got #{opts[:path].inspect})" unless parts.size == 3
db, schema, table = parts

BASE = ENV.fetch('SIGMA_BASE_URL') { abort 'set SIGMA_BASE_URL' }
TOK  = ENV.fetch('SIGMA_API_TOKEN') { abort 'set SIGMA_API_TOKEN' }

def http(method, path, body = nil, accept_json: true)
  uri = URI("#{BASE}#{path}")
  req = case method
        when :post   then r = Net::HTTP::Post.new(uri);   r['Content-Type'] = 'application/json' if body; r.body = body if body; r
        when :get    then Net::HTTP::Get.new(uri)
        when :delete then Net::HTTP::Delete.new(uri)
        end
  req['Authorization'] = "Bearer #{TOK}"
  req['Accept']        = 'application/json' if accept_json
  Net::HTTP.start(uri.host, uri.port, use_ssl: true) { |h| h.request(req) }
end

# INFORMATION_SCHEMA queries per dialect.
information_schema_sql = case opts[:dialect]
                        when 'snowflake', 'postgres', 'redshift', 'sqlserver'
                          # ANSI-style — all four expose INFORMATION_SCHEMA at the database level.
                          "SELECT COLUMN_NAME, DATA_TYPE FROM #{db}.INFORMATION_SCHEMA.COLUMNS " \
                            "WHERE TABLE_SCHEMA = '#{schema}' AND TABLE_NAME = '#{table}' " \
                            "ORDER BY ORDINAL_POSITION"
                        when 'bigquery'
                          # BigQuery uses backticks + region-specific dataset INFORMATION_SCHEMA
                          "SELECT column_name AS COLUMN_NAME, data_type AS DATA_TYPE " \
                            "FROM `#{db}.#{schema}`.INFORMATION_SCHEMA.COLUMNS " \
                            "WHERE table_name = '#{table}' ORDER BY ordinal_position"
                        else
                          abort "unsupported --dialect #{opts[:dialect].inspect}; use snowflake|postgres|bigquery|redshift|sqlserver"
                        end

# Resolve a folder if not supplied.
folder_id = opts[:folder]
unless folder_id
  res = http(:get, '/v2/files?typeFilters=workbook&limit=1')
  if res.is_a?(Net::HTTPSuccess)
    list = JSON.parse(res.body) rescue { 'entries' => [] }
    folder_id = list.dig('entries', 0, 'parentId')
  end
end
abort 'could not resolve a folder ID; pass --folder-id' unless folder_id

probe_name = "_probe_csql_#{SecureRandom.hex(4)}"
spec = {
  name: probe_name,
  folderId: folder_id,
  schemaVersion: 1,
  pages: [
    {
      id: 'p1', name: 'p1',
      elements: [
        {
          id: 'probe', kind: 'table', name: 'Probe',
          source: { kind: 'sql', connectionId: opts[:conn], statement: information_schema_sql },
          columns: [
            { id: 'c-name', name: 'column_name', formula: '[Custom SQL/COLUMN_NAME]' },
            { id: 'c-type', name: 'data_type',   formula: '[Custom SQL/DATA_TYPE]' }
          ]
        }
      ]
    }
  ]
}

warn "probing: #{opts[:path]} via INFORMATION_SCHEMA (#{opts[:dialect]})"
res = http(:post, '/v2/workbooks/spec', JSON.generate(spec))
# Response body may be JSON ({"workbookId":"..."}) or YAML; tolerate both.
parsed = (JSON.parse(res.body) rescue nil)
wb_id  = parsed && parsed['workbookId']
wb_id ||= res.body[/workbookId:\s*['"]?([\w-]+)/, 1]
unless wb_id && res.is_a?(Net::HTTPSuccess)
  warn "POST failed (HTTP #{res.code}):"
  warn res.body
  exit 2
end
warn "probe workbook created: #{wb_id}"

cleanup = lambda do
  http(:delete, "/v2/files/#{wb_id}")
  warn "probe workbook deleted: #{wb_id}"
end

at_exit(&cleanup)

# Export the probe element to CSV; poll until ready.
exp = http(:post, "/v2/workbooks/#{wb_id}/export",
           JSON.generate(elementId: 'probe', format: { type: 'csv' }))
query_id = (JSON.parse(exp.body) rescue {})['queryId']
unless query_id
  warn "export POST failed (HTTP #{exp.code}):"
  warn exp.body
  exit 2
end

csv_body = nil
20.times do |i|
  sleep(i.zero? ? 0.5 : 1)
  dl = http(:get, "/v2/query/#{query_id}/download", nil, accept_json: false)
  ct = dl['Content-Type'].to_s
  if ct.include?('csv')
    csv_body = dl.body
    break
  end
end
unless csv_body
  warn 'export did not complete in 20s'
  exit 3
end

rows = CSV.parse(csv_body, headers: true)
cols = rows.map { |r| { 'name' => r['column_name'], 'type' => r['data_type'].to_s } }
if cols.empty?
  warn "INFORMATION_SCHEMA returned 0 rows — check spelling of #{opts[:path]} or pass --dialect"
  exit 4
end

result = {
  'connection_id' => opts[:conn],
  'table_path'    => opts[:path],
  'columns'       => cols
}
out = JSON.pretty_generate(result)
if opts[:out]
  File.write(opts[:out], out)
  puts "wrote #{opts[:out]} (#{cols.size} columns)"
else
  puts out
end
