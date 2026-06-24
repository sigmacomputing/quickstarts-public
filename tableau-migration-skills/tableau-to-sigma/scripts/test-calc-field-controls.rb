#!/usr/bin/env ruby
# Regression test for the calc-field control path — the parameter-switch
# dashboard class where the left-sidebar controls bind to CALCULATED fields
# (a role/team bucket, a cleaned rank) and parameters drive Switch() display
# logic. Before these fixes the auto-control builder silently skipped them:
#   - "shared filter has no resolvable column_caption (raw_param=…Calculation_…)"
#   - "parameter 'Switch Metric' … skipped (orphan parameter)"
#
# Deterministic + offline: synthesizes a minimal .twb and runs the ACTUAL
# parse-twb-layout.rb on it, then asserts the two parser fixes:
#   1. A filter bound to a calc field (`…[none:Calculation_<id>:nk]`) resolves a
#      real column_caption instead of nil (guid_from_param calc-id support).
#   2. A calc that references a parameter by its INTERNAL NAME
#      (`[Parameters].[Parameter 5]`) records the param's CAPTION ("Switch
#      Metric") in parameter_refs, so the builder's caption-based orphan check
#      no longer drops it.
#
# Usage:  ruby scripts/test-calc-field-controls.rb

require 'json'
require 'tmpdir'

DIR    = __dir__
PARSER = File.join(DIR, 'parse-twb-layout.rb')

fails = []
def check(cond, msg, fails)
  fails << msg unless cond
  puts "  #{cond ? 'PASS' : 'FAIL'}  #{msg}"
end

# Minimal .twb exercising both gaps. The calc field "Team" (id Calculation_558…)
# backs a shared-view quick filter; the parameter "Switch Metric" (internal name
# "Parameter 5") is referenced by a worksheet calc via [Parameters].[Parameter 5].
TWB = <<~XML
  <?xml version='1.0' encoding='utf-8' ?>
  <workbook>
    <datasources>
      <datasource caption='Sales' name='federated.x'>
        <column param-domain-type='list' caption='Switch Metric' name='[Parameter 5]' datatype='integer' value='1'>
          <members>
            <member value='1' />
            <member value='2' />
            <member value='3' />
          </members>
        </column>
        <column caption='Team' name='[Calculation_558946121845510144]' datatype='string' role='dimension'>
          <calculation class='tableau' formula='IF [Role] = &quot;AE&quot; THEN &quot;Strategic&quot; ELSE &quot;Regional&quot; END' />
        </column>
      </datasource>
    </datasources>
    <worksheets>
      <worksheet name='Summary'>
        <table>
          <view>
            <datasource-dependencies datasource='federated.x'>
              <column caption='Metric Display' name='[Calculation_990]' datatype='real' role='measure'>
                <calculation class='tableau' formula='IF [Parameters].[Parameter 5] = 1 THEN [Actuals] ELSE [CVR] END' />
              </column>
            </datasource-dependencies>
            <filter class='categorical' column='[federated.x].[none:Calculation_558946121845510144:nk]'>
              <groupfilter function='member' member='&quot;Strategic&quot;' />
            </filter>
          </view>
        </table>
      </worksheet>
    </worksheets>
    <shared-view name='sv1'>
      <filter class='categorical' column='[federated.x].[none:Calculation_558946121845510144:nk]'>
        <groupfilter function='member' member='&quot;Strategic&quot;' />
      </filter>
    </shared-view>
  </workbook>
XML

meta = nil
Dir.mktmpdir do |d|
  twb = File.join(d, 'wb.twb')
  out = File.join(d, 'layout.json')
  File.write(twb, TWB)
  ok = system('ruby', PARSER, twb, out, out: File::NULL, err: File::NULL)
  abort 'test bug: parse-twb-layout.rb exited non-zero on the fixture' unless ok
  # ARGV[1] receives the LAYOUT (dashboard/zone) array; the worksheets /
  # shared_filters / parameters meta is written to the derived `<out>-meta.json`.
  meta = JSON.parse(File.read(out.sub(/\.json$/, '-meta.json')))
end

# ---- Gap A: calc-field filter resolves a caption ---------------------------
sf = (meta['shared_filters'] || []).first
check(!sf.nil?, 'Gap A: shared filter parsed from <shared-view>', fails)
check(sf && sf['column_caption'] == 'Team',
      "Gap A: calc-field filter resolves column_caption 'Team' (got #{sf && sf['column_caption'].inspect})", fails)
check(sf && sf['column_guid'] == 'Calculation_558946121845510144',
      'Gap A: column_guid captures the Calculation_<id> token', fails)

# ---- Gap B: param referenced by internal name → caption in parameter_refs ---
calcs = meta.dig('worksheets', 'Summary', 'calculations') || []
mdisp = calcs.find { |c| c['caption'] == 'Metric Display' }
check(!mdisp.nil?, 'Gap B: worksheet calc "Metric Display" parsed', fails)
refs = mdisp ? (mdisp['parameter_refs'] || []) : []
check(refs.include?('Switch Metric'),
      "Gap B: parameter_refs normalizes [Parameters].[Parameter 5] → caption 'Switch Metric' (got #{refs.inspect})", fails)
check(!refs.include?('Parameter 5'),
      'Gap B: raw internal name "Parameter 5" not leaked into parameter_refs', fails)

puts
if fails.empty?
  puts 'ALL PASS — calc-field controls + param-by-name resolution intact'
  exit 0
else
  puts "FAILURES (#{fails.length}):"
  fails.each { |f| puts "  - #{f}" }
  exit 1
end
