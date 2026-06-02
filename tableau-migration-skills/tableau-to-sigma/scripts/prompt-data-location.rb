#!/usr/bin/env ruby
# Ask the user how Claude should identify the warehouse tables for this
# conversion. Three modes:
#   user-provided   — user types connection / database / schema
#   auto-search     — user authorizes Claude to call Sigma catalog search
#   probe-fallback  — user opts into brute-force probing across connections
#
# Runs after URL resolution and BEFORE any catalog lookup. Per SKILL.md
# Phase 0c, downstream phases must read the resulting data-location.json
# and respect the chosen mode — no silent catalog calls before the user
# has answered.
#
# Usage:
#   ruby scripts/prompt-data-location.rb --workdir /tmp/<slug>
#   ruby scripts/prompt-data-location.rb --workdir /tmp/<slug> --force

require 'json'
require 'time'
require 'optparse'

opts = {}
OptionParser.new do |p|
  p.on('--workdir DIR', 'Output directory (required)') { |v| opts[:workdir] = v }
  p.on('--force', 'Overwrite an existing data-location.json without asking') { opts[:force] = true }
end.parse!

abort "Missing --workdir"                              unless opts[:workdir]
abort "Workdir does not exist: #{opts[:workdir]}"      unless Dir.exist?(opts[:workdir])

out_path = File.join(opts[:workdir], 'data-location.json')

if File.exist?(out_path) && !opts[:force]
  existing = JSON.parse(File.read(out_path))
  puts "data-location.json already exists at #{out_path} (mode: #{existing['mode']})."
  if existing['mode'] == 'user-provided'
    puts "  Connection: #{existing['connection_name']}"
    puts "  Database:   #{existing['database']}"
    puts "  Schema:     #{existing['schema']}"
  end
  print "Reuse it? [Y/n] "
  answer = $stdin.gets.chomp.downcase
  if answer.empty? || answer == 'y' || answer == 'yes'
    puts "Reusing existing data-location.json."
    exit 0
  end
end

puts "Sigma warehouse location for the source data"
puts
puts "How should Claude identify the warehouse tables for this conversion?"
puts "  1. I'll provide the connection name, database, and schema."
puts "  2. Let Claude search my Sigma org's catalog for matching tables."
puts "  3. Skip — Claude will brute-force probe every Sigma connection (slowest path)."
puts
print "Choice [1/2/3, default 1]: "
choice = $stdin.gets.chomp
choice = '1' if choice.empty?

case choice
when '1'
  print "Connection name (as it appears in Sigma's Administration > Connections): "
  connection_name = $stdin.gets.chomp
  print "Database: "
  database = $stdin.gets.chomp
  print "Schema: "
  schema = $stdin.gets.chomp

  if [connection_name, database, schema].any?(&:empty?)
    abort "All three values are required for option 1. Aborting without writing."
  end

  data = {
    'mode'            => 'user-provided',
    'connection_name' => connection_name,
    'database'        => database,
    'schema'          => schema,
    'captured_at'     => Time.now.utc.iso8601
  }
when '2'
  data = {
    'mode'        => 'auto-search',
    'captured_at' => Time.now.utc.iso8601
  }
  puts
  puts "Claude is authorized to call Sigma catalog search to find matching tables."
when '3'
  data = {
    'mode'        => 'probe-fallback',
    'captured_at' => Time.now.utc.iso8601
  }
  puts
  puts "Discovery will brute-force probe every Sigma connection. This is slow and triggers many bash-approval prompts."
else
  abort "Invalid choice: #{choice}. Aborting."
end

File.write(out_path, JSON.pretty_generate(data))
puts
puts "Wrote #{out_path}:"
JSON.pretty_generate(data).each_line { |l| puts "  #{l.chomp}" }
