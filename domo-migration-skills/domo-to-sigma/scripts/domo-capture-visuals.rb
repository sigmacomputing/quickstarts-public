#!/usr/bin/env ruby
# Phase 1b — visual capture for domo-to-sigma.
#
#   ruby scripts/domo-capture-visuals.rb --pages 123,456
#   ruby scripts/domo-capture-visuals.rb --pages 123 --no-pdf      # skip page PDF
#   ruby scripts/domo-capture-visuals.rb --cards 789,790           # render specific cards
#
# WHY THIS EXISTS
# A Domo migration that only reads DataSets + chart-type strings rebuilds
# dashboards from guesses, and the output looks generically templated (the
# "design still a big issue" feedback). This script captures a VISUAL
# reference — a true PNG per card + a full-page PDF, fed to the build step and
# the MANDATORY layout-visual-qa gate (compare Sigma render <-> Domo source,
# page-to-page). See shared refs/layout-visual-qa.md,
# feedback_phase1d_dashboard_png, batch_converter_png_brief.
#
# This is the automated upgrade of the old Tier-B "manually export each card as
# PNG" fallback in refs/connection.md — it needs the private dev token (Tier A).
#
# NOTE on layout geometry: this script used to ALSO extract card x/y/w/h into
# discovery/layout/<pageId>.json (normalize_layout). That path was a dead end —
# domo-discover.rb's --pages run never read it, so a migration's real card
# coordinates never reached build-domo-layout.rb (it auto-stacked instead).
# Task 1 (lib/domo_sigma_util.rb's DomoSigma.merge_geometry) now copies the
# SAME private-API page-layout geometry directly onto discovery/cards.json
# during domo-discover.rb --pages, which build-domo-layout.rb reads. That is
# the ONE geometry source; this script no longer extracts or emits geometry —
# it only stages PNG/PDF visual references.
#
# Prereqs (see refs/connection.md):
#   export DOMO_INSTANCE=acme DOMO_DEV_TOKEN=...
#   export DOMO_CLIENT_ID=... DOMO_CLIENT_SECRET=...   # for public page() lookup
#   eval "$(scripts/get-domo-token.sh)"                     # sets DOMO_ACCESS_TOKEN
#
# Outputs (all under $DOMO_DISCOVERY_DIR when set — see OUT below):
#   discovery/png/cards/<cardId>.png   per-card visual reference (CHART/KPI cards)
#   discovery/png/cards/<cardId>.pdf   per-card visual reference (TABLE cards — see below)
#   discovery/png/pages/<pageId>.pdf   full-page source reference — ⚠ NOT ALWAYS
#                                      AVAILABLE. The page-render endpoint is a hard
#                                      404 on at least some instances (confirmed live
#                                      2026-07-30). When it is missing this script
#                                      writes page-visual-unavailable.json and the
#                                      layout-visual-qa gate must fall back to the
#                                      per-card visuals. Do not assume the PDF exists.
#
# ⚠ TABLE cards cannot be rendered as PNG: parts=image returns 400 for a
# badge_table card (imageGrid/grid too). They render only with parts=imagePDF,
# whose payload arrives under `html` as an HTML-wrapped base64 PDF, not under
# image.data. See refs/live-validation-2026-07-30.md and Domo.decode_render.

require 'json'
require 'fileutils'
require 'optparse'
require_relative 'lib/domo_rest'

# Honor the run workdir like every sibling script (domo-discover.rb's OUT). This
# used to hardcode the SKILL directory, so a run invoked with --out <workdir>
# still scattered PNGs into the repo working tree (tripping lint-tree-litter).
OUT       = ENV['DOMO_DISCOVERY_DIR'] || File.expand_path('../discovery', __dir__)
CARD_PNG  = File.join(OUT, 'png', 'cards')
PAGE_PDF  = File.join(OUT, 'png', 'pages')
[CARD_PNG, PAGE_PDF].each { |d| FileUtils.mkdir_p(d) }

opts = { pdf: true }
OptionParser.new do |o|
  o.on('--pages IDS', Array) { |v| opts[:pages] = v }
  o.on('--cards IDS', Array) { |v| opts[:cards] = v }
  o.on('--no-pdf')           { opts[:pdf] = false }
  o.on('--width N', Integer) { |v| opts[:width]  = v }
  o.on('--height N', Integer){ |v| opts[:height] = v }
end.parse!(ARGV)

if Domo.dev_token.nil?
  warn <<~MSG
    DOMO_DEV_TOKEN is unset => TIER B (public API only).
    Visual capture requires the private render endpoint, so it is not
    available. Fall back to the manual path in refs/connection.md:
      - export each card as a PNG from the Domo UI,
      - drop them in discovery/png/cards/ named <cardId>.png,
      - capture the full page (UI "Export to PDF") into discovery/png/pages/.
    Then read those images during build + the layout-visual-qa gate.
  MSG
  exit 3
end

WIDTH  = opts[:width]  || 1000
HEIGHT = opts[:height] || 700

# Card ids for a page, from the PUBLIC page() response — the same field
# domo-discover.rb reads (`page['cardIds'] || page['cards']`). No private-API
# layout call is needed here anymore; geometry lives solely in cards.json via
# domo-discover.rb's merge_geometry.
def page_card_ids(public_page)
  Array(public_page['cardIds'] || public_page['cards']).map do |c|
    c.is_a?(Hash) ? (c['id'] || c['cardId'] || c['urn']) : c
  end.compact
end

def write_bytes(path, bytes)
  return warn("  SKIP #{File.basename(path)} (empty render)") if bytes.nil? || bytes.empty?
  File.binwrite(path, bytes)
  warn "  wrote #{path} (#{bytes.bytesize} bytes)"
end

# chartType per card id, read from a prior domo-discover.rb run. Needed because
# TABLE cards take a different render `parts` (see header). Absent cards.json we
# simply try PNG first and fall back to PDF on failure.
def chart_types_by_card
  path = File.join(OUT, 'cards.json')
  cards = JSON.parse(File.read(path)) rescue nil
  return {} unless cards.is_a?(Array)
  cards.each_with_object({}) do |c, h|
    next unless c.is_a?(Hash) && c['id']
    h[c['id'].to_s] = c['chartType'].to_s
  end
end
CHART_TYPES = chart_types_by_card

# A Domo TABLE card. Exact-match the confirmed enum token — badge_datagrid does
# NOT exist (refs/live-validation-2026-07-30.md), so never substring-match here.
def table_card?(card_id)
  CHART_TYPES[card_id.to_s] == 'badge_table'
end

def capture_card_pdf(card_id)
  raw = Domo.private_put_raw("/api/content/v1/cards/kpi/#{card_id}/render",
                             body: { width: WIDTH, height: HEIGHT, queryOverrides: {} },
                             query: { parts: 'imagePDF' })
  write_bytes(File.join(CARD_PNG, "#{card_id}.pdf"), raw && Domo.decode_render(raw))
  true
rescue => e
  warn "  render FAIL card #{card_id} (imagePDF): #{e.message}"
  false
end

def capture_card(card_id)
  # Tables: go straight to imagePDF — parts=image is a guaranteed 400 for them.
  return capture_card_pdf(card_id) if table_card?(card_id)
  png = Domo.render_card_png(card_id, width: WIDTH, height: HEIGHT)
  write_bytes(File.join(CARD_PNG, "#{card_id}.png"), png)
  true
rescue => e
  # An unknown/absent chartType can still turn out to be a table; a 400 here is
  # the signature of that, so retry once as a PDF before reporting failure.
  if e.message.include?('400')
    warn "  card #{card_id}: parts=image 400 — retrying as imagePDF (likely a table card)"
    return capture_card_pdf(card_id)
  end
  warn "  render FAIL card #{card_id}: #{e.message}"
  false
end

# --- per-page capture -------------------------------------------------------
if opts[:pages]
  opts[:pages].each do |pid|
    warn "page #{pid}:"
    public_page = (Domo.page(pid) rescue {}) || {}
    card_ids    = page_card_ids(public_page)
    warn "  #{card_ids.size} card(s)"

    card_ids.each { |cid| capture_card(cid) }

    if opts[:pdf]
      # Full-page reference for the layout-visual-qa source-fidelity comparison.
      #
      # LIVE FINDING (2026-07-30): /api/content/v1/pages/{pageId}/render is a hard
      # **404** on at least some instances — it 404'd for all three pages tested,
      # so the QA gate's primary side-by-side input simply does not exist there.
      # Degrading to per-card visuals is correct, but it must be RECORDED, not
      # just logged: the gate needs to know its reference is missing rather than
      # silently comparing against nothing. No alternative page-render path is
      # known — do not invent one; if you find a working endpoint, document it in
      # refs/live-validation-2026-07-30.md first.
      begin
        pdf = Domo.private_put_raw("/api/content/v1/pages/#{pid}/render",
                                   body: { width: 1600 }, query: { parts: 'imagePDF' })
        write_bytes(File.join(PAGE_PDF, "#{pid}.pdf"), pdf && Domo.decode_render(pdf))
      rescue => e
        warn "  page PDF unavailable (#{e.message}) — rely on per-card visuals for QA"
        marker = File.join(OUT, 'page-visual-unavailable.json')
        prior  = (JSON.parse(File.read(marker)) rescue nil)
        prior  = [] unless prior.is_a?(Array)
        prior << { 'pageId' => pid.to_s, 'reason' => e.message.to_s[0, 300],
                   'fallback' => 'per-card visuals in png/cards/' }
        File.write(marker, JSON.pretty_generate(prior.uniq { |h| h['pageId'] }))
        warn "  recorded #{marker} (layout-visual-qa: no page-level reference for this page)"
      end
    end
  end
end

# --- explicit card list -----------------------------------------------------
if opts[:cards]
  warn 'cards:'
  opts[:cards].each { |cid| capture_card(cid) }
end

unless opts[:pages] || opts[:cards]
  abort 'nothing to do — pass --pages <ids> and/or --cards <ids>'
end

warn "\nNext: run domo-discover.rb --pages <ids> for cards.json geometry (merge_geometry),"
warn "then build-domo-layout.rb. READ discovery/png/** during build + the mandatory"
warn "layout-visual-qa gate."
