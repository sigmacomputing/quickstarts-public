#!/usr/bin/env ruby
# End-to-end (offline): migrate-domo.rb's --offline mode against the scrubbed
# synthetic fixture at test/fixtures/domo-estate/ (pages.json + cards.json —
# 2x2 grid geometry: a KPI card and a bar chart share a row at distinct x_pct,
# an image card ("Logo", referencing the synthetic png/cards/img1.png) sits to
# their right, and a table card sits in the row below). Exercises the real
# subprocess entrypoint (like test-e2e.rb / test-build-domo-layout.rb), not
# just individual functions, so this proves the phase chain actually composes:
#   seed discovery -> build-workbook -> build-workbook-spec[offline-local] ->
#   build-domo-layout -> build-dashboard-layout -> put-layout[offline-local]
#
#   ruby test/test-migrate-domo.rb

require 'json'
require 'tmpdir'

SKILL   = File.expand_path('..', __dir__)
SCRIPTS = File.join(SKILL, 'scripts')
FIXTURE = File.join(__dir__, 'fixtures', 'domo-estate')

$failures = 0
def ok(c, m) if c then puts "  ok: #{m}" else $failures += 1; puts "  FAIL: #{m}" end end
def eq(actual, expected, msg)
  if actual == expected
    puts "  ok: #{msg}"
  else
    $failures += 1
    puts "  FAIL: #{msg}\n        expected #{expected.inspect}\n        got      #{actual.inspect}"
  end
end

# Sanity: the fixture itself must actually carry a KPI card, an image card
# referencing the synthetic logo, and multi-column (not single-column) x
# geometry — otherwise the assertions below would be vacuous.
cards = JSON.parse(File.read(File.join(FIXTURE, 'cards.json')))
ok(cards.any? { |c| c['sigmaKindHint'] == 'kpi-chart' }, 'sanity: fixture cards.json includes a KPI card')
ok(cards.any? { |c| c['chartType'].to_s == 'image' }, 'sanity: fixture cards.json includes an image card')
ok(File.exist?(File.join(FIXTURE, 'png', 'cards', 'img1.png')), 'sanity: fixture stages png/cards/img1.png for the image card')
ok(cards.map { |c| c['x'] }.uniq.size >= 3, 'sanity: fixture geometry spans >= 3 distinct x values (a real 2D layout, not a stack)')
ok(cards.any? { |c| c['limit'].to_i.positive? }, 'sanity: fixture cards.json includes a card with a row limit (bead 2ef7)')
ok(cards.any? { |c| c['datasetId'] == 'ds-dim' }, 'sanity: fixture cards.json includes a card bound to a non-dominant DataSet (bead ziht)')
ok(cards.any? { |c| c['summaryNumber'] && !Array(c['groupBy']).empty? },
   'sanity: fixture cards.json includes a non-Rule-0 card (real grouping) that ALSO carries a summaryNumber (bead 08sf)')
ok(File.exist?(File.join(FIXTURE, 'dm-spec.json')), 'sanity: fixture stages dm-spec.json (build-dm.rb pre-post shape) for the ds-dim sub-master')
ok(File.exist?(File.join(FIXTURE, 'dm-ids.json')), 'sanity: fixture stages dm-ids.json (synthesized post-and-readback) for the ds-dim sub-master')

Dir.mktmpdir('migrate-domo-e2e') do |out_dir|
  cmd = ['ruby', File.join(SCRIPTS, 'migrate-domo.rb'), '--offline', FIXTURE, '--out', out_dir]
  output = IO.popen(cmd, err: [:child, :out], &:read)
  status = $?.success?
  ok(status, "migrate-domo.rb --offline exits 0\n#{output unless status}")

  # ---- run-state.json: every named phase accounted for (done or skip, never
  # silently missing) ----------------------------------------------------
  run_state_path = File.join(out_dir, 'run-state.json')
  ok(File.exist?(run_state_path), 'wrote run-state.json')
  run_state = JSON.parse(File.read(run_state_path))
  required_phases = %w[discover capture-visuals convert-beast-modes build-workbook
                       build-workbook-spec post-and-readback build-domo-layout
                       build-dashboard-layout put-layout layout-2d-flag
                       verify-parity assert-phase6-ran]
  missing = required_phases.reject { |p| run_state['phases'].key?(p) }
  ok(missing.empty?, "run-state.json accounts for every phase in the chain (missing: #{missing.join(', ')})")
  eq(run_state['mode'], 'offline', 'run-state.json records mode=offline')

  # ---- (a) layout-2d.flag == 'grid' (NOT 'stack') ------------------------
  flag_path = File.join(out_dir, 'layout-2d.flag')
  ok(File.exist?(flag_path), 'wrote layout-2d.flag')
  flag = File.read(flag_path).strip
  eq(flag, 'grid', "layout-2d.flag is 'grid' (fixture has >= 2 zones at distinct x within a row) — NOT 'stack'")

  # ---- workbook-spec.json assembled with the layout merged in ------------
  spec_path = File.join(out_dir, 'workbook-spec.json')
  ok(File.exist?(spec_path), 'wrote workbook-spec.json')
  spec = JSON.parse(File.read(spec_path))
  all_elements = spec['pages'].flat_map { |p| p['elements'] || [] }
  ok(spec['layout'].is_a?(String) && spec['layout'].include?('<Page'), 'workbook-spec.json has a merged <Page> layout XML (put-layout offline step ran)')

  # ---- (b) an inline data-URI image element ------------------------------
  image_el = all_elements.find { |e| e['kind'] == 'image' }
  ok(image_el, 'workbook-spec.json contains an image-kind element')
  if image_el
    ok(image_el['url'].to_s.start_with?('data:image/png;base64,'),
       "image element's url is an inline data-URI (data:image/png;base64,...), got #{image_el['url'].to_s[0, 40].inspect}")
    b64 = image_el['url'].to_s.sub('data:image/png;base64,', '')
    ok(!b64.strip.empty?, 'image data-URI carries non-empty base64 payload')
  end

  # ---- (c) the KPI element's formula is <Agg>([Master/...]) -------------
  kpi_el = all_elements.find { |e| e['kind'] == 'kpi-chart' }
  ok(kpi_el, 'workbook-spec.json contains a kpi-chart element')
  if kpi_el
    formula = kpi_el.dig('columns', 0, 'formula').to_s
    ok(formula =~ /\A(Sum|Avg|Count|CountDistinct|Min|Max)\(\[Master\/[^\]]+\]\)\z/,
       "KPI formula is <Agg>([Master/...]) — got #{formula.inspect}")
    ok(kpi_el.dig('value', 'columnId') == kpi_el.dig('columns', 0, 'id'), 'KPI value binds via value.columnId (not id)')
  end

  # ---- (d) bead 2ef7: card['limit'] -> an element-level top-n filter -----
  topn_el = all_elements.find { |e| e.dig('filters', 0, 'kind') == 'top-n' }
  ok(topn_el, 'workbook-spec.json contains an element with a top-n filter (bead 2ef7)')
  if topn_el
    eq(topn_el.dig('filters', 0, 'rowCount'), 10, "top-n filter's rowCount matches the card's limit (10)")
  end

  # ---- (e) bead ziht: a card on a non-dominant DataSet (ds-dim) routes to --
  # its own hidden sub-master (master-<dataset>), not the shared master, and
  # that sub-master element appears exactly once under the Data page.
  data_page = spec['pages'].find { |p| p['id'] == 'page-data' || p['name'] == 'Data' }
  ok(data_page, 'workbook-spec.json has a Data page')
  submaster_el = all_elements.find { |e| e.dig('source', 'elementId').to_s.start_with?('master-') }
  ok(submaster_el, "workbook-spec.json contains an element sourced from a per-dataset sub-master " \
                   "(bead ziht) — got source #{submaster_el && submaster_el['source']}")
  if submaster_el && data_page
    sm_id = submaster_el.dig('source', 'elementId')
    on_data_page = Array(data_page['elements']).select { |e| e['id'] == sm_id }
    eq(on_data_page.size, 1, "the sub-master '#{sm_id}' appears exactly once under the Data page")
  end

  # ---- (f) bead 08sf: a companion kpi-chart element for a card whose ------
  # Summary Number is NOT the whole card (i.e. not a Rule-0 KPI card).
  kpi_els = all_elements.select { |e| e['kind'] == 'kpi-chart' }
  rule0_kpi_cards = cards.count do |c|
    c['sigmaKindHint'] == 'kpi-chart' ||
      (c['summaryNumber'] && Array(c['groupBy']).empty? && (c['columns'] || []).size <= 1)
  end
  eq(kpi_els.size, rule0_kpi_cards + 1,
     "kpi-chart element count (#{kpi_els.size}) is one more than the #{rule0_kpi_cards} genuine Rule-0 " \
     'KPI card(s) — a companion KPI was emitted for the non-KPI card carrying a summaryNumber (bead 08sf)')

  # Tightened per the final review (I2): a bare count bump could silently
  # absorb an unrelated spurious KPI from a different bug. Assert the
  # SPECIFIC companion element (id ends '-summary') is present, not just that
  # the total moved by one.
  companion_el = kpi_els.find { |e| e['id'].to_s.end_with?('-summary') }
  ok(companion_el, "workbook-spec.json contains the SPECIFIC companion KPI element (id ending " \
                   "'-summary'), not just an incidental kpi-chart count bump (bead 08sf)")

  # ---- (g) final review Important I1/I2: the companion KPI element's id ---
  # must appear in the MERGED <Page> layout XML, not just the element tree —
  # otherwise it is present in the spec but never actually rendered on the
  # migrated page (exactly what I1 found: build-domo-layout.rb derived zones
  # from cards.json, and a companion's "-summary" id matches no card). Fixed
  # via build-domo-layout.rb's load_chart_specs_companions + a
  # pseudo-card synthesis, mirroring the pre-existing orphan-control pattern
  # (see build-domo-layout.rb) — confirm it landed by checking the companion's
  # own element id shows up as a LayoutElement's elementId= attribute.
  if companion_el
    ok(spec['layout'].to_s.include?(%(elementId="#{companion_el['id']}")),
       "the companion KPI element '#{companion_el['id']}' has its OWN LayoutElement zone in the " \
       'merged layout XML — it is placed on the page, not just present in the element tree (I1 fix)')
  end

  # ---- idempotency: a second run with no --force is a no-op (all skip) --
  cmd2 = ['ruby', File.join(SCRIPTS, 'migrate-domo.rb'), '--offline', FIXTURE, '--out', out_dir]
  output2 = IO.popen(cmd2, err: [:child, :out], &:read)
  ok($?.success?, "re-run without --force exits 0\n#{output2 unless $?.success?}")
  rerun_state = JSON.parse(File.read(run_state_path))
  built_phases = %w[build-workbook build-workbook-spec build-domo-layout build-dashboard-layout put-layout]
  ok(built_phases.all? { |p| rerun_state['phases'][p]['status'] == 'skip' },
     'idempotent re-run (no --force) skips every previously-built phase')

  # ---- --force rebuilds (still lands on the same, deterministic flag) ---
  cmd3 = ['ruby', File.join(SCRIPTS, 'migrate-domo.rb'), '--offline', FIXTURE, '--out', out_dir, '--force']
  output3 = IO.popen(cmd3, err: [:child, :out], &:read)
  ok($?.success?, "--force re-run exits 0\n#{output3 unless $?.success?}")
  forced_state = JSON.parse(File.read(run_state_path))
  ok(built_phases.all? { |p| forced_state['phases'][p]['status'] == 'done' }, '--force rebuilds every phase (status done, not skip)')
  eq(File.read(flag_path).strip, 'grid', '--force re-run recomputes the same grid flag')
end

# ---- fail-fast: a fixture missing cards.json aborts loudly, non-zero ------
Dir.mktmpdir('migrate-domo-badfixture') do |bad_fixture|
  Dir.mktmpdir('migrate-domo-badout') do |out_dir|
    File.write(File.join(bad_fixture, 'pages.json'), '[]') # cards.json deliberately absent
    cmd = ['ruby', File.join(SCRIPTS, 'migrate-domo.rb'), '--offline', bad_fixture, '--out', out_dir]
    output = IO.popen(cmd, err: [:child, :out], &:read)
    ok(!$?.success?, 'a fixture missing cards.json fails fast (non-zero exit), not a silent partial run')
    ok(output.include?('cards.json'), 'the failure message names the missing file')
  end
end

puts
if $failures.zero? then puts "ALL PASS"; exit 0 else puts "#{$failures} FAILURE(S)"; exit 1 end
