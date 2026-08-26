#!/usr/bin/env ruby
# frozen_string_literal: true
# collect-parity-actuals.rb — the SIGMA-SIDE half of the parity oracle.
#
# Exports every chartable element of the migrated workbook and writes its rows
# in the shape verify-parity.rb's `actual` side consumes. Paired with
# collect-parity-expected.rb (the Domo side); build-parity-oracle.rb joins them.
#
#   ruby scripts/collect-parity-actuals.rb --plan <dir>/parity-plan.json \
#     --workbook-id <wb> --out <dir>/parity-actuals.json [--pool 4] [--timeout 120]
#
# Output (--out): { "<sigma_element_id>": { "chart": "...", "rows": [[...]],
# "columns": [...] }, ... } and, for anything it could not serve, an
# `unavailable` entry carrying a MEASURED reason — never a silent omission,
# because a tile missing from the plan shrinks gate 1's denominator and reads
# exactly like a clean pass.
#
# KEYED BY ELEMENT ID, NOT DISPLAY NAME — this is load-bearing.
# An earlier cut keyed `results` by the chart's display name. Domo hands the same
# generic summary label to many cards, so on the real 65-tile page ELEVEN tiles
# share a name with at least one other: "New Visits in Period" names 4 distinct
# elements, "Change over 7 Days" 3, "Surveys in Period" and "US Leads in Period"
# 2 each. phase6-parity-domo.rb:190-193 says as much in its own comment ("the
# same KPI title repeated on two pages is routine") and compares as a MULTISET
# for exactly this reason.
#
# Name-keying broke two ways at once, both silent:
#   * last writer wins in the thread pool, non-deterministically, and the losing
#     exports vanished with NO `unavailable` entry — contradicting the guarantee
#     stated above;
#   * the join then attached that ONE surviving export to EVERY tile sharing the
#     name, so N-1 tiles were scored against another element's data.
# Reproduced on the real element ids: a genuine match reported DIVERGE, and a
# genuine migration bug (42 vs 7) reported PASS 100% — an unearned pass, the
# precise failure this whole chain exists to prevent.
# Element ids are unique by construction, so they are the only safe key.
#
# WHY THIS IS NOT A PORT OF tableau-to-sigma's collect-parity-actuals.rb.
# That script is 441 lines and only 2 of them are Tableau-specific, so a port
# looked free. But most of its bulk is machinery for problems measured on
# TABLEAU workbooks — wide pivot-grid CSV exports that need a totals-JSON
# fallback, multi-million-row unaggregated detail tables that hung the pool,
# per-chart row-limit accounting. None of that has been observed on a Domo
# workbook, and importing it would mean carrying (and having to maintain)
# behaviour justified by evidence from another converter.
#
# domo already owns the identical fetch, live-proven since 2026-07-30, inside
# verify-warehouse.rb — export POST, poll the download, back off on 429/408/50x.
# That is now lib/element_export.rb and this script builds directly on it. If a
# Domo run turns up a pivot-export 500 or an oversized element, add the specific
# guard then, with the live evidence attached — the way tableau's grew.
#
# THE PIVOT CAVEAT IS REAL AND IS RECORDED, NOT SOLVED. Tableau measured that a
# pivot element's CSV export is the WIDE grid, not the long row/col/value tuples
# the comparison expects. Domo's spec emits 13 `table` elements; whether any
# render as a wide pivot is UNKNOWN until a live run. Rather than guess, this
# script records each tile's column count and header shape so the first live run
# shows immediately which elements came back wide — and those become recorded
# exclusions with a measured reason, not silent failures.
require 'json'
require 'csv'
require 'optparse'
require 'time'

opts = { pool: 4, timeout: 120 }
OptionParser.new do |p|
  p.banner = 'Usage: collect-parity-actuals.rb --plan PATH --workbook-id ID --out PATH'
  p.on('--plan PATH', 'parity plan (build-parity-plan.rb output)') { |v| opts[:plan] = v }
  p.on('--workbook-id ID', 'live Sigma workbook id') { |v| opts[:wb] = v }
  p.on('--out PATH', 'output JSON') { |v| opts[:out] = v }
  p.on('--pool N', Integer, 'parallel exports (default 4)') { |v| opts[:pool] = v }
  p.on('--timeout S', Integer, 'per-element poll budget seconds (default 120)') { |v| opts[:timeout] = v }
  p.on('--fixture PATH', 'TEST ONLY: elementId → CSV map, bypasses the export API') { |v| opts[:fixture] = v }
end.parse!
%i[plan wb out].each { |k| abort "missing --#{k == :wb ? 'workbook-id' : k}" unless opts[k] }

$LOAD_PATH.unshift File.expand_path('lib', __dir__)
require 'element_export'
require 'sigma_rest' unless opts[:fixture]

fixture = opts[:fixture] ? JSON.parse(File.read(opts[:fixture])) : nil
plan = JSON.parse(File.read(opts[:plan]))
charts = plan.is_a?(Hash) ? (plan['charts'] || []) : Array(plan)
abort('plan has no charts') if charts.empty?

results = {}
unavailable = []
mutex = Mutex.new
queue = charts.dup

threads = [opts[:pool], 1].max.times.map do
  Thread.new do
    loop do
      c = mutex.synchronize { queue.shift }
      break unless c
      name = c['chart'].to_s
      eid  = c['sigma_element_id'].to_s
      status, payload = ElementExport.fetch_csv(eid, opts[:wb],
                                                timeout: opts[:timeout], fixture: fixture)
      if status == :fail
        mutex.synchronize do
          unavailable << { 'chart' => name, 'element_id' => eid, 'reason' => payload.to_s }
          warn "  FAIL #{eid} #{name[0, 34]} — #{payload.to_s[0, 50]}"
        end
        next
      end
      rows = (CSV.parse(payload.to_s) rescue [])
      if rows.empty?
        mutex.synchronize do
          unavailable << { 'chart' => name, 'element_id' => eid,
                           'reason' => 'export CSV empty / unparseable' }
          warn "  EMPTY #{eid} #{name[0, 34]}"
        end
        next
      end
      headers = rows.shift.map { |h| h.to_s.strip }

      # HEADERS BUT NO DATA ROWS is a real defect, not an empty comparison.
      # Measured on the 2026-08-07 run: FOUR elements exported column headers and
      # zero rows — a bar chart, a table, a region-map and a scatter. The element
      # renders nothing in Sigma. Recording it as a successful export made the
      # join compare N Domo rows against 0 Sigma rows, which scores as an
      # ordinary DIVERGE and hides the actual finding ("this tile is blank")
      # among value mismatches. It belongs in `unavailable` so it becomes an
      # exclusion with a reason an operator can act on.
      if rows.empty?
        mutex.synchronize do
          unavailable << { 'chart' => name, 'element_id' => eid,
                           'columns' => headers,
                           'reason' => 'Sigma element exported column headers but ZERO data rows ' \
                                       "(#{headers.size} column(s): #{headers.join(', ')}) — the " \
                                       'tile renders nothing; fix the element rather than scoring it' }
          warn "  NO ROWS #{eid} #{name[0, 30]} (#{headers.size} header(s), 0 rows)"
        end
        next
      end
      mutex.synchronize do
        # Keyed by element id — see the header. A collision here would mean the
        # PLAN listed the same element twice, which is a different (and louder)
        # problem than two elements sharing a title, so say so rather than
        # overwrite.
        if results.key?(eid)
          unavailable << { 'chart' => name, 'element_id' => eid,
                           'reason' => 'element id appears more than once in the parity plan — ' \
                                       'refusing to overwrite the first export' }
          warn "  DUPLICATE ELEMENT ID #{eid} — recorded, not overwritten"
        else
          results[eid] = {
            'chart'      => name,
            'element_id' => eid,
            'columns'    => headers,
            'rows'       => rows,
            'n_columns'  => headers.size,
            'n_rows'     => rows.size,
          }
        end
        warn "  [#{results.size + unavailable.size}/#{charts.size}] #{eid} #{name[0, 30]} " \
             "(#{rows.size}r x #{headers.size}c)"
      end
    end
  end
end
threads.each(&:join)

doc = {
  'fetched_at'   => Time.now.utc.iso8601,
  'workbook_id'  => opts[:wb],
  'source'       => 'sigma-element-export',
  'charts_total' => charts.size,
  'charts_ok'    => results.size,
  'charts'       => results,
  'unavailable'  => unavailable,
}
File.write(opts[:out], JSON.pretty_generate(doc))
warn "\nwrote #{opts[:out]} — #{results.size}/#{charts.size} elements exported"
unless unavailable.empty?
  warn "#{unavailable.size} element(s) could not be exported — these MUST reach " \
       'parity-plan-exclusions.json with a reason, never be dropped:'
  unavailable.each { |u| warn "    #{u['chart']} — #{u['reason'][0, 80]}" }
end
exit 0
