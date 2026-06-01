#!/usr/bin/env ruby
# Smoke test for scripts/extract-calc-fields.rb.
#
# Runs the script against a known workbook (default: the dataflow site's
# "NHL 2022-2023 Season Stats" workbook — 112 calcs, 1 LOD) and asserts:
#   - exit 0
#   - n_calcs > 0
#   - source is one of: "metadata-api", "twb-xml-fallback"
#   - a known LOD formula round-trips intact (when present)
#
# Usage:
#   eval "$(scripts/get-tableau-token.sh)"
#   ruby scripts/test-calc-discovery.rb \
#     [--workbook-luid <luid>]     # default: NHL workbook
#     [--twb <path>]               # default: /tmp/assessment-dataflow/twbs/<luid>.twb
#     [--source auto|metadata|twb] # default: auto
#     [--min-calcs N]              # default: 1

require 'json'
require 'optparse'
require 'tempfile'

DEFAULT_LUID = 'a57eeaf7-ec89-45ab-bd25-162901af7e9e'

opts = {
  luid: DEFAULT_LUID,
  source: 'auto',
  min_calcs: 1
}
OptionParser.new do |p|
  p.on('--workbook-luid LUID')      { |v| opts[:luid] = v }
  p.on('--twb PATH')                { |v| opts[:twb] = v }
  p.on('--source {auto|metadata|twb}', %w[auto metadata twb]) { |v| opts[:source] = v }
  p.on('--min-calcs N', Integer)    { |v| opts[:min_calcs] = v }
end.parse!

opts[:twb] ||= "/tmp/assessment-dataflow/twbs/#{opts[:luid]}.twb"

script = File.expand_path('extract-calc-fields.rb', __dir__)
out_tmp = Tempfile.new(['calc-fields-', '.json'])
out_path = out_tmp.path
out_tmp.close

cmd = [
  'ruby', script,
  '--workbook-luid', opts[:luid],
  '--out', out_path,
  '--source', opts[:source],
  '--twb', opts[:twb],
  '--refresh'
]

warn "RUN: #{cmd.join(' ')}"
ok = system(*cmd, out: File::NULL)
unless ok
  warn "FAIL: extract-calc-fields.rb exited #{$?.exitstatus}"
  exit 1
end

result = JSON.parse(File.read(out_path))

errors = []
errors << "n_calcs (#{result['n_calcs']}) < min_calcs (#{opts[:min_calcs]})" \
  if result['n_calcs'].to_i < opts[:min_calcs]
unless %w[metadata-api twb-xml-fallback].include?(result['source'])
  errors << "unexpected source: #{result['source'].inspect}"
end

# If any LOD calcs exist, ensure their formula round-trips (still contains the
# FIXED/INCLUDE/EXCLUDE token).
lod_calcs = (result['calcs'] || []).select { |c| c['is_lod'] }
if lod_calcs.any?
  bad_lod = lod_calcs.find { |c| c['formula'] !~ /\{\s*(FIXED|INCLUDE|EXCLUDE)/i }
  errors << "LOD calc lost its FIXED/INCLUDE/EXCLUDE token: #{bad_lod['name'].inspect}" if bad_lod
end

if errors.any?
  warn "FAIL:"
  errors.each { |e| warn "  - #{e}" }
  exit 1
end

puts "OK — source=#{result['source']} n_calcs=#{result['n_calcs']} n_lods=#{result['n_lods']} n_sql=#{result['n_requires_custom_sql']}"
sample = (result['calcs'] || []).first(3).map { |c| "  #{c['name']}: #{c['formula'][0, 80]}" }
puts sample.join("\n") if sample.any?
exit 0
