#!/usr/bin/env ruby
# Render <out>/readout.html — a customer-facing, share-friendly HTML report for a
# ThoughtSpot -> Sigma migration assessment.
#
# Canonical renderer (replaces the divergent python render_html.py). Reads the
# single assessment.json written by scripts/scan.py. Sigma-branded, byte-aligned
# with the tableau-assessment gold standard.
#
# Usage:
#   ruby scripts/render-readout-html.rb --out ~/thoughtspot-migration
#   ruby scripts/render-readout-html.rb --json /path/assessment.json --out /tmp/x

require 'json'
require 'optparse'
require 'cgi'
require 'date'
require 'set'

opts = {}
OptionParser.new do |p|
  p.on('--out DIR')  { |v| opts[:out]  = v }
  p.on('--json FILE') { |v| opts[:json] = v }
end.parse!
abort('--out required') unless opts[:out]

json_path = opts[:json] || File.join(opts[:out], 'assessment.json')
abort("assessment.json not found at #{json_path}") unless File.exist?(json_path)
d = JSON.parse(File.read(json_path))

def h(s); CGI.escapeHTML(s.to_s); end
def num(n); n.to_i.to_s.reverse.scan(/.{1,3}/).join(',').reverse; end

# ---------- gather computed values ----------
inst = d['instance'] || {}
env  = d['environment_overview'] || {}
host = inst['host'] || 'unknown'
generated_at = inst['generated_at'] || Time.now.strftime('%Y-%m-%d')
formatted_date = Date.parse(generated_at).strftime('%B %d, %Y') rescue generated_at

profiles    = d['profiles'] || []
exportable  = profiles.select { |p| p['exportable'] }
locked      = profiles.reject { |p| p['exportable'] }
shortlist   = d['shortlist'] || exportable
ownership   = d['ownership'] || []
connections = d['connections'] || []
tables      = d['tables'] || []
ds_summary  = d['datasource_summary'] || {}
usage_by_user = d['usage_by_user'] || []
total_views = (d['total_views'] || 0).to_i
usage_available = d['usage_available']
usage_note  = d['usage_note']
coverage    = (d['coverage'] || 0).to_f
chart_types = d['chart_types'] || {}
unsupported_types = d['unsupported_chart_types'] || {}
models_used = d['models_used'] || []

total_viz = chart_types.values.sum
n_unsupported_viz = unsupported_types.values.sum

# usage-ranked profiles (cold = zero views when usage is available)
ranked_by_views = profiles.sort_by { |p| -(p['views'] || 0).to_i }
cold = usage_available ? profiles.select { |p| (p['views'] || 0).to_i.zero? } : []

# shortlist roll-ups
top5 = shortlist.first(5)
sl_top5_views     = top5.sum { |r| (r['views'] || 0).to_i }
sl_total_unsup    = shortlist.sum { |r| (r['unsupported'] || []).size }
sl_migrate_first  = shortlist.count { |r| r['tag'] == 'migrate-first' }
sl_easy_win       = shortlist.count { |r| r['tag'] == 'easy-win' }
sl_needs_scout    = shortlist.count { |r| r['tag'] == 'needs-gap-scout' }
sl_retire         = shortlist.count { |r| r['tag'] == 'retire' }
top5_pct = total_views.zero? ? 0 : (sl_top5_views.to_f / total_views * 100).round
n_with_unsup = exportable.count { |p| (p['unsupported'] || []).any? }

# top owner concentration
top_owner_pct  = 0
top_owner_name = '—'
total_owned = ownership.sum { |o| o['liveboards'].to_i }
if total_owned.positive?
  top = ownership.max_by { |o| o['liveboards'].to_i }
  top_owner_pct  = (top['liveboards'].to_f / total_owned * 100).round
  top_owner_name = top['author']
end

# ---------- HTML helpers ----------
TAG_LABELS = {
  'migrate-first'   => 'Migrate first',
  'easy-win'        => 'Easy win',
  'moderate'        => 'Standard',
  'needs-gap-scout' => 'Needs review',
  'retire'          => 'Retire'
}
TAG_CLASSES = {
  'migrate-first'   => 'tag-go',
  'easy-win'        => 'tag-blue',
  'moderate'        => 'tag-gray',
  'needs-gap-scout' => 'tag-warn',
  'retire'          => 'tag-mute'
}

def tag_pill(t)
  %(<span class="tag #{TAG_CLASSES[t]}">#{h(TAG_LABELS[t] || t)}</span>)
end

# Horizontal bar cell — value normalized to max
def bar_cell(value, max, color = 'bar-blue')
  pct = max.zero? ? 0 : (value.to_f / max * 100).round
  %(<div class="bar-cell"><div class="bar-track"><div class="bar-fill #{color}" style="width:#{pct}%"></div></div><div class="bar-num">#{num(value)}</div></div>)
end

def kpi(label, value, sub = nil)
  s = sub ? %(<div class="kpi-sub">#{h(sub)}</div>) : ''
  %(<div class="kpi"><div class="kpi-v">#{h(value)}</div><div class="kpi-l">#{h(label)}</div>#{s}</div>)
end

# Generic data table renderer.
def table(headers, rows, opts = {})
  cls = opts[:class] || ''
  cols = headers.size
  align = opts[:align] || Array.new(cols, 'left')
  thead = "<thead><tr>" + headers.each_with_index.map { |c, i| %(<th class="al-#{align[i]}">#{h(c)}</th>) }.join + "</tr></thead>"
  tbody = "<tbody>" + rows.map do |r|
    "<tr>" + r.each_with_index.map { |c, i|
      cell = c.to_s
      content = cell.start_with?('<') ? cell : h(cell)
      %(<td class="al-#{align[i]}">#{content}</td>)
    }.join + "</tr>"
  end.join + "</tbody>"
  %(<table class="data #{cls}">#{thead}#{tbody}</table>)
end

# Hero: headline finding
hero_finding =
  if usage_available && total_views.positive?
    if sl_total_unsup.zero? && sl_migrate_first.positive?
      'Pilot migration is low-risk: the most-used Liveboards use only chart types Sigma handles automatically.'
    else
      "The top-5 pilot covers #{top5_pct}% of all-time views. #{n_with_unsup} Liveboard#{n_with_unsup == 1 ? '' : 's'} elsewhere use a chart type that warrants individual review when planning their conversion."
    end
  elsif exportable.any?
    "#{exportable.size} Liveboard#{exportable.size == 1 ? '' : 's'} are readable and ranked by conversion effort. Connect usage data to prioritize by audience."
  else
    'Environment scan complete.'
  end

# ---------- Section 01: KPI tiles ----------
kpi_html = [
  kpi('Liveboards',  env['liveboards'], "#{exportable.size} readable · #{locked.size} system/locked"),
  kpi('Answers',     env['answers']),
  kpi('Models / worksheets', env['models']),
  kpi('Tables',      env['tables'], "#{ds_summary['file_uploaded_tables'] || 0} file-uploaded"),
  kpi('Connections', env['connections'], "#{ds_summary['embrace'] || 0} Embrace · #{ds_summary['falcon'] || 0} Falcon"),
  kpi('Total views', num(total_views), usage_available ? 'last 12 months' : 'usage not connected')
].join

# ---------- Section 02: Liveboard priority & usage ----------
usage_html = ''
if ranked_by_views.any?
  max_v = [ranked_by_views.first['views'].to_i, 1].max
  rows = ranked_by_views.first(10).each_with_index.map do |p, i|
    name = p['name']
    %(<tr>
      <td class="rank">#{i + 1}</td>
      <td>#{h(name)}</td>
      <td class="muted">#{h((p['author'] || '—').to_s.sub(/@.*/, ''))}</td>
      <td>#{bar_cell(p['views'] || 0, max_v)}</td>
      <td class="al-right num muted">#{p['users'] || 0}</td>
      <td class="al-right num muted">#{p['viz'] || '—'}</td>
    </tr>)
  end.join
  usage_html = <<~HTML
    <table class="data">
      <thead>
        <tr>
          <th class="al-right">#</th>
          <th>Liveboard</th>
          <th>Author</th>
          <th>Views</th>
          <th class="al-right">Distinct users</th>
          <th class="al-right">Viz</th>
        </tr>
      </thead>
      <tbody>#{rows}</tbody>
    </table>
  HTML
end

# ---------- Section 03: Ownership & concentration ----------
ownership_html = ''
if ownership.any?
  max_lb = [ownership.first['liveboards'].to_i, 1].max
  rows = ownership.first(15).map do |o|
    %(<tr>
      <td>#{h(o['author'])}</td>
      <td>#{bar_cell(o['liveboards'], max_lb)}</td>
    </tr>)
  end.join
  ownership_html = <<~HTML
    <table class="data">
      <thead><tr><th>Author</th><th>Liveboards</th></tr></thead>
      <tbody>#{rows}</tbody>
    </table>
  HTML
end

# ---------- Section 04: Data-source patterns ----------
ds_stat_row = <<~ROW
  <div class="stat-row">
    <div class="stat #{(ds_summary['embrace'] || 0).positive? ? 'stat-go' : ''}">
      <div class="stat-l">Embrace (live)</div>
      <div class="stat-v #{(ds_summary['embrace'] || 0).positive? ? 'go' : ''}">#{ds_summary['embrace'] || 0}</div>
      <div class="stat-sub">query pushed to the warehouse — Sigma connects to the same source</div>
    </div>
    <div class="stat #{(ds_summary['falcon'] || 0).positive? ? 'stat-warn' : ''}">
      <div class="stat-l">Falcon (in-memory)</div>
      <div class="stat-v #{(ds_summary['falcon'] || 0).positive? ? 'warn' : ''}">#{ds_summary['falcon'] || 0}</div>
      <div class="stat-sub">in-memory cache — data must live in a warehouse for Sigma</div>
    </div>
    <div class="stat #{(ds_summary['file_uploaded_tables'] || 0).positive? ? 'stat-warn' : ''}">
      <div class="stat-l">File-uploaded tables</div>
      <div class="stat-v #{(ds_summary['file_uploaded_tables'] || 0).positive? ? 'warn' : ''}">#{ds_summary['file_uploaded_tables'] || 0}</div>
      <div class="stat-sub">CSV/XLSX uploads — land in your warehouse first</div>
    </div>
  </div>
ROW

conn_html = ''
if connections.any?
  rows = connections.first(20).map do |c|
    badge_cls = c['class'] == 'embrace' ? 'ds-published' : 'ds-embedded'
    badge = c['class'] == 'embrace' ? 'Embrace — live' : (c['class'] == 'falcon' ? 'Falcon — in-memory' : 'Unknown')
    %(<tr>
      <td>#{h(c['name'])}</td>
      <td><span class="ds-bucket #{badge_cls}">#{h(badge)}</span></td>
      <td><code>#{h(c['connection_type'] || '—')}</code></td>
      <td class="muted">#{h((c['author'] || '—').to_s.sub(/@.*/, ''))}</td>
    </tr>)
  end.join
  conn_html = <<~HTML
    <table class="data">
      <thead><tr><th>Connection</th><th>Type</th><th>Connector class</th><th>Author</th></tr></thead>
      <tbody>#{rows}</tbody>
    </table>
  HTML
end

uploaded_tables = tables.select { |t| t['file_uploaded'] }
uploaded_html = ''
if uploaded_tables.any?
  uploaded_html = %(<p class="note"><strong>#{uploaded_tables.size} file-uploaded table#{uploaded_tables.size == 1 ? '' : 's'}</strong> (no governed warehouse source): ) +
                  uploaded_tables.first(20).map { |t| %(<code>#{h(t['name'])}</code>) }.join(', ') +
                  (uploaded_tables.size > 20 ? " + #{uploaded_tables.size - 20} more" : '') +
                  ' — these need a one-time load into your warehouse before the Sigma model can reference them.</p>'
end

# ---------- Section 05: User activity (only if BI Server usage present) ----------
activity_html = ''
if usage_by_user.any?
  max_a = [usage_by_user.first['actions'].to_i, 1].max
  rows = usage_by_user.first(15).map do |u|
    %(<tr>
      <td>#{h(u['user'].to_s.sub(/@.*/, ''))}</td>
      <td>#{bar_cell(u['actions'], max_a)}</td>
    </tr>)
  end.join
  activity_html = <<~HTML
    <table class="data">
      <thead><tr><th>User</th><th>Actions (last 12 months)</th></tr></thead>
      <tbody>#{rows}</tbody>
    </table>
  HTML
end

# ---------- Section 06: Migration shortlist + per-Liveboard complexity ----------
shortlist_html = ''
if shortlist.any?
  max_score = [shortlist.map { |r| r['value_cost'].to_f }.max || 0, 0.001].max
  rows = shortlist.first(15).map do |r|
    unsup = r['unsupported'] || []
    risk_cls, risk_txt =
      if unsup.any?
        ['risk-red', "#{unsup.size} chart type#{unsup.size == 1 ? '' : 's'} to review"]
      elsif (r['n_formula'] || 0).positive?
        ['risk-amber', "#{r['n_formula']} formula#{r['n_formula'] == 1 ? '' : 's'}"]
      else
        ['risk-clean', 'No issues']
      end
    %(<tr>
      <td>#{h(r['name'])}</td>
      <td>#{bar_cell(r['views'] || 0, [ranked_by_views.first&.dig('views').to_i, 1].max)}</td>
      <td class="al-right num">#{r['users'] || 0}</td>
      <td><span class="risk-chip #{risk_cls}"><span class="risk-dot"></span>#{h(risk_txt)}</span></td>
      <td class="al-right num">#{format('%.3f', r['value_cost'] || 0)}</td>
      <td>#{tag_pill(r['tag'])}</td>
    </tr>)
  end.join
  shortlist_html = <<~HTML
    <table class="data shortlist">
      <thead>
        <tr>
          <th>Liveboard</th>
          <th>Usage</th>
          <th class="al-right">Users</th>
          <th>Conversion risk</th>
          <th class="al-right">Value/cost</th>
          <th>Recommendation</th>
        </tr>
      </thead>
      <tbody>#{rows}</tbody>
    </table>
    <p class="note">Conversion risk legend: <strong>No issues</strong> = every chart type and field converts automatically · <strong>N formulas</strong> = converts automatically; TML formulas translate to Sigma formulas with a quick check · <strong>N chart types to review</strong> = uses a chart kind without a 1:1 Sigma mapping yet, warranting individual evaluation.</p>
  HTML
end

complexity_html = ''
if exportable.any?
  rows = exportable.sort_by { |p| -p['complexity'].to_i }.map do |p|
    unsup = p['unsupported'] || []
    unsup_cell = unsup.any? ? %(<span class="warn-num">#{unsup.size}</span>) : '<span class="muted">0</span>'
    types_cell = p['chart_types'].to_h.sort_by { |_, n| -n }.map { |k, n| "#{h(k)}×#{n}" }.join(', ')
    %(<tr>
      <td>#{h(p['name'])}</td>
      <td class="al-right num">#{p['viz']}</td>
      <td class="al-right num muted">#{(p['chart_types'] || {}).size}</td>
      <td class="al-right num muted">#{(p['models'] || []).size}</td>
      <td class="al-right num muted">#{p['n_formula'] || 0}</td>
      <td class="al-right num">#{p['complexity']}</td>
      <td class="al-right">#{unsup_cell}</td>
      <td class="muted breakdown">#{types_cell}</td>
    </tr>)
  end.join
  complexity_html = <<~HTML
    <h3>Per-Liveboard complexity</h3>
    <table class="data">
      <thead>
        <tr>
          <th>Liveboard</th>
          <th class="al-right">Viz</th>
          <th class="al-right">Chart kinds</th>
          <th class="al-right">Models</th>
          <th class="al-right">TML formulas</th>
          <th class="al-right">Complexity</th>
          <th class="al-right">Review</th>
          <th>Chart types</th>
        </tr>
      </thead>
      <tbody>#{rows}</tbody>
    </table>
    <p class="note">Complexity = viz count + 2×chart kinds + 3×models + 2×TML formulas + filters. A relative effort proxy, not a time estimate.</p>
  HTML
end

# Chart-type coverage bars
coverage_html = ''
if total_viz.positive?
  max_n = chart_types.values.max
  rows = chart_types.sort_by { |_, n| -n }.map do |k, n|
    unsup = unsupported_types.key?(k)
    color = unsup ? 'bar-warn' : 'bar-blue'
    [
      %(<code>#{h(k)}</code>),
      bar_cell(n, max_n, color),
      unsup ? %(<span class="risk-chip risk-amber"><span class="risk-dot"></span>Needs mapping</span>) : %(<span class="risk-chip risk-clean"><span class="risk-dot"></span>Supported</span>)
    ]
  end
  coverage_html = "<h3>Chart-type coverage — #{format('%.1f', coverage)}% (#{total_viz - n_unsupported_viz}/#{total_viz} viz supported)</h3>" +
                  table(['Chart type', 'Count', 'Sigma readiness'], rows, align: %w[left left left]) +
                  %(<p class="note">Supported types map to Sigma via the <code>thoughtspot-to-sigma</code> pipeline today. Types flagged for mapping (PIVOT_TABLE, WATERFALL, FUNNEL, SCATTER, BUBBLE, TREEMAP, GEO_AREA, LINE_STACKED_COLUMN) are mostly native in Sigma — they just need element-builder mapping work.</p>)
end

models_used_html = ''
if models_used.any?
  models_used_html = %(<p class="note"><strong>#{models_used.size} model#{models_used.size == 1 ? '' : 's'}/worksheet#{models_used.size == 1 ? '' : 's'}</strong> referenced by the exportable Liveboards — migrate these to Sigma data models first: ) +
                     models_used.first(20).map { |m| %(<code>#{h(m)}</code>) }.join(', ') +
                     (models_used.size > 20 ? " + #{models_used.size - 20} more" : '') + '.</p>'
end

# ---------- estimated migration effort (token model) ----------
effort_html = ''
token_model_path = File.join(__dir__, '..', 'refs', 'token-model.json')
if shortlist.any? && File.exist?(token_model_path)
  tm = JSON.parse(File.read(token_model_path)) rescue nil
  if tm
    bucket  = 'mechanical'
    n_dash  = shortlist.size
    n_rev   = n_with_unsup
    pd      = (tm['per_dashboard'] || {})[bucket] || {}
    pr      = tm['per_review_item'] || {}
    cal     = tm['calibration'] || {}
    est = lambda { |m| (pd["#{m}_usd"].to_f * n_dash) + (pr["#{m}_usd"].to_f * n_rev) }
    opus_usd   = est.call('opus')
    sonnet_usd = est.call('sonnet')
    fmt = lambda { |v| '$' + format('%.2f', v) }
    effort_num = format('%02d', section_n + 1)
    effort_html = <<~HTML
      <section>
        <div class="section-head">
          <span class="section-num">#{effort_num}</span>
          <h2 class="section-title">Estimated migration effort (tokens / $)</h2>
          <span class="section-aside">one-shot orchestrator path</span>
        </div>
        <p class="section-lede">A planning estimate of the LLM cost to migrate the shortlisted Liveboards via the <code>thoughtspot-to-sigma</code> one-shot orchestrator. The mechanical model converter is deterministic, so per-Liveboard cost is flat; each Liveboard flagged for review adds one human-decision round.</p>
        <div class="stat-row">
          <div class="stat stat-go">
            <div class="stat-l">Estimated cost · Opus</div>
            <div class="stat-v go">#{fmt.call(opus_usd)}</div>
            <div class="stat-sub">#{n_dash} Liveboards + #{n_rev} review</div>
          </div>
          <div class="stat">
            <div class="stat-l">Estimated cost · Sonnet</div>
            <div class="stat-v">#{fmt.call(sonnet_usd)}</div>
            <div class="stat-sub">same scope, Sonnet pricing</div>
          </div>
          <div class="stat">
            <div class="stat-l">Basis</div>
            <div class="stat-v" style="font-size:20px;">#{n_dash}<span style="font-size:14px;color:var(--mute);font-weight:600;"> × per-dashboard</span></div>
            <div class="stat-sub">+ #{n_rev} item#{n_rev == 1 ? '' : 's'} need review</div>
          </div>
        </div>
        <table class="data">
          <thead>
            <tr><th>Component</th><th class="al-right">Opus</th><th class="al-right">Sonnet</th></tr>
          </thead>
          <tbody>
            <tr><td>#{n_dash} Liveboards × per-dashboard</td><td class="al-right num">#{fmt.call(pd['opus_usd'].to_f * n_dash)}</td><td class="al-right num">#{fmt.call(pd['sonnet_usd'].to_f * n_dash)}</td></tr>
            <tr><td>+ #{n_rev} item#{n_rev == 1 ? '' : 's'} need review</td><td class="al-right num">#{fmt.call(pr['opus_usd'].to_f * n_rev)}</td><td class="al-right num">#{fmt.call(pr['sonnet_usd'].to_f * n_rev)}</td></tr>
            <tr><td><strong>Total estimated</strong></td><td class="al-right num"><strong>#{fmt.call(opus_usd)}</strong></td><td class="al-right num"><strong>#{fmt.call(sonnet_usd)}</strong></td></tr>
          </tbody>
        </table>
        <p class="note">Calibrated #{h(cal['date'])}, one-shot orchestrator path — LLM cost only; rescale $ by your coding agent's pricing. A naive agent-driven migration is ~12–20× more expensive.</p>
      </section>
    HTML
  end
end

# ---------- assemble HTML ----------
html = <<~HTML
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ThoughtSpot Environment Report — #{h(host)}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=DM+Mono:wght@400;500&display=swap');
  :root {
    /* Sigma brand palette — Shadow/Nimbus/White neutrals, Insight (CTA only), brand accents */
    --bg:#fafafa; --card:#ffffff; --ink:#292929; --ink-2:#3d3d3d;
    --line:#e5e5e5; --line-soft:#f5f5f5;
    --accent:#292929; --accent-soft:#f0f0f0;
    --insight:#f0ff45;
    --go:#1f9d57; --go-soft:#e6fbef;
    --warn:#c2562a; --warn-soft:#fff1ea;
    --blue:#2b8ca6; --blue-soft:#eaf8fc;
    --mute:#6e7877; --mute-soft:#f0f0f0;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--ink); }
  body {
    font-family: "DM Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    font-size: 14px; line-height: 1.55; -webkit-font-smoothing: antialiased;
  }
  main { max-width: 1120px; margin: 0 auto; padding: 48px 48px 80px; }

  /* Brand masthead */
  .brand-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 28px; }
  .brand-mark { font-weight: 700; font-size: 21px; letter-spacing: -0.02em; color: var(--ink); }
  .brand-dot  { width: 9px; height: 9px; border-radius: 2px; background: var(--blue);
                -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .brand-tag  { font-size: 12px; color: var(--mute); font-weight: 500;
                text-transform: uppercase; letter-spacing: 0.08em; }

  /* Header */
  .doc-header { margin-bottom: 40px; }
  .doc-eyebrow { font-size: 11px; font-weight: 600; color: var(--accent);
                 text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }
  .doc-title { font-size: 36px; font-weight: 700; letter-spacing: -0.02em;
               margin: 0 0 8px; line-height: 1.1; color: var(--ink); }
  .doc-meta { font-size: 13px; color: var(--ink-2); }
  .doc-meta a { color: var(--ink-2); text-decoration: none; border-bottom: 1px dashed var(--line); }
  .doc-meta a:hover { color: var(--ink); }

  /* Hero finding banner */
  .hero {
    background: var(--accent-soft); border: 1px solid var(--line);
    border-left: 4px solid var(--blue);
    border-radius: 8px;
    padding: 18px 22px; margin-bottom: 40px;
    display: flex; align-items: center; gap: 16px;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .hero-label { font-size: 11px; font-weight: 700; color: var(--accent);
                text-transform: uppercase; letter-spacing: 0.08em;
                white-space: nowrap; padding-right: 16px;
                border-right: 1px solid var(--line); }
  .hero-text { font-size: 15px; color: var(--ink); font-weight: 500; line-height: 1.4; }

  /* Section */
  section { margin-bottom: 56px; }
  section.section-tight { margin-bottom: 36px; }
  .section-head { display: flex; align-items: baseline; justify-content: space-between;
                  margin-bottom: 16px; padding-bottom: 12px;
                  border-bottom: 1px solid var(--line); }
  .section-num { font-size: 12px; font-weight: 600; color: var(--mute);
                 letter-spacing: 0.06em; }
  .section-title { font-size: 22px; font-weight: 600; letter-spacing: -0.01em;
                   margin: 0; flex: 1; padding-left: 14px; }
  .section-aside { font-size: 12px; color: var(--mute); }
  .section-lede { font-size: 14px; color: var(--ink-2); margin: -4px 0 16px; }

  /* KPIs */
  .kpi-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
  .kpi {
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 18px 16px;
  }
  .kpi-v { font-size: 28px; font-weight: 700; letter-spacing: -0.01em;
           color: var(--ink); line-height: 1; }
  .kpi-l { font-size: 11px; color: var(--mute); text-transform: uppercase;
           letter-spacing: 0.06em; font-weight: 600; margin-top: 10px; }
  .kpi-sub { font-size: 11px; color: var(--mute); margin-top: 4px; line-height: 1.4; }

  /* Stat callouts */
  .stat-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
              margin-bottom: 24px; }
  .stat {
    background: #fafafa;
    border: 1px solid var(--line); border-left: 3px solid var(--accent);
    border-radius: 8px;
    padding: 16px 18px;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .stat.stat-go   { border-left-color: var(--go);   background: var(--go-soft); }
  .stat.stat-warn { border-left-color: var(--warn); background: var(--warn-soft); }
  .stat-l { font-size: 10px; color: var(--mute); text-transform: uppercase;
            letter-spacing: 0.06em; font-weight: 700; margin-bottom: 6px; }
  .stat-v { font-size: 30px; font-weight: 700; line-height: 1; letter-spacing: -0.02em;
            color: var(--ink); }
  .stat-v.go   { color: var(--go); }
  .stat-v.warn { color: var(--warn); }
  .stat-sub { font-size: 12px; color: var(--mute); margin-top: 6px; }

  /* Tables */
  table.data { width: 100%; border-collapse: collapse; background: var(--card);
               border: 1px solid var(--line); border-radius: 10px; overflow: hidden;
               font-size: 13px; }
  table.data th { font-weight: 600; font-size: 11px; color: var(--mute);
                  text-transform: uppercase; letter-spacing: 0.06em;
                  padding: 12px 16px; background: #fafafa;
                  border-bottom: 1px solid var(--line); text-align: left; }
  table.data td { padding: 12px 16px; border-bottom: 1px solid var(--line-soft);
                  vertical-align: middle; }
  table.data tbody tr:last-child td { border-bottom: 0; }
  table.data tbody tr:hover td { background: #fafafa; }
  .al-right { text-align: right; }
  .al-left  { text-align: left; }
  /* Pin numeric + bar columns to content width so the text column absorbs the
     slack — keeps a short value tight against its header instead of stranding it
     across an over-wide column. */
  table.data td.al-right, table.data th.al-right,
  table.data td:has(.bar-cell) { width: 1%; white-space: nowrap; }
  .num { font-variant-numeric: tabular-nums; }
  .muted { color: var(--mute); }
  .warn { color: var(--warn); }
  .warn-num { color: var(--warn); font-weight: 700; }
  .rank { font-variant-numeric: tabular-nums; color: var(--mute); font-weight: 600; width: 32px; }
  .workbook-link { color: var(--ink); text-decoration: none;
                   border-bottom: 1px solid var(--line); }
  .workbook-link:hover { color: var(--accent); border-bottom-color: var(--accent); }
  .breakdown { font-size: 12px; font-variant-numeric: tabular-nums; }
  .breakdown span { margin-right: 8px; }

  /* Tags */
  .tag { display: inline-block; padding: 3px 10px; border-radius: 99px;
         font-size: 11px; font-weight: 600; letter-spacing: 0.01em;
         white-space: nowrap; }
  .tag-go    { background: var(--go-soft);    color: var(--go); }
  .tag-blue  { background: var(--blue-soft);  color: var(--blue); }
  .tag-gray  { background: #f5f5f5;           color: var(--ink-2); }
  .tag-warn  { background: var(--warn-soft);  color: var(--warn); }
  .tag-mute  { background: var(--mute-soft);  color: var(--mute); }

  /* Bar cells (in tables) */
  .bar-cell { display: flex; align-items: center; gap: 10px;
              justify-content: flex-start; }
  .bar-track { flex: none; width: 84px; height: 6px; background: #f5f5f5; border-radius: 4px;
               overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 4px; }
  .bar-blue { background: linear-gradient(90deg, #4cec8c, #2fb874); }
  .bar-warn { background: linear-gradient(90deg, #f0a868, #c2562a); }
  .bar-num { font-variant-numeric: tabular-nums; font-weight: 600;
             min-width: 36px; text-align: right; }

  /* Data-source bucket badge */
  .ds-bucket { display: inline-block; padding: 3px 10px; border-radius: 6px;
               font-size: 11px; font-weight: 600;
               -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .ds-published { background: var(--blue-soft); color: var(--blue); }
  .ds-embedded  { background: #f5f5f5; color: var(--ink-2); }

  /* Risk chip — used in shortlist + verdicts + coverage */
  .risk-chip { display: inline-flex; align-items: center; gap: 6px;
               font-size: 12px; font-variant-numeric: tabular-nums; }
  .risk-dot { width: 8px; height: 8px; border-radius: 50%;
              -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .risk-clean .risk-dot { background: var(--go); }
  .risk-clean             { color: var(--go); font-weight: 600; }
  .risk-green .risk-dot { background: #84cc16; }
  .risk-green             { color: var(--ink-2); }
  .risk-amber .risk-dot { background: #f59e0b; }
  .risk-amber             { color: #a16207; font-weight: 600; }
  .risk-red   .risk-dot { background: var(--warn); }
  .risk-red               { color: var(--warn); font-weight: 700; }
  .risk-mute  .risk-dot { background: var(--mute); }
  .risk-mute              { color: var(--mute); }

  /* Cluster member display */
  .cluster-member { padding: 2px 0; font-size: 12px; line-height: 1.4; }
  .cluster-member + .cluster-member { border-top: 1px dashed var(--line-soft); }

  /* Inline user pill (top-users cell) */
  .inline-pill { display: inline-block; padding: 1px 7px; border-radius: 99px;
                 font-size: 11px; background: #f1f5f9; color: var(--ink-2);
                 font-variant-numeric: tabular-nums; margin-right: 4px;
                 -webkit-print-color-adjust: exact; print-color-adjust: exact; }

  /* Top-view cell — most-used view per workbook */
  .top-view-cell { font-size: 12px; line-height: 1.3; }
  .top-view-pct  { font-size: 11px; margin-top: 2px; }

  /* Per-user top-workbook list (inside table cell) */
  .top-wb { font-size: 11px; line-height: 1.4; display: flex;
            justify-content: space-between; gap: 12px;
            padding: 1px 0; }
  .top-wb + .top-wb { border-top: 1px dotted var(--line-soft); padding-top: 3px; margin-top: 3px; }
  .top-wb span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }

  /* Unique-to-user expander */
  details.unique-detail { font-size: 11px; }
  details.unique-detail summary { cursor: pointer; color: var(--accent); font-weight: 600;
                                  list-style: none; padding: 2px 0; }
  details.unique-detail summary::-webkit-details-marker { display: none; }
  details.unique-detail summary::before { content: '▸ '; color: var(--mute); }
  details.unique-detail[open] summary::before { content: '▾ '; }
  details.unique-detail div { padding-left: 12px; font-size: 11px; line-height: 1.4; }

  /* Notes + callouts */
  .note { font-size: 12px; color: var(--mute); font-style: italic;
          margin: 12px 0 0; }
  .callout {
    background: var(--warn-soft); border-left: 3px solid var(--warn);
    padding: 12px 16px; border-radius: 6px; margin-top: 16px;
    font-size: 13px; color: #7c2d12;
  }
  .callout strong { color: #7c2d12; }
  .callout code { background: rgba(0,0,0,0.06); padding: 1px 5px; border-radius: 3px;
                  font-size: 12px; }

  code { font-family: "DM Mono", ui-monospace, "SF Mono", Menlo, monospace; font-size: 12.5px;
         background: var(--line-soft); padding: 1px 6px; border-radius: 4px; }

  /* Next steps */
  ol.next-steps { margin: 0; padding-left: 0; counter-reset: step;
                  list-style: none; }
  ol.next-steps li { counter-increment: step; padding: 14px 0 14px 44px;
                     position: relative; border-bottom: 1px solid var(--line-soft);
                     font-size: 14px; }
  ol.next-steps li:last-child { border-bottom: 0; }
  ol.next-steps li::before {
    content: counter(step); position: absolute; left: 0; top: 14px;
    width: 28px; height: 28px; border-radius: 50%;
    background: var(--accent-soft); color: var(--accent);
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums;
  }
  ol.next-steps li strong { color: var(--ink); }

  /* Privacy two-column */
  .priv-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  .priv-col h3 { font-size: 13px; font-weight: 600; color: var(--ink);
                 margin: 0 0 10px; text-transform: uppercase; letter-spacing: 0.04em; }
  .priv-col ul { margin: 0; padding-left: 0; list-style: none; }
  .priv-col li { padding: 6px 0 6px 22px; position: relative;
                 font-size: 13px; color: var(--ink-2); }
  .priv-col.crossed li::before {
    content: '→'; position: absolute; left: 0; color: var(--warn); font-weight: 700;
  }
  .priv-col.local li::before {
    content: '◊'; position: absolute; left: 0; color: var(--go); font-weight: 700;
  }

  footer { color: var(--mute); font-size: 11px; text-align: center;
           margin-top: 56px; padding-top: 20px; border-top: 1px solid var(--line); }

  @media print {
    @page { margin: 0.6in 0.5in 0.6in; size: letter portrait; }
    body { background: white; font-size: 11.5px; }
    main { max-width: none; padding: 0; }
    .doc-header { margin-bottom: 18px; }
    .doc-title { font-size: 26px; }
    .hero { margin-bottom: 24px; padding: 12px 16px; page-break-after: avoid; }
    .hero-text { font-size: 13px; }
    section { margin-bottom: 24px; page-break-inside: auto; }
    section.section-tight { margin-bottom: 18px; }
    .section-head { margin-bottom: 10px; padding-bottom: 8px; page-break-after: avoid; }
    .section-title { font-size: 16px; }
    .section-lede { font-size: 12px; margin: -2px 0 10px; }
    .kpi-grid { gap: 8px; }
    .kpi { padding: 12px; }
    .kpi-v { font-size: 22px; }
    .kpi-l { font-size: 10px; margin-top: 6px; }
    .kpi-sub { font-size: 10px; margin-top: 3px; }
    .stat-row { gap: 8px; margin-bottom: 14px; }
    .stat { padding: 12px 14px; }
    .stat-v { font-size: 24px; }
    table.data { font-size: 11px; page-break-inside: auto; }
    table.data thead { display: table-header-group; }
    table.data th { padding: 8px 10px; font-size: 10px; }
    table.data td { padding: 8px 10px; }
    table.data tr { page-break-inside: avoid; page-break-after: auto; }
    .tag, .ds-bucket { font-size: 10px; padding: 2px 8px; }
    .bar-track { max-width: 60px; height: 5px; }
    .note { font-size: 11px; }
    .callout { padding: 8px 12px; font-size: 11px; }
    ol.next-steps li { padding: 10px 0 10px 36px; font-size: 12px; }
    ol.next-steps li::before { width: 22px; height: 22px; font-size: 11px; top: 10px; }
    .priv-col li { font-size: 11px; padding: 4px 0 4px 18px; }
    footer { margin-top: 24px; padding-top: 12px; }
    /* Force backgrounds + colors to render */
    .hero, .kpi, .stat, table.data, table.data th, .ds-bucket, .tag,
    .bar-track, .bar-fill, .risk-dot, .callout, ol.next-steps li::before {
      -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important;
    }
    /* Avoid awkward page splits at section boundaries */
    section h2, .section-head { page-break-after: avoid; }
    .stat-row, .priv-grid { page-break-inside: avoid; }
  }
</style>
</head>
<body>
<main>

<div class="brand-bar">
  <span class="brand-dot"></span>
  <span class="brand-mark">sigma</span>
  <span class="brand-tag">Migration Assessment</span>
</div>
<div class="doc-header">
  <div class="doc-eyebrow">ThoughtSpot Environment Report</div>
  <h1 class="doc-title">#{h(host)}</h1>
  <div class="doc-meta">Generated #{h(formatted_date)}</div>
</div>

<div class="hero">
  <div class="hero-label">Headline finding</div>
  <div class="hero-text">#{h(hero_finding)}</div>
</div>

<section>
  <div class="section-head">
    <span class="section-num">01</span>
    <h2 class="section-title">Environment overview</h2>
  </div>
  <div class="kpi-grid">#{kpi_html}</div>
</section>

<section>
  <div class="section-head">
    <span class="section-num">02</span>
    <h2 class="section-title">Liveboard priority &amp; usage</h2>
    <span class="section-aside">Top 10 of #{env['liveboards']} Liveboards · #{num(total_views)} total views</span>
  </div>
  <p class="section-lede">Liveboards ranked by all-time interactive views from the <code>TS: BI Server</code> system worksheet — ThoughtSpot's built-in usage log. This is the foundation of any migration plan: focus effort where audience attention already is.</p>
  #{usage_html}
  #{usage_available ? '' : %(<p class="note">Usage data was not available for this run (#{h(usage_note)}). Liveboards above are ordered as listed; connect an admin identity to rank by views.</p>)}
  #{cold.any? ? %(<p class="note"><strong>#{cold.size} Liveboard#{cold.size == 1 ? '' : 's'}</strong> have zero recorded views in the window: ) + cold.first(15).map { |p| %(<code>#{h(p['name'])}</code>) }.join(', ') + (cold.size > 15 ? " + #{cold.size - 15} more" : '') + ' — strong candidates for retirement.</p>' : ''}
</section>

<section>
  <div class="section-head">
    <span class="section-num">03</span>
    <h2 class="section-title">Ownership &amp; concentration</h2>
    <span class="section-aside">#{ownership.size} author#{ownership.size == 1 ? '' : 's'}</span>
  </div>
  <p class="section-lede">Liveboard authorship across the instance. High concentration in one or two authors is a governance signal — what happens to their content if they leave?</p>
  #{ownership_html}
  #{total_owned.positive? ? %(<p class="note">Top-author concentration: <strong>#{top_owner_pct}%</strong> of Liveboards authored by <code>#{h(top_owner_name)}</code>.</p>) : ''}
</section>

<section>
  <div class="section-head">
    <span class="section-num">04</span>
    <h2 class="section-title">Data-source patterns</h2>
    <span class="section-aside">#{env['connections']} connection#{env['connections'] == 1 ? '' : 's'} · #{env['tables']} tables</span>
  </div>
  <p class="section-lede">How data reaches your Liveboards. <strong>Embrace</strong> connections push queries live to a warehouse — Sigma connects to the same source with no data movement. <strong>Falcon</strong> (in-memory) and <strong>file-uploaded</strong> tables hold data inside ThoughtSpot and must be landed in a warehouse before Sigma can model them.</p>
  #{ds_stat_row}
  #{conn_html}
  #{uploaded_html}
</section>

HTML

# Section 05: User activity (conditional)
section_n = 5
if activity_html != ''
  html += <<~HTML
  <section>
    <div class="section-head">
      <span class="section-num">05</span>
      <h2 class="section-title">User activity</h2>
      <span class="section-aside">Top 15 of #{usage_by_user.size} active user#{usage_by_user.size == 1 ? '' : 's'}</span>
    </div>
    <p class="section-lede">Per-user action volume from the <code>TS: BI Server</code> log over the last 12 months. This is the population that needs to land smoothly on Sigma.</p>
    #{activity_html}
  </section>

  HTML
  section_n = 6
end

mig_num  = format('%02d', section_n)
priv_num = format('%02d', section_n + 2)
next_num = format('%02d', section_n + 3)

# Section: Migration shortlist + complexity
html += <<~HTML
<section>
  <div class="section-head">
    <span class="section-num">#{mig_num}</span>
    <h2 class="section-title">Migration to Sigma — recommended sequence</h2>
    <span class="section-aside">#{shortlist.size} exportable Liveboards · #{format('%.1f', coverage)}% chart-type coverage</span>
  </div>
  <p class="section-lede">If you choose to migrate to Sigma, this is the order that minimizes risk while covering the most user impact. Liveboards are ranked by usage value relative to conversion complexity. The top of the list is the recommended starting point for a pilot.</p>

  <div class="stat-row">
    <div class="stat">
      <div class="stat-l">Top-5 usage share</div>
      <div class="stat-v">#{top5_pct}<span style="font-size: 16px; color: var(--mute); font-weight: 600;">%</span></div>
      <div class="stat-sub">of #{num(total_views)} total views</div>
    </div>
    <div class="stat stat-#{sl_total_unsup.zero? ? 'go' : 'warn'}">
      <div class="stat-l">Chart types to review</div>
      <div class="stat-v #{sl_total_unsup.zero? ? 'go' : 'warn'}">#{sl_total_unsup}</div>
      <div class="stat-sub">unsupported chart kinds across the shortlist</div>
    </div>
    <div class="stat">
      <div class="stat-l">Needs review · Retire</div>
      <div class="stat-v">#{sl_needs_scout}<span style="font-size: 16px; color: var(--mute); font-weight: 600;"> · #{sl_retire}</span></div>
      <div class="stat-sub">Liveboards of #{shortlist.size} total</div>
    </div>
  </div>

  #{shortlist_html}
  #{complexity_html}
  #{coverage_html}
  #{models_used_html}
  #{sl_total_unsup.positive? ?
    %(<div class="callout"><strong>#{n_with_unsup} Liveboard#{n_with_unsup == 1 ? '' : 's'}</strong> use a chart type without a 1:1 Sigma mapping in the current pipeline (PIVOT_TABLE, WATERFALL, FUNNEL, SCATTER, BUBBLE, TREEMAP, GEO_AREA, LINE_STACKED_COLUMN). Sigma supports most of these natively — they just need element-builder mapping work, identified up-front so there are no surprises mid-migration.</div>) : ''}
</section>
HTML
html += effort_html
html += <<~HTML

<section class="section-tight">
  <div class="section-head">
    <span class="section-num">#{priv_num}</span>
    <h2 class="section-title">Data handling</h2>
  </div>
  <p class="section-lede">This report was generated by an LLM-driven scan of your ThoughtSpot instance. What that means for the data that left your environment:</p>
  <div class="priv-grid">
    <div class="priv-col crossed">
      <h3>Read by the scanner</h3>
      <ul>
        <li>Aggregate counts (Liveboard, Answer, model, table, connection totals)</li>
        <li>Liveboard names, author names, connection names</li>
        <li>Per-object views &amp; distinct users from <code>TS: BI Server</code></li>
        <li>Liveboard TML — visualization config, chart types, referenced models, TML formula text</li>
      </ul>
    </div>
    <div class="priv-col local">
      <h3>Never left your environment</h3>
      <ul>
        <li>Underlying warehouse rows — the scan never queries source data</li>
        <li>Falcon in-memory data and uploaded file contents</li>
        <li>Database / connection credentials</li>
        <li>Answer result-set data — only metadata is read</li>
      </ul>
    </div>
  </div>
</section>

<section class="section-tight">
  <div class="section-head">
    <span class="section-num">#{next_num}</span>
    <h2 class="section-title">Recommended next steps</h2>
  </div>
  <ol class="next-steps">
    <li><strong>Pilot the top #{[5, shortlist.size].min} Liveboard#{[5, shortlist.size].min == 1 ? '' : 's'}.</strong> They represent #{top5_pct}% of total interactive views with #{sl_total_unsup} chart type#{sl_total_unsup == 1 ? '' : 's'} flagged for review between them — the lowest-risk way to demonstrate end-to-end migration with the <code>thoughtspot-to-sigma</code> skill.</li>
HTML

if models_used.any?
  html += "    <li><strong>Migrate the #{models_used.size} referenced model#{models_used.size == 1 ? '' : 's'}/worksheet#{models_used.size == 1 ? '' : 's'} to Sigma data models first.</strong> Liveboards re-point to a converted data model, so building these up-front lets multiple Liveboards share one model.</li>\n"
end
if (ds_summary['file_uploaded_tables'] || 0).positive? || (ds_summary['falcon'] || 0).positive?
  n_land = (ds_summary['file_uploaded_tables'] || 0) + (ds_summary['falcon'] || 0)
  html += "    <li><strong>Land #{n_land} in-memory / file-uploaded source#{n_land == 1 ? '' : 's'} in your warehouse.</strong> Falcon caches and CSV/XLSX uploads have no governed warehouse source — they must be loaded before Sigma can model them.</li>\n"
end
if sl_needs_scout.positive?
  html += "    <li><strong>Plan individual review time for #{sl_needs_scout} Liveboard#{sl_needs_scout == 1 ? '' : 's'}.</strong> Each uses a chart type that benefits from a tailored conversion approach.</li>\n"
end
if sl_retire.positive?
  html += "    <li><strong>Retire #{sl_retire} Liveboard#{sl_retire == 1 ? '' : 's'}</strong> with zero recorded views. No migration value, and dropping them simplifies the cutover.</li>\n"
end

html += <<~HTML
  </ol>
</section>

<footer>
  Report generated #{h(formatted_date)} · supporting JSON (<code>assessment.json</code>) alongside in the same folder
</footer>

</main>
</body>
</html>
HTML

out_path = File.join(opts[:out], 'readout.html')
File.write(out_path, html)
puts "wrote #{out_path} (#{File.size(out_path)} bytes)"
