#!/usr/bin/env ruby
# Phase 1c — Discover calculated fields for a Tableau workbook.
#
# Primary path:  Tableau Metadata API (GraphQL at /api/metadata/graphql).
#                Returns formula + dependency graph. Works regardless of VDS state.
# Fallback path: Parse the cached .twb XML. Returns formula only (no dep graph).
#
# Both paths emit the same JSON shape so downstream phases don't care which fired.
#
# Usage:
#   ruby extract-calc-fields.rb --workbook-luid <luid> \
#     [--out <wb-dir>/calc-fields.json] \
#     [--source auto|metadata|twb] \
#     [--twb <path>] \
#     [--refresh]
#
# Exit codes:
#   0 — success (metadata-api OR twb-xml-fallback)
#   3 — both paths failed
#   4 — metadata-api responded but workbook luid not in returned data
#   2 — bad arguments
#
# The old (pre-2026-05-26) signature was
#   ruby extract-calc-fields.rb <ds-metadata.json> <out.json>
# That signature is gone. The new script fetches metadata itself by workbook LUID.

require 'json'
require 'time'
require 'optparse'
require 'fileutils'
$LOAD_PATH.unshift File.expand_path('lib', __dir__)
require 'tableau_rest'

# ---- argument parsing ---------------------------------------------------

opts = {
  source: 'auto',
  refresh: false
}
OptionParser.new do |p|
  p.on('--workbook-luid LUID')      { |v| opts[:workbook_luid] = v }
  p.on('--out PATH')                { |v| opts[:out] = v }
  p.on('--source {auto|metadata|twb}', %w[auto metadata twb]) { |v| opts[:source] = v }
  p.on('--twb PATH')                { |v| opts[:twb] = v }
  p.on('--refresh')                 { opts[:refresh] = true }
end.parse!

unless opts[:workbook_luid]
  warn 'usage: extract-calc-fields.rb --workbook-luid <luid> [--out PATH] ' \
       '[--source auto|metadata|twb] [--twb PATH] [--refresh]'
  exit 2
end

luid = opts[:workbook_luid]
out_path = opts[:out] || File.join('/tmp', "calc-fields-#{luid}.json")
twb_path = opts[:twb] || "/tmp/assessment-dataflow/twbs/#{luid}.twb"

FileUtils.mkdir_p(File.dirname(out_path))

# ---- cache reuse --------------------------------------------------------

# Cache freshness rule: "same Tableau auth session". We don't have a session
# timestamp, so use the cached file's mtime within the current process's
# clock vs the auth env (TABLEAU_AUTH_TOKEN). A token lasts ~2h. We treat a
# cached calc-fields.json as fresh if it exists and is < 1h old, unless
# --refresh is set.
def cache_fresh?(path)
  return false unless File.file?(path)
  age = Time.now - File.mtime(path)
  age < 3600
end

if !opts[:refresh] && cache_fresh?(out_path)
  warn "calc-fields.json fresh at #{out_path} (#{(Time.now - File.mtime(out_path)).to_i}s old); use --refresh to bypass"
  puts File.read(out_path)
  exit 0
end

# ---- formula translation hints (carried over from the v1 script) --------

# Window/table-calc split (WINPROBE-validated, bead 427, 2026-06-12):
# AUTO functions translate to Sigma-NATIVE window math emitted as chart-element
# viz formulas on the yAxis by build-charts-from-signals.rb — single DM base
# element, ZERO Custom SQL (930/930 cells exact vs warehouse). MANUAL functions
# have no validated mapping and still require human translation (Custom SQL or
# re-authoring). See refs/window-functions.md for the full mapping table.
TABLEAU_WINDOW_FNS_AUTO = %w[
  WINDOW_SUM WINDOW_AVG WINDOW_MIN WINDOW_MAX WINDOW_COUNT WINDOW_STDEV
  RUNNING_SUM RUNNING_AVG RUNNING_COUNT RUNNING_MIN RUNNING_MAX
  RANK RANK_DENSE RANK_PERCENTILE
  INDEX TOTAL LOOKUP
].freeze
TABLEAU_WINDOW_FNS_MANUAL = %w[
  WINDOW_MEDIAN WINDOW_PERCENTILE WINDOW_CORR WINDOW_COVAR WINDOW_COVARP
  WINDOW_VAR WINDOW_VARP WINDOW_STDEVP
  RANK_MODIFIED RANK_UNIQUE
  FIRST LAST SIZE PREVIOUS_VALUE
].freeze
TABLEAU_WINDOW_FNS = (TABLEAU_WINDOW_FNS_AUTO + TABLEAU_WINDOW_FNS_MANUAL).freeze

def detect_window_fns(formula)
  TABLEAU_WINDOW_FNS.select { |fn| formula =~ /\b#{Regexp.escape(fn)}\s*\(/i }
end

def detect_manual_window_fns(formula)
  TABLEAU_WINDOW_FNS_MANUAL.select { |fn| formula =~ /\b#{Regexp.escape(fn)}\s*\(/i }
end

def lod?(formula)
  formula =~ /\{\s*(FIXED|INCLUDE|EXCLUDE)\b/i
end

def gotchas(formula)
  notes = []
  notes << 'IIF(c, t, e) → If(c, t, e) in Sigma' if formula =~ /\bIIF\s*\(/i
  notes << 'COUNTD → CountDistinct in Sigma' if formula =~ /\bCOUNTD\b/i
  notes << 'Tableau IF/IFNULL falls through to ELSE on NULL; Sigma If returns Null — wrap nullable source with Coalesce' \
    if formula =~ /\bIF\b[\s\S]+(>=|<=|=|<|>)/i

  manual_hits = detect_manual_window_fns(formula)
  auto_hits   = detect_window_fns(formula) - manual_hits
  if auto_hits.any?
    notes << "AUTO-TRANSLATED when plotted (WINPROBE-validated mapping, refs/window-functions.md): #{auto_hits.join(', ')} → " \
             'Sigma-NATIVE window math emitted as a CHART-element viz formula on the yAxis by build-charts-from-signals.rb. ' \
             'RUNNING_*→Cumulative*; WINDOW_AVG/SUM/MAX/MIN(x,-n,0)→Moving*(x,n); agg/WINDOW_SUM(agg)→PercentOfTotal(agg,"grand_total"); ' \
             'RANK/RANK_DENSE/RANK_PERCENTILE→Rank/RankDense/RankPercentile(agg,"desc"); INDEX()→RowNumber(); LOOKUP(x,±n)→Lag/Lead(x,n); ' \
             'RUNNING_SUM/TOTAL pareto→CumulativeSum(PercentOfTotal(agg,"grand_total")); unbounded WINDOW_MAX/MIN/SUM→hidden two-level ' \
             'grouped helper (consumer re-aggregates Max/Min, NEVER Sum). Single DM base element, NO Custom SQL. ' \
             'Placement: chart yAxis ONLY — these silently error in DM calc columns and grouping-table master calcs, ' \
             'and the *Over family (SumOver/RankOver/...) is "Unknown function" in every spec context.'
  end
  if manual_hits.any?
    notes << "MANUAL. #{manual_hits.join(', ')} has no validated Sigma chart-formula mapping — port via a Custom SQL " \
             'data-model element (kind: "sql", ANSI OVER(...)) or re-author in Sigma. Also MANUAL: any compute-using/' \
             'addressing override beyond the default Table(Across) / a simple partition ("restart every", pane-relative, ' \
             'compute-along-non-axis-dim) — build-charts emits these as flags, never guesses.'
  end

  if formula.scan(/\{\s*FIXED/i).length >= 2
    notes << 'AUTO-DECOMPOSED (nested LOD): {FIXED…{FIXED…}} becomes a helper-element CHAIN — ' \
             'build-charts-from-signals.rb writes the per-level plan to the -lod-chains.json sidecar ' \
             '(innermost first); build one grouped element per level, each outer level sourcing the inner ' \
             'element WITH groupingId (or a Custom SQL GROUP BY) or outer Avg/Median/Count come out row-weighted.'
  elsif formula =~ /\{\s*FIXED\b/i
    notes << 'AUTO-TRANSLATED when plotted: {FIXED <dims>:<agg>} becomes a hidden two-level grouped helper element ' \
             '(visibleAsSource:false; inner grouping = the FIXED dims computing the LOD aggregate, outer grouping = ' \
             'the chart dims computing the 2nd-stage aggregate; the chart Max()es the outer calc). ' \
             '⚠ carried chart dims must be functionally dependent on the FIXED dims — verify in Sigma. ' \
             'NEVER translate as SumOver/CountOver in master or DM-element calc columns (silent error).'
  end
  if formula =~ /\{\s*INCLUDE\b/i
    notes << 'MANUAL. {INCLUDE <dim>:<agg>} needs the chart grouping context: add <dim> to the chart grouping and use ' \
             'the plain aggregate, OR a fine-grain subquery (Custom SQL element) joined back to the view grain.'
  end
  if formula =~ /\{\s*EXCLUDE\b/i
    notes << 'MANUAL. {EXCLUDE <dim>:<agg>} needs the chart grouping context: remove <dim> from the chart grouping and ' \
             'use the plain aggregate, OR <agg>(<expr>) OVER (PARTITION BY <view-dims-minus-excluded>) via Custom SQL.'
  end
  notes
end

# FIXED LODs and the AUTO window/table-calc family are auto-translated (hidden
# grouped helper / Sigma-native chart viz formulas — see gotchas above), so
# they no longer force the Custom-SQL decision path or the exit-4 workbook
# handoff. Only the MANUAL window residues (WINDOW_MEDIAN/PERCENTILE/CORR/...,
# PREVIOUS_VALUE, SIZE, FIRST/LAST) and INCLUDE/EXCLUDE LODs still do.
def requires_custom_sql?(formula)
  detect_manual_window_fns(formula).any? || !!(formula =~ /\{\s*(INCLUDE|EXCLUDE)\b/i)
end

# ---- Metadata API path --------------------------------------------------

GRAPHQL_QUERY = <<~GRAPHQL
  query($luid: String!) {
    workbooks(filter: {luid: $luid}) {
      name luid
      embeddedDatasources {
        name
        fields {
          __typename name
          ... on CalculatedField {
            formula isHidden role dataType aggregation
            fields { name __typename }
            upstreamFields { name }
          }
        }
      }
    }
  }
GRAPHQL

def fetch_via_metadata_api(luid)
  body = JSON.generate(query: GRAPHQL_QUERY, variables: { luid: luid })
  begin
    resp = Tableau.request(
      :post,
      '/api/metadata/graphql',
      body: body,
      content_type: 'application/json',
      accept: 'application/json'
    )
  rescue Tableau::Error => e
    # Tableau::Error includes "POST /path -> <code> <msg>\n<body>" — surface for the
    # caller to fall back rather than crash.
    return { ok: false, error: e.message }
  end

  if resp.is_a?(Hash) && resp['errors']
    return { ok: false, error: "GraphQL errors: #{resp['errors'].inspect}" }
  end

  wbs = resp.dig('data', 'workbooks') || []
  return { ok: false, error: 'no_workbook_in_response', wb_count: 0 } if wbs.empty?

  wb = wbs.first
  calcs = []
  (wb['embeddedDatasources'] || []).each do |ds|
    ds_name = ds['name']
    (ds['fields'] || []).each do |f|
      next unless f['__typename'] == 'CalculatedField'
      formula = f['formula'].to_s
      depends_on = (f['fields'] || []).map { |d| d['name'] }.compact.uniq
      calcs << {
        name: f['name'],
        datasource: ds_name,
        formula: formula,
        role: f['role'],
        data_type: f['dataType'],
        aggregation: f['aggregation'],
        is_hidden: f['isHidden'] == true,
        is_lod: !!lod?(formula),
        depends_on: depends_on,
        requires_custom_sql: requires_custom_sql?(formula),
        translation_notes: gotchas(formula)
      }
    end
  end

  { ok: true, workbook_name: wb['name'], calcs: calcs }
end

# ---- .twb XML fallback --------------------------------------------------

require 'rexml/document'

def fetch_via_twb_xml(twb_path)
  return { ok: false, error: "twb not found: #{twb_path}" } unless File.file?(twb_path)
  doc = REXML::Document.new(File.read(twb_path))

  calcs = []
  # In a .twb, each <datasource> has a <column> children with optional
  # <calculation class='tableau' formula='...'/>. caption is the user-facing
  # name; name (e.g. "[Calculation_123]") is the internal id. role is
  # "dimension" / "measure"; datatype is "real" / "string" / etc.
  doc.elements.each('//datasource') do |ds|
    ds_name = ds.attributes['caption'] || ds.attributes['name']
    next if ds_name && ds_name.start_with?('Parameter')
    ds.elements.each('column') do |col|
      calc_el = col.elements['calculation']
      next unless calc_el
      next unless calc_el.attributes['class'] == 'tableau'
      formula = calc_el.attributes['formula'].to_s
      next if formula.empty?
      caption = col.attributes['caption']
      internal_name = col.attributes['name']
      data_type = col.attributes['datatype']
      role = col.attributes['role'] # dimension|measure
      role_norm = role == 'measure' ? 'MEASURE' : (role == 'dimension' ? 'DIMENSION' : role)
      hidden = col.attributes['hidden'] == 'true'
      default_agg = col.attributes['default-aggregation']
      calcs << {
        name: caption || internal_name,
        datasource: ds_name,
        formula: formula,
        role: role_norm,
        data_type: data_type ? data_type.upcase : nil,
        aggregation: default_agg,
        is_hidden: hidden,
        is_lod: !!lod?(formula),
        depends_on: [], # not available without a resolved field graph
        requires_custom_sql: requires_custom_sql?(formula),
        translation_notes: gotchas(formula)
      }
    end
  end

  { ok: true, calcs: calcs }
end

# ---- orchestration ------------------------------------------------------

source_chosen = nil
final_calcs = nil
wb_name = nil
metadata_err = nil

case opts[:source]
when 'metadata'
  r = fetch_via_metadata_api(luid)
  if r[:ok]
    source_chosen = 'metadata-api'
    final_calcs = r[:calcs]
    wb_name = r[:workbook_name]
  else
    warn "metadata-api failed: #{r[:error]}"
    if r[:error] == 'no_workbook_in_response'
      exit 4
    end
    exit 3
  end
when 'twb'
  r = fetch_via_twb_xml(twb_path)
  if r[:ok]
    source_chosen = 'twb-xml-fallback'
    final_calcs = r[:calcs]
  else
    warn "twb-xml fallback failed: #{r[:error]}"
    exit 3
  end
when 'auto'
  r = fetch_via_metadata_api(luid)
  if r[:ok]
    source_chosen = 'metadata-api'
    final_calcs = r[:calcs]
    wb_name = r[:workbook_name]
  else
    metadata_err = r[:error]
    warn "metadata-api unavailable (#{metadata_err}); falling back to .twb XML at #{twb_path}"
    r2 = fetch_via_twb_xml(twb_path)
    if r2[:ok]
      source_chosen = 'twb-xml-fallback'
      final_calcs = r2[:calcs]
    else
      warn "both paths failed — metadata: #{metadata_err}; twb: #{r2[:error]}"
      exit 3
    end
  end
end

n_calcs = final_calcs.size
n_lods  = final_calcs.count { |c| c[:is_lod] }
n_sql   = final_calcs.count { |c| c[:requires_custom_sql] }

result = {
  workbook_luid: luid,
  workbook_name: wb_name,
  source: source_chosen,
  generated_at: Time.now.utc.iso8601,
  n_calcs: n_calcs,
  n_lods: n_lods,
  n_requires_custom_sql: n_sql,
  metadata_api_error: metadata_err,
  calcs: final_calcs
}

File.write(out_path, JSON.pretty_generate(result))
warn "wrote #{out_path}  (source=#{source_chosen}, n_calcs=#{n_calcs}, n_lods=#{n_lods}, n_sql=#{n_sql})"
puts JSON.pretty_generate(result)
exit 0
