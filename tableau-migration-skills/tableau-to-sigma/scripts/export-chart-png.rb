#!/usr/bin/env ruby
# Phase 6d — visual verification.
# Export PNG screenshots of every chart in a converted Sigma workbook so the
# agent can eyeball the result against the Tableau source PNGs (which the
# Tableau MCP can already produce).
#
# Background: spec round-trip + CSV value parity confirm correctness of data
# and structure. But neither catches visual regressions: a "log scale" that
# silently gets dropped, a "show data labels" that doesn't render, a wrong
# color palette, a stacked-vs-grouped bar mix-up. A PNG export per chart
# closes that loop. Verified end-to-end against Sigma's POST/v2/workbooks/
# {wb}/export → GET /v2/query/{q}/download flow on 2026-05-22.
#
# Usage:
#   ruby scripts/export-chart-png.rb \
#     --workbook <workbookId> \
#     --out-dir /tmp/<wb-name>/screenshots/ \
#     [--element-ids id1,id2,...]   # default: every chart-shaped element
#     [--width 1400] [--height 700]
#
# Output:
#   <out-dir>/<elementId>.png         per chart
#   <out-dir>/_manifest.json          { elementId → {kind, name, png_path, bytes} }
#
# Env: SIGMA_BASE_URL and SIGMA_API_TOKEN must be set.

require 'json'
require 'yaml'
require 'net/http'
require 'uri'
require 'fileutils'
require 'optparse'

opts = { width: 1400, height: 700 }
OptionParser.new do |p|
  p.on('--workbook ID')     { |v| opts[:workbook]    = v }
  p.on('--out-dir D')       { |v| opts[:out_dir]     = v }
  p.on('--element-ids IDS') { |v| opts[:element_ids] = v.split(',') }
  p.on('--width N',  Integer) { |v| opts[:width]  = v }
  p.on('--height N', Integer) { |v| opts[:height] = v }
end.parse!
%i[workbook out_dir].each { |k| abort "missing --#{k.to_s.tr('_','-')}" unless opts[k] }

BASE = ENV.fetch('SIGMA_BASE_URL')
TOK  = ENV.fetch('SIGMA_API_TOKEN')

CHART_KINDS = %w[bar-chart line-chart area-chart combo-chart scatter-chart
                 pie-chart donut-chart kpi-chart region-map point-map
                 pivot-table table].freeze

def http(method, path, body = nil, accept: 'application/json')
  uri = URI("#{BASE}#{path}")
  req = case method
        when :post then r = Net::HTTP::Post.new(uri); r.body = body; r['Content-Type'] = 'application/json'; r
        when :get  then Net::HTTP::Get.new(uri)
        end
  req['Authorization'] = "Bearer #{TOK}"
  req['Accept']        = accept
  Net::HTTP.start(uri.host, uri.port, use_ssl: true, read_timeout: 60) { |h| h.request(req) }
end

# 1. Discover elements to screenshot
spec_resp = http(:get, "/v2/workbooks/#{opts[:workbook]}/spec", accept: 'application/json')
abort "GET spec failed: #{spec_resp.code} #{spec_resp.body[0..200]}" unless spec_resp.code.to_i == 200
spec = begin
  JSON.parse(spec_resp.body)
rescue JSON::ParserError
  YAML.safe_load(spec_resp.body, permitted_classes: [Date, Time])
end
elements = (spec['pages'] || []).flat_map { |p| p['elements'] || [] }
targets = if opts[:element_ids]
            elements.select { |e| opts[:element_ids].include?(e['id']) }
          else
            elements.select { |e| CHART_KINDS.include?(e['kind']) }
          end
abort 'no matching elements' if targets.empty?
warn "screenshotting #{targets.size} elements: #{targets.map { |e| e['id'] }.join(', ')}"

FileUtils.mkdir_p(opts[:out_dir])
manifest = {}

# 2. Kick off all exports in parallel, then poll
queue = targets.map do |el|
  body = JSON.generate({
    elementId: el['id'],
    format: { type: 'png', pixelWidth: opts[:width], pixelHeight: opts[:height] }
  })
  resp = http(:post, "/v2/workbooks/#{opts[:workbook]}/export", body)
  parsed = JSON.parse(resp.body)
  { element: el, query_id: parsed['queryId'], status: parsed['queryId'] ? :pending : :error,
    error: parsed['queryId'] ? nil : resp.body }
end

# 3. Poll each query until 200 or timeout
queue.each do |q|
  next if q[:status] == :error
  out_path = File.join(opts[:out_dir], "#{q[:element]['id']}.png")
  done = false
  20.times do |i|
    sleep 3
    resp = http(:get, "/v2/query/#{q[:query_id]}/download")
    if resp.code.to_i == 200 && resp.body.bytesize > 1000 && resp.body.start_with?("\x89PNG".b)
      File.binwrite(out_path, resp.body)
      done = true
      break
    elsif resp.code.to_i == 204
      next  # still rendering
    elsif resp.code.to_i >= 400
      q[:status] = :error
      q[:error] = "#{resp.code}: #{resp.body[0..200]}"
      break
    end
  end
  if done
    q[:status]   = :ok
    q[:png_path] = out_path
    q[:bytes]    = File.size(out_path)
  elsif q[:status] != :error
    q[:status]   = :timeout
  end
end

# 4. Manifest + summary
queue.each do |q|
  manifest[q[:element]['id']] = {
    'kind'     => q[:element]['kind'],
    'name'     => q[:element]['name'],
    'status'   => q[:status].to_s,
    'png_path' => q[:png_path],
    'bytes'    => q[:bytes],
    'error'    => q[:error]
  }
end
File.write(File.join(opts[:out_dir], '_manifest.json'), JSON.pretty_generate(manifest))

ok      = queue.count { |q| q[:status] == :ok }
errors  = queue.count { |q| q[:status] == :error }
timeout = queue.count { |q| q[:status] == :timeout }
warn ""
warn "Screenshots: #{ok}/#{queue.size} ok, #{errors} error, #{timeout} timeout"
warn "Manifest: #{File.join(opts[:out_dir], '_manifest.json')}"
exit (errors + timeout) > 0 ? 1 : 0
