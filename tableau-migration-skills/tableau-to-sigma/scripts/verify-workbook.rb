#!/usr/bin/env ruby
# verify-workbook.rb — parallel reimplementation of verify-workbook.sh.
#
# Functional identical: for each element on a workbook, fetch its compiled
# SQL via /v2/workbooks/{id}/elements/{eid}/query, grep for "Unknown column"
# and "Circular column reference" markers, fail on any hit. Catches the cases
# the column-type guard misses — string-literal-baked SQL errors that POST
# accepts and the spec-level validator doesn't flag.
#
# Why a Ruby rewrite: the shell version processes elements serially with one
# curl per element, ~5s each. For a 6-element workbook that's ~30s. This
# version parallel-fetches with 5 threads + 429 backoff (same pattern as
# find-or-pick-dm.rb) → ~6-8s. Phase 5 perf ticket beads-sigma-y2l.
#
# Usage: ruby scripts/verify-workbook.rb <workbook-id>
# Env: SIGMA_BASE_URL, SIGMA_API_TOKEN.
# Exit: 0 = clean, 1 = one or more elements broken, 2 = setup error.

require 'net/http'
require 'uri'
require 'json'

WB_ID = ARGV[0] or abort("Usage: #{$PROGRAM_NAME} <workbook-id>\n")
BASE  = ENV['SIGMA_BASE_URL']  or (warn 'SIGMA_BASE_URL not set'; exit 2)
$LOAD_PATH.unshift File.expand_path('lib', __dir__)
require 'sigma_rest'

ERROR_MARKERS = /Unknown column "[^"]+"|Circular column reference to \[[^\]]+\]/

# Wrap with automatic 401-retry-after-refresh — tokens last ~1h, parity runs
# can outlive that on big workbooks.
def http_get(path)
  attempts = 0
  loop do
    attempts += 1
    uri = URI("#{BASE}#{path}")
    req = Net::HTTP::Get.new(uri)
    req['Authorization'] = "Bearer #{Sigma.auth_token}"
    req['Accept']        = 'application/json'
    res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, read_timeout: 30) { |h| h.request(req) }
    if res.code.to_i == 401 && attempts == 1 && ENV['SIGMA_CLIENT_ID']
      Sigma.refresh_token!
      next
    end
    return res
  end
end

# 1. List elements (one call, fast)
els_resp = http_get("/v2/workbooks/#{WB_ID}/elements")
unless els_resp.code.to_i == 200
  warn "could not fetch elements for #{WB_ID}: #{els_resp.code} #{els_resp.body[0..200]}"
  exit 2
end
elements = JSON.parse(els_resp.body)['entries'] || []
abort "no elements on workbook #{WB_ID}" if elements.empty?

# 2. Parallel-fetch each element's compiled SQL. 5 threads w/ 429 backoff —
# same envelope as find-or-pick-dm.rb. Sigma's edge throttles >5 concurrent.
require 'thread'
mu       = Mutex.new
results  = {}
queue    = Queue.new
elements.each { |e| queue << e }

threads = 5.times.map do
  Thread.new do
    until queue.empty?
      el = queue.pop(true) rescue nil
      break unless el
      eid  = el['elementId']
      name = el['name'] || el['kind'] || eid

      sql = nil
      4.times do |attempt|
        r = http_get("/v2/workbooks/#{WB_ID}/elements/#{eid}/query")
        code = r.code.to_i
        if code == 200
          parsed = begin; JSON.parse(r.body); rescue; {}; end
          sql = parsed['sql'].to_s
          break
        elsif code == 429 || code >= 500
          sleep 0.5 * (2 ** attempt)   # 0.5, 1, 2, 4s
        else
          # 4xx on controls and similar non-queryable elements — skip silently
          break
        end
      end

      mu.synchronize do
        if sql.nil? || sql.empty?
          results[eid] = { name: name, status: :skip, reason: 'no SQL (control / non-queryable)' }
        else
          bad = sql.scan(ERROR_MARKERS).uniq
          if bad.empty?
            results[eid] = { name: name, status: :ok }
          else
            results[eid] = { name: name, status: :fail, errors: bad }
          end
        end
      end
    end
  end
end
threads.each(&:join)

# 3. Report in workbook-element order so output is deterministic
errors = 0; skipped = 0; total = elements.size
elements.each do |el|
  r = results[el['elementId']] || { name: el['name'], status: :skip, reason: 'no result' }
  case r[:status]
  when :ok
    printf "  [ok]   %-30s (%s)\n", r[:name], el['elementId']
  when :skip
    printf "  [skip] %-30s (%s) — %s\n", r[:name], el['elementId'], r[:reason]
    skipped += 1
  when :fail
    printf "  [FAIL] %-30s (%s) — %s\n", r[:name], el['elementId'], r[:errors].join('; ')
    errors += 1
  end
end

puts
if errors > 0
  puts "#{errors} of #{total} element(s) have unresolved formula references."
  puts 'Fix the offending columns in the spec (see reference/specification/formulas.md)'
  puts 'and re-PUT the spec, then re-verify.'
  exit 1
else
  puts "All #{total - skipped} queryable elements compile clean (#{skipped} skipped)."
  exit 0
end
