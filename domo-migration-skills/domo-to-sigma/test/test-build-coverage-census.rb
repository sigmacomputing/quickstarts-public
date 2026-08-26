#!/usr/bin/env ruby
# Offline contracts for build-coverage-census.rb.
require 'json'
require 'tmpdir'
require 'open3'

SCRIPT = File.expand_path('../scripts/build-coverage-census.rb', __dir__)

$failures = 0
def eq(actual, expected, message)
  if actual == expected
    puts "  ok: #{message}"
  else
    $failures += 1
    puts "  FAIL: #{message}\n    exp #{expected.inspect}\n    got #{actual.inspect}"
  end
end

def run_census(spec)
  Dir.mktmpdir do |dir|
    discovery = File.join(dir, 'discovery')
    Dir.mkdir(discovery)
    File.write(File.join(discovery, 'cards.json'),
               JSON.generate([{ 'id' => 825_387_640, 'title' => 'Midwest' }]))
    File.write(File.join(dir, 'workbook-spec.json'), JSON.generate(spec))
    _out, err, status = Open3.capture3('ruby', SCRIPT, '--workdir', dir)
    census = JSON.parse(File.read(File.join(dir, 'coverage.json')))
    yield(status.exitstatus, err, census)
  end
end

element = { 'id' => 'el-825387640', 'kind' => 'bar-chart',
            'columns' => [{ 'id' => 'm-v', 'name' => 'Value' }] }

puts '== released flat workbook code =='
released = {
  'name' => 'WB',
  'document' => {
    'schemaVersion' => 1, 'kind' => 'workbook',
    'pages' => [{ 'id' => 'page-1', 'name' => 'Overview' }],
    'elements' => [element],
  },
}
run_census(released) do |exit_code, _err, census|
  eq(exit_code, 0, 'census exits 0')
  eq(census['cards_built'], 1, 'document-global element matches its source card')
  eq(census['cards_dropped'], 0, 'no false dropped-card scope cut')
end

puts '== legacy page-nested compatibility =='
legacy = {
  'name' => 'WB', 'kind' => 'workbook',
  'pages' => [{ 'id' => 'page-1', 'name' => 'Overview', 'elements' => [element] }],
}
run_census(legacy) do |exit_code, _err, census|
  eq(exit_code, 0, 'legacy census exits 0')
  eq(census['cards_built'], 1, 'legacy pages[].elements still works')
  eq(census['cards_dropped'], 0, 'legacy shape remains complete')
end

puts
if $failures.zero?
  puts 'ALL PASS'
  exit 0
else
  puts "#{$failures} FAILURE(S)"
  exit 1
end
