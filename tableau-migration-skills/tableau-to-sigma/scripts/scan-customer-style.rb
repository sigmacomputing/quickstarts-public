#!/usr/bin/env ruby
# Phase 0c — sample a customer's recent Sigma workbooks and aggregate the
# style choices they actually make (color palettes, layout grids, number
# formats, chart-kind mix, dataLabel default, etc.) so subsequent Tableau→
# Sigma conversions emit specs that blend in with the customer's existing
# work rather than the converter's generic defaults.
#
# Usage:
#   ruby scripts/scan-customer-style.rb \
#     --sample 20 \
#     --out-dir /tmp/<customer>/style-profile/
#     [--sort updatedAt:desc]   # default
#     [--workbook-ids id1,id2]  # bypass listing, pin a specific set
#     [--exclude-folder FID]    # skip a folder (e.g. "Archive")
#
# Output:
#   <out-dir>/style-profile.json   — machine-readable aggregate
#   <out-dir>/style-profile.md     — human summary
#   <out-dir>/raw-specs/<wbId>.yaml (when --keep-raw)
#
# Env: SIGMA_BASE_URL and SIGMA_API_TOKEN.
#
# Privacy: scanner reads SPEC shape and column-formula strings — it does not
# query any data. Spec strings can still contain customer-named columns;
# treat the output as customer-confidential.

require 'json'
require 'yaml'
require 'net/http'
require 'uri'
require 'fileutils'
require 'optparse'

opts = { sample: 20, sort: 'updatedAt:desc', keep_raw: false }
OptionParser.new do |p|
  p.on('--sample N', Integer)   { |v| opts[:sample]   = v }
  p.on('--out-dir D')           { |v| opts[:out_dir]  = v }
  p.on('--sort S')              { |v| opts[:sort]     = v }
  p.on('--workbook-ids IDS')    { |v| opts[:wb_ids]   = v.split(',') }
  p.on('--exclude-folder F')    { |v| opts[:excl]     = v }
  p.on('--keep-raw')            { |_| opts[:keep_raw] = true }
end.parse!
abort 'missing --out-dir' unless opts[:out_dir]

BASE = ENV.fetch('SIGMA_BASE_URL')
TOK  = ENV.fetch('SIGMA_API_TOKEN')

def http_get(path, accept: 'application/json')
  uri = URI("#{BASE}#{path}")
  req = Net::HTTP::Get.new(uri)
  req['Authorization'] = "Bearer #{TOK}"
  req['Accept']        = accept
  Net::HTTP.start(uri.host, uri.port, use_ssl: true, read_timeout: 60) { |h| h.request(req) }
end

FileUtils.mkdir_p(opts[:out_dir])
FileUtils.mkdir_p(File.join(opts[:out_dir], 'raw-specs')) if opts[:keep_raw]

# 1. Pick the sample
wb_ids = opts[:wb_ids]
if wb_ids.nil?
  warn "listing workbooks (sample #{opts[:sample]}, sort #{opts[:sort]})"
  page = nil
  collected = []
  loop do
    qs = "limit=#{[opts[:sample] - collected.size, 100].min}"
    qs += "&page=#{page}" if page
    resp = http_get("/v2/workbooks?#{qs}")
    abort "list failed: #{resp.code}" unless resp.code.to_i == 200
    data = JSON.parse(resp.body)
    rows = (data['entries'] || data['workbooks'] || data).is_a?(Array) ? (data['entries'] || data['workbooks'] || data) : (data['entries'] || [])
    rows = (data['entries'] || []) if rows.empty? && data.is_a?(Hash)
    rows.each do |r|
      next if opts[:excl] && r['folderId'] == opts[:excl]
      collected << r['workbookId']
      break if collected.size >= opts[:sample]
    end
    break if collected.size >= opts[:sample]
    page = data['nextPage']
    break if page.nil? || page.empty?
  end
  wb_ids = collected
end
warn "scanning #{wb_ids.size} workbooks"

# 2. Per-workbook spec walk
profile = {
  'sample_size'      => 0,
  'sources_seen'     => Hash.new(0),
  'chart_kind_counts'=> Hash.new(0),
  'palettes'         => Hash.new(0),   # serialized scheme → freq
  'palette_modes'    => Hash.new(0),   # color.by values
  'layout_grid_cols' => Hash.new(0),
  'format_strings'   => Hash.new(0),
  'format_kinds'     => Hash.new(0),
  'datalabel_labels' => Hash.new(0),
  'stacking_modes'   => Hash.new(0),
  'sort_directions'  => Hash.new(0),
  'controls_per_page'=> [],
  'pages_per_workbook'=> [],
  'elements_per_page'=> [],
  'element_naming_case' => Hash.new(0),
  'schema_versions'  => Hash.new(0),
  'visibility'       => Hash.new(0),
  'workbooks'        => []
}

def case_of(s)
  return 'empty' if s.nil?
  # Sigma styled-name shape: { text:"X", visibility:"shown", ... } — unwrap
  s = s['text'] || s.values.find { |v| v.is_a?(String) } || '' if s.is_a?(Hash)
  return 'empty' if s.to_s.empty?
  s = s.to_s
  return 'snake' if s.include?('_')
  return 'kebab' if s.include?('-') && s == s.downcase
  return 'upper' if s == s.upcase && s =~ /[A-Z]/
  return 'lower' if s == s.downcase
  return 'sentence' if s =~ /^[A-Z][a-z]/ && s.count(' ') >= 1 && s.split(' ')[1..]&.all? { |w| w[0] == w[0].downcase || w =~ /^[A-Z][A-Z]/ }
  return 'title' if s.split(' ').all? { |w| w =~ /^[A-Z]/ }
  'mixed'
end

def walk(o, &b)
  b.call(o)
  if o.is_a?(Hash); o.each_value { |v| walk(v, &b) }
  elsif o.is_a?(Array); o.each { |v| walk(v, &b) }
  end
end

wb_ids.each_with_index do |wb_id, i|
  warn "  [#{i + 1}/#{wb_ids.size}] #{wb_id}"
  resp = http_get("/v2/workbooks/#{wb_id}/spec", accept: 'application/json')
  next unless resp.code.to_i == 200

  spec = begin
    JSON.parse(resp.body)
  rescue JSON::ParserError
    YAML.safe_load(resp.body, permitted_classes: [Date, Time])
  end
  File.write(File.join(opts[:out_dir], 'raw-specs', "#{wb_id}.yaml"), spec.to_yaml) if opts[:keep_raw]

  profile['sample_size'] += 1
  profile['schema_versions'][spec['schemaVersion'].to_s] += 1
  pages = spec['pages'] || []
  profile['pages_per_workbook'] << pages.size

  wb_charts = 0
  pages.each do |page|
    els = page['elements'] || []
    chart_els = els.select { |e| e['kind'] && e['kind'] != 'text' && e['kind'] != 'container' }
    profile['elements_per_page'] << chart_els.size
    controls_count = els.count { |e| e['kind'] == 'control' || e['kind'].to_s.start_with?('control-') }
    profile['controls_per_page'] << controls_count

    # Layout grid extraction from XML
    if page['layout'].is_a?(String) && (m = page['layout'].match(/gridTemplateColumns="repeat\((\d+),/))
      profile['layout_grid_cols'][m[1].to_i] += 1
    end

    els.each do |el|
      kind = el['kind']
      next if kind.nil?
      profile['chart_kind_counts'][kind] += 1
      wb_charts += 1
      profile['element_naming_case'][case_of(el['name'])] += 1
      profile['sources_seen'][el.dig('source', 'kind') || 'none'] += 1

      # Color palette
      if (color = el['color'])
        profile['palette_modes'][color['by'] || 'unknown'] += 1
        if color['scheme'].is_a?(Array) && !color['scheme'].empty?
          key = color['scheme'].join(',')
          profile['palettes'][key] += 1
        end
      end

      # Stacking
      profile['stacking_modes'][el['stacking'].to_s] += 1 if el.key?('stacking')

      # xAxis sort
      if (sort = el.dig('xAxis', 'sort'))
        profile['sort_directions'][sort['direction'].to_s] += 1
      end

      # dataLabel
      if (dl = el['dataLabel'])
        profile['datalabel_labels'][dl['labels'].to_s] += 1
      end

      # Per-column format strings + kinds
      (el['columns'] || []).each do |c|
        if (f = c['format'])
          profile['format_kinds'][f['kind'].to_s] += 1 if f['kind']
          profile['format_strings'][f['formatString'].to_s] += 1 if f['formatString']
        end
      end

      # Visibility
      profile['visibility'][el['visibility'].to_s] += 1 if el.key?('visibility')
    end
  end
  profile['workbooks'] << { 'workbookId' => wb_id, 'chart_count' => wb_charts, 'page_count' => pages.size }
end

# 3. Rank / summarize
def topn(h, n = 5)
  h.sort_by { |_, v| -v }.first(n).to_h
end

summary = profile.merge(
  'top_palettes'        => topn(profile['palettes']),
  'top_format_strings'  => topn(profile['format_strings'], 10),
  'top_chart_kinds'     => topn(profile['chart_kind_counts'], 10),
  'avg_pages_per_wb'    => profile['pages_per_workbook'].empty? ? 0 : profile['pages_per_workbook'].sum.to_f / profile['pages_per_workbook'].size,
  'avg_elements_per_page' => profile['elements_per_page'].empty? ? 0 : profile['elements_per_page'].sum.to_f / profile['elements_per_page'].size,
  'avg_controls_per_page' => profile['controls_per_page'].empty? ? 0 : profile['controls_per_page'].sum.to_f / profile['controls_per_page'].size
)

File.write(File.join(opts[:out_dir], 'style-profile.json'), JSON.pretty_generate(summary))

md = String.new
md << "# Customer style profile\n\n"
md << "_#{summary['sample_size']} workbooks scanned, #{summary['chart_kind_counts'].values.sum} elements total._\n\n"
md << "## Top chart kinds\n\n"
summary['top_chart_kinds'].each { |k, c| md << "- **#{k}**: #{c}\n" }
md << "\n## Top color palettes (by exact scheme array)\n\n"
if summary['top_palettes'].empty?
  md << "_No `color.scheme` arrays found — customer relies on Sigma defaults._\n"
else
  summary['top_palettes'].each { |hex, c| md << "- #{c}× `#{hex}`\n" }
end
md << "\n## Top number-format strings\n\n"
summary['top_format_strings'].each { |s, c| md << "- #{c}× `#{s}`\n" }
md << "\n## Layout grids\n\n"
profile['layout_grid_cols'].sort_by { |_, v| -v }.each { |cols, n| md << "- `repeat(#{cols}, 1fr)`: #{n} pages\n" }
md << "\n## dataLabel preference\n\n"
profile['datalabel_labels'].each { |v, c| md << "- `labels: #{v}`: #{c} charts\n" }
md << "\n## Stacking\n\n"
profile['stacking_modes'].each { |v, c| md << "- `stacking: #{v}`: #{c}\n" }
md << "\n## Element naming case\n\n"
profile['element_naming_case'].sort_by { |_, v| -v }.each { |k, v| md << "- #{k}: #{v}\n" }
md << "\n## Density\n\n"
md << "- pages per workbook (avg): #{summary['avg_pages_per_wb'].round(1)}\n"
md << "- elements per page (avg): #{summary['avg_elements_per_page'].round(1)}\n"
md << "- controls per page (avg): #{summary['avg_controls_per_page'].round(1)}\n"
md << "\n## Source kinds\n\n"
profile['sources_seen'].each { |k, v| md << "- `#{k}`: #{v}\n" }
md << "\n## Schema version distribution\n\n"
profile['schema_versions'].each { |k, v| md << "- v#{k}: #{v}\n" }

File.write(File.join(opts[:out_dir], 'style-profile.md'), md)
warn ""
warn "Profile written:"
warn "  JSON: #{File.join(opts[:out_dir], 'style-profile.json')}"
warn "  MD:   #{File.join(opts[:out_dir], 'style-profile.md')}"
