#!/usr/bin/env ruby
# Detect whether a prior Phase-1 conversion run already produced the discovery
# artifacts we'd otherwise re-fetch from Tableau (views CSVs, view PNGs, the
# .twb, gap-scan output, layout JSON). If yes, emit absolute paths so the new
# conversion can reuse them instead of re-running tableau-discover.rb /
# scan-workbook-gaps.rb / parse-twb-layout.rb — easily saves 3+ minutes.
#
# Usage:
#   ruby scripts/find-prior-cache.rb --name <workbook-slug> [--out <file>.json]
#
# Output JSON shape:
#   {
#     "name": "workforce",
#     "found": true|false,
#     "cache_dirs": ["/tmp/audit-run-1/workforce", "/tmp/converter-test/workforce"],
#     "views_csv_dir": ".../views",            # or null
#     "views_png_dir": ".../views-png",        # or null
#     "twb":           ".../workbook-content.twb",   # or null
#     "gaps_report":   ".../*-gaps-report.md", # or null
#     "gaps_json":     ".../*-gaps.json",
#     "dashboard_layout":      ".../dashboard-layout.json",
#     "dashboard_layout_meta": ".../dashboard-layout-meta.json",
#     "get_workbook":  ".../get-workbook.json",
#     "dm_spec":       ".../dm-spec.json",
#     "wb_spec":       ".../wb-spec.json",
#     "dm_ids":        ".../dm-ids.json",
#     "wb_ids":        ".../wb-ids.json"
#   }
#
# Search locations (in order, first hit wins per artifact):
#   /tmp/audit-run-*/<name>/...
#   /tmp/converter-test/<name>/...
#   /tmp/<name>/...

require 'json'
require 'optparse'

opts = {}
OptionParser.new do |p|
  p.on('--name N') { |v| opts[:name] = v }
  p.on('--out P')  { |v| opts[:out]  = v }
end.parse!
abort 'missing --name' unless opts[:name]

name = opts[:name]
candidate_dirs = (
  Dir.glob("/tmp/audit-run-*/#{name}") +
  ["/tmp/converter-test/#{name}",
   "/tmp/#{name}"]
).select { |d| File.directory?(d) }

# For each artifact, find the first matching file across candidate_dirs.
def first_existing(dirs, *suffixes)
  dirs.each do |d|
    suffixes.each do |s|
      candidates = Dir.glob(File.join(d, s))
      hit = candidates.find { |f| File.file?(f) || File.directory?(f) }
      return hit if hit
    end
  end
  nil
end

result = {
  'name'                  => name,
  'found'                 => !candidate_dirs.empty?,
  'cache_dirs'            => candidate_dirs,
  'views_csv_dir'         => first_existing(candidate_dirs, 'views'),
  'views_png_dir'         => first_existing(candidate_dirs, 'views-png'),
  'twb'                   => first_existing(candidate_dirs, 'workbook-content.twb', '*.twb'),
  'gaps_report'           => first_existing(candidate_dirs, '*-gaps-report.md', 'gaps-report.md'),
  'gaps_json'             => first_existing(candidate_dirs, '*-gaps.json', 'gaps.json'),
  'dashboard_layout'      => first_existing(candidate_dirs, 'dashboard-layout.json'),
  'dashboard_layout_meta' => first_existing(candidate_dirs, 'dashboard-layout-meta.json'),
  'dashboard_render_png'  => first_existing(candidate_dirs, 'dashboard-render.png'),
  'get_workbook'          => first_existing(candidate_dirs, 'get-workbook.json'),
  'dm_spec'               => first_existing(candidate_dirs, 'dm-spec.json'),
  'wb_spec'               => first_existing(candidate_dirs, 'wb-spec.json'),
  'dm_ids'                => first_existing(candidate_dirs, 'dm-ids.json'),
  'wb_ids'                => first_existing(candidate_dirs, 'wb-ids.json'),
  'master_columns'        => first_existing(candidate_dirs, 'master-columns.json'),
  'workbook_signature'    => first_existing(candidate_dirs, 'workbook-signature.json'),
  'calc_fields'           => first_existing(candidate_dirs, 'calc-fields.json')
}

# --- Calc-fields cache freshness check -----------------------------------
# Surface a fresh calc-fields.json so subagents skip Phase 1e entirely
# (extract-calc-fields.rb hit Metadata API + .twb fallback). Stale (> 1h old)
# is reported but should still be re-fetched.
if result['calc_fields'] && File.file?(result['calc_fields'])
  age = Time.now - File.mtime(result['calc_fields'])
  begin
    parsed = JSON.parse(File.read(result['calc_fields']))
    result['calc_fields_meta'] = {
      'path'         => result['calc_fields'],
      'age_seconds'  => age.to_i,
      'fresh'        => age < 3600,
      'source'       => parsed['source'],
      'n_calcs'      => parsed['n_calcs'],
      'n_lods'       => parsed['n_lods'],
      'workbook_luid' => parsed['workbook_luid']
    }
  rescue StandardError
    result['calc_fields_meta'] = { 'path' => result['calc_fields'], 'age_seconds' => age.to_i, 'parse_error' => true }
  end
end

# --- Consistency check: dm-spec vs dm-ids element counts/names -----------
# OCT's v2 run hit a cached dir where dm-ids.json described a 6-element DM
# but dm-spec.json had 3 elements (stale spec). The agent then hand-rebuilt
# from dm-ids and lost ~5 minutes of confusion. Warn loudly when both files
# exist but disagree so the agent re-runs discover-columns +
# post-and-readback instead of trusting the stale spec.
def element_names_from(path)
  return nil unless path && File.file?(path)
  parsed =
    begin
      JSON.parse(File.read(path))
    rescue JSON::ParserError
      # spec may be YAML-style — try YAML
      begin
        require 'yaml'
        YAML.safe_load(File.read(path), permitted_classes: [Date, Time])
      rescue StandardError
        return nil
      end
    end
  return nil unless parsed.is_a?(Hash)
  pages = parsed['pages'] || []
  elements = pages.flat_map { |p| (p.is_a?(Hash) && p['elements']) || [] }
  # Fallback for legacy specs with a bare top-level elements array
  elements = parsed['elements'] if elements.empty? && parsed['elements'].is_a?(Array)
  elements.map { |e| (e.is_a?(Hash) && (e['name'] || e['id'])) || nil }.compact
end

dm_spec_names = element_names_from(result['dm_spec'])
dm_ids_names  = element_names_from(result['dm_ids'])

if dm_spec_names && dm_ids_names
  if dm_spec_names.length != dm_ids_names.length || dm_spec_names.sort != dm_ids_names.sort
    warn "WARN: dm-spec / dm-ids element count mismatch " \
         "(#{dm_spec_names.length} vs #{dm_ids_names.length}) — " \
         "cached spec likely stale, regenerate via discover-columns + post-and-readback"
    warn "  dm-spec.json elements: #{dm_spec_names.inspect}"
    warn "  dm-ids.json  elements: #{dm_ids_names.inspect}"
    result['dm_cache_warning'] = {
      'dm_spec_count' => dm_spec_names.length,
      'dm_ids_count'  => dm_ids_names.length,
      'dm_spec_names' => dm_spec_names,
      'dm_ids_names'  => dm_ids_names,
      'message'       => 'dm-spec / dm-ids element count mismatch — cached spec likely stale'
    }
  end
end

out_json = JSON.pretty_generate(result)
if opts[:out]
  File.write(opts[:out], out_json)
  warn "wrote #{opts[:out]}"
end
puts out_json
