#!/usr/bin/env ruby
# Phase-1 discovery via the Tableau REST API. Use this when the Tableau MCP isn't available
# (or when you want a single-command CLI that produces all Phase-1 artifacts).
#
# Output layout (matches what the MCP-driven Phase 1 produces):
#   /tmp/<name>/get-workbook.json     — workbook metadata + view list
#   /tmp/<name>/ds-metadata.json      — VDS read-metadata response (field list + formulas)
#   /tmp/<name>/graphql-fields.json   — metadata API field list (cleaner formulas)
#   /tmp/<name>/views/<viewId>.csv    — every view's data CSV
#   /tmp/<name>/views/<viewId>.png    — dashboard view image only (skip other views by default)
#   /tmp/<name>/workbook-content.twb  — raw .twb XML (or .twbx zip bytes)
#
# Usage:
#   eval "$(scripts/get-tableau-token.sh)"
#   ruby scripts/tableau-discover.rb \
#     --workbook-name "Orders Conversion Test" \
#     --datasource-name "ORDER_FACT (MY_CONNECTION.ORDER_FACT)+ (New Virtual Connection)" \
#     --out /tmp/orders
#
# At least one of --workbook-id / --workbook-name is required.
# --datasource-luid / --datasource-name are optional (skipped if neither given).

require 'json'
require 'fileutils'
require 'optparse'

$LOAD_PATH.unshift File.expand_path('lib', __dir__)
require 'tableau_rest'

opts = { fetch_view_images: 'dashboard-only' }
OptionParser.new do |o|
  o.on('--workbook-name NAME')    { |v| opts[:workbook_name] = v }
  o.on('--workbook-id ID')        { |v| opts[:workbook_id] = v }
  o.on('--datasource-name NAME')  { |v| opts[:datasource_name] = v }
  o.on('--datasource-luid LUID')  { |v| opts[:datasource_luid] = v }
  o.on('--no-auto-ds', 'Disable .twb-based datasource auto-detect') { opts[:no_auto_ds] = true }
  o.on('--out DIR', 'Output directory (required)') { |v| opts[:out] = v }
  o.on('--skip-images')           { opts[:fetch_view_images] = 'none' }
  o.on('--all-view-images')       { opts[:fetch_view_images] = 'all' }
  o.on('--skip-content')          { opts[:skip_content] = true }
end.parse!

abort 'Missing --out' unless opts[:out]
abort 'Need --workbook-id or --workbook-name' unless opts[:workbook_id] || opts[:workbook_name]

FileUtils.mkdir_p(opts[:out])
FileUtils.mkdir_p(File.join(opts[:out], 'views'))

# 1. Workbook
wb = if opts[:workbook_id]
       Tableau.get_workbook(opts[:workbook_id])
     else
       hit = Tableau.find_workbook_by_name(opts[:workbook_name])
       abort "No workbook found with name=#{opts[:workbook_name]}" unless hit
       Tableau.get_workbook(hit['id'])
     end
File.write(File.join(opts[:out], 'get-workbook.json'), JSON.pretty_generate(wb))
warn "wrote get-workbook.json  (id=#{wb['id']} views=#{wb.dig('views', 'view')&.size})"

views = wb.dig('views', 'view') || []
views = [views] unless views.is_a?(Array)

# 2a. Download workbook content (.twb / .twbx) FIRST so we can auto-detect
#     the primary datasource caption from it when --datasource-name is omitted.
twb_xml = nil
unless opts[:skip_content]
  bytes = Tableau.download_workbook_content(wb['id'])
  if bytes.start_with?("PK\x03\x04")
    twbx_path = File.join(opts[:out], 'workbook-content.twbx')
    File.binwrite(twbx_path, bytes)
    warn "wrote workbook-content.twbx  (#{bytes.bytesize} bytes)"

    require 'tmpdir'
    Dir.mktmpdir do |tmp|
      unless system('unzip', '-o', '-q', twbx_path, '-d', tmp)
        warn '.twbx auto-unzip failed (unzip command not available?); leaving .twbx in place'
      else
        inner = Dir.glob(File.join(tmp, '**', '*.twb')).first
        if inner
          twb_path = File.join(opts[:out], 'workbook-content.twb')
          FileUtils.cp(inner, twb_path)
          warn "extracted workbook-content.twb  (#{File.size(twb_path)} bytes) from .twbx"
          twb_xml = File.read(twb_path)
        else
          warn '.twbx contained no inner .twb — odd'
        end
      end
    end
  else
    twb_path = File.join(opts[:out], 'workbook-content.twb')
    File.binwrite(twb_path, bytes)
    warn "wrote workbook-content.twb  (#{bytes.bytesize} bytes)"
    twb_xml = bytes.force_encoding('UTF-8')
  end
end

# 2b. Datasource metadata (VDS + GraphQL) — with .twb-based auto-detect
ds_luid = opts[:datasource_luid]
if ds_luid.nil? && opts[:datasource_name]
  hit = Tableau.find_datasource_by_name(opts[:datasource_name])
  ds_luid = hit['id'] if hit
end

if ds_luid.nil? && !opts[:no_auto_ds] && twb_xml
  # Parse .twb for the first non-Parameters <datasource caption='X'> and try to
  # find that datasource on the Tableau site. Strip the trailing "+ (...)" Tableau
  # decoration that virtual-connection-backed datasources get.
  caption = twb_xml.scan(/<datasource\s+caption='([^']+)'/).flatten
                   .reject { |c| c == 'Parameters' }
                   .first
  if caption
    bare = caption.sub(/\s*\+?\s*\(New Virtual Connection\)\s*$/i, '').strip
    %W[#{caption} #{bare}].uniq.each do |cand|
      hit = Tableau.find_datasource_by_name(cand)
      if hit
        ds_luid = hit['id']
        opts[:datasource_name] = cand
        warn "auto-detected datasource from .twb: #{cand.inspect} (luid=#{ds_luid})"
        break
      end
    end
    warn "could not resolve auto-detected datasource caption #{caption.inspect}; pass --datasource-luid to override" if ds_luid.nil?
  end
end

if ds_luid
  vds = Tableau.read_metadata(ds_luid)
  File.write(File.join(opts[:out], 'ds-metadata.json'), JSON.pretty_generate(vds))
  field_count = vds.dig('data')&.size || 0
  warn "wrote ds-metadata.json  (#{field_count} fields)"

  gql = Tableau.graphql_datasource_fields(ds_luid)
  File.write(File.join(opts[:out], 'graphql-fields.json'), JSON.pretty_generate(gql))
  warn 'wrote graphql-fields.json'
else
  warn 'no --datasource-luid/--datasource-name supplied (and auto-detect found nothing); skipping VDS + GraphQL fetches'
end

# 3. View CSVs — fire in parallel via threads. REST CSV endpoint handles concurrency
#    better than MCP image fetches (which contend on VizQL sessions), but at 6+ workers
#    we've seen 401s on Tableau Cloud. Cap at 4 and auto-retry any 401 once after a
#    brief backoff — a second-pass solo retry recovers cleanly when contention clears.
require 'thread'
view_pool = Queue.new
views.each { |v| view_pool << v }
csv_threads = Array.new([4, views.size].min) do
  Thread.new do
    until view_pool.empty?
      v = view_pool.pop(true) rescue nil
      break unless v
      attempts = 0
      begin
        attempts += 1
        csv = Tableau.view_data(v['id'])
        File.write(File.join(opts[:out], 'views', "#{v['id']}.csv"), csv)
        warn "wrote views/#{v['id']}.csv  (#{v['name']})"
      rescue Tableau::Error => e
        msg = e.message.lines.first&.chomp || ''
        if attempts < 2 && msg =~ /\b401\b/
          sleep(1.5)
          retry
        end
        warn "view CSV failed for #{v['name']} (#{v['id']}) after #{attempts} attempt(s): #{msg}"
      end
    end
  end
end
csv_threads.each(&:join)

# 4. View images
case opts[:fetch_view_images]
when 'none'
  warn 'skipping view images (--skip-images)'
when 'dashboard-only'
  # Heuristic: the largest view by viewUrlName length OR the one whose name matches "overview" / "dashboard"
  dash = views.find { |v| v['name'] =~ /\boverview\b|\bdashboard\b/i } ||
         views.max_by { |v| (v['name'] || '').length }
  if dash
    png = Tableau.view_image(dash['id'])
    File.binwrite(File.join(opts[:out], 'views', "#{dash['id']}.png"), png)
    warn "wrote views/#{dash['id']}.png  (dashboard: #{dash['name']})"
  end
when 'all'
  views.each do |v|
    png = Tableau.view_image(v['id'])
    File.binwrite(File.join(opts[:out], 'views', "#{v['id']}.png"), png)
    warn "wrote views/#{v['id']}.png  (#{v['name']})"
  rescue Tableau::Error => e
    warn "view PNG failed for #{v['name']} (#{v['id']}): #{e.message.lines.first&.chomp}"
  end
end

# 5. Workbook content was downloaded earlier (step 2a) so the auto-detect could see it.

warn 'done.'
