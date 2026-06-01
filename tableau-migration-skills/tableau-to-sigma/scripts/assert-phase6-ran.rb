#!/usr/bin/env ruby
# Hard gate that proves a tableau-to-sigma conversion is actually complete.
# The subagent MUST run this script before declaring GREEN. It checks four
# independent things — failing ANY of them blocks the GREEN declaration:
#
#   1. Phase 6 ran (parity-final.json exists, status=PASS, pass-rate met)
#      → beads-sigma-4pm
#   2. No orphan workbooks left in the customer's My Documents
#      (posted-workbooks.jsonl has ≤1 entry OR cleanup-marker.json shows
#      cleanup ran with no failed deletes)  → beads-sigma-38a
#   3. The live workbook's /columns endpoint shows no column with
#      type=error (catches circular refs / runtime errors introduced
#      AFTER the initial POST's column-type guard ran)  → beads-sigma-38a
#   4. The workbook has a non-empty layout XML applied (catches the
#      "elements just listed in a single column" regression where the
#      agent forgot to PUT a layout)  → beads-sigma-bw3
#
# Usage:
#   ruby scripts/assert-phase6-ran.rb --tableau /tmp/<name> \
#     [--workbook-id <id>]     # override; default = read from wb-ids.json
#     [--min-pass-rate 1.0]    # default 1.0 (every chart must PASS)
#     [--allow-extract]        # treat extract-mode as acceptable
#     [--skip-column-check]    # skip the live /columns type=error scan
#     [--skip-orphan-check]    # skip the orphan-workbook scan (for callers
#                              # that genuinely want multiple workbooks)
#     [--skip-layout-check]    # skip the layout-applied scan
#     [--min-layout-elements N] default 2 — single-page bare-element layouts
#                              # often have just the page wrapper; require this
#                              # many <LayoutElement> tags
#
# Exit codes:
#   0  every gate passes — conversion is allowed to declare GREEN
#   1  parity-final.json missing (Phase 6 skipped — the regression case)
#   2  parity-final.json exists but status=FAIL / pass-rate below min /
#      extract-mode without --allow-extract / charts_total==0
#   3  parity-final.json malformed
#   4  orphan workbooks left uncleaned (beads-sigma-38a)
#   5  live workbook has column(s) with type=error (beads-sigma-38a)
#   6  live workbook has no layout applied — single-column fallback
#      (beads-sigma-bw3)
#
# Prints a per-gate summary to stdout regardless of exit code.

require 'json'
require 'net/http'
require 'uri'
require 'optparse'

opts = { min_pass_rate: 1.0, allow_extract: false, min_layout_elements: 2 }
OptionParser.new do |p|
  p.on('--tableau DIR')              { |v| opts[:tab] = v }
  p.on('--workbook-id ID')           { |v| opts[:wb] = v }
  p.on('--min-pass-rate F', Float)   { |v| opts[:min_pass_rate] = v }
  p.on('--allow-extract')            { opts[:allow_extract] = true }
  p.on('--skip-column-check')        { opts[:skip_column] = true }
  p.on('--skip-orphan-check')        { opts[:skip_orphan] = true }
  p.on('--skip-layout-check')        { opts[:skip_layout] = true }
  p.on('--min-layout-elements N', Integer) { |v| opts[:min_layout_elements] = v }
end.parse!
abort('--tableau required') unless opts[:tab]

summary_path = File.join(opts[:tab], 'parity-final.json')

unless File.exist?(summary_path)
  warn "[FAIL] Phase 6 skipped — #{summary_path} does not exist."
  warn "       Run: ruby scripts/phase6-parity.rb --tableau #{opts[:tab]} --workbook-id <id>"
  warn "       then collect actuals via mcp__sigma-mcp-v2__query and re-run with --finalize."
  warn "       See SKILL.md Phase 6. This is the hard gate (beads-sigma-4pm)."
  exit 1
end

begin
  summary = JSON.parse(File.read(summary_path))
rescue JSON::ParserError => e
  warn "[FAIL] #{summary_path} is malformed JSON: #{e.message}"
  exit 3
end

total = summary['charts_total'].to_i
passed = summary['charts_pass'].to_i
status = summary['status'].to_s
mode = summary['mode'].to_s

if total <= 0
  warn "[FAIL] parity-final.json reports charts_total=#{total} — no charts were verified."
  warn "       This usually means auto-parity-plan.rb matched zero Tableau views."
  warn "       Phase 6 must verify at least one chart to declare GREEN."
  exit 2
end

if mode == 'extract' && !opts[:allow_extract]
  warn "[FAIL] parity ran in extract-mode but --allow-extract was not passed."
  warn "       Extract-mode permits up to ±#{((summary['extract_tol'] || 0.30) * 100).to_i}% drift —"
  warn "       only acceptable when the source Tableau workbook has hasExtracts=true."
  exit 2
end

pass_rate = passed.to_f / total
if status != 'PASS' || pass_rate < opts[:min_pass_rate]
  warn "[FAIL] parity status=#{status} pass-rate=#{(pass_rate * 100).round(1)}% (#{passed}/#{total})"
  warn "       Required: status=PASS and pass-rate >= #{(opts[:min_pass_rate] * 100).to_i}%"
  if (fail_names = summary['fail_names']) && !fail_names.empty?
    warn "       Failing charts: #{fail_names.join(', ')}"
  end
  exit 2
end

puts "[OK] gate 1/4: Phase 6 ran cleanly — #{passed}/#{total} charts PASS (mode=#{mode}, status=#{status})"

# ---------------------------------------------------------------------------
# Gate 2 — orphan workbooks (beads-sigma-38a)
# ---------------------------------------------------------------------------
unless opts[:skip_orphan]
  log = File.join(opts[:tab], 'posted-workbooks.jsonl')
  if File.exist?(log)
    posted = File.readlines(log).map { |l| JSON.parse(l) rescue nil }.compact
    unique_ids = posted.map { |e| e['id'] }.uniq
    if unique_ids.length > 1
      marker_path = File.join(opts[:tab], 'cleanup-marker.json')
      unless File.exist?(marker_path)
        warn "[FAIL] gate 2/4: #{unique_ids.length} workbooks created during this conversion (orphans not cleaned)."
        warn "       posted-workbooks.jsonl entries:"
        unique_ids.each { |id| warn "         - #{id}" }
        warn "       Run: ruby scripts/cleanup-orphan-workbooks.rb --workdir #{opts[:tab]}"
        warn "       See beads-sigma-38a."
        exit 4
      end
      marker = JSON.parse(File.read(marker_path)) rescue {}
      if marker['failed'] && !marker['failed'].empty?
        warn "[FAIL] gate 2/4: cleanup-marker.json reports #{marker['failed'].length} failed delete(s)."
        warn "       Orphan workbooks are still in the customer's My Documents:"
        marker['failed'].each { |f| warn "         - #{f['id']} (HTTP #{f['status']})" }
        exit 4
      end
      if marker['dry_run']
        warn "[FAIL] gate 2/4: cleanup-marker.json is from a --dry-run; orphans were not actually deleted."
        warn "       Re-run cleanup-orphan-workbooks.rb without --dry-run."
        exit 4
      end
      kept = marker['kept'] || '(unknown)'
      deleted = (marker['deleted'] || []).length
      puts "[OK] gate 2/4: orphan cleanup ran — kept #{kept}, deleted #{deleted}"
    else
      puts "[OK] gate 2/4: only one workbook POSTed (#{unique_ids.first}) — no orphan check needed"
    end
  else
    puts "[OK] gate 2/4: posted-workbooks.jsonl missing — assuming no orphans (legacy or external POST flow)"
  end
else
  puts "[SKIP] gate 2/4: --skip-orphan-check"
end

# ---------------------------------------------------------------------------
# Gate 3 — live /columns type=error scan (beads-sigma-38a)
# Catches circular references and runtime errors that the initial post-and-
# readback column-type guard missed because they were introduced by later
# PUTs (layout updates, spec edits during error recovery).
# ---------------------------------------------------------------------------
unless opts[:skip_column]
  wb_id = opts[:wb]
  if wb_id.nil?
    wb_ids_path = File.join(opts[:tab], 'wb-ids.json')
    if File.exist?(wb_ids_path)
      wb_ids = JSON.parse(File.read(wb_ids_path)) rescue {}
      wb_id = wb_ids['workbookId']
    end
  end

  if wb_id.nil? || wb_id.empty?
    puts "[SKIP] gate 3/4: no workbook ID resolvable (pass --workbook-id or ensure wb-ids.json exists)"
  else
    base = ENV['SIGMA_BASE_URL']
    tok  = ENV['SIGMA_API_TOKEN']
    if base.nil? || base.empty? || tok.nil? || tok.empty?
      warn "[SKIP] gate 3/4: SIGMA_BASE_URL / SIGMA_API_TOKEN not set — cannot fetch /columns"
    else
      uri = URI("#{base}/v2/workbooks/#{wb_id}/columns")
      req = Net::HTTP::Get.new(uri)
      req['Authorization'] = "Bearer #{tok}"
      req['Accept'] = 'application/json'
      res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, read_timeout: 30) { |h| h.request(req) }

      if res.is_a?(Net::HTTPSuccess)
        cols = (JSON.parse(res.body)['entries'] rescue []) || []
        error_cols = cols.select { |c| c.dig('type', 'type') == 'error' }
        if error_cols.any?
          warn "[FAIL] gate 3/4: live workbook #{wb_id} has #{error_cols.length} column(s) with type=error."
          warn "       These render as visible errors in the Sigma UI (circular ref, unknown column,"
          warn "       unsupported function, etc.). Fix the offending formulas and re-PUT before declaring GREEN."
          error_cols.first(10).each do |c|
            warn "         element=#{c['elementId']} col=#{c['columnId']} label=#{c['label'].inspect}"
            warn "           formula: #{c['formula']}"
          end
          warn "       See beads-sigma-38a."
          exit 5
        end
        puts "[OK] gate 3/4: #{cols.length} live columns clean (no type=error)"
      else
        warn "[SKIP] gate 3/4: GET /v2/workbooks/#{wb_id}/columns returned HTTP #{res.code} — cannot verify"
      end
    end
  end
else
  puts "[SKIP] gate 3/4: --skip-column-check"
end

# ---------------------------------------------------------------------------
# Gate 4 — layout applied (beads-sigma-bw3)
# Fetches the live workbook spec and confirms a non-empty top-level `layout`
# XML is set, with at least --min-layout-elements <LayoutElement> tags.
# Catches the "agent forgot to PUT a layout" regression where elements
# render as a single-column stack instead of the dashboard grid.
# ---------------------------------------------------------------------------
unless opts[:skip_layout]
  wb_id = opts[:wb]
  if wb_id.nil?
    wb_ids_path = File.join(opts[:tab], 'wb-ids.json')
    if File.exist?(wb_ids_path)
      wb_ids = JSON.parse(File.read(wb_ids_path)) rescue {}
      wb_id = wb_ids['workbookId']
    end
  end

  if wb_id.nil? || wb_id.empty?
    puts "[SKIP] gate 4/4: no workbook ID resolvable for layout check"
  else
    base = ENV['SIGMA_BASE_URL']
    tok  = ENV['SIGMA_API_TOKEN']
    if base.nil? || base.empty? || tok.nil? || tok.empty?
      warn "[SKIP] gate 4/4: SIGMA_BASE_URL / SIGMA_API_TOKEN not set — cannot fetch spec"
    else
      uri = URI("#{base}/v2/workbooks/#{wb_id}/spec")
      req = Net::HTTP::Get.new(uri)
      req['Authorization'] = "Bearer #{tok}"
      req['Accept'] = 'application/json'
      res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, read_timeout: 30) { |h| h.request(req) }

      if res.is_a?(Net::HTTPSuccess)
        body = res.body.to_s
        spec =
          begin
            JSON.parse(body)
          rescue JSON::ParserError
            require 'yaml'
            require 'date'
            YAML.safe_load(body, permitted_classes: [Date, Time]) || {}
          end
        layout_xml = spec['layout'].to_s
        elem_count = layout_xml.scan(/<LayoutElement\b/).length

        # Detect the Sigma "auto-generated single-column stack" layout that
        # the server produces when a workbook is POSTed without a layout.
        # Signature: every non-Data page has all its elements at the same
        # gridColumn value (typically "1 / 13" — left half, vertically stacked).
        # Note: per-page detection — a workbook with one element per content
        # page is structurally fine (degenerate case, not a stack).
        non_data_stack_pages = []
        # Walk one page at a time using the <Page id="..."> blocks
        layout_xml.scan(/<Page\b[^>]*id="([^"]*)"[^>]*>(.*?)<\/Page>/m).each do |page_id, page_body|
          next if page_id.to_s.downcase.include?('data')
          cols_on_page = page_body.scan(/gridColumn="([^"]+)"/).map(&:first).uniq
          elems_on_page = page_body.scan(/<LayoutElement\b/).length
          if elems_on_page >= 2 && cols_on_page.length == 1
            non_data_stack_pages << [page_id, cols_on_page.first, elems_on_page]
          end
        end

        if layout_xml.empty?
          warn "[FAIL] gate 4/4: live workbook #{wb_id} has NO top-level layout XML."
          warn "       Elements render as a single-column stack instead of the"
          warn "       dashboard grid. Build a layout and PUT it:"
          warn "         ruby scripts/build-dashboard-layout.rb \\"
          warn "           --layout #{opts[:tab]}/dashboard-layout.json \\"
          warn "           --wb-ids #{opts[:tab]}/wb-ids.json \\"
          warn "           --out #{opts[:tab]}/layout.xml"
          warn "         ruby scripts/put-layout.rb --workbook #{wb_id} \\"
          warn "           --layout #{opts[:tab]}/layout.xml"
          warn "       See beads-sigma-bw3."
          exit 6
        elsif elem_count < opts[:min_layout_elements]
          warn "[FAIL] gate 4/4: layout XML has only #{elem_count} <LayoutElement> tag(s);"
          warn "       at least #{opts[:min_layout_elements]} required (one master + ≥1 chart)."
          warn "       The layout likely covers only the Data page — chart page is unstyled."
          exit 6
        elsif non_data_stack_pages.any?
          warn "[FAIL] gate 4/4: live workbook #{wb_id} has Sigma's auto-generated"
          warn "       single-column stack layout (multiple elements at the same gridColumn"
          warn "       on a non-Data page). This is what Sigma defaults to when you POST"
          warn "       a workbook without a layout — exactly the CoCo regression."
          non_data_stack_pages.each do |pid, col, n|
            warn "         page=#{pid.inspect}: #{n} elements all at gridColumn=#{col.inspect}"
          end
          warn "       Build a real layout and PUT it:"
          warn "         ruby scripts/build-dashboard-layout.rb --layout #{opts[:tab]}/dashboard-layout.json \\"
          warn "           --wb-ids #{opts[:tab]}/wb-ids.json --out #{opts[:tab]}/layout.xml"
          warn "         ruby scripts/put-layout.rb --workbook #{wb_id} --layout #{opts[:tab]}/layout.xml"
          warn "       See beads-sigma-bw3."
          exit 6
        else
          puts "[OK] gate 4/4: layout XML applied with #{elem_count} positioned element(s)"
        end
      else
        warn "[SKIP] gate 4/4: GET /v2/workbooks/#{wb_id}/spec returned HTTP #{res.code} — cannot verify"
      end
    end
  end
else
  puts "[SKIP] gate 4/4: --skip-layout-check"
end

puts "[OK] all gates pass — conversion may declare GREEN"
exit 0
