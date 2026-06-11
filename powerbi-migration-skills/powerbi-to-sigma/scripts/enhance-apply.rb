#!/usr/bin/env ruby
# frozen_string_literal: true
#
# enhance-apply.rb — Phase E (opt-in) shared engine, part 2 of 2: APPLY.
#
# CLONE-FIRST, ACCEPT-ONLY, PARITY-GATED application of enhancements.json
# candidates produced by enhance-scan.rb:
#   1. CLONE: GET the parity-verified workbook's spec and POST it as
#      "<name> — Enhanced". The 1:1 parity artifact is NEVER written.
#   2. ACCEPT: only candidates named in --accept (id list) or matching
#      --accept all-low-risk are applied. Everything else is recorded as
#      skipped. Candidates whose patch carries unmet 'needs' (e.g. map
#      centroids) are skipped with the reason, never half-applied.
#   3. APPLY ONE AT A TIME with a parity-unchanged gate: after each item,
#      spot-query 2-3 UNTOUCHED elements on the clone AND the same elements
#      on the original simultaneously; any divergence (clone != original at
#      the same instant — live-drift-proof, the trial's lesson) auto-REVERTS
#      that item and flags it. enhance-report.json records
#      applied/skipped/reverted with evidence.
#
# This file is the SHARED Phase-E engine, vendored byte-identical into every
# covered plugin (md5 discipline — same as escalate-gap.py).
#
# Usage:
#   ruby scripts/enhance-apply.rb --workbook-id <parityWorkbookId> \
#     --enhancements <enhancements.json> \
#     --accept all-low-risk | --accept id1,id2,... \
#     [--name '<clone name>'] [--out enhance-report.json] [--probes N]
#
# Every applied item lands in the CONTAINER SYSTEM (see the layout-placement
# section): controls -> control band, KPIs -> KPI band, grain/drill switchers
# -> inside their chart's container, notes -> a slim band under the header.
# Pre-container clones get their layout regenerated as a banded layout first.
# The finalize runs the shared layout lint (lib/layout_lint.rb) and prints the
# hard screenshot checklist — the agent MUST export the full-page PNG and
# verify each item.
#
# Exit codes: 0 = done (clone created; accepted items applied or cleanly
# reverted; parity-unchanged gate green; layout lint clean); 2 = nothing
# accepted; 3 = the parity-unchanged gate could not be restored (clone left
# for inspection, report says so); 4 = layout lint violations on the clone
# (fix + re-PUT, then re-lint); other = error.

require 'json'
require 'yaml'
require 'time'
require 'date'
require 'optparse'

HERE = __dir__
$LOAD_PATH.unshift File.expand_path('lib', HERE)
require 'sigma_rest'

opts = { probes: 3 }
OptionParser.new do |o|
  o.on('--workbook-id ID')   { |v| opts[:wb] = v }
  o.on('--enhancements P')   { |v| opts[:enh] = File.expand_path(v) }
  o.on('--accept LIST')      { |v| opts[:accept] = v }
  o.on('--name NAME')        { |v| opts[:name] = v }
  o.on('--out PATH')         { |v| opts[:out] = File.expand_path(v) }
  o.on('--probes N', Integer) { |v| opts[:probes] = v }
end.parse!
abort 'missing --workbook-id' unless opts[:wb]
abort 'missing --enhancements' unless opts[:enh] && File.exist?(opts[:enh])
abort 'missing --accept (id list or all-low-risk) — nothing applies without explicit acceptance' unless opts[:accept]

ORIG_WB = opts[:wb]
enh = JSON.parse(File.read(opts[:enh]))
OUT = opts[:out] || File.join(File.dirname(opts[:enh]), 'enhance-report.json')

candidates = enh['candidates'] || []
accepted_ids =
  if opts[:accept].strip.casecmp?('all-low-risk')
    candidates.select { |c| c['risk'].to_s == 'low' }.map { |c| c['id'] }
  else
    opts[:accept].split(',').map(&:strip).reject(&:empty?)
  end
unknown = accepted_ids - candidates.map { |c| c['id'] }
abort "FATAL: --accept names unknown candidate id(s): #{unknown.join(', ')}" if unknown.any?

accepted = candidates.select { |c| accepted_ids.include?(c['id']) }
skipped  = candidates.reject { |c| accepted_ids.include?(c['id']) }
                     .map { |c| { 'id' => c['id'], 'risk' => c['risk'], 'reason' => 'not accepted' } }
if accepted.empty?
  puts 'enhance-apply: no candidate accepted — nothing to do (no clone created).'
  File.write(OUT, JSON.pretty_generate(
    'workbook_id' => ORIG_WB, 'status' => 'nothing-accepted',
    'applied' => [], 'skipped' => skipped, 'reverted' => [],
    'descoped_notes' => enh['descoped_notes'] || []))
  exit 2
end

READONLY_KEYS = %w[workbookId url ownerId createdBy updatedBy createdAt updatedAt
                   documentVersion latestDocumentVersion].freeze

def clean(spec)
  s = JSON.parse(JSON.generate(spec))
  READONLY_KEYS.each { |k| s.delete(k) }
  s
end

# Sigma's workbook POST/PUT responses can come back as YAML — parse leniently.
def lenient(body)
  return body if body.is_a?(Hash)
  YAML.safe_load(body.to_s, permitted_classes: [Date, Time]) rescue nil
end

def export_rows(wb, element_id, timeout: 75)
  res = Sigma.request(:post, "/v2/workbooks/#{wb}/export",
                      body: { 'elementId' => element_id, 'format' => { 'type' => 'json' } }.to_json)
  qid = res.is_a?(Hash) ? res['queryId'] : nil
  return nil unless qid
  deadline = Time.now + timeout
  while Time.now < deadline
    body = (Sigma.request(:get, "/v2/query/#{qid}/download", binary: true) rescue nil)
    if body && !body.strip.empty?
      parsed = (JSON.parse(body) rescue nil)
      return parsed if parsed.is_a?(Array)
      return parsed['rows'] if parsed.is_a?(Hash) && parsed['rows'].is_a?(Array)
      lines = body.each_line.map { |l| (JSON.parse(l) rescue nil) }.compact
      return lines unless lines.empty?
    end
    sleep 2
  end
  nil
rescue StandardError
  nil
end

# Order-insensitive, float-tolerant normalization for row comparison.
def norm_rows(rows)
  return nil unless rows.is_a?(Array)
  rows.map do |r|
    r.transform_values { |v| v.is_a?(Numeric) ? v.to_f.round(4) : v }
  end.sort_by { |r| JSON.generate(r.sort.to_h) }
end

# ---------------------------------------------------------------------------
# Container-aware layout placement (phase-e layout-quality fix).
#
# The first Phase E shipped enhancements by APPENDING <LayoutElement>s at the
# bottom of the Page block — controls/KPIs/notes dumped below the fold, the
# grain switcher orphaned at the foot. Every applied item now lands in the
# container system instead:
#   - selection controls       -> the control band (created if absent)
#   - comparison KPIs          -> the KPI band (created if absent)
#   - grain/drill switcher     -> INSIDE its chart's own container (slim row
#                                 above the chart)
#   - migration/freshness note -> a slim note band directly under the header
# If the cloned parity workbook PREDATES container layouts (no <GridContainer>
# in its layout), the clone's layout is REGENERATED as a banded layout first,
# using the builder's shared container machinery (lib/layout.rb).
# ---------------------------------------------------------------------------
require 'layout' # scripts/lib/layout.rb — SigmaLayout container machinery

CTRL_BAND_PREFIX = 'phasee-ctrl-band'
KPI_BAND_PREFIX  = 'phasee-kpi-band'
NOTE_BAND_PREFIX = 'phasee-note-band'
# vertical order of phasee-created bands under the header (note = slimmest,
# closest to the header; KPIs above the charts read best below the controls)
BAND_PRIORITY = { NOTE_BAND_PREFIX => 0, CTRL_BAND_PREFIX => 1, KPI_BAND_PREFIX => 2 }.freeze
BAND_ROWS = { NOTE_BAND_PREFIX => 2, CTRL_BAND_PREFIX => 3, KPI_BAND_PREFIX => 6 }.freeze

def page_block(spec, page_id)
  return nil if page_id.nil?
  spec['layout'].to_s.match(%r{(<Page\b[^>]*\bid="#{Regexp.escape(page_id)}"[^>]*>)(.*?)(</Page>)}m)
end

def replace_page_inner!(spec, page_id, new_inner)
  m = page_block(spec, page_id) or return nil
  spec['layout'] = spec['layout'].to_s.sub(m[0]) { "#{m[1]}#{new_inner}#{m[3]}" }
  true
end

# Direct children of a page block: [{tag:, eid:, c0:, c1:, r0:, r1:, s:, e:,
# head_e:, inner: (containers only)}] — byte offsets into the inner string.
def scan_top(inner)
  out = []
  pos = 0
  while (m = inner.match(%r{<(GridContainer|LayoutElement)\b[^>]*?(/>|>)}m, pos))
    tag = m[1]
    open_e = m.end(0)
    ent_end = open_e
    body = nil
    if tag == 'GridContainer' && m[2] == '>'
      close = inner.match(%r{</GridContainer>}m, open_e)
      ent_end = close ? close.end(0) : open_e
      body = close ? inner[open_e...close.begin(0)] : ''
    end
    head = inner[m.begin(0)...open_e]
    out << { tag: tag, eid: head[/elementId="([^"]*)"/, 1],
             c0: head[/gridColumn="\s*(\d+)/, 1].to_i,
             c1: head[/gridColumn="\s*\d+\s*\/\s*(\d+)/, 1].to_i,
             r0: head[/gridRow="\s*(\d+)/, 1].to_i,
             r1: head[/gridRow="\s*\d+\s*\/\s*(\d+)/, 1].to_i,
             s: m.begin(0), e: ent_end, head_e: open_e, inner: body }
    pos = ent_end
  end
  out
end

def set_rows(head, r0, r1)
  head.sub(/gridRow="[^"]*"/) { %(gridRow="#{r0} / #{r1}") }
end

# Shift every top-level entry starting at/after from_row down by delta rows.
def shift_top_rows(inner, from_row, delta)
  res = inner.dup
  scan_top(inner).reverse_each do |t|
    next unless t[:r0] >= from_row
    res[t[:s]...t[:head_e]] = set_rows(inner[t[:s]...t[:head_e]], t[:r0] + delta, t[:r1] + delta)
  end
  res
end

# Regenerate a banded layout for every dashboard page of a pre-container clone
# (flat <LayoutElement> list -> header band + row-band GridContainers via the
# builder's shared SigmaLayout machinery). No-op when containers exist.
def ensure_banded!(spec)
  return false if spec['layout'].to_s.include?('<GridContainer')
  changed = false
  (spec['pages'] || []).each do |pg|
    next if pg['id'].to_s.downcase.include?('data')
    m = page_block(spec, pg['id']) or next
    kind_of = (pg['elements'] || []).to_h { |e| [e['id'], e['kind']] }
    items = scan_top(m[2]).select { |t| t[:tag] == 'LayoutElement' }
                          .map { |t| [t[:eid], t[:c0], t[:c1], t[:r0], t[:r1]] }
    next if items.empty?
    # an existing short top text element (the dashboard's own title) becomes
    # the header band's text (recolored white for the dark band); otherwise
    # SigmaLayout adds a header from the page name -> workbook name chain
    # (resolve_header_title — never a generic "Page 1" auto-name). The
    # candidate may start up to one row below the topmost element (classic
    # title boxes are nudged a few px down; exact-row equality was the
    # PHASEE2 fragility).
    top_row = items.map { |i| i[3] }.min
    own_hdr = items.find { |i| i[3] <= top_row + 1 && kind_of[i[0]] == 'text' && (i[4] - i[3]) <= 5 }
    if own_hdr && items.length > 1
      items -= [own_hdr]
      hdr_el = (pg['elements'] || []).find { |e| e['id'] == own_hdr[0] }
      if hdr_el && hdr_el['body'].is_a?(String) && !hdr_el['body'].include?('color:')
        plain = hdr_el['body'].gsub(/^#+\s*/, '').strip
        hdr_el['body'] = %(# <span style="color: #FFFFFF">#{plain}</span>)
      end
      xml, extra = SigmaLayout.banded_page(pg['id'], items, header_el: own_hdr[0],
                                           id_prefix: "band-#{pg['id']}")
    else
      hdr_title = SigmaLayout.resolve_header_title(pg['name'], spec['name']) || 'Dashboard'
      xml, extra = SigmaLayout.banded_page(pg['id'], items, title: hdr_title,
                                           id_prefix: "band-#{pg['id']}")
    end
    new_ids = (pg['elements'] || []).map { |e| e['id'] }
    pg['elements'] = (pg['elements'] || []) + extra.reject { |e| new_ids.include?(e['id']) }
    spec['layout'] = spec['layout'].to_s.sub(m[0]) { xml }
    changed = true
  end
  changed
end

# Row where a new phasee band of `prefix` should start on this page: under the
# header band (the row-1 container), below any already-created phasee band of
# lower priority.
def band_anchor_row(ents, prefix)
  hdr = ents.select { |t| t[:tag] == 'GridContainer' }
            .find { |t| t[:r0] <= 1 }
  row = hdr ? hdr[:r1] : (ents.map { |t| t[:r0] }.min || 1)
  ents.each do |t|
    pfx = BAND_PRIORITY.keys.find { |p| t[:eid].to_s.start_with?(p) }
    row = [row, t[:r1]].max if pfx && BAND_PRIORITY[pfx] < BAND_PRIORITY[prefix]
  end
  row
end

# Find-or-create the phasee band container for `prefix` on the page; returns
# the band's container element id. Creates the spec-side `kind: container`
# placeholder and shifts everything below the insertion point down.
def ensure_band!(spec, page, prefix)
  m = page_block(spec, page['id']) or raise "no layout block for page #{page['id']}"
  ents = scan_top(m[2])
  existing = ents.find { |t| t[:eid].to_s.start_with?(prefix) }
  return existing[:eid] if existing
  rows = BAND_ROWS[prefix]
  cid = "#{prefix}-#{page['id']}"[0, 60]
  anchor = band_anchor_row(ents, prefix)
  inner = shift_top_rows(m[2], anchor, rows)
  band = SigmaLayout.gc(cid, 1, 25, anchor, anchor + rows, '')
  replace_page_inner!(spec, page['id'], "#{inner}\n#{band}\n")
  (page['elements'] ||= []) << SigmaLayout.container_el(cid) unless page['elements'].any? { |e| e['id'] == cid }
  cid
end

# Place an element INTO a band container, flowing left-to-right then wrapping
# to a new row (growing the band + shifting the bands below it).
def band_add!(spec, page_id, band_cid, element_id, grid_column, height)
  m = page_block(spec, page_id) or raise "no layout block for page #{page_id}"
  ents = scan_top(m[2])
  band = ents.find { |t| t[:eid] == band_cid } or raise "band #{band_cid} not found"
  c0, c1 = grid_column.to_s.scan(/\d+/).map(&:to_i)
  c0 = 1 if c0.nil? || c0 < 1
  c1 = [c0 + 8, 25].min if c1.nil? || c1 <= c0
  width = c1 - c0
  band_rows = band[:r1] - band[:r0]
  h = [height || band_rows, band_rows].min
  h = band_rows if h <= 0
  kids = scan_top(band[:inner].to_s)
  if kids.empty?
    row = 1
    place_c0 = c0
  else
    cur = kids.map { |k| k[:r0] }.max
    cur_kids = kids.select { |k| k[:r0] == cur }
    max_c1 = cur_kids.map { |k| k[:c1] }.max
    if max_c1 + width <= 25
      row = cur
      place_c0 = max_c1
    else
      row = kids.map { |k| k[:r1] }.max
      place_c0 = c0
    end
  end
  grow = [row + h - 1 - band_rows, 0].max
  entry = SigmaLayout.le(element_id, place_c0, place_c0 + width, row, row + h)
  new_band_inner = "#{band[:inner]}\n#{entry}"
  new_band_head = set_rows(m[2][band[:s]...band[:head_e]], band[:r0], band[:r1] + grow)
  new_band = "#{new_band_head}#{new_band_inner}\n</GridContainer>"
  inner = m[2].dup
  inner[band[:s]...band[:e]] = new_band
  inner = shift_below!(inner, band[:eid], band[:r1], grow) if grow.positive?
  replace_page_inner!(spec, page_id, inner)
end

# After growing a band, push every OTHER top-level entry that started at/after
# the band's old end row down by delta.
def shift_below!(inner, except_eid, from_row, delta)
  res = inner.dup
  scan_top(inner).reverse_each do |t|
    next if t[:eid] == except_eid || t[:r0] < from_row
    res[t[:s]...t[:head_e]] = set_rows(inner[t[:s]...t[:head_e]], t[:r0] + delta, t[:r1] + delta)
  end
  res
end

# Place a control INSIDE the container of the chart it drives: a slim row is
# opened at the top of that container (children shifted down), the container
# grows, and the bands below shift. Falls back to nil when the chart has no
# container (caller then uses the control band).
CHART_CTRL_ROWS = 2
def add_into_chart_container!(spec, page_id, chart_eid, ctrl_eid, grid_column)
  m = page_block(spec, page_id) or return nil
  ents = scan_top(m[2])
  host = ents.find { |t| t[:tag] == 'GridContainer' && t[:inner].to_s.include?(%(elementId="#{chart_eid}")) }
  return nil unless host
  c0, c1 = grid_column.to_s.scan(/\d+/).map(&:to_i)
  c0, c1 = 17, 25 if c0.nil? || c1.nil? || c1 <= c0
  kids_shifted = shift_top_rows(host[:inner].to_s, 1, CHART_CTRL_ROWS)
  entry = SigmaLayout.le(ctrl_eid, c0, c1, 1, 1 + CHART_CTRL_ROWS)
  new_head = set_rows(m[2][host[:s]...host[:head_e]], host[:r0], host[:r1] + CHART_CTRL_ROWS)
  new_host = "#{new_head}#{entry}\n#{kids_shifted}\n</GridContainer>"
  inner = m[2].dup
  inner[host[:s]...host[:e]] = new_host
  inner = shift_below!(inner, host[:eid], host[:r1], CHART_CTRL_ROWS)
  replace_page_inner!(spec, page_id, inner)
  true
end

# Band routing per added element kind.
def place_added_element!(spec, page, el, hint)
  grid_column = hint && hint['grid_column']
  height = hint && hint['height']
  case el['kind']
  when 'control'
    band = ensure_band!(spec, page, CTRL_BAND_PREFIX)
    band_add!(spec, page['id'], band, el['id'], grid_column || '1 / 9', height || BAND_ROWS[CTRL_BAND_PREFIX])
  when 'kpi-chart'
    band = ensure_band!(spec, page, KPI_BAND_PREFIX)
    band_add!(spec, page['id'], band, el['id'], grid_column || '1 / 13', height || BAND_ROWS[KPI_BAND_PREFIX])
  when 'text'
    band = ensure_band!(spec, page, NOTE_BAND_PREFIX)
    band_add!(spec, page['id'], band, el['id'], grid_column || '1 / 25', height || BAND_ROWS[NOTE_BAND_PREFIX])
  else
    band = ensure_band!(spec, page, KPI_BAND_PREFIX)
    band_add!(spec, page['id'], band, el['id'], grid_column || '1 / 25', height || BAND_ROWS[KPI_BAND_PREFIX])
  end
end

def find_element(spec, element_id)
  (spec['pages'] || []).each do |p|
    (p['elements'] || []).each { |e| return [p, e] if e['id'] == element_id }
  end
  nil
end

# Apply one candidate's patch to a working spec (in place). Returns a
# human-readable description, or raises with the reason it cannot apply.
def apply_patch!(spec, cand)
  patch = cand['patch']
  raise 'candidate has no machine patch (propose-in-UI only)' unless patch.is_a?(Hash)
  if patch['needs'] && (patch[patch['needs']].nil? || patch[patch['needs']].empty?)
    raise "patch needs '#{patch['needs']}' filled in before apply (see candidate.proposed)"
  end
  case patch['op']
  when 'add_elements'
    page = (spec['pages'] || []).find { |p| p['id'] == patch['page_id'] } ||
           (spec['pages'] || []).reject { |p| p['id'] == 'page-data' }.first
    raise 'target page not found' unless page
    hints = Array(patch['layout']).to_h { |l| [l['element_id'], l] }
    Array(patch['elements']).each do |el|
      raise "element id #{el['id']} already exists" if find_element(spec, el['id'])
      (page['elements'] ||= []) << el
      place_added_element!(spec, page, el, hints[el['id']])
    end
    "added #{Array(patch['elements']).size} element(s) into page #{page['id']}'s bands"
  when 'set_column_formula'
    _pg, el = find_element(spec, patch['element_id'])
    raise "element #{patch['element_id']} not found" unless el
    col = (el['columns'] || []).find { |c| c['id'] == patch['column_id'] }
    raise "column #{patch['column_id']} not found on #{patch['element_id']}" unless col
    col['formula'] = patch['formula']
    "set #{patch['element_id']}/#{patch['column_id']} formula"
  when 'rename_element'
    _pg, el = find_element(spec, patch['element_id'])
    raise "element #{patch['element_id']} not found" unless el
    el['name'] = patch['name']
    "renamed #{patch['element_id']} -> '#{patch['name']}'"
  when 'add_control_and_rewire'
    pg, el = find_element(spec, patch.dig('rewire', 'element_id'))
    raise "element #{patch.dig('rewire', 'element_id')} not found" unless el
    col = (el['columns'] || []).find { |c| c['id'] == patch.dig('rewire', 'column_id') }
    raise 'rewire column not found' unless col
    ctrl = patch['control']
    raise "control id #{ctrl['id']} already exists" if find_element(spec, ctrl['id'])
    (pg['elements'] ||= []) << ctrl
    col['formula'] = patch.dig('rewire', 'formula')
    # the switcher lives WITH the chart it drives: a slim row inside that
    # chart's container (falls back to the control band when uncontainered).
    hint = Array(patch['layout']).find { |l| l['element_id'] == ctrl['id'] } || {}
    placed = add_into_chart_container!(spec, pg['id'], el['id'], ctrl['id'], hint['grid_column'])
    unless placed
      band = ensure_band!(spec, pg, CTRL_BAND_PREFIX)
      band_add!(spec, pg['id'], band, ctrl['id'], hint['grid_column'] || '17 / 25', hint['height'] || 3)
    end
    "added control #{ctrl['controlId']} #{placed ? "inside #{el['id']}'s container" : 'to the control band'} + rewired #{el['id']}"
  when 'set_element_prop'
    _pg, el = find_element(spec, patch['element_id'])
    raise "element #{patch['element_id']} not found" unless el
    el[patch['prop']] = patch['value']
    "set #{patch['element_id']}.#{patch['prop']}"
  when 'replace_with_point_map'
    pg, el = find_element(spec, patch['element_id'])
    raise "element #{patch['element_id']} not found" unless el
    geo = patch['geo_column']
    cents = patch['centroids'] || {}
    raise 'centroids empty' if cents.empty?
    sw = lambda do |idx, default|
      args = cents.flat_map { |val, ll| ["\"#{val}\"", ll[idx].to_s] }.join(', ')
      "Switch([#{geo}], #{args}, #{default})"
    end
    geo_ref = patch['geo_ref'] ||
              (el['columns'] || []).map { |c| c['formula'] }.find { |f| f.to_s =~ /\/#{Regexp.escape(geo)}\]\z/ }
    raise 'cannot resolve a geo column reference' unless geo_ref
    map_el = {
      'id' => "map-phasee-#{el['id']}"[0, 40], 'kind' => 'point-map',
      'source' => el['source'],
      'columns' => [
        { 'id' => 'map-phasee-geo', 'formula' => geo_ref, 'name' => geo },
        { 'id' => 'map-phasee-lat', 'formula' => sw.call(0, '39'), 'name' => 'Lat' },
        { 'id' => 'map-phasee-lng', 'formula' => sw.call(1, '-98'), 'name' => 'Long' },
        { 'id' => 'map-phasee-val', 'formula' => patch['value_formula'],
          'name' => patch['value_name'] || 'Value' }
      ],
      'latitude' => { 'id' => 'map-phasee-lat' }, 'longitude' => { 'id' => 'map-phasee-lng' },
      'size' => { 'id' => 'map-phasee-val' },
      'color' => { 'by' => 'category', 'column' => 'map-phasee-geo' },
      'name' => "#{el['name']} (map restored)"
    }
    pg['elements'].delete(el)
    pg['elements'] << map_el
    spec['layout'] = spec['layout'].to_s.gsub(/elementId="#{Regexp.escape(el['id'])}"/,
                                              %(elementId="#{map_el['id']}"))
    "replaced #{el['id']} with point-map #{map_el['id']}"
  else
    raise "unknown patch op #{patch['op'].inspect}"
  end
end

# Element ids a candidate touches (so probes only use UNTOUCHED elements).
def touched_ids(cand)
  p = cand['patch'] || {}
  ids = [p['element_id'], p.dig('rewire', 'element_id')]
  ids += Array(p['elements']).map { |e| e['id'] }
  ids += [p['control'] && p['control']['id']]
  ids.compact.uniq
end

# ---------------------------------------------------------------------------
# 1. CLONE — the 1:1 parity artifact is never touched.
# ---------------------------------------------------------------------------
orig_meta_before = Sigma.request(:get, "/v2/workbooks/#{ORIG_WB}")
orig_spec = Sigma.request(:get, "/v2/workbooks/#{ORIG_WB}/spec")
abort "FATAL: cannot read spec of #{ORIG_WB}" unless orig_spec.is_a?(Hash) && orig_spec['pages']
clone_name = opts[:name] || "#{orig_spec['name']} — Enhanced"

clone_spec = clean(orig_spec)
clone_spec['name'] = clone_name
post = lenient(Sigma.request(:post, '/v2/workbooks/spec',
                             body: JSON.generate(clone_spec), binary: true))
clone_id = post.is_a?(Hash) && (post['workbookId'] || post['id'])
abort "FATAL: clone POST returned no workbookId: #{post.inspect[0, 300]}" unless clone_id
puts "enhance-apply: clone '#{clone_name}' = #{clone_id} (original #{ORIG_WB} untouched)"

# ---------------------------------------------------------------------------
# 2. Pick probe elements (untouched by ANY accepted item) + baseline check.
# ---------------------------------------------------------------------------
all_touched = accepted.flat_map { |c| touched_ids(c) }
viz_kinds = %w[bar-chart line-chart area-chart pie-chart combo-chart scatter-chart kpi-chart table pivot-table]
probe_pool = (orig_spec['pages'] || []).reject { |p| p['id'] == 'page-data' }
                                       .flat_map { |p| p['elements'] || [] }
                                       .select { |e| viz_kinds.include?(e['kind']) }
                                       .reject { |e| all_touched.include?(e['id']) }
probes = probe_pool.first(opts[:probes]).map { |e| e['id'] }
abort 'FATAL: no untouched element available as a parity probe' if probes.empty?
puts "   parity probes (untouched elements): #{probes.join(', ')}"

# clone-vs-original at (near) the same instant: live-drift-proof comparison.
def probe_pair(clone_id, orig_id, probes)
  probes.to_h do |el|
    [el, { 'clone' => norm_rows(export_rows(clone_id, el)),
           'orig' => norm_rows(export_rows(orig_id, el)) }]
  end
end

def probe_diffs(pair)
  pair.reject { |_el, v| v['clone'] && v['orig'] && v['clone'] == v['orig'] }.keys
end

baseline = probe_pair(clone_id, ORIG_WB, probes)
bad = probe_diffs(baseline)
abort "FATAL: clone baseline already diverges from original on #{bad.join(', ')} — aborting before any change" if bad.any?
puts "   baseline: clone == original on #{probes.size}/#{probes.size} probe(s)"

# ---------------------------------------------------------------------------
# 3. Apply accepted items ONE AT A TIME with the parity-unchanged gate.
# ---------------------------------------------------------------------------
def put_spec(wb, spec)
  lenient(Sigma.request(:put, "/v2/workbooks/#{wb}/spec",
                        body: JSON.generate(spec), binary: true))
end

current = clean(Sigma.request(:get, "/v2/workbooks/#{clone_id}/spec"))

# Pre-container clone? (parity workbook built before banded layouts existed.)
# Regenerate a banded layout FIRST so every applied item has a container
# system to land in. Layout-only change — element data untouched, so the
# parity probes are unaffected by construction.
if ensure_banded!(current)
  put_spec(clone_id, current)
  current = clean(Sigma.request(:get, "/v2/workbooks/#{clone_id}/spec"))
  puts '   clone layout predates containers — regenerated banded layout (header + row bands)'
end

applied = []
reverted = []
gate_green = true

accepted.each do |cand|
  print "   [#{cand['id']}] "
  prev = JSON.parse(JSON.generate(current))
  begin
    desc = apply_patch!(current, cand)
  rescue StandardError => e
    skipped << { 'id' => cand['id'], 'risk' => cand['risk'], 'reason' => "not applied: #{e.message}" }
    current = prev
    puts "SKIP (#{e.message})"
    next
  end
  begin
    put_spec(clone_id, current)
  rescue StandardError => e
    current = prev
    (put_spec(clone_id, current) rescue nil) # restore server state if the PUT half-landed
    reverted << { 'id' => cand['id'], 'reason' => "PUT rejected: #{e.message.to_s.gsub(/\s+/, ' ')[0, 200]}" }
    puts 'REVERTED (PUT rejected)'
    next
  end
  # parity-unchanged gate: untouched probes, clone vs original, same instant.
  pair = probe_pair(clone_id, ORIG_WB, probes)
  diffs = probe_diffs(pair)
  if diffs.any?
    current = prev
    begin
      put_spec(clone_id, current)
      recheck = probe_diffs(probe_pair(clone_id, ORIG_WB, probes))
      gate_green &&= recheck.empty?
    rescue StandardError
      gate_green = false
    end
    reverted << { 'id' => cand['id'],
                  'reason' => "parity-unchanged gate: untouched element(s) #{diffs.join(', ')} shifted vs original" }
    puts "REVERTED (probes shifted: #{diffs.join(', ')})"
  else
    applied << { 'id' => cand['id'], 'category' => cand['category'], 'change' => desc,
                 'evidence' => cand['evidence'] }
    puts "APPLIED (#{desc}; #{probes.size} probe(s) unchanged)"
  end
end

# ---------------------------------------------------------------------------
# 4. Finalize: layout lint (hard) + re-read the live layout + final report.
# ---------------------------------------------------------------------------
# Layout-quality lint (shared lib/layout_lint.rb, vendored byte-identical):
# raw-id display names / controls outside containers / dead zones. The clone
# must lint CLEAN — a parity-green visual mess is exactly the regression this
# phase exists to prevent.
require 'layout_lint'
live_spec = clean(Sigma.request(:get, "/v2/workbooks/#{clone_id}/spec"))
lint_violations = LayoutLint.lint(live_spec)
if lint_violations.any?
  warn "enhance-apply FINALIZE FAIL — layout lint: #{lint_violations.size} violation(s) on the clone:"
  lint_violations.each { |v| warn "  - #{v}" }
end

final_pair = probe_pair(clone_id, ORIG_WB, probes)
final_ok = probe_diffs(final_pair).empty?
gate_green &&= final_ok
orig_meta_after = Sigma.request(:get, "/v2/workbooks/#{ORIG_WB}")
orig_untouched = orig_meta_before['updatedAt'] == orig_meta_after['updatedAt']

report = {
  'workbook_id' => ORIG_WB,
  'workbook_name' => orig_spec['name'],
  'clone_id' => clone_id,
  'clone_name' => clone_name,
  'clone_url' => (lenient(post) || {})['url'],
  'accepted' => accepted_ids,
  'applied' => applied,
  'skipped' => skipped,
  'reverted' => reverted,
  'descoped_notes' => enh['descoped_notes'] || [],
  'parity_unchanged_gate' => {
    'probe_elements' => probes,
    'method' => 'clone-vs-original simultaneous JSON exports (live-drift-proof), after every item',
    'green' => gate_green
  },
  'layout_lint' => {
    'violations' => lint_violations,
    'green' => lint_violations.empty?
  },
  'original_untouched' => {
    'updatedAt_before' => orig_meta_before['updatedAt'],
    'updatedAt_after' => orig_meta_after['updatedAt'],
    'unchanged' => orig_untouched
  },
  'finished_at' => Time.now.utc.iso8601
}
File.write(OUT, JSON.pretty_generate(report))

puts
puts "enhance-apply: #{applied.size} applied, #{skipped.size} skipped, #{reverted.size} reverted"
puts "   clone: '#{clone_name}' (#{clone_id})"
puts "   parity-unchanged gate: #{gate_green ? 'GREEN' : 'NOT GREEN (see report)'}; original untouched: #{orig_untouched}"
puts "   layout lint: #{lint_violations.empty? ? 'CLEAN' : "#{lint_violations.size} violation(s) — FIX BEFORE DECLARING DONE"}"
puts "   report -> #{OUT}"
puts
puts '──────────────── HARD SCREENSHOT CHECKLIST (Phase E finalize) ────────────────'
puts 'The lint is mechanical; YOUR EYES are the last gate. Export the FULL-PAGE PNG'
puts "of the clone (scripts/sigma-export-png.py --workbook #{clone_id}) and verify"
puts 'EVERY item — list each with pass/fail in your report:'
puts '  [ ] every chart/control title is human-readable (no raw element ids)'
puts '  [ ] the page has a header band (dark, full-width, page title)'
puts '  [ ] selection controls sit together in a control band near the top'
puts '  [ ] every control is adjacent to / inside the container of what it filters'
puts '      (grain/drill switchers INSIDE their chart\'s container)'
puts '  [ ] no orphan elements below the fold (nothing dumped at the page foot)'
puts '  [ ] no dead zones; row heights look even across each band'
puts '──────────────────────────────────────────────────────────────────────────────'
exit(lint_violations.any? ? 4 : (gate_green ? 0 : 3))
