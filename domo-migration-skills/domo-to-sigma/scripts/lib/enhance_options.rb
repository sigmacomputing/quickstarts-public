# frozen_string_literal: true

# Pure app-option rollup for Phase E.
#
# enhance-scan.rb owns live discovery and candidate detection. This module
# takes only plain Ruby values and turns them into user-meaningful app options,
# making the recommendation heuristic fully offline-testable.
module EnhanceOptions
  PLANNING_VOCAB = %w[
    forecast plan budget target assumption driver scenario projection outlook
    variance
  ].freeze
  APPROVAL_VOCAB = %w[
    approve approved approval reject rejected pending submit submitted review
    reviewer hold policy decision
  ].freeze
  EXCEPTION_VOCAB = %w[
    exception risk breach alert stockout overstock overdue anomaly threshold
    violation coverage reorder expedite
  ].freeze
  ALLOCATION_VOCAB = %w[
    allocate allocation capacity headcount workforce quota territory spread
    hiring requisition budget target
  ].freeze
  DECISION_MEMBERS = %w[
    pending approved rejected submitted in-review review hold on-hold approve
    reject counter
  ].freeze
  EXCEPTION_MEMBERS = %w[
    stockout-risk below-reorder-point overstock exception risk breach alert
    overdue anomaly healthy
  ].freeze

  module_function

  # Returns { 'signals' => Hash, 'app_options' => Array }.
  #
  # candidates: existing enhancements.json candidate objects.
  # shared_master_chart_count: total number of charts sharing master sources.
  # calc_blob: serialized source calc/layout artifacts, already lowercased or
  #            any object responding to #to_s.
  # write_connection_available: whether SIGMA_WRITE_CONNECTION_ID is present.
  # data_profile: optional scan profile:
  #   {field_names:[], member_values:{field=>[]}, formula_text:""}
  def build(candidates:, shared_master_chart_count:, calc_blob:,
            write_connection_available:, data_profile: {})
    ids_by_prefix = lambda do |prefix|
      candidates.map { |c| c['id'] }.select { |id| id.start_with?(prefix) }
    end
    ids_in_category = lambda do |category, risk = nil|
      candidates.select do |c|
        c['category'] == category && (risk.nil? || c['risk'] == risk)
      end.map { |c| c['id'] }
    end

    profile = normalize_profile(data_profile)
    blob = [calc_blob, profile['formula_text'], profile['field_names']].join(' ').downcase
    planning_hits = PLANNING_VOCAB.select { |word| blob.include?(word) }
    approval_hits = APPROVAL_VOCAB.select { |word| blob.include?(word) }
    exception_hits = EXCEPTION_VOCAB.select { |word| blob.include?(word) }
    allocation_hits = ALLOCATION_VOCAB.select { |word| blob.include?(word) }
    member_tokens = profile['member_values'].values.flatten.map { |v| token(v) }.uniq
    decision_members = member_tokens & DECISION_MEMBERS
    exception_members = member_tokens & EXCEPTION_MEMBERS
    fields = profile['field_names'].map(&:downcase)

    structural = structural_signals(fields, blob, decision_members,
                                    exception_members, member_tokens)
    scores = score_archetypes(planning_hits, approval_hits, exception_hits,
                              allocation_hits, structural)
    qualified = scores.select { |_name, rec| rec['qualified'] }.keys
    detected_modules = modules_for(qualified)
    signals = {
      'has_date_trend' =>
        !ids_by_prefix.call('comparison-kpi-pair').empty? ||
        !ids_by_prefix.call('interactivity-grain-').empty?,
      'shared_master_chart_count' => shared_master_chart_count,
      'selection_dim_count' =>
        ids_by_prefix.call('interactivity-selection-').size,
      'planning_vocabulary' => planning_hits,
      'approval_vocabulary' => approval_hits,
      'exception_vocabulary' => exception_hits,
      'allocation_vocabulary' => allocation_hits,
      'decision_members' => decision_members,
      'exception_members' => exception_members,
      'field_names' => profile['field_names'],
      'stable_key_candidates' => structural['stable_key_candidates'],
      'looks_like_planning_model' => scores['scenario-planning']['qualified'],
      'write_connection_available' => !!write_connection_available,
      'archetype_scores' => scores.transform_values { |s| s['score'] },
      'qualified_archetypes' => qualified,
      'detected_modules' => detected_modules
    }

    options = []
    interactivity_ids =
      ids_in_category.call('interactivity-recovery', 'low')
    unless interactivity_ids.empty?
      options << {
        'id' => 'option-interactive-dashboard',
        'label' => 'Interactive analysis dashboard',
        'summary' =>
          'Restore the filtering and grain switching the source dashboard ' \
          'had, without touching any figure.',
        'evidence' =>
          "#{signals['selection_dim_count']} filterable dimension(s) across " \
          "#{signals['shared_master_chart_count']} chart(s) sharing a master " \
          'source.',
        'risk' => 'low',
        'candidate_ids' => interactivity_ids
      }
    end

    kpi_ids = ids_in_category.call('comparison-enrichment')
    unless kpi_ids.empty?
      options << {
        'id' => 'option-exec-kpi-strip',
        'label' => 'Executive KPI summary',
        'summary' =>
          'Add period-over-period KPI cards above the existing charts.',
        'evidence' =>
          'A date-grouped measure chart was found, so prior-period ' \
          'comparison is derivable.',
        'risk' => 'low',
        'candidate_ids' => kpi_ids
      }
    end

    polish_ids = ids_in_category.call('fidelity-polish', 'low')
    unless polish_ids.empty?
      options << {
        'id' => 'option-polish-pack',
        'label' => 'Fidelity polish only',
        'summary' =>
          'Labels, titles and axis fixes that close cosmetic gaps against ' \
          'the source.',
        'evidence' => "#{polish_ids.size} low-risk polish item(s) detected.",
        'risk' => 'low',
        'candidate_ids' => polish_ids
      }
    end

    options.concat(archetype_options(signals, scores))
    options.each do |option|
      next unless option['archetype']
      option['optional_modules'] = detected_modules - option['modules']
    end

    options << {
      'id' => 'option-parity-only',
      'label' => 'Keep the parity dashboard as-is',
      'summary' =>
        'Make no enhancements. The verified 1:1 migration stands on its own.',
      'evidence' =>
        'Parity is already verified; enhancement is always optional.',
      'risk' => 'low',
      'candidate_ids' => []
    }

    archetype_choices = options.select { |o| o['archetype'] }
    recommended =
      if archetype_choices.any?
        archetype_choices.max_by do |o|
          [o['score'], archetype_precedence(o['archetype'])]
        end['id']
      else
        (options.reject { |o| o['candidate_ids'].empty? }
                .max_by { |o| o['candidate_ids'].size } || options.last)['id']
      end
    options.each { |option| option['recommended'] = option['id'] == recommended }

    { 'signals' => signals, 'app_options' => options }
  end

  def normalize_profile(profile)
    p = profile.is_a?(Hash) ? profile : {}
    fields = Array(p['field_names'] || p[:field_names]).map(&:to_s).uniq
    members = p['member_values'] || p[:member_values] || {}
    members = members.each_with_object({}) do |(field, values), out|
      out[field.to_s] = Array(values).compact.map(&:to_s).uniq.first(100)
    end
    {
      'field_names' => fields,
      'member_values' => members,
      'formula_text' => (p['formula_text'] || p[:formula_text]).to_s
    }
  end

  def token(value)
    value.to_s.downcase.strip.gsub(/[^a-z0-9]+/, '-').gsub(/^-|-$/, '')
  end

  def any_field?(fields, *patterns)
    fields.any? { |field| patterns.any? { |p| field.match?(p) } }
  end

  def structural_signals(fields, blob, decision_members, exception_members,
                         member_tokens)
    keys = fields.select do |f|
      f.match?(/(^|[\s_-])(id|key|sku|uuid)([\s_-]|$)/) ||
        f.match?(/(deal|req|request|order|ticket|case|employee)[\s_-]*id/)
    end
    composites = []
    time_field = fields.find { |f| f.match?(/date|month|quarter|period|week/) }
    line_field = fields.find do |f|
      f.match?(/line[\s_-]*item|account|metric|product|department|category/)
    end
    composites << "#{time_field} + #{line_field}" if time_field && line_field
    stable_keys = (keys + composites).uniq
    actual = member_tokens.include?('actual') ||
             any_field?(fields, /\bactual/)
    forecast = member_tokens.any? { |m| %w[forecast plan budget target].include?(m) } ||
               any_field?(fields, /\bforecast/, /\bplan\b/)
    {
      'has_actual_forecast' => actual && forecast,
      'has_time_grain' =>
        any_field?(fields, /date/, /month/, /quarter/, /period/, /week/, /year/),
      'has_driver_fields' =>
        any_field?(fields, /driver/, /assumption/, /rate/, /scenario/),
      'has_budget_target' =>
        any_field?(fields, /budget/, /target/, /quota/, /capacity/),
      'has_actual_baseline' =>
        any_field?(fields, /actual/, /baseline/, /current/, /on[\s_-]*hand/),
      'has_allocatable_dimension' =>
        any_field?(fields, /department/, /team/, /region/, /territory/,
                   /category/, /channel/, /role/, /location/),
      'has_capacity_measure' =>
        any_field?(fields, /headcount/, /capacity/, /quota/, /units?/,
                   /cost/, /salary/, /spend/),
      'has_decision_states' => decision_members.size >= 2,
      'has_pending_state' => decision_members.include?('pending'),
      'has_aging_measure' =>
        any_field?(fields, /days?[\s_-]*(pending|open|age)/, /aging/, /sla/,
                   /overdue/),
      'has_policy_threshold' =>
        any_field?(fields, /policy/, /threshold/, /tier/, /discount/,
                   /limit/, /approval/) ||
        blob.match?(/[<>]=?\s*(\[|[0-9])/),
      'has_owner_reviewer' =>
        any_field?(fields, /owner/, /reviewer/, /assignee/, /approver/,
                   /\brep\b/),
      'has_exception_states' => !exception_members.empty?,
      'has_exception_measure' =>
        any_field?(fields, /exception/, /risk/, /breach/, /alert/, /coverage/,
                   /reorder/, /safety[\s_-]*stock/, /variance/),
      'has_stable_key' => !stable_keys.empty?,
      'stable_key_candidates' => stable_keys
    }
  end

  def score_archetypes(planning_hits, approval_hits, exception_hits,
                       allocation_hits, s)
    planning = 0
    planning += 3 if s['has_actual_forecast']
    planning += 2 if s['has_time_grain']
    planning += 2 if s['has_driver_fields']
    planning += [planning_hits.size, 2].min
    planning += 1 if s['has_stable_key']

    allocation = 0
    allocation += 3 if s['has_budget_target']
    allocation += 2 if s['has_actual_baseline']
    allocation += 2 if s['has_allocatable_dimension']
    allocation += 2 if s['has_capacity_measure']
    allocation += 1 unless allocation_hits.empty?
    allocation += 1 if s['has_stable_key']

    approval = 0
    approval += 3 if s['has_decision_states']
    approval += 2 if s['has_pending_state']
    approval += 2 if s['has_aging_measure']
    approval += 2 if s['has_policy_threshold']
    approval += 1 if s['has_owner_reviewer']
    approval += 2 if s['has_stable_key']
    approval += 1 if approval_hits.size >= 2

    exception = 0
    exception += 3 if s['has_exception_states']
    exception += 2 if s['has_exception_measure']
    exception += 2 if s['has_policy_threshold']
    exception += 1 if s['has_owner_reviewer']
    exception += 2 if s['has_stable_key']
    exception += 1 if exception_hits.size >= 2

    {
      'scenario-planning' =>
        score_record(planning, 5, planning_evidence(s, planning_hits)),
      'allocation-capacity' =>
        score_record(allocation, 6, allocation_evidence(s, allocation_hits)),
      'approval-workflow' =>
        score_record(approval, 6, approval_evidence(s, approval_hits)),
      'exception-command-center' =>
        score_record(exception, 5, exception_evidence(s, exception_hits))
    }
  end

  def score_record(score, threshold, evidence)
    {
      'score' => score,
      'qualified' => score >= threshold,
      'confidence' => score >= threshold + 3 ? 'high' :
                      (score >= threshold ? 'medium' : 'low'),
      'evidence' => evidence
    }
  end

  def planning_evidence(s, hits)
    out = []
    out << 'Actual and forecast/plan members coexist.' if s['has_actual_forecast']
    out << 'A date/period grain is present.' if s['has_time_grain']
    out << 'Driver/assumption/scenario fields are present.' if s['has_driver_fields']
    out << "Planning terms: #{hits.join(', ')}." unless hits.empty?
    out
  end

  def allocation_evidence(s, hits)
    out = []
    out << 'Budget/target/capacity fields are present.' if s['has_budget_target']
    out << 'Actual/baseline fields are present.' if s['has_actual_baseline']
    out << 'An allocatable organizational dimension is present.' if s['has_allocatable_dimension']
    out << 'Capacity/cost/unit measures are present.' if s['has_capacity_measure']
    out << "Allocation terms: #{hits.join(', ')}." unless hits.empty?
    out
  end

  def approval_evidence(s, hits)
    out = []
    out << 'Multiple decision-state members are present.' if s['has_decision_states']
    out << 'Pending state is present.' if s['has_pending_state']
    out << 'Aging/SLA fields are present.' if s['has_aging_measure']
    out << 'Policy/tier/threshold fields are present.' if s['has_policy_threshold']
    out << 'A stable entity key is present.' if s['has_stable_key']
    out << "Approval terms: #{hits.join(', ')}." unless hits.empty?
    out
  end

  def exception_evidence(s, hits)
    out = []
    out << 'Exception/risk members are present.' if s['has_exception_states']
    out << 'Exception/coverage/reorder fields are present.' if s['has_exception_measure']
    out << 'A stable entity key is present.' if s['has_stable_key']
    out << "Exception terms: #{hits.join(', ')}." unless hits.empty?
    out
  end

  def archetype_options(signals, scores)
    options = []
    options << planning_option(signals, scores['scenario-planning']) if
      scores['scenario-planning']['qualified']
    options << allocation_option(signals, scores['allocation-capacity']) if
      scores['allocation-capacity']['qualified']
    options << approval_option(signals, scores['approval-workflow']) if
      scores['approval-workflow']['qualified']
    options << exception_option(signals, scores['exception-command-center']) if
      scores['exception-command-center']['qualified']
    options
  end

  def modules_for(archetypes)
    modules = []
    if archetypes.include?('scenario-planning')
      modules.concat %w[scenario-library writeback-grid scenario-comparison
                        impact-bridge]
    end
    if archetypes.include?('allocation-capacity')
      modules.concat %w[writeback-grid budget-variance]
    end
    if archetypes.include?('approval-workflow')
      modules.concat %w[decision-queue status-lifecycle audit-log]
    end
    if archetypes.include?('exception-command-center')
      modules.concat %w[exception-queue recommended-action resolution-log]
    end
    modules << 'workbook-agent' unless archetypes.empty?
    modules.uniq
  end

  def common_requirements(signals)
    reqs = []
    reqs << 'SIGMA_WRITE_CONNECTION_ID' unless
      signals['write_connection_available']
    reqs << 'stable entity/composite key' if
      signals['stable_key_candidates'].empty?
    reqs
  end

  def option_base(id:, label:, archetype:, score:, summary:, modules:, refs:,
                  signals:)
    {
      'id' => id,
      'label' => label,
      'archetype' => archetype,
      'score' => score['score'],
      'confidence' => score['confidence'],
      'summary' => summary,
      'evidence' => score['evidence'].join(' '),
      'evidence_items' => score['evidence'],
      'risk' => 'medium',
      'candidate_ids' => [],
      'modules' => modules,
      'requires' => common_requirements(signals),
      'manual_refs' => refs
    }
  end

  def planning_option(signals, score)
    option_base(
      id: 'option-planning-writeback',
      label: 'Driver-based planning app (write-back)',
      archetype: 'scenario-planning',
      score: score,
      summary:
        'The source is a planning model, not just a report. An input-table ' \
        'app can let users edit the plan and write it back, with approvals ' \
        'and an audit log.',
      modules: %w[scenario-library writeback-grid scenario-comparison
                  impact-bridge workbook-agent],
      refs: [
        'sigma-workbooks/reference/specification/input-tables.md',
        'sigma-workbooks/reference/workflows/planning-apps.md',
        'sigma-workbooks/reference/workflows/actions.md'
      ],
      signals: signals
    )
  end

  def allocation_option(signals, score)
    option_base(
      id: 'option-allocation-capacity',
      label: 'Allocation / capacity planning app',
      archetype: 'allocation-capacity',
      score: score,
      summary: 'Allocate budget, capacity, headcount, quota, or units across an organizational grain and compare the editable plan with the baseline.',
      modules: %w[writeback-grid budget-variance approval-log workbook-agent],
      refs: ['sigma-workbooks/reference/workflows/allocation-apps.md',
             'sigma-workbooks/reference/workflows/actions.md'],
      signals: signals
    )
  end

  def approval_option(signals, score)
    option_base(
      id: 'option-approval-workflow',
      label: 'Approval and decision workflow',
      archetype: 'approval-workflow',
      score: score,
      summary: 'Turn the existing status/aging/policy queue into editable decisions, status transitions, and an append-only audit log.',
      modules: %w[decision-queue status-lifecycle audit-log workbook-agent],
      refs: ['sigma-workbooks/reference/workflows/approval-apps.md',
             'sigma-workbooks/reference/workflows/actions.md'],
      signals: signals
    )
  end

  def exception_option(signals, score)
    option_base(
      id: 'option-exception-command-center',
      label: 'Exception command center',
      archetype: 'exception-command-center',
      score: score,
      summary: 'Turn exception/risk rows into prioritized, owned resolutions with editable overrides and an audit trail.',
      modules: %w[exception-queue recommended-action resolution-log workbook-agent],
      refs: ['sigma-workbooks/reference/workflows/exception-apps.md',
             'sigma-workbooks/reference/workflows/actions.md'],
      signals: signals
    )
  end

  def archetype_precedence(archetype)
    {
      'exception-command-center' => 4,
      'approval-workflow' => 3,
      'allocation-capacity' => 2,
      'scenario-planning' => 1
    }.fetch(archetype, 0)
  end
end
