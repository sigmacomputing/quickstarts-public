#!/usr/bin/env ruby
# frozen_string_literal: true
#
# enhance-select.rb — Phase E (opt-in) shared engine, part 1.5 of 3: SELECT.
#
# Turns a human's answer to the Phase E design interview into a durable,
# auditable artifact (enhance-selection.json) and the exact candidate-id list
# that enhance-apply.rb's accept-only contract expects.
#
# Why this exists: scan emits `app_options` (user-meaningful app shapes) plus
# `candidates` (individual patches). Before this script the agent had to
# translate an interview answer into a --enhance-accept CLI string by hand,
# which left no record of WHAT was offered, what was chosen, or what was
# declined. That record is the difference between "an agent changed things"
# and "a human approved these changes".
#
# This script NEVER writes to Sigma and never applies anything — it only
# records a decision. Application stays enhance-apply.rb's job, still gated on
# explicit acceptance.
#
# Usage:
#   ruby scripts/enhance-select.rb --enhancements <workdir>/enhancements.json \
#     --option <app-option-id> [--also id1,id2] [--confirm-medium id1,id2] \
#     [--out <workdir>/enhance-selection.json]
#
#   --option           an id from enhancements.json app_options[] (repeatable)
#   --also             extra candidate ids to include beyond the option's set
#   --confirm-medium   medium-risk candidate ids the human explicitly confirmed
#   --print-accept     print just the resolved --enhance-accept value and exit
#
# Exit codes: 0 ok · 2 usage/not-found · 3 nothing selected

require 'json'
require 'optparse'
require 'time'

options = { option: [], also: [], confirm_medium: [] }
parser = OptionParser.new do |o|
  o.on('--enhancements PATH') { |v| options[:enhancements] = v }
  o.on('--option ID') { |v| options[:option] << v }
  o.on('--also LIST') { |v| options[:also].concat(v.split(',').map(&:strip).reject(&:empty?)) }
  o.on('--confirm-medium LIST') { |v| options[:confirm_medium].concat(v.split(',').map(&:strip).reject(&:empty?)) }
  o.on('--out PATH') { |v| options[:out] = v }
  o.on('--print-accept') { options[:print_accept] = true }
end
parser.parse!

def die(msg, code = 2)
  warn "enhance-select: #{msg}"
  exit code
end

die("--enhancements is required\n#{parser}") unless options[:enhancements]
die("no such file: #{options[:enhancements]}") unless File.exist?(options[:enhancements])
die('at least one --option is required (use option-parity-only to decline)') if options[:option].empty?

scan = JSON.parse(File.read(options[:enhancements]))
app_options = scan['app_options'] || []
die('enhancements.json has no app_options[] — regenerate it with a current enhance-scan.rb', 2) if app_options.empty?

by_id = app_options.each_with_object({}) { |o, h| h[o['id']] = o }
unknown = options[:option].reject { |id| by_id.key?(id) }
die("unknown --option id(s): #{unknown.join(', ')} (available: #{by_id.keys.join(', ')})") unless unknown.empty?

candidates_by_id = (scan['candidates'] || []).each_with_object({}) { |c, h| h[c['id']] = c }
bad_also = options[:also].reject { |id| candidates_by_id.key?(id) }
die("unknown --also candidate id(s): #{bad_also.join(', ')}") unless bad_also.empty?

selected = options[:option].flat_map { |id| by_id[id]['candidate_ids'] || [] }
accepted = (selected + options[:also]).uniq

# Medium-risk work needs a named human confirmation, not a bulk opt-in. Anything
# medium that was not explicitly confirmed is dropped and reported, so a
# too-broad option choice can never quietly apply a risky rewrite.
medium = accepted.select { |id| candidates_by_id.dig(id, 'risk') == 'medium' }
unconfirmed = medium - options[:confirm_medium]
accepted -= unconfirmed

# An option with a requires[] (e.g. a write connection) cannot be executed by
# enhance-apply; surface it as follow-up work rather than pretending it applied.
blocked = options[:option].map { |id| by_id[id] }
                          .reject { |o| (o['requires'] || []).empty? }
                          .map { |o| { 'option_id' => o['id'], 'requires' => o['requires'], 'manual_refs' => o['manual_refs'] || [] } }

if options[:print_accept]
  puts accepted.join(',')
  exit(accepted.empty? ? 3 : 0)
end

out_path = options[:out] || File.join(File.dirname(options[:enhancements]), 'enhance-selection.json')
selection = {
  'schemaVersion' => 1,
  'workbook_id' => scan['workbook_id'],
  'recorded_at' => Time.now.utc.iso8601,
  'selected_option_ids' => options[:option],
  'declined_option_ids' => by_id.keys - options[:option],
  'accepted_candidate_ids' => accepted,
  'dropped_unconfirmed_medium' => unconfirmed,
  'manual_followups' => blocked,
  'enhance_accept_value' => accepted.join(',')
}
File.write(out_path, JSON.pretty_generate(selection))

puts "enhance-select: recorded #{options[:option].join(', ')} -> #{out_path}"
puts "  accepted #{accepted.size} candidate(s): #{accepted.empty? ? '(none)' : accepted.join(', ')}"
unless unconfirmed.empty?
  puts "  DROPPED #{unconfirmed.size} unconfirmed medium-risk item(s): #{unconfirmed.join(', ')}"
  puts '    re-run with --confirm-medium <ids> only after the human confirms each one.'
end
blocked.each do |b|
  puts "  MANUAL follow-up for #{b['option_id']}: needs #{b['requires'].join(', ')}"
  b['manual_refs'].each { |r| puts "    see #{r}" }
end
puts '  next: ruby scripts/migrate-tableau.rb --finalize --enhance ' \
     "--enhance-accept #{accepted.empty? ? '<none — nothing to apply>' : accepted.join(',')}"
exit(0)
