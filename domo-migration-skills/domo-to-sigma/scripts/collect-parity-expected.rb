#!/usr/bin/env ruby
# frozen_string_literal: true
# collect-parity-expected.rb — the DOMO-SIDE half of the parity oracle.
#
# Fetches, for every card on the migrated page, the values Domo ITSELF renders,
# and writes them in the shape verify-parity.rb's `expected` side consumes.
# Paired with collect-parity-actuals.rb (the Sigma side); build-parity-oracle.rb
# joins the two into the plan phase6-parity-domo.rb finalizes.
#
#   ruby scripts/collect-parity-expected.rb --workdir <dir> [--out PATH] [--pool 4]
#
# Output (--out, default <workdir>/parity-expected.json):
#   { "<chart name>": { "rows": [[dim, val], ...], "source": "domo-card-data",
#                       "card_id": "...", "mappings": [...] }, ... }
# plus, for every card carrying one, a companion entry keyed "<chart name>"
# for the `-summary` tile holding a single [[label, summaryNumber]] row.
#
# WHY THIS ENDPOINT, AND NOT RECONSTRUCTED AGGREGATIONS.
# The 2026-08-05 gold audit sized this collector at 3-5 days because it assumed
# expected values had to be RE-DERIVED from Domo.query_dataset — re-implementing
# each card's aggregation, filters, rolling date window, top-N and COUNT DISTINCT
# in our own code, then hoping our re-derivation matched Domo's. Every one of
# those is a place to be silently wrong, and the audit catalogued them as such:
# 28 of 36 cards carry a relative date window, several wrap aggregate Beast
# Modes, top-N has no documented tie-break.
#
# GET /api/content/v1/cards/{id}/data removes the entire class: Domo evaluates
# its own card — window, filters, aggregation, ordering, limit — and hands back
# the rendered rows. We re-derive nothing. Probed live 2026-08-07 against page
# 59931332: 36/36 cards return HTTP 200, 35 carry real rows, 31 carry a
# summaryNumber, and the mapped coverage is 64 of the gate's 65 chartable tiles.
#
# THE ONE CARD THIS CANNOT SERVE is 983053598 "Survey Completion Rate", which
# returns metadata with no `rows` key at all. That is the SAME card the audit
# independently flagged as "never statically scoreable — the date window is
# baked into the plotted VALUE, not the filter, so the true answer changes
# daily". Two unrelated methods landing on the same single exception is the
# strongest evidence available that it is genuinely un-scoreable rather than a
# gap in this script. It is emitted to the exclusion ledger WITH THAT REASON by
# build-parity-oracle.rb, never silently dropped — an omitted tile would shrink
# the denominator and read as a clean pass (the exact inflation
# phase6-parity-domo.rb's census exists to refuse).
#
# SAME-DAY FETCH IS LOAD-BEARING. Because Domo evaluates relative windows at
# FETCH time, the expected and actual sides must be collected in the same run
# (same UTC day) or a rolling-7-day card legitimately disagrees with itself.
# This script stamps `fetched_at` and build-parity-oracle.rb refuses to join
# sides whose stamps straddle a UTC date boundary.
require 'json'
require 'optparse'
require 'time'
$LOAD_PATH.unshift(File.join(__dir__, 'lib'))
require 'domo_rest'

opts = { pool: 4 }
OptionParser.new do |p|
  p.banner = 'Usage: collect-parity-expected.rb --workdir DIR [--out PATH] [--pool N]'
  p.on('--workdir DIR', 'run directory (reads discovery/cards.json)') { |v| opts[:wd] = v }
  p.on('--out PATH', 'output JSON (default <workdir>/parity-expected.json)') { |v| opts[:out] = v }
  p.on('--pool N', Integer, 'parallel fetches (default 4)') { |v| opts[:pool] = v }
  p.on('--cards-json PATH', 'override discovery/cards.json') { |v| opts[:cards] = v }
end.parse!

abort('--workdir required') unless opts[:wd] && Dir.exist?(opts[:wd])
cards_path = opts[:cards] || File.join(opts[:wd], 'discovery', 'cards.json')
abort("cards.json not found at #{cards_path}") unless File.exist?(cards_path)
out_path = opts[:out] || File.join(opts[:wd], 'parity-expected.json')

raw = JSON.parse(File.read(cards_path))
cards = raw.is_a?(Array) ? raw : Array(raw['cards'])
abort('no cards found') if cards.empty?

# ---- shaping ---------------------------------------------------------------

# Domo labels each column's ROLE in `mappings`, parallel to `columns`/`rows`.
# Roles seen live on the 36-card sample page:
#   ITEM|VALUE                      simple dimension + measure        (17)
#   ITEM|SERIES|SERIES[|SERIES]     multi-series                      (12)
#   CATEGORY|CURRENT|TARGET         gauge                              (2)
#   SERIES|ITEM|VALUE               series-first ordering              (1)
#   XTIME|VALUE|SERIES|BUBBLESIZE   scatter/bubble                     (2)
#   ITEM|VALUE|POP_PERIOD|POP_INDEX period-over-period                 (1)
#   DATE|EVENT                      event stream                            (1)
# Rows are passed through as whole tuples rather than projected down to two
# columns: verify-parity.rb's strict_compare is exact tuple-set equality, so
# dropping a channel here would compare a 3-series chart on one series and call
# it a pass. The mappings are recorded alongside so the join can align column
# ORDER against the Sigma export rather than assuming it.
def shape_rows(data)
  rows = data['rows']
  return nil unless rows.is_a?(Array)
  rows.map { |r| Array(r) }
end

# Domo sometimes plots ONE measure on TWO channels, so its row carries the same
# value twice while Sigma's export carries it once. Measured 2026-08-07:
#   Top 20 Organic Tweets   ['Text','Favorite Count','Favorite Count']
#                           -> ["...", 2817, 2817]     Sigma: ["...", 1287]
#   Page Engagement Rate    ['Date','Engaged Users','Unique Impressions','Engaged Users']
#                           -> ["2026-07-25", 3288.0, 202283, 3288]
#   Page View Growth        ['Date','Unique Page Views','Page Views','Unique Page Views']
# Comparing whole tuples, that arity difference fails the tile before any value
# is looked at — a pure artifact of how Domo reports channels.
#
# THE TEST IS DELIBERATELY STRICTER THAN "SAME COLUMN NAME". A later channel is
# dropped only when its name matches an earlier one AND every row's value is
# numerically equal. Name alone would corrupt Domo's table-default COUNT shape,
# where the row-key column appears as BOTH the dimension and the counted measure
# — e.g. Least Clicked Campaigns is ['campaign_title','campaign_title'] with
# values ["Gembucket campaign", 2]. Those are different data under one name and
# must both survive; the strict test leaves them alone.
#
# Returns [rows, columns, mappings, dropped] — dropped names are recorded on the
# card so the collapse is auditable, never invisible.
def dedupe_channels(rows, columns, mappings)
  cols = Array(columns)
  return [rows, cols, Array(mappings), []] if cols.size < 2 || rows.empty?

  numeric = ->(v) { f = Float(v.to_s) rescue nil; f }
  drop = []
  (1...cols.size).each do |j|
    (0...j).each do |i|
      next if drop.include?(i)
      next unless cols[j].to_s == cols[i].to_s
      same = rows.all? do |r|
        a = numeric.call(Array(r)[i])
        b = numeric.call(Array(r)[j])
        (a && b) ? a == b : Array(r)[i].to_s == Array(r)[j].to_s
      end
      if same
        drop << j
        break
      end
    end
  end
  return [rows, cols, Array(mappings), []] if drop.empty?

  keep = (0...cols.size).reject { |k| drop.include?(k) }
  [rows.map { |r| keep.map { |k| Array(r)[k] } },
   keep.map { |k| cols[k] },
   keep.map { |k| Array(mappings)[k] },
   drop.map { |k| cols[k] }]
end

# The card's own KPI value — what the migrated `<el>-summary` companion tile
# plots. `summary` carries BOTH forms:
#
#   {"label": "Sales in Period", "value": "$9.7M", "number": 9690690.9317, ...}
#
# TAKE `number`. `value` and the top-level `summaryNumber` are DISPLAY strings,
# and comparing one of those against Sigma's raw export is a guaranteed false
# divergence — a bug this returned on its first cut. verify-parity.rb normalises
# numerically, and in Ruby "$9.7M".to_f is 0.0, so the tile compared 0.0 against
# 9690690.93 and DIVERGED. Percent cards fail differently and just as silently:
# "35.61%".to_f is 35.61 while `number` is 0.3561, a 100x mismatch. All 29
# companion KPI tiles on the live page would have failed this way — a ~45% false
# failure rate on gate 1, reading exactly like a catastrophic conversion bug and
# sending the next person hunting something that was never broken.
#
# A display string is used ONLY as a last resort, when no numeric form exists at
# all, and even then it is left to verify-parity to normalise — better a tile
# that fails loudly than one silently scored on a formatted string.
#
# `status` is still honoured: "not_ran" means Domo declined to compute the
# summary, which is not a zero.
def summary_value(doc)
  s = doc['summary']
  if s.is_a?(Hash) && s['status'].to_s != 'not_ran'
    n = s['number']
    return n if n.is_a?(Numeric)
    v = s['value']
    return v if !v.nil? && v.to_s.strip != ''
  end
  sn = doc['summaryNumber']
  return sn if !sn.nil? && sn.to_s.strip != ''
  nil
end

# ---- fetch -----------------------------------------------------------------

results = {}
errors  = []
mutex   = Mutex.new
queue   = cards.dup
threads = [opts[:pool], 1].max.times.map do
  Thread.new do
    loop do
      card = mutex.synchronize { queue.shift }
      break unless card
      cid   = card['id'].to_s
      title = (card['title'] || card['name'] || cid).to_s
      begin
        doc = Domo.private_get("/api/content/v1/cards/#{cid}/data")
        data = doc['data'] || {}
        rows = shape_rows(data)
        sv   = summary_value(doc)
        mutex.synchronize do
          if rows.nil?
            # No `rows` key at all — record the refusal WITH the card's own
            # metadata so the exclusion ledger can cite a measured reason
            # instead of a guess.
            errors << { 'card_id' => cid, 'title' => title,
                        'reason' => 'domo card-data returned no `rows` key (card computes its ' \
                                    'value from a window baked into the plotted measure)',
                        'mappings' => data['mappings'], 'num_rows' => data['numRows'] }
          else
            rows, cols, maps, dropped = dedupe_channels(rows, data['columns'], data['mappings'])
            results[cid] = {
              'card_id'   => cid,
              'title'     => title,
              'rows'      => rows,
              'columns'   => cols,
              'mappings'  => maps,
              'num_rows'  => data['numRows'],
              'datasource' => data['datasource'],
              'source'    => 'domo-card-data',
            }
            results[cid]['dropped_duplicate_channels'] = dropped unless dropped.empty?
          end
          results[cid]['summary_value'] = sv if sv && results[cid]
          warn "  [#{results.size + errors.size}/#{cards.size}] #{title[0, 46]}"
        end
      rescue StandardError => e
        mutex.synchronize do
          errors << { 'card_id' => cid, 'title' => title, 'reason' => "fetch failed: #{e.message}" }
          warn "  ERROR #{cid} #{title[0, 40]}: #{e.message}"
        end
      end
    end
  end
end
threads.each(&:join)

doc = {
  'fetched_at'   => Time.now.utc.iso8601,
  'source'       => 'domo-card-data',
  'endpoint'     => '/api/content/v1/cards/{id}/data',
  'cards_total'  => cards.size,
  'cards_ok'     => results.size,
  'cards_failed' => errors.size,
  'cards'        => results,
  'unavailable'  => errors,
}
File.write(out_path, JSON.pretty_generate(doc))
warn "\nwrote #{out_path} — #{results.size}/#{cards.size} cards carry rows, " \
     "#{results.count { |_, v| v['summary_value'] }} carry a summary value"
unless errors.empty?
  warn "#{errors.size} card(s) could not be served — these MUST reach " \
       'parity-plan-exclusions.json with a reason, never be dropped:'
  errors.each { |e| warn "    #{e['card_id']}  #{e['title']}  — #{e['reason']}" }
end
exit 0
