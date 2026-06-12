# frozen_string_literal: true
#
# control_lint.rb — mechanized control-wiring lint for built Sigma workbooks.
#
# SHARED lib, vendored byte-identical into every covered plugin's scripts/lib/
# (md5 discipline — same as layout_lint.rb / sigma_rest.rb). Run by:
#   - post-and-readback.rb (--type workbook) right after the layout lint
#   - assert-phase6-ran.rb gate 7 (with a --skip-control-lint escape)
#   - scripts/probe-controls.rb (reuses the reach computation to pick its
#     in-closure / out-of-closure probe elements)
#
# It exists because a workbook can pass parity + layout gates and still ship
# controls that DO NOTHING (the "Orders Overview (from Looker)" estate escape:
# three list controls bound to no element at all) or controls that silently
# skip same-page charts (the PHASEE "Action(Region) → Monthly Revenue Trend"
# escape, and the Qlik class: source full of listboxes, spec with zero
# controls). Three checks:
#
#   (a) dead control — every kind:control element must have >=1 `filters`
#       target resolving to a REAL element id in the spec, OR be referenced
#       as [controlId] in at least one non-control element (formula / spec
#       reference). A control with neither is furniture: a user changes it
#       and nothing on the page reacts.
#   (b) reach — source-closure walk from the control's targets (filter
#       targets + formula-referencing elements, expanded downstream through
#       source.elementId chains). Any same-page QUERYABLE element outside
#       the closure flags PARTIAL with the element names. Intentional
#       single-chart switchers (grain / geo-level segmented controls) are
#       allow-listed via the controlScope annotation (CONTRACT below).
#   (c) source-scope coverage — when a control-scope sidecar is provided
#       (emitted by the builder from the SOURCE BI artifact's filter
#       signals), FAIL if the source had filter signals but the spec has
#       zero controls, if an annotated control is missing from the spec,
#       or if an annotated mustReach element is not in that control's
#       closure.
#
# CONTRACT — <out>/control-scope.json (emitted by the converter/builder next
# to the workbook spec; post-and-readback.rb and assert-phase6-ran.rb pick it
# up from the workdir automatically, or take --control-scope PATH):
#
#   {
#     "version": 1,
#     "source": "qlik",               // provenance tag, free-form
#     "sourceFilterSignals": 3,       // count of filter-like signals detected
#                                     //   in the source artifact (listboxes,
#                                     //   quick filters, actions, slicers,
#                                     //   prompts, dashboard filters...).
#                                     //   >0 with zero spec controls = FAIL.
#     "controls": [
#       {
#         "controlId": "ctl-region",           // spec controlId (required)
#         "sourceName": "Region quick filter", // optional, for messages
#         "scope": "page",                     // "page" (default): the reach
#                                              //   check applies to every
#                                              //   same-page queryable element
#                                              // OR an array of element ids /
#                                              //   display names the control
#                                              //   is INTENDED to affect — the
#                                              //   single-chart-switcher
#                                              //   allowlist (grain controls)
#         "mustReach": ["Monthly Revenue Trend"] // optional hard assertions:
#                                              //   each must be in the closure
#       }
#     ]
#   }
#
# In-spec alternative (pre-POST local specs only): a control element may carry
#   "controlScope": ["Element Name", ...]   // or "page"
# with the same meaning as scope. NOTE: Sigma strips unknown keys on readback,
# so the SIDECAR is the durable form — builders should emit both when the
# allowlist must survive a live re-lint of the posted workbook.
#
# MCP / export-API note (verified empirically 2026-06-12 on tj-wells-1989):
# the Sigma MCP query path (mcp__sigma-mcp-v2__query) evaluates a workbook
# element WITH the workbook's saved control DEFAULTS applied and exposes NO
# parameter mechanism to override them. The REST export API
# (POST /v2/workbooks/{id}/export with `"parameters": {"<controlId>": "<value>"}`)
# IS the only programmatic way to exercise a non-default control value — which
# is why probe-controls.rb (the flip test) is built on export, not MCP.
#
# API:
#   report     = ControlLint.controls_report(spec)   # per-control reach rows
#   violations = ControlLint.lint(spec, scope: nil)  # scope = parsed sidecar
#   -> array of human-readable violation strings; empty = clean.
#
# Standalone:
#   ruby scripts/lib/control_lint.rb <spec.json|spec.yaml> [control-scope.json]
require 'json'
require 'set'

module ControlLint
  QUERYABLE = %w[
    table pivot-table input-table bar-chart line-chart pie-chart donut-chart
    area-chart scatter-chart combo-chart kpi-chart box-chart funnel-chart
    gauge-chart waterfall-chart sankey-chart region-map point-map viz chart
    treemap-chart heatmap-chart word-cloud
  ].to_set.freeze

  module_function

  # { element_id => {el:, page:, kind:, name:, srcel:} } for every element.
  def elements(spec)
    out = {}
    (spec['pages'] || []).each do |pg|
      (pg['elements'] || []).each do |el|
        eid = el['id'] || el['elementId']
        next unless eid
        out[eid] = { el: el, page: pg['name'] || pg['id'],
                     kind: (el['kind'] || el['type']).to_s,
                     name: el['name'], srcel: source_element_id(el) }
      end
    end
    out
  end

  # Unwraps {kind:"source", source:{elementId}} and direct {elementId} forms.
  def source_element_id(el)
    src = el['source']
    return nil unless src.is_a?(Hash)
    src = src['source'] if src['kind'] == 'source' && src['source'].is_a?(Hash)
    src.is_a?(Hash) ? src['elementId'] : nil
  end

  def control?(info)
    info[:kind].include?('control')
  end

  # Transitive closure of elements sourcing (directly or via chains) from any
  # element in `roots`. Returns roots + downstream ids.
  def closure(elems, roots)
    reach = roots.to_set
    loop do
      grew = false
      elems.each do |eid, info|
        next if reach.include?(eid)
        next unless info[:srcel] && reach.include?(info[:srcel])
        reach << eid
        grew = true
      end
      break unless grew
    end
    reach
  end

  # Non-control elements whose serialized spec references [controlId] —
  # catches formula refs (If([GeoLevel]="State",...)) and any other spec-level
  # binding that names the control.
  def formula_refs(elems, cid)
    return [] if cid.nil? || cid.to_s.empty?
    pat = /\[#{Regexp.escape(cid)}\]/
    elems.select { |_eid, info| !control?(info) && JSON.generate(info[:el]).match?(pat) }
         .keys
  end

  # Per-control reach report. Each row:
  #   { control_element_id:, control_id:, name:, page:, control_type:,
  #     filter_targets: [ids], ghost_targets: [ids], formula_refs: [ids],
  #     reach: Set[ids], page_queryable: [ids], uncovered: [ids] }
  def controls_report(spec)
    elems = elements(spec)
    rows = []
    elems.each do |eid, info|
      next unless control?(info)
      el = info[:el]
      cid = el['controlId']
      tgt_ids = (el['filters'] || []).map { |t| t.is_a?(Hash) ? t.dig('source', 'elementId') : nil }.compact
      live    = tgt_ids.select { |t| elems.key?(t) }
      frefs   = formula_refs(elems, cid)
      roots   = (live + frefs).uniq
      reach   = roots.empty? ? Set.new : closure(elems, roots)
      page_q  = elems.select do |qid, i|
        qid != eid && i[:page] == info[:page] && QUERYABLE.include?(i[:kind])
      end.keys
      rows << { control_element_id: eid, control_id: cid, name: info[:name],
                page: info[:page], control_type: el['controlType'],
                filter_targets: live, ghost_targets: tgt_ids - live,
                formula_refs: frefs, reach: reach, page_queryable: page_q,
                uncovered: page_q.reject { |q| reach.include?(q) } }
    end
    rows
  end

  # Resolve a sidecar element reference (id or display name) to element ids.
  def resolve_ref(elems, ref)
    return [ref] if elems.key?(ref)
    elems.select { |_eid, i| i[:name] == ref }.keys
  end

  def label(elems, eid)
    n = elems[eid] && elems[eid][:name]
    n && !n.to_s.empty? ? "#{n.inspect} (#{eid})" : eid
  end

  def lint(spec, scope: nil)
    violations = []
    elems = elements(spec)
    rows  = controls_report(spec)

    scope_by_cid = {}
    if scope.is_a?(Hash)
      Array(scope['controls']).each do |c|
        scope_by_cid[c['controlId']] = c if c.is_a?(Hash) && c['controlId']
      end
      # (c) the Qlik class: source had filter signals, spec built zero controls.
      signals = scope['sourceFilterSignals'].to_i
      if signals.positive? && rows.empty?
        violations << "no controls built: the source artifact reported #{signals} filter signal(s) " \
                      '(control-scope.json sourceFilterSignals) but the spec contains ZERO control ' \
                      'elements — the source dashboard is interactive and the migration shipped a ' \
                      'static one; build the controls (or set sourceFilterSignals to 0 with a ' \
                      'reason if the signals are genuinely non-portable)'
      end
    end

    rows.each do |r|
      ann = scope_by_cid.delete(r[:control_id]) || {}
      ann_scope = ann['scope'] || elems[r[:control_element_id]][:el]['controlScope']
      ctl_label = "control #{label(elems, r[:control_element_id])}#{r[:control_id] ? " [#{r[:control_id]}]" : ''} on page #{r[:page].inspect}"

      r[:ghost_targets].each do |g|
        violations << "ghost target: #{ctl_label} lists filter target #{g.inspect} which does not " \
                      'resolve to any element in the spec — fix or drop the target'
      end

      # (a) dead control --------------------------------------------------------
      if r[:reach].empty?
        violations << "dead control: #{ctl_label} has no resolving `filters` target and no " \
                      '[controlId] reference in any non-control element — a user changes it and ' \
                      'nothing reacts; wire it (filters: [{source:{elementId}, columnId}]) or, if ' \
                      'the bound column genuinely does not exist on any element, REMOVE the ' \
                      'control (honest) instead of shipping furniture'
        next
      end

      # (c) mustReach assertions -------------------------------------------------
      Array(ann['mustReach']).each do |ref|
        ids = resolve_ref(elems, ref)
        if ids.empty?
          violations << "scope mustReach: #{ctl_label} — annotated element #{ref.inspect} does not " \
                        'exist in the spec'
        elsif ids.none? { |i| r[:reach].include?(i) }
          violations << "scope mustReach: #{ctl_label} does NOT reach annotated element " \
                        "#{ref.inspect} — wire a filter target (or formula ref) so it does"
        end
      end

      # (b) reach / PARTIAL --------------------------------------------------------
      if ann_scope.is_a?(Array)
        # Explicit allowlist (single-chart switcher): every listed element must
        # be reached; same-page elements OUTSIDE the list are intentionally
        # unaffected and not flagged.
        ann_scope.each do |ref|
          ids = resolve_ref(elems, ref)
          if ids.empty?
            violations << "controlScope: #{ctl_label} — scoped element #{ref.inspect} does not exist " \
                          'in the spec'
          elsif ids.none? { |i| r[:reach].include?(i) }
            violations << "controlScope: #{ctl_label} does NOT reach its scoped element #{ref.inspect}"
          end
        end
      elsif r[:uncovered].any?
        names = r[:uncovered].map { |u| label(elems, u) }
        violations << "partial control: #{ctl_label} affects #{r[:page_queryable].length - r[:uncovered].length} " \
                      "of #{r[:page_queryable].length} same-page queryable element(s); NOT affected: " \
                      "#{names.join(', ')} — wire those elements (add filter targets on their " \
                      'sources, matching the source dashboard\'s filter scope) or declare the ' \
                      'narrow scope intentional via controlScope (sidecar control-scope.json ' \
                      'scope:[...] — see header CONTRACT)'
      end
    end

    # (c) annotated controls that never made it into the spec ------------------
    scope_by_cid.each do |cid, c|
      violations << "missing control: control-scope.json expects control #{cid.inspect}" \
                    "#{c['sourceName'] ? " (source: #{c['sourceName'].inspect})" : ''} but the spec " \
                    'has no control with that controlId — the source filter was not migrated'
    end

    violations
  end
end

if __FILE__ == $PROGRAM_NAME
  abort 'usage: ruby control_lint.rb <workbook-spec.json|yaml> [control-scope.json]' unless ARGV[0] && File.exist?(ARGV[0])
  body = File.read(ARGV[0])
  spec =
    begin
      JSON.parse(body)
    rescue JSON::ParserError
      require 'yaml'
      require 'date'
      YAML.safe_load(body, permitted_classes: [Date, Time], aliases: true) || {}
    end
  scope = ARGV[1] && File.exist?(ARGV[1]) ? JSON.parse(File.read(ARGV[1])) : nil
  v = ControlLint.lint(spec, scope: scope)
  if v.empty?
    n = ControlLint.controls_report(spec).length
    puts "control lint: clean (#{n} control(s) checked)"
  else
    warn "control lint: #{v.size} violation(s):"
    v.each { |x| warn "  - #{x}" }
    exit 1
  end
end
