#!/usr/bin/env ruby
# Phase 6f-visual — IMAGE-based parity for tiles whose Tableau data export came
# back EMPTY (action-filter-gated sheets etc.). Those tiles are BUILT from the
# .twb shelf signals (so the viz is never dropped) but can't be value-diffed —
# there are no exportable actuals. Instead of letting them pass parity silently,
# this fetches the TABLEAU VIEW IMAGE (which always renders) and the SIGMA
# ELEMENT render side-by-side so the agent can confirm the migrated tile matches.
#
# Reads  <tableau-dir>/visual-verify-tiles.json  (written by build-charts-from-
# signals.rb) and writes, per tile, two PNGs + a manifest the hard gate checks:
#   <tableau-dir>/visual-verify/<slug>.tableau.png
#   <tableau-dir>/visual-verify/<slug>.sigma.png
#   <tableau-dir>/visual-verify/manifest.json
#
# Usage:
#   eval "$(scripts/get-token.sh)"; eval "$(scripts/get-tableau-token.sh)"
#   ruby scripts/verify-visual-tiles.rb --workbook <sigmaWorkbookId> --tableau-dir <dir>
#
# After it runs: READ each pair with the Read tool and compare (shape, trend,
# axis, magnitudes). Mark reviewed tiles by setting "visual_verified": true in
# the manifest, then the hard gate (assert-phase6-ran.rb) treats them as passed.

require 'json'
require 'optparse'
require 'fileutils'
require_relative 'lib/tableau_rest'

opts = {}
OptionParser.new do |p|
  p.on('--workbook ID')     { |v| opts[:wb] = v }
  p.on('--tableau-dir DIR') { |v| opts[:tab] = v }
  p.on('--w N', Integer)    { |v| opts[:w] = v }
  p.on('--h N', Integer)    { |v| opts[:h] = v }
end.parse!
%i[wb tab].each { |k| abort("missing --#{k.to_s.tr('_', '-')}") unless opts[k] }
opts[:w] ||= 1400
opts[:h] ||= 900

sidecar = File.join(opts[:tab], 'visual-verify-tiles.json')
unless File.exist?(sidecar)
  puts "no visual-verify-tiles.json in #{opts[:tab]} — nothing to verify (no empty-export tiles). OK."
  exit 0
end
tiles = JSON.parse(File.read(sidecar))
if tiles.empty?
  puts 'visual-verify-tiles.json is empty — no empty-export tiles. OK.'
  exit 0
end

outdir = File.join(opts[:tab], 'visual-verify')
FileUtils.mkdir_p(outdir)
png_script = File.join(__dir__, 'sigma-export-png.py')

slugify = ->(s) { s.to_s.downcase.gsub(/[^a-z0-9]+/, '-').gsub(/^-|-$/, '')[0..50] }
manifest = []
tiles.each do |t|
  ws   = t['worksheet']
  slug = slugify.call(ws)
  tab_png   = File.join(outdir, "#{slug}.tableau.png")
  sigma_png = File.join(outdir, "#{slug}.sigma.png")
  rec = { 'worksheet' => ws, 'element_id' => t['element_id'], 'view_id' => t['view_id'],
          'reason' => t['reason'], 'tableau_png' => nil, 'sigma_png' => nil,
          'visual_verified' => false }

  # 1) Tableau view image (renders fine even though its data export was empty)
  begin
    if t['view_id']
      bytes = Tableau.view_image(t['view_id'], width: opts[:w], height: opts[:h])
      File.binwrite(tab_png, bytes)
      rec['tableau_png'] = tab_png if File.size?(tab_png)
    end
  rescue StandardError => e
    warn "  WARN  Tableau image fetch failed for #{ws.inspect}: #{e.class}: #{e.message}"
  end

  # 2) Sigma element render
  if t['element_id']
    ok = system('python3', png_script, '--workbook', opts[:wb], '--element', t['element_id'],
                '--out', sigma_png, '--w', opts[:w].to_s, '--h', opts[:h].to_s,
                out: File::NULL, err: File::NULL)
    rec['sigma_png'] = sigma_png if ok && File.size?(sigma_png)
  end

  status = (rec['tableau_png'] && rec['sigma_png']) ? 'READY for review' : 'INCOMPLETE'
  puts "  #{ws}  → #{status}  (tableau=#{rec['tableau_png'] ? 'ok' : 'MISSING'}, sigma=#{rec['sigma_png'] ? 'ok' : 'MISSING'})"
  manifest << rec
end

man_path = File.join(outdir, 'manifest.json')
File.write(man_path, JSON.pretty_generate(manifest))
ready = manifest.count { |m| m['tableau_png'] && m['sigma_png'] }
puts
puts "wrote #{man_path} (#{ready}/#{manifest.size} tile(s) ready for visual review)"
puts 'NEXT: READ each tableau_png / sigma_png pair and compare (trend, axis, magnitudes).'
puts '      Set "visual_verified": true per reviewed tile so assert-phase6-ran.rb counts it as passed.'
# Non-zero exit if any tile could not be staged for review — the orchestrator
# surfaces it rather than declaring parity done with an unverifiable tile.
exit(ready == manifest.size ? 0 : 7)
