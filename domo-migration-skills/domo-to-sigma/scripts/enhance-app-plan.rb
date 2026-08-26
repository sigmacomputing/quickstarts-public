#!/usr/bin/env ruby
# frozen_string_literal: true
#
# enhance-app-plan.rb — Phase E app architecture plan.
#
# Converts one selected app_options[] recommendation plus the user's
# architecture choices into app-plan.json. It does not write to Sigma.
#
# Usage:
#   ruby scripts/enhance-app-plan.rb \
#     --enhancements <workdir>/enhancements.json \
#     --option option-planning-writeback \
#     [--editable drivers|line-values|both|none] \
#     [--approval yes|no] [--scenarios yes|no] \
#     [--agent analyze|recommend|write-after-approval|none] \
#     [--unit-of-work TEXT] [--write-mode append|overwrite] \
#     --out <workdir>/app-plan.json

require 'json'
require 'optparse'
require 'time'

opts = {
  editable: nil,
  approval: nil,
  scenarios: nil,
  agent: nil,
  unit_of_work: nil,
  write_mode: nil
}
parser = OptionParser.new do |p|
  p.on('--enhancements PATH') { |v| opts[:enhancements] = v }
  p.on('--option ID') { |v| opts[:option] = v }
  p.on('--editable MODE') { |v| opts[:editable] = v }
  p.on('--approval BOOL') { |v| opts[:approval] = v }
  p.on('--scenarios BOOL') { |v| opts[:scenarios] = v }
  p.on('--agent MODE') { |v| opts[:agent] = v }
  p.on('--unit-of-work TEXT') { |v| opts[:unit_of_work] = v }
  p.on('--write-mode MODE') { |v| opts[:write_mode] = v }
  p.on('--out PATH') { |v| opts[:out] = v }
end
parser.parse!

def die(msg)
  warn "enhance-app-plan: #{msg}"
  exit 2
end

def bool(value, default)
  return default if value.nil?
  return true if %w[yes true 1].include?(value.to_s.downcase)
  return false if %w[no false 0].include?(value.to_s.downcase)
  die("expected yes|no, got #{value.inspect}")
end

%i[enhancements option].each do |key|
  die("--#{key.to_s.tr('_', '-')} is required") unless opts[key]
end
die("no such file: #{opts[:enhancements]}") unless
  File.exist?(opts[:enhancements])

doc = JSON.parse(File.read(opts[:enhancements]))
option = (doc['app_options'] || []).find { |o| o['id'] == opts[:option] }
die("unknown option #{opts[:option].inspect}") unless option
die("#{opts[:option]} is not an app archetype") unless option['archetype']

defaults = {
  'scenario-planning' => {
    editable: 'both', scenarios: true, approval: true,
    agent: 'recommend', grain: %w[Scenario Period Planning\ Line],
    editable_columns: ['Method', 'Uplift %', 'Dollar Change', 'New Amount',
                       'Rationale']
  },
  'allocation-capacity' => {
    editable: 'line-values', scenarios: false, approval: true,
    agent: 'recommend', grain: ['Period', 'Allocation Dimension'],
    editable_columns: ['Allocated Units', 'Uplift %', 'Override Amount',
                       'Rationale']
  },
  'approval-workflow' => {
    editable: 'line-values', scenarios: false, approval: true,
    agent: 'recommend', grain: ['Entity Key'],
    editable_columns: ['Decision', 'Counter Value', 'Reviewer', 'Decision Note']
  },
  'exception-command-center' => {
    editable: 'line-values', scenarios: false, approval: false,
    agent: 'recommend', grain: ['Entity Key'],
    editable_columns: ['Decision', 'Override', 'Owner', 'Resolution Note']
  }
}.fetch(option['archetype'])

editable = opts[:editable] || defaults[:editable]
die("invalid --editable #{editable.inspect}") unless
  %w[drivers line-values both none].include?(editable)
agent = opts[:agent] || defaults[:agent]
die("invalid --agent #{agent.inspect}") unless
  %w[analyze recommend write-after-approval none].include?(agent)
approval = bool(opts[:approval], defaults[:approval])
scenarios = bool(opts[:scenarios], defaults[:scenarios])
write_mode = (opts[:write_mode] || 'append').to_s.downcase
die("invalid --write-mode #{write_mode.inspect}") unless
  %w[append overwrite].include?(write_mode)
unit_of_work = opts[:unit_of_work].to_s.strip
unit_of_work = defaults[:grain].join(' × ') if unit_of_work.empty?

modules = Array(option['modules']).dup
modules.concat(Array(option['optional_modules']))
modules << 'approval-log' if approval
modules << 'scenario-library' if scenarios
modules.delete('workbook-agent') if agent == 'none'
modules << 'workbook-agent' unless agent == 'none'
modules.uniq!

prerequisites = Array(option['requires']).dup
stable_keys = doc.dig('signals', 'stable_key_candidates') || []
write_gap = prerequisites.any? { |p| p.to_s.downcase.include?('write') }
l1_ready = !write_gap && !stable_keys.empty?

# Rails before agents (BUILD L1→L3): do not authorize write-after-approval
# without a governed write path underneath.
if agent == 'write-after-approval' && !l1_ready
  die('agent write-after-approval requires L1 readiness first ' \
      '(stable key candidates + write-enabled connection). ' \
      'Put the workflow on rails before putting an agent on it.')
end
if agent == 'recommend' && !l1_ready
  warn 'enhance-app-plan: WARN — agent=recommend without L1 write readiness; ' \
       'keep the agent read-only until a stable key and write connection exist.'
end

manual_steps = []
if editable != 'none'
  manual_steps << 'For every input table: kebab → Set data entry permission → Only in published version.'
  manual_steps << 'Publish and type into a real cell in the published view.'
end
manual_steps << 'Keep parameter-driven calculations and controls in the workbook document; do not reference data-model controls from workbook formulas.'
manual_steps << 'STOP: confirm this app-plan (archetype, unit of work, write mode, agents) with the human before any sigma-authoring writeback work.'
if write_mode == 'append' && editable != 'none'
  manual_steps << 'Append-only ledger: include is_current, is_deleted, effective_from_ts/effective_to_ts, and created/updated audit columns; supersede on restatement (never destroy).'
  manual_steps << 'Publish a CURRENT_* warehouse view (is_current=true AND is_deleted=false) as the dashboard read surface.'
end
if approval
  manual_steps << 'Model status lifecycle with a state-history table (old status, new status, who, when, why).'
end

verification = [
  'Baseline numeric oracle matches the parity workbook/source.',
  'Editable grain is unique and row count matches the declared formula.',
  'Positive and negative business-impact examples calculate with the correct sign.',
  'Selected-scope analytics change; all-scope comparisons retain every entity/scenario.',
  'Published data entry persists after refresh.'
]
verification << 'Edit scenario A, prove B is unchanged, then switch back and prove A persists.' if scenarios
verification << 'Approve/update one entity, prove another entity is unchanged, and verify the audit row.' if approval
verification << 'Ask the agent a question with a known answer and verify values, scope, and action claims.' unless agent == 'none'

plan = {
  'schemaVersion' => 1,
  'workbookId' => doc['workbook_id'],
  'generatedAt' => Time.now.utc.iso8601,
  'selectedOptionId' => option['id'],
  'archetype' => option['archetype'],
  'score' => option['score'],
  'confidence' => option['confidence'],
  'evidence' => option['evidence_items'] || [option['evidence']],
  'sourceSignals' => doc['signals'] || {},
  'unitOfWork' => unit_of_work,
  'writeMode' => write_mode,
  'userChoices' => {
    'editable' => editable,
    'approval' => approval,
    'scenarios' => scenarios,
    'agent' => agent,
    'writeMode' => write_mode
  },
  'grain' => {
    'recommended' => defaults[:grain],
    'requiresUniquenessValidation' => true,
    'stableKeyCandidates' => stable_keys
  },
  'editableSurface' => {
    'mode' => editable,
    'suggestedColumns' =>
      editable == 'none' ? [] : defaults[:editable_columns]
  },
  'modules' => modules,
  'prerequisites' => prerequisites.uniq,
  'manualSteps' => manual_steps,
  'buildRefs' => Array(option['manual_refs']),
  'verificationGates' => verification
}

out = opts[:out] ||
      File.join(File.dirname(opts[:enhancements]), 'app-plan.json')
File.write(out, JSON.pretty_generate(plan))
puts "enhance-app-plan: #{option['archetype']} (score #{option['score']}, " \
     "#{option['confidence']}) -> #{out}"
puts "  unitOfWork: #{unit_of_work}"
puts "  writeMode: #{write_mode}"
puts "  grain: #{defaults[:grain].join(' × ')}"
puts "  modules: #{modules.join(', ')}"
puts "  prerequisites: #{prerequisites.empty? ? '(none)' : prerequisites.join(', ')}"
