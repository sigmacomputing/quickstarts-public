#!/usr/bin/env ruby
# GET a workbook spec, replace per-page layouts with a single top-level layout
# XML (provided), strip read-only fields, PUT back.
#
# Container layouts: a <GridContainer> in the layout XML must be paired with a
# `kind: container` placeholder element in the spec (else it is silently
# dropped — layout-playbook.md). Layout builders that emit GridContainers
# write a sidecar `<layout>.elements.json` ({pageId: [element, ...]}) next to
# the layout XML; this script injects those elements (containers + header
# text) into the matching pages before the PUT. Pass --elements to override
# the sidecar path. Injection is idempotent (existing element ids are kept).
#
# Usage:
#   ruby put-layout.rb --workbook <wbId> --layout <layout.xml> \
#     [--elements <elements.json>]

require 'json'
require 'yaml'
require 'date'
require 'optparse'
# sigma_rest self-exchanges SIGMA_CLIENT_ID/SECRET (auto-loading
# ~/.sigma-migration/env) exactly like the phase 1-4 scripts — SIGMA_API_TOKEN
# is optional, not a hard requirement (bead eqom).
$LOAD_PATH.unshift File.expand_path('lib', __dir__)
require 'sigma_rest'

opts = {}
OptionParser.new do |p|
  p.on('--workbook ID') { |v| opts[:wb] = v }
  p.on('--layout PATH') { |v| opts[:layout] = v }
  p.on('--elements PATH', 'spec elements to inject (default: <layout>.elements.json if present)') { |v| opts[:elements] = v }
end.parse!
%i[wb layout].each { |k| abort("missing --#{k}") unless opts[k] }

def http(method, path, body = nil)
  Sigma.request(method, path, body: body, binary: true)
end

xml = File.read(opts[:layout])
abort "FATAL: empty elementId in layout XML" if xml.match?(/elementId=""/)

spec = JSON.parse(http(:get, "/v2/workbooks/#{opts[:wb]}/spec"))
spec['pages'].each { |p| p.delete('layout') }
spec['layout'] = xml

# Inject container/header-text spec elements (see header comment).
elements_path = opts[:elements] || "#{opts[:layout]}.elements.json"
if File.exist?(elements_path)
  inject = JSON.parse(File.read(elements_path))
  injected = 0
  inject.each do |page_id, els|
    page = spec['pages'].find { |p| p['id'] == page_id }
    unless page
      warn "WARN: elements sidecar references unknown page #{page_id.inspect} — skipped"
      next
    end
    page['elements'] ||= []
    existing = page['elements'].map { |e| e['id'] }
    els.each do |el|
      next if existing.include?(el['id'])
      page['elements'] << el
      injected += 1
    end
  end
  puts "injected #{injected} container/header element(s) from #{elements_path}"
end
%w[workbookId url ownerId createdBy updatedBy createdAt updatedAt latestDocumentVersion].each { |k| spec.delete(k) }

begin
  resp_body = http(:put, "/v2/workbooks/#{opts[:wb]}/spec", JSON.pretty_generate(spec))
rescue Sigma::Error => e
  puts "ERROR: #{e.message}"
  exit 1
end
parsed = YAML.safe_load(resp_body, permitted_classes: [Date, Time])
puts parsed['workbookId'] ? "PUT ok: workbookId=#{parsed['workbookId']}" : "ERROR: #{parsed.inspect}"
exit(parsed['workbookId'] ? 0 : 1)
