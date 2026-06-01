#!/usr/bin/env ruby
# GET a workbook spec, replace per-page layouts with a single top-level layout
# XML (provided), strip read-only fields, PUT back.
#
# Usage:
#   ruby put-layout.rb --workbook <wbId> --layout <layout.xml>

require 'net/http'
require 'uri'
require 'json'
require 'yaml'
require 'date'
require 'optparse'

opts = {}
OptionParser.new do |p|
  p.on('--workbook ID') { |v| opts[:wb] = v }
  p.on('--layout PATH') { |v| opts[:layout] = v }
end.parse!
%i[wb layout].each { |k| abort("missing --#{k}") unless opts[k] }

BASE = ENV.fetch('SIGMA_BASE_URL')
TOK  = ENV.fetch('SIGMA_API_TOKEN')

def http(method, path, body = nil)
  uri = URI("#{BASE}#{path}")
  req = case method
        when :get then Net::HTTP::Get.new(uri)
        when :put then r = Net::HTTP::Put.new(uri); r.body = body; r['Content-Type'] = 'application/json'; r
        end
  req['Authorization'] = "Bearer #{TOK}"
  req['Accept']        = 'application/json'
  Net::HTTP.start(uri.host, uri.port, use_ssl: true) { |h| h.request(req) }
end

xml = File.read(opts[:layout])
abort "FATAL: empty elementId in layout XML" if xml.match?(/elementId=""/)

spec = JSON.parse(http(:get, "/v2/workbooks/#{opts[:wb]}/spec").body)
spec['pages'].each { |p| p.delete('layout') }
spec['layout'] = xml
%w[workbookId url ownerId createdBy updatedBy createdAt updatedAt latestDocumentVersion].each { |k| spec.delete(k) }

resp = http(:put, "/v2/workbooks/#{opts[:wb]}/spec", JSON.pretty_generate(spec))
parsed = YAML.safe_load(resp.body, permitted_classes: [Date, Time])
puts parsed['workbookId'] ? "PUT ok: workbookId=#{parsed['workbookId']}" : "ERROR: #{parsed.inspect}"
exit(parsed['workbookId'] ? 0 : 1)
