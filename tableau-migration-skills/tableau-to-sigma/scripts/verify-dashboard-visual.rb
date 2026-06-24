#!/usr/bin/env ruby
# Phase 6f — FULL-DASHBOARD visual ground truth + repair loop enabler. The
# mandatory visual gate compares the WHOLE Sigma page to the WHOLE source
# Tableau dashboard (per-element checks miss layout/relationship defects —
# overlaps, dead zones, wrong relative sizing, stranded controls). This stages
# both images side by side per dashboard so the agent can diff them, fix the
# spec, re-render, and repeat until they match — then records the pairing the
# gate (assert-phase6-ran gate 8) and the agent rely on.
#
# For each Tableau dashboard it:
#   1. finds the source DASHBOARD view (view name == dashboard name) and fetches
#      its Tableau image (reusing the cached views/<id>.png if discovery got it),
#   2. renders the matching Sigma PAGE (page name == dashboard name),
#   3. writes  <dir>/visual-qa/<slug>.source.png + <slug>.sigma.png  + a
#      compare-manifest.json the agent fills in (visual_match per dashboard).
#
# Usage:
#   eval "$(scripts/get-token.sh)"; eval "$(scripts/get-tableau-token.sh)"
#   ruby scripts/verify-dashboard-visual.rb --workbook <sigmaWbId> --tableau-dir <dir>
#
# Then: READ each <slug>.source.png vs <slug>.sigma.png, fix any divergence
# (re-PUT the spec + re-render), and set "visual_match": true per dashboard.

require 'json'
require 'optparse'
require 'fileutils'
require_relative 'lib/tableau_rest'

opts = { w: 1700, h: 1100 }
OptionParser.new do |p|
  p.on('--workbook ID')     { |v| opts[:wb] = v }
  p.on('--tableau-dir DIR') { |v| opts[:tab] = v }
  p.on('--w N', Integer)    { |v| opts[:w] = v }
  p.on('--h N', Integer)    { |v| opts[:h] = v }
end.parse!
%i[wb tab].each { |k| abort("missing --#{k.to_s.tr('_', '-')}") unless opts[k] }

dash_layout = JSON.parse(File.read(File.join(opts[:tab], 'dashboard-layout.json')))
wb_ids = JSON.parse(File.read(File.join(opts[:tab], 'wb-ids.json')))
gw = (JSON.parse(File.read(File.join(opts[:tab], 'get-workbook.json'))) rescue {})
views = gw.dig('views', 'view') || []
views = [views] unless views.is_a?(Array)
view_id_by_name = views.each_with_object({}) { |v, h| h[v['name']] = v['id'] if v['name'] }
page_id_by_name = (wb_ids['pages'] || []).each_with_object({}) { |p, h| h[p['name']] = p['id'] if p['name'] }

outdir = File.join(opts[:tab], 'visual-qa')
FileUtils.mkdir_p(outdir)
png_script = File.join(__dir__, 'sigma-export-png.py')
slugify = ->(s) { s.to_s.downcase.gsub(/[^a-z0-9]+/, '-').gsub(/^-|-$/, '')[0..50] }

manifest = []
dash_layout.each do |d|
  name = d['dashboard']
  next if name.to_s.start_with?('[synthetic]')
  slug = slugify.call(name)
  src_png = File.join(outdir, "#{slug}.source.png")
  sig_png = File.join(outdir, "#{slug}.sigma.png")
  rec = { 'dashboard' => name, 'source_png' => nil, 'sigma_png' => nil, 'visual_match' => false }

  # 1) Source Tableau dashboard image (reuse the cached discovery PNG if present)
  vid = view_id_by_name[name]
  cached = vid && File.join(opts[:tab], 'views', "#{vid}.png")
  begin
    if cached && File.size?(cached)
      FileUtils.cp(cached, src_png)
    elsif vid
      File.binwrite(src_png, Tableau.view_image(vid, width: opts[:w], height: opts[:h]))
    end
    rec['source_png'] = src_png if File.size?(src_png)
  rescue StandardError => e
    warn "  WARN  source dashboard image failed for #{name.inspect}: #{e.class}: #{e.message}"
  end

  # 2) Sigma page render
  pid = page_id_by_name[name] || page_id_by_name.reject { |k, _| k == 'Data' }.values.first
  if pid
    ok = system('python3', png_script, '--workbook', opts[:wb], '--page', pid,
                '--out', sig_png, '--w', opts[:w].to_s, '--h', opts[:h].to_s,
                out: File::NULL, err: File::NULL)
    rec['sigma_png'] = sig_png if ok && File.size?(sig_png)
  end

  status = (rec['source_png'] && rec['sigma_png']) ? 'READY for side-by-side' : 'INCOMPLETE'
  puts "  #{name}  → #{status}  (source=#{rec['source_png'] ? 'ok' : 'MISSING'}, sigma=#{rec['sigma_png'] ? 'ok' : 'MISSING'})"
  manifest << rec
end

man_path = File.join(outdir, 'compare-manifest.json')
File.write(man_path, JSON.pretty_generate(manifest))
ready = manifest.count { |m| m['source_png'] && m['sigma_png'] }
puts
puts "wrote #{man_path} (#{ready}/#{manifest.size} dashboard(s) staged for full-page comparison)"
puts 'REPAIR LOOP: READ each <slug>.source.png vs <slug>.sigma.png. For any divergence (missing/wrong-kind'
puts '  tile, overlap, dead zone, wrong sizing, stranded control), fix the spec + re-render, then re-run.'
puts '  Set "visual_match": true per dashboard once it matches.'
exit(ready == manifest.size ? 0 : 7)
