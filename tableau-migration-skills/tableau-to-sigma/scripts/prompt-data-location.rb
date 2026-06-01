#!/usr/bin/env ruby
# Capture the Sigma warehouse location for the source data BEFORE discovery.
# Skips speculative connection probing later in the workflow — on orgs with
# many Sigma connections, brute-force probing becomes O(connections × paths)
# and frustrates users with bash-approval prompts.
#
# Usage:
#   ruby scripts/prompt-data-location.rb --workdir /tmp/<slug>
#   ruby scripts/prompt-data-location.rb --workdir /tmp/<slug> --force
#
# Writes: <workdir>/data-location.json
# Skips writing (and prints a note) if user declines on the first prompt.

require 'json'
require 'time'
require 'optparse'

opts = {}
OptionParser.new do |p|
  p.on('--workdir DIR', 'Output directory (required)') { |v| opts[:workdir] = v }
  p.on('--force', 'Overwrite an existing data-location.json without asking')   { opts[:force] = true }
end.parse!

abort "Missing --workdir"                              unless opts[:workdir]
abort "Workdir does not exist: #{opts[:workdir]}"      unless Dir.exist?(opts[:workdir])

out_path = File.join(opts[:workdir], 'data-location.json')

if File.exist?(out_path) && !opts[:force]
  existing = JSON.parse(File.read(out_path))
  puts "data-location.json already exists at #{out_path}:"
  puts "  Connection: #{existing['connection_name']}"
  puts "  Database:   #{existing['database']}"
  puts "  Schema:     #{existing['schema']}"
  puts
  print "Reuse it? [Y/n] "
  answer = $stdin.gets.chomp.downcase
  if answer.empty? || answer == 'y' || answer == 'yes'
    puts "Reusing existing data-location.json."
    exit 0
  end
end

puts "Sigma warehouse location for the source data"
puts "Provide the Sigma connection name and warehouse path where the source data lives."
puts "Press Enter on the first prompt to skip — discovery will fall back to probing all connections."
puts

print "Connection name (as it appears in Sigma's Administration > Connections, e.g. 'Snowflake East'): "
connection_name = $stdin.gets.chomp

if connection_name.empty?
  puts
  puts "Skipped. Discovery will probe Sigma connections to find the source tables."
  puts "On orgs with many connections this can be slow and triggers many bash-approval prompts —"
  puts "re-run this script later (--force to overwrite) if you want to skip the probe."
  exit 0
end

print "Database (e.g. 'QUICKSTARTS'): "
database = $stdin.gets.chomp

print "Schema (e.g. 'TABLEAU_SUPERSTORE'): "
schema = $stdin.gets.chomp

if [database, schema].any?(&:empty?)
  abort "Database and Schema are required when a connection name is provided. Aborting without writing."
end

data = {
  'connection_name' => connection_name,
  'database'        => database,
  'schema'          => schema,
  'captured_at'     => Time.now.utc.iso8601
}

File.write(out_path, JSON.pretty_generate(data))
puts
puts "Wrote #{out_path}:"
JSON.pretty_generate(data).each_line { |l| puts "  #{l.chomp}" }
puts
puts "Discovery scripts will resolve <connection_name> to a connection ID and use"
puts "<database>.<schema>.<table> for each Tableau-referenced table. No connection probing."
