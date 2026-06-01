#!/usr/bin/env ruby
# Scout's terminal step: given a candidate Sigma formula + the gap context,
# validate against the customer's Sigma site and persist the rule on success
# or escalate on failure.
#
# This is what the gap-scout subagent invokes via Bash. The subagent does the
# Claude-reasoning side (proposing the candidate); this script does the
# deterministic side (POST, validate, write yaml).
#
# Usage:
#   ruby scripts/scout-validate-and-persist.rb \
#     --feature 'WINDOW_AVG' \
#     --pattern '\bWINDOW_AVG\s*\(\s*SUM\s*\(\[([^\]]+)\]\)\s*\)' \
#     --template 'MovingAvg(Sum([Master/\1]), -10, 10)' \
#     --test-formula 'MovingAvg(Sum([Master/Sales]), -10, 10)' \
#     --data-model-id <dm-id> \
#     --master-element-id master \
#     [--folder-id <folder-id>] \
#     [--description "..."] \
#     [--hint "Sigma window functions silently error in grouping-table charts"] \
#     [--example-from "workbook.twb line 123"] \
#     [--max-attempts 3]
#
# Output (JSON to stdout):
#   {
#     "status": "validated" | "escalated",
#     "rule_path": "~/.tableau-to-sigma/learned-rules.yaml",     // on success
#     "workbook_id": "...",                                       // on success
#     "escalation_path": "~/.tableau-to-sigma/escalations/...",   // on failure
#     "attempts": [...]
#   }

require 'json'
require 'optparse'
require 'open3'
require 'time'
require_relative 'learned-rules'

opts = { max_attempts: 1 }
OptionParser.new do |p|
  p.on('--feature S')              { |v| opts[:feature] = v }
  p.on('--pattern S')              { |v| opts[:pattern] = v }
  p.on('--template S')             { |v| opts[:template] = v }
  p.on('--test-formula S')         { |v| opts[:test_formula] = v }
  p.on('--data-model-id S')        { |v| opts[:dm_id] = v }
  p.on('--master-element-id S')    { |v| opts[:el_id] = v }
  p.on('--folder-id S')            { |v| opts[:folder_id] = v }
  p.on('--description S')          { |v| opts[:description] = v }
  p.on('--hint S')                 { |v| opts[:hint] = v }
  p.on('--example-from S')         { |v| opts[:example_from] = v }
  p.on('--max-attempts N', Integer){ |v| opts[:max_attempts] = v }
  p.on('--chart-kind S')           { |v| opts[:chart_kind] = v }
  p.on('--escalate-to S', 'gh | beads | none (default: auto — try gh, then beads)') { |v| opts[:escalate_to] = v }
  p.on('--github-repo S', 'GitHub repo for issue filing (default: sigmacomputing/quickstarts-public)') { |v| opts[:github_repo] = v }
end.parse!

%i[feature pattern template test_formula dm_id el_id].each { |k| abort("missing --#{k.to_s.tr('_','-')}") unless opts[k] }

VALIDATE = File.join(__dir__, 'validate-sigma-formula.rb')

attempt = {
  'sigma_formula' => opts[:test_formula],
  'tested_at'     => Time.now.utc.iso8601
}

# Run validate-sigma-formula.rb
cmd = ['ruby', VALIDATE,
       '--formula',           opts[:test_formula],
       '--data-model-id',     opts[:dm_id],
       '--master-element-id', opts[:el_id],
       '--label',             "scout:#{opts[:feature]}"]
cmd << '--folder-id'  << opts[:folder_id]  if opts[:folder_id]
cmd << '--chart-kind' << opts[:chart_kind] if opts[:chart_kind]

stdout, stderr, status = Open3.capture3(*cmd)
result = (JSON.parse(stdout) rescue { 'status' => 'error', 'raw' => stdout, 'stderr' => stderr })
attempt['result'] = result

if result['status'] == 'ok'
  rule = {
    'feature'            => opts[:feature],
    'description'        => opts[:description],
    'tableau_pattern'    => opts[:pattern],
    'sigma_template'     => opts[:template],
    'hint'               => opts[:hint],
    'validated_at'       => Time.now.utc.iso8601,
    'validated_workbook' => result['workbook_id'],
    'example_from'       => opts[:example_from],
    'confidence'         => 'validated'
  }
  path = LearnedRules.append(rule)
  puts JSON.pretty_generate({
    'status'      => 'validated',
    'rule_path'   => path,
    'workbook_id' => result['workbook_id'],
    'attempts'    => [attempt],
    'rule'        => rule
  })
  exit 0
else
  payload = {
    'feature'         => opts[:feature],
    'description'     => opts[:description],
    'tableau_pattern' => opts[:pattern],
    'tableau_template_attempted' => opts[:template],
    'test_formula'    => opts[:test_formula],
    'example_from'    => opts[:example_from],
    'attempts'        => [attempt],
    'escalated_at'    => Time.now.utc.iso8601
  }
  esc_path = LearnedRules.escalate(payload)

  # Auto-file: try gh first, then beads, then skip.
  filed_via = nil
  filed_id  = nil
  target    = opts[:escalate_to] || 'auto'
  title = "Tableau→Sigma gap: #{opts[:feature]} (#{opts[:description] || 'no description'})"
  body  = String.new
  body << "**Feature:** `#{opts[:feature]}`\n\n"
  body << "**Tableau pattern:** `#{opts[:pattern]}`\n\n"
  body << "**Tried Sigma template:** `#{opts[:template]}`\n\n"
  body << "**Test formula POSTed:** `#{opts[:test_formula]}`\n\n"
  body << "**Sigma response:**\n```json\n#{JSON.pretty_generate(attempt['result'])}\n```\n\n"
  body << "**Example source:** #{opts[:example_from] || '(not provided)'}\n\n"
  body << "**Escalation YAML:** `#{esc_path}`\n\n"
  body << "_Filed automatically by `scripts/scout-validate-and-persist.rb`._\n"

  if %w[auto gh].include?(target) && system('which gh > /dev/null 2>&1')
    repo = opts[:github_repo] || 'sigmacomputing/quickstarts-public'
    out, _err, st = Open3.capture3('gh', 'issue', 'create', '--repo', repo, '--title', title, '--body', body, '--label', 'tableau-to-sigma,gap-scout-escalation')
    if st.success?
      filed_via = 'gh'
      filed_id  = out.strip.split('/').last
    end
  end

  if filed_via.nil? && %w[auto beads].include?(target) && system('which bd > /dev/null 2>&1') && Dir.exist?(File.expand_path('~/.beads-sigma'))
    out, _err, st = Open3.capture3({ 'PWD' => File.expand_path('~/.beads-sigma') }, 'bd', 'create', title, '--priority', '2', '--labels', 'sigma-converter,tableau-to-sigma,gap-scout-escalation', '--description', body, '--silent', chdir: File.expand_path('~/.beads-sigma'))
    if st.success?
      filed_via = 'beads'
      filed_id  = out.strip
    end
  end

  puts JSON.pretty_generate({
    'status'          => 'escalated',
    'escalation_path' => esc_path,
    'filed_via'       => filed_via,
    'filed_id'        => filed_id,
    'attempts'        => [attempt]
  })
  exit 2
end
