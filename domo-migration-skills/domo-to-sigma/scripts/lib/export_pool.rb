# frozen_string_literal: true
#
# export_pool.rb — BOUNDED element CSV export collection (issue #416).
#
# WHY. verify-anchors.rb and collect-parity-actuals.rb share the same element
# CSV export flow (POST /v2/workbooks/{wb}/export → poll
# GET /v2/query/{q}/download). Before this lib, --timeout bounded only the
# per-element POLL WAIT: the download of the CSV body, CSV.parse over it, and
# the per-cell scans were all unbounded, and the export itself carried no row
# cap — so a multi-million-row unaggregated detail grid (the shape a faithful
# 1:1 Tableau-table migration produces) hung the pool for 15+ minutes at 100%
# CPU with zero output (field-reported, 2026-07-17: 3 flat detail tables up to
# ~5.1M rows). Two fixes, both here so the scripts cannot drift apart:
#
#   1. Deadline — ONE wall-clock budget computed at process start. Every poll
#      loop and download checks it, so --timeout bounds TOTAL runtime.
#   2. rowLimit — Sigma's export API accepts a rowLimit (docs: "Export
#      workbook"; CSV/JSON/XLSX are truncated at 1M rows regardless), so the
#      export, the download, the CSV.parse, and every downstream scan are all
#      bounded by the caller's row cap. A bounded export can be TRUNCATED —
#      truncated?() detects it and callers MUST treat a miss/compare over a
#      truncated export as inconclusive, never as a hard verdict.
#
# The caller must `require 'sigma_rest'` first (this lib calls Sigma.request,
# which is exactly what the offline test stubs replace).

require 'json'
require 'timeout'

module ExportPool
  # Sigma truncates CSV/JSON/XLSX exports at 1M rows no matter what — a
  # rowLimit above this is meaningless (batch with `offset` if you truly need
  # more; none of these verification flows do).
  SIGMA_EXPORT_HARD_CAP = 1_000_000

  # Whole-run wall-clock budget, created ONCE at the start of a run and shared
  # by every worker: when it expires, everything stops — poll loops, retries,
  # downloads, and elements not yet started.
  class Deadline
    attr_reader :budget

    def initialize(seconds)
      @t0 = Time.now
      @budget = seconds.to_f
    end

    def elapsed
      Time.now - @t0
    end

    def remaining
      @budget - elapsed
    end

    def expired?
      remaining <= 0
    end
  end

  module_function

  # POST the export, bounded to row_limit rows (nil = unbounded, discouraged).
  # Returns the queryId or nil.
  def start_csv_export(wb, element_id, row_limit)
    start_export(wb, element_id, 'csv', row_limit)
  end

  # JSON twin of start_csv_export. Sigma's element JSON export returns the
  # element's LONG-FORM rows (one object per row keyed by column display name),
  # and — unlike the CSV export — it does NOT 500 on a pivot carrying a `totals`
  # key. That makes it the automatic fallback for the pivot CSV-export platform
  # bug (see collect-parity-actuals.rb). Same POST shape, format.type = json.
  def start_json_export(wb, element_id, row_limit)
    start_export(wb, element_id, 'json', row_limit)
  end

  # POST /v2/workbooks/{wb}/export for one element in the given format
  # ('csv' | 'json'), bounded to row_limit rows (nil = unbounded). Returns the
  # queryId or nil.
  def start_export(wb, element_id, fmt, row_limit)
    body = { elementId: element_id, format: { type: fmt } }
    body[:rowLimit] = row_limit if row_limit
    r = Sigma.request(:post, "/v2/workbooks/#{wb}/export", body: JSON.generate(body))
    r && r['queryId']
  end

  # Poll for the rendered CSV and download it, bounded by the shared deadline.
  # Returns [:ok, body] | [:timeout, nil] | [:html, nil] (HTML behind a 200 =
  # renderer error). Raises Sigma::Error for non-404 HTTP failures (callers
  # keep their own retry/fallback policies).
  def poll_csv_download(qid, deadline, poll_interval: 1.0)
    poll_download(qid, deadline, accept: 'text/csv', poll_interval: poll_interval)
  end

  # JSON twin of poll_csv_download — same bounded-poll/download contract, same
  # return shape, only the Accept header differs.
  def poll_json_download(qid, deadline, poll_interval: 1.0)
    poll_download(qid, deadline, accept: 'application/json', poll_interval: poll_interval)
  end

  # Poll for the rendered export body and download it, bounded by the shared
  # deadline. `accept` selects the wire format ('text/csv' | 'application/json'
  # — both stream identically). Returns [:ok, body] | [:timeout, nil] |
  # [:html, nil] (HTML behind a 200 = renderer error). Raises Sigma::Error for
  # non-404 HTTP failures (callers keep their own retry/fallback policies).
  def poll_download(qid, deadline, accept:, poll_interval: 1.0)
    loop do
      return [:timeout, nil] if deadline.expired?
      sleep([poll_interval, [deadline.remaining, 0.05].max].min)
      return [:timeout, nil] if deadline.expired?
      begin
        # The download itself is bounded too: rowLimit keeps the body small,
        # and Timeout hard-caps a stalled or endlessly-streaming read at the
        # remaining budget (previously an unbounded multi-hundred-MB body read
        # was the first half of the silent hang).
        b = Timeout.timeout([deadline.remaining, 1.0].max) do
          Sigma.request(:get, "/v2/query/#{qid}/download", accept: accept, binary: true)
        end
        next if b.to_s.empty? # still rendering
        return [:html, nil] if b.to_s.lstrip.start_with?('<')
        return [:ok, b]
      rescue Timeout::Error
        return [:timeout, nil]
      rescue Sigma::Error => e
        raise unless e.message.lines.first.to_s =~ /\b404\b/ # not materialized yet — keep polling
      end
    end
  end

  # Parse a Sigma JSON-export body into an array of row hashes (each keyed by
  # column display name). Handles both `format.type:"json"` (one JSON array of
  # objects) and `"jsonl"`/NDJSON (one object per line), plus a defensive
  # {"rows"|"data": [...]} wrapper. Returns [] for a blank/empty body.
  def parse_json_rows(body)
    s = body.to_s.strip
    return [] if s.empty?
    parsed = (JSON.parse(s) rescue nil)
    case parsed
    when Array then parsed.select { |r| r.is_a?(Hash) }
    when Hash
      rows = parsed['rows'] || parsed['data']
      rows.is_a?(Array) ? rows.select { |r| r.is_a?(Hash) } : [parsed]
    else
      # NDJSON: one JSON object per line.
      s.each_line.map { |ln| JSON.parse(ln) rescue nil }.select { |r| r.is_a?(Hash) }
    end
  end

  # rows INCLUDE the header row. A bounded export that came back full is
  # conservatively truncated (the element may hold exactly row_limit rows, but
  # the caller cannot tell the difference — treat verdicts over it as
  # inconclusive either way).
  def truncated?(rows, row_limit)
    !row_limit.nil? && rows.is_a?(Array) && (rows.length - 1) >= row_limit
  end

  # One progress line per pool event, stamped with run-elapsed seconds — the
  # pool is never silent for minutes. Single write() so concurrent workers
  # don't interleave mid-line; stderr so stdout contracts stay clean.
  def progress(deadline, msg)
    $stderr.write(format("  [pool +%6.1fs] %s\n", deadline.elapsed, msg))
  end
end
