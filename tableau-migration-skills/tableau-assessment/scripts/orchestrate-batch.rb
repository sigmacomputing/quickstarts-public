#!/usr/bin/env ruby
# Plan a bulk Tableau→Sigma conversion batch from migration-plan.json.
# This script doesn't itself spawn subagents — subagent spawning happens at
# the agent's conversation layer via the Agent tool. This script produces:
#
#   1. A respecting-DM-clusters execution plan as `batch-plan.json`:
#      - For each cluster: a "leader" workbook that builds the cluster's DM
#        (Phase 1-4 from scratch) and N "follower" workbooks that reuse the
#        leader's DM via Phase 1.5 (find-or-pick-dm.rb).
#      - Leaders run first, sequentially within a cluster but in parallel
#        across clusters. Followers run in parallel once their leader is done.
#      - Concurrency cap: --concurrent (default 3) controls how many
#        subagents the conversation-layer fires in any single message-batch.
#
#   2. The exact agent briefs (markdown) the conversation-layer should pass
#      into each Agent(subagent_type='general-purpose') call.
#
#   3. An empty `batch-results.json` skeleton the conversation-layer fills
#      in as each subagent completes (workbookId → status / sigma_url /
#      parity_tier / duration_s / errors).
#
# Aggregate semantics (continue-on-failure):
#   - GREEN: workbook posted clean (0 column-errors, verify-workbook.rb clean)
#            AND all chart actuals strict-PASS (or PASS in extract-mode).
#   - YELLOW: workbook posted clean BUT one or more charts diverge in values.
#            Structural conversion succeeded; needs human review.
#   - RED: column-type errors, POST failure, verify failure, or no actuals.
#
# Usage:
#   ruby scripts/orchestrate-batch.rb \
#     --plan /tmp/assessment-<site>/migration-plan.json \
#     --out  /tmp/assessment-<site>/batch/ \
#     [--concurrent 3] \
#     [--limit 8]        # max workbooks to convert this batch
#     [--workbook-ids id1,id2,...]   # override: pin a specific subset

require 'json'
require 'fileutils'
require 'optparse'

opts = { concurrent: 3, limit: 8 }
OptionParser.new do |p|
  p.on('--plan PATH')              { |v| opts[:plan] = v }
  p.on('--out DIR')                { |v| opts[:out]  = v }
  p.on('--concurrent N', Integer)  { |v| opts[:concurrent] = v }
  p.on('--limit N',      Integer)  { |v| opts[:limit]      = v }
  p.on('--workbook-ids IDS')       { |v| opts[:wb_ids] = v.split(',') }
  # --ds-override <path-to.json>
  # JSON shape:
  #   { "<cluster_id>": {
  #       "warehouse_tables": ["MYDB.MYSCHEMA.MY_TABLE", ...],
  #       "table_columns":    { "MYDB.MYSCHEMA.MY_TABLE": ["YEAR", ...] },
  #       "build_4_panel_dashboard": true,
  #       "note": "human-readable why-this-override note for the subagent"
  #     },
  #     "<cluster_id_2>": { ... } }
  # Used to fix clusters whose .twb-extracted "tables" are Tableau extract
  # tokens (`EXTRACT.EXTRACT`, `*#CSV`) instead of real warehouse tables.
  # Auto-detection of bogus tokens is OUT OF SCOPE — humans pass overrides
  # via this flag based on assessment-readout review.
  p.on('--ds-override PATH',
       'JSON map cluster_id -> {warehouse_tables, table_columns, note} ' \
       'overriding .twb-extracted tables for that cluster.') { |v| opts[:ds_override] = v }
end.parse!
%i[plan out].each { |k| abort "missing --#{k}" unless opts[k] }

FileUtils.mkdir_p(opts[:out])
plan = JSON.parse(File.read(opts[:plan]))

# Load DS overrides up-front so cluster-leader briefs reference real tables.
overrides = {}
if opts[:ds_override]
  abort "ds-override file not found: #{opts[:ds_override]}" unless File.exist?(opts[:ds_override])
  overrides = JSON.parse(File.read(opts[:ds_override]))
  abort '--ds-override must be a JSON object keyed by cluster_id' unless overrides.is_a?(Hash)
end

# Select workbooks for this batch — explicit IDs if given, else use the
# suggested_batch from the plan (top N by score, already filtered to
# tableau-to-sigma path), capped by --limit.
selected_ids =
  if opts[:wb_ids]
    opts[:wb_ids]
  else
    (plan.dig('summary', 'suggested_batch') || []).map { |w| w['workbookId'] }
  end
selected_ids = selected_ids.first(opts[:limit])
selected = plan['workbooks'].select { |w| selected_ids.include?(w['workbookId']) }
abort 'no workbooks selected' if selected.empty?

# Group by cluster — one leader per cluster, rest are followers.
by_cluster = selected.group_by do |w|
  w['cluster_id'] || "singleton-#{w['workbookId'].to_s[0..7].empty? ? 'unknown' : w['workbookId'][0..7]}"
end
clusters = by_cluster.map do |cid, members|
  # Highest-score member is the leader (most likely to be representative).
  sorted = members.sort_by { |m| -(m['score'].to_f) }
  leader = sorted.first
  followers = sorted.drop(1)
  cluster_meta = (plan['dm_clusters'] || []).find { |c| c['id'] == cid }
  {
    'cluster_id'              => cid,
    'leader'                  => leader,
    'followers'               => followers,
    'shared_warehouse_tables' => cluster_meta ? cluster_meta['shared_warehouse_tables'] : []
  }
end

# Wave-style schedule:
# - Wave 0: all cluster leaders fire in parallel (up to --concurrent at a time).
#   Each leader runs the FULL tableau-to-sigma pipeline including building or
#   reusing a DM. The leader's result becomes the cluster's canonical DM id.
# - Wave 1: all followers fire in parallel, each told to reuse their cluster
#   leader's DM via find-or-pick-dm.rb + inspect-dm-shape.rb.
# Within each wave, the conversation-layer batches subagents into messages of
# `--concurrent` parallel Agent() calls.
waves = []
waves << { 'wave' => 0, 'kind' => 'leaders',    'subagents' => clusters.map { |c| { 'cluster_id' => c['cluster_id'], 'workbook' => c['leader'] } } }
follower_subs = clusters.flat_map do |c|
  c['followers'].map { |f| { 'cluster_id' => c['cluster_id'], 'workbook' => f, 'reuse_leader' => true } }
end
waves << { 'wave' => 1, 'kind' => 'followers', 'subagents' => follower_subs } if follower_subs.any?

# Best-effort PNG count from a cached views dir at /tmp/<wb-name>/views/*.png.
# Returns nil if we can't introspect — the brief then falls back to a fetch
# instruction instead of a hardcoded count.
def cached_png_count(wb_name, out_dir)
  candidates = [
    File.join('/tmp', wb_name.to_s.gsub(/\W+/, '-').downcase, 'views'),
    File.join(out_dir.to_s, wb_name.to_s.gsub(/\W+/, '-').downcase, 'views-png'),
    File.join(out_dir.to_s, wb_name.to_s.gsub(/\W+/, '-').downcase, 'views')
  ]
  candidates.each do |d|
    next unless File.directory?(d)
    pngs = Dir.glob(File.join(d, '*.png'))
    return pngs.size unless pngs.empty?
  end
  nil
end

# Brief generator. The conversation-layer feeds this string into the `prompt:`
# of an Agent() call. Brief is self-contained — subagent doesn't see the
# outer session's history.
# Per-cluster warehouse-tables, with optional CLI override applied. See
# --ds-override flag — humans pass a JSON map of `cluster_id` →
# `{ warehouse_tables: [...], table_columns: {...}, build_4_panel_dashboard: bool, note: "..." }`
# to correct clusters whose .twb-extracted "tables" are Tableau extract
# tokens (e.g. `EXTRACT.EXTRACT`, `*#CSV`) instead of real warehouse tables
# (Snowflake / BigQuery / Databricks / Postgres / etc.).
def effective_warehouse_tables(cluster, overrides)
  ov = overrides[cluster['cluster_id']]
  return cluster['shared_warehouse_tables'] unless ov && ov['warehouse_tables']
  ov['warehouse_tables']
end

def agent_brief(sub, cluster, batch_results_path, leader_dm_id_path, out_dir, overrides = {})
  wb = sub['workbook']
  reuse = sub['reuse_leader']
  png_count = cached_png_count(wb['name'], out_dir)
  png_count_str = png_count ? "approximately #{png_count}" : 'one per dashboard sheet'
  wb_dir_hint = wb['name'].to_s.gsub(/\W+/, '-').downcase
  override = overrides[sub['cluster_id']] || {}
  shared_tables = effective_warehouse_tables(cluster, overrides)
  override_block =
    if override.any?
      <<~OV
        DS OVERRIDE (operator-supplied) — DO NOT use the .twb-extracted tables.
        Use these instead for all DM sourcing and parity work:
          warehouse_tables: #{(override['warehouse_tables'] || []).inspect}
        #{override['table_columns'] ? "  table_columns:    #{override['table_columns'].to_json}" : ''}
        #{override['build_4_panel_dashboard'] ? '  build_4_panel_dashboard: true' : ''}
        #{override['note'] ? "  note: #{override['note']}" : ''}

      OV
    else
      ''
    end
  <<~BRIEF
    Convert one Tableau workbook to Sigma using the tableau-to-sigma skill.

    WORKBOOK
    - name:       #{wb['name']}
    - workbookId: #{wb['workbookId']}
    - priority:   #{wb['priority_tier']}

    SKILL: ~/.claude/skills/tableau-to-sigma/  (read SKILL.md fully)

    #{override_block}#{reuse ? <<~REUSE : <<~LEAD}
      DM REUSE — your cluster leader has already built/picked the DM. Read
      `#{leader_dm_id_path}` for `{ dataModelId, fact_element_id, denorm_plan_path }`.
      Skip Phase 2 + 3 entirely. In Phase 4, source your workbook's master
      table(s) using the leader's DM. Use the denorm plan at `denorm_plan_path`
      verbatim — direct refs for `location:fact`, Lookup formulas for
      `location:dim`. This is the dd7 preflight pattern.
    REUSE

      DM LEAD — your cluster's first workbook. You'll either:
      (a) find a reusable DM in this org via Phase 1.5 picker, then run
          Phase 1.5b inspect-dm-shape.rb on it, OR
      (b) build a new DM (Phases 2-4) sourcing from these shared warehouse
          tables: #{shared_tables.inspect}
      Once your DM is determined, WRITE `#{leader_dm_id_path}` with
      `{ dataModelId, fact_element_id, fact_element_name, denorm_plan_path }`
      so followers can reuse it. If you ran inspect-dm-shape.rb, that's the
      denorm_plan_path.

      **`fact_element_name` MUST be the live name on the DM**, not whatever
      you originally wrote in your spec. After POSTing the DM (or after
      Phase 1.5 picks one), you MUST introspect via:
        GET /v2/dataModels/<dataModelId>/spec
      and read the actual `name` attribute on your chosen fact element.
      Audit-run-1 (Orders cluster) had a leader write `fact_element_name: "Fact"`
      when the live element was `ORDER_FACT` — its follower had to GET the
      leader's workbook spec to recover, costing ~2 min. Don't repeat that:
      the GET-and-record step is cheap and mandatory.
    LEAD

    >>>>>> CRITICAL — VISUAL FIDELITY REQUIREMENT <<<<<<

    You MUST treat the source dashboard PNGs as ground truth — CSV column
    parity alone has shipped customer-visible visual regressions (heatmaps
    rendered as bar charts, log scales silently dropped, missing annotations).

    BEFORE writing any workbook spec:
    1. Read every per-sheet PNG at `<out-dir>/<wb-dir>/views-png/*.png`
       OR `/tmp/#{wb_dir_hint}/views/*.png` via the Read tool. Expected
       count: #{png_count_str}. If the directory is empty, fall back to
       `mcp__tableau__get-view-image` per view (one solo request at a time —
       parallel requests 401).
    2. For each PNG, decide: chart kind, dual-axis vs single, annotations,
       data labels, axis scale (log vs linear), reference lines, palette.
    3. **LAYOUT COMPOSITION** — the dashboard PNG (named like
       `Dashboard*`, `*Overview*`, or whichever zone is the largest /
       multi-element) tells you the GRID. Count its columns and rows of
       tiles. Read the .twb zone tree at `<out-dir>/twbs/<luid>.twb` or
       use `scripts/parse-twb-layout.rb` for per-tile `x_pct, y_pct,
       w_pct, h_pct` — translate those into 24-column / multi-row
       `<LayoutElement>` positions. A 3-column × 2-row source dashboard
       MUST become a 3-column × 2-row Sigma layout, NOT a single-column
       stack. Single-column layouts are the most common visual regression
       across audit batches — every chart at `gridColumn="1 / 13"` is
       almost always wrong unless the source PNG also stacks vertically.

    AFTER workbook PUT, BEFORE declaring GREEN:
    4. POST `/v2/workbooks/{wb}/export` with body
       `{pageId, format: {type: "png", pixelWidth: 1920, pixelHeight: 1500}}`,
       then poll `GET /v2/query/{q}/download` until content-type is image/png.
       Save the bytes to `<out-dir>/<wb-dir>/sigma-render.png`.
    5. Read `sigma-render.png` via the Read tool and visually compare it
       to each source PNG you read in step 1. The comparison MUST check
       both (a) per-chart fidelity (chart kind, axis values, color, labels)
       AND (b) **whole-dashboard composition** — does the Sigma render
       have the same number of tile columns and rows as the source
       dashboard PNG? If the source is a 3×2 grid and Sigma renders a
       single tall column with the right half empty, that's a layout
       failure — downgrade to YELLOW with `error_summary` noting the
       grid mismatch, even if every individual chart value matches.
       If a tile is missing entirely, RED. If proportions/positions
       diverge by more than ~25% of grid width, YELLOW.
    6. The result line MUST include `screenshot_path: "<absolute path>"`.
       GREEN tier is INVALID without a non-null screenshot_path AND
       composition match.

    SUBSTITUTIONS for unsupported Tableau chart types (when source PNG
    shows one of these, render the listed Sigma equivalent and note the
    substitution in error_summary):
      - treemap                       → donut-chart
      - heatmap (1D color matrix)     → pivot-table with rowsBy + columnsBy +
                                        divergent backgroundScale on values
      - point-map without lat/long    → bar / region-map (by region code)
      - packed-bubble                 → bar-chart (sized by measure)
      - density / contour             → scatter-plot with binning

    PERF
    - Fire all `mcp__tableau__get-view-data` calls in ONE parallel batch.
    - Use `find-or-pick-dm.rb --auto-pick` to skip the UX prompt.
    - Run `verify-workbook.rb`, NOT the deprecated .sh.
    - Fetch chart actuals via `mcp__sigma-mcp-v2__query` in one parallel batch.
    - Source `phase-timer.sh` and write phase-timings.json to your working dir.
    - Column discovery: use `scripts/discover-columns.rb --connection-id <id>
      --table-path <db>.<schema>.<table>` (Sigma REST, warehouse-agnostic),
      NOT a warehouse-specific CLI like `snow sql DESCRIBE TABLE`. The same
      script works against any Sigma-supported warehouse (Snowflake, BigQuery,
      Databricks, Postgres, etc.). If it 404s, the table isn't in Sigma's
      catalog — fall back to Custom SQL per SKILL.md Phase 1e.1.

    >>>>>> SPEC-SHAPE GOTCHAS — pre-warning <<<<<<

    These seven shapes keep getting relearned at runtime across audit batches.
    Bake them into your spec from the first POST attempt — do NOT discover
    them by HTTP 400.

    - bar/line/area/scatter/combo `yAxis: { columnIds: [<id>, ...] }` —
      a single object whose `columnIds` is an array. NOT a bare array
      (`yAxis: [<id>]`) and NOT `yAxis: { columnId: ... }`.
    - chart `color: { by: "category" | "scale", column: <id> }`. NOT
      `{ columnId: <id> }`. `by` is required; `column` (singular) names the
      column ID.
    - `region-map` geography: `region: { id: <col-id>, regionType: "us-state" }`.
      NOT `geography: ...`. Valid regionTypes: `us-state`, `us-county`,
      `us-zipcode` (NOT `us-zip`), `us-cbsa` (NOT `us-msa`), `country`.
    - sort direction: `direction: "ascending" | "descending"` — full words.
      `asc` / `desc` are silently dropped and the chart renders unsorted.
    - DM relationships: `keys: [{ columnA: <id>, columnB: <id> }, ...]`.
      NOT `joinColumns: [...]`. The keys live on the source element, not the
      target.
    - Lookup formulas reference **column DISPLAY names**, not column IDs:
      `Lookup([Other_DM/Customer Name], [Master/Customer Key], [Other_DM/Customer Key])`.
      Element-name then slash then human-readable column name (the `name`
      field, never the `id` field). Cross-element refs inside a DM use
      `[BaseElement/REL_NAME/Field]`.
    - pivot-table value/dim shapes are NOT symmetric:
        values:    [<bare-id-string>, ...]          # array of strings
        rowsBy:    [{ id: <col-id> }, ...]          # array of objects
        columnsBy: [{ id: <col-id> }, ...]          # array of objects
      Mixing these (`values: [{id: ...}]` or `rowsBy: ["..."]`) silently
      renders an empty pivot. Verified 2026-05-24.
    - pivot-table / table `conditionalFormats[].columnIds` — NOT `columns`.
      The first POST in audit-run-1 (NASA agent) failed because the
      staging workbook-layout.md showed `columns`; the live API requires
      `columnIds`. Verified 2026-05-24.

    >>>>>> PHASE 6 IS MANDATORY — HARD GATE <<<<<<

    Phase 6 (parity verification) is the single most commonly-skipped step
    in subagent runs — beads-sigma-4pm. To prevent silent skips:

    1. Run `ruby scripts/phase6-parity.rb --tableau /tmp/<wb-dir> --workbook-id <id>`
       (Pass 1 builds the plan).
    2. Fire the listed MCP queries in ONE parallel batch, collect actuals,
       write `/tmp/<wb-dir>/parity-actuals.json`.
    3. Re-run with `--finalize --actuals ...` (Pass 2). This writes
       `/tmp/<wb-dir>/parity-final.json` — the sentinel the hard gate checks.
    4. **If you POSTed the workbook more than once** during spec iteration
       (each post-and-readback.rb invocation creates a NEW workbook — POST
       is create-only), run:
       `ruby scripts/cleanup-orphan-workbooks.rb --workdir /tmp/<wb-dir>`
       to delete the orphans. This MUST run before step 6 or the gate
       will fail with exit 4. See beads-sigma-38a.
    5. **Apply the layout** (MANDATORY — beads-sigma-bw3 — CoCo regression
       where elements rendered as a single-column stack):
       `ruby scripts/build-dashboard-layout.rb --layout /tmp/<wb-dir>/dashboard-layout.json --wb-ids /tmp/<wb-dir>/wb-ids.json --out /tmp/<wb-dir>/layout.xml`
       `ruby scripts/put-layout.rb --workbook <id> --layout /tmp/<wb-dir>/layout.xml`
       Skipping this step means the workbook PUTs without a top-level
       layout and Sigma renders every tile in a single column — exit 6
       on the gate. ALSO: KPI tiles (Tableau scorecards — mark=Text with
       one measure and no dims) now auto-emit as Sigma kpi-chart from
       parse-twb-layout; verify they appear in the readback before
       running the layout script.
    6. **MANDATORY FINAL STEP — before writing the result line, run:**
       `ruby scripts/assert-phase6-ran.rb --tableau /tmp/<wb-dir>`
       The gate checks FOUR things: Phase 6 ran, no orphan workbooks
       remain, no live column has type=error, and a layout XML is
       applied. Exit 0 → write GREEN if all other gates pass. Any
       non-zero exit → you MUST downgrade to YELLOW (parity skipped/
       incomplete, orphans uncleaned, runtime errors, layout missing)
       or RED (parity failed). Do NOT declare GREEN if assert-phase6-ran.rb
       did not exit 0. There is no exception.

    **If MCP query fails mid-Phase-6 with an auth-related error**, the
    Sigma MCP session has staled. Re-call `mcp__sigma-mcp-v2__begin_session`
    and retry the query. Do NOT skip Phase 6 because of a recoverable
    auth error — that's the 2026-05-22 cluster-follower regression.

    **POST vs PUT for spec updates.** `POST /v2/workbooks/spec` is
    create-only. After your first successful POST, every spec update
    MUST be a `PUT /v2/workbooks/{id}/spec` against the same ID. Re-POSTing
    creates a duplicate workbook in the customer's My Documents — exactly
    the 2026-05-28 regression that left three workbooks behind. post-and-
    readback.rb now logs every POST to posted-workbooks.jsonl and prints
    a loud warning on second+ invocation.

    DELIVERABLES on completion — APPEND ONE LINE to `#{batch_results_path}`
    as JSON (newline-delimited; tolerate races with file locking):
      { workbookId, cluster_id: "#{sub['cluster_id']}", role: "#{reuse ? 'follower' : 'leader'}",
        sigma_workbook_url, sigma_workbook_id, dm_id_used,
        parity_tier: "GREEN" | "YELLOW" | "RED",
        column_errors: <int>, verify_status: "clean" | "fail",
        charts_pass: <int>, charts_total: <int>,
        phase6_assert_exit: <0|1|2|3>,        # MANDATORY — must be present
        screenshot_path: "<absolute path to sigma-render.png>" | null,
        duration_s: <float>, error_summary: <string|null> }

    PARITY TIER RULES
    - GREEN: column_errors==0 AND verify=="clean" AND charts_total > 0 AND
             charts_pass==charts_total AND phase6_assert_exit==0 AND
             screenshot_path != null AND you Read-back the Sigma PNG and
             confirmed visual parity with the source dashboard PNG(s).
             (charts_total==0 is NOT GREEN — that's the historic loophole;
             assert-phase6-ran.rb already rejects it.)
    - YELLOW: workbook posted clean BUT (charts_pass<charts_total OR
              phase6_assert_exit != 0 OR visual divergence noted in
              error_summary)
    - RED: any column_error OR verify=="fail" OR POST failure OR
           screenshot_path is null (couldn't render the Sigma workbook)

    CONTINUE-ON-FAILURE — if you hit a hard blocker (POST rejects, column-type
    error you can't resolve in 2 retry attempts, etc.), file a beads ticket
    via `bd create` and write a RED result line. Do not block other workbooks.

    Do NOT push any code changes.
  BRIEF
end

# Emit the plan: per-wave, per-subagent briefs the conversation-layer fires.
batch_results_path = File.join(opts[:out], 'batch-results.jsonl')
File.write(batch_results_path, '')   # empty file for subagent appends

cluster_lookup = clusters.each_with_object({}) { |c, h| h[c['cluster_id']] = c }
schedule = waves.map do |wave|
  {
    'wave'              => wave['wave'],
    'kind'              => wave['kind'],
    'concurrency'       => opts[:concurrent],
    'subagent_count'    => wave['subagents'].size,
    'subagents'         => wave['subagents'].map do |sub|
      cluster = cluster_lookup[sub['cluster_id']]
      leader_dm_id_path = File.join(opts[:out], "#{sub['cluster_id']}-leader-dm.json")
      {
        'subagent_label'   => "#{sub['workbook']['name'].gsub(/\W+/, '-')[0..40]}",
        'cluster_id'       => sub['cluster_id'],
        'role'             => sub['reuse_leader'] ? 'follower' : 'leader',
        'workbookId'       => sub['workbook']['workbookId'],
        'workbook_name'    => sub['workbook']['name'],
        'leader_dm_id_path'=> leader_dm_id_path,
        'agent_brief'      => agent_brief(sub, cluster, batch_results_path, leader_dm_id_path, opts[:out], overrides)
      }
    end
  }
end

File.write(File.join(opts[:out], 'batch-plan.json'),
           JSON.pretty_generate({
             'concurrent'           => opts[:concurrent],
             'continue_on_failure'  => true,
             'parity_tiers'         => {
               'GREEN'  => 'workbook clean + all charts strict-PASS',
               'YELLOW' => 'workbook clean + some chart parity diverges',
               'RED'    => 'column errors / POST fail / verify fail'
             },
             'cluster_count'        => clusters.size,
             'workbook_count'       => selected.size,
             'batch_results_path'   => batch_results_path,
             'waves'                => schedule
           }))

# Render an aggregation script the conversation-layer can run after each wave.
# Single-quoted heredoc disables ALL interpolation; the path is injected via
# a templated placeholder (avoids the #{...} collision with the embedded
# Ruby code in this heredoc).
agg_path = File.join(opts[:out], 'aggregate-results.rb')
agg_src = <<~'AGG'
  #!/usr/bin/env ruby
  # Read batch-results.jsonl and emit a summary table.
  require 'json'
  results_path = '__BATCH_RESULTS_PATH__'
  results = File.readlines(results_path).map { |l| JSON.parse(l) rescue nil }.compact
  if results.empty?
    puts "no results yet"
    exit 0
  end
  by_tier = results.group_by { |r| r["parity_tier"] }
  puts "Batch result (#{results.size} workbooks):"
  %w[GREEN YELLOW RED].each do |t|
    rs = by_tier[t] || []
    next if rs.empty?
    puts "  #{t}: #{rs.size}"
    rs.each { |r| puts "    - #{r["workbook_name"] || r["workbookId"]} (#{r["duration_s"]&.round(1)}s) → #{r["sigma_workbook_url"]}" }
  end
  total_s = results.sum { |r| r["duration_s"].to_f }
  puts ""
  puts "Total wall time across subagents (parallel): #{total_s.round(1)}s"
  if (max_r = results.max_by { |r| r["duration_s"].to_f })
    puts "Effective wall time (max in any wave):       #{max_r['duration_s']&.round(1)}s"
  end
AGG
File.write(agg_path, agg_src.sub('__BATCH_RESULTS_PATH__', batch_results_path))
File.chmod(0755, agg_path)

puts "wrote #{File.join(opts[:out], 'batch-plan.json')}"
puts "  clusters:  #{clusters.size}"
puts "  workbooks: #{selected.size}"
schedule.each do |w|
  puts "  wave #{w['wave']} (#{w['kind']}): #{w['subagent_count']} subagents @ concurrency=#{w['concurrency']}"
  # Per-subagent line — emit the actual role pulled from the subagent entry,
  # not an empty placeholder. Previously the loop emitted `<name> ()` because
  # `role` was sourced from an empty variable instead of the wave kind /
  # subagent entry.
  w['subagents'].each do |sa|
    puts "    - #{sa['workbook_name']} (#{sa['role']}) [cluster #{sa['cluster_id']}]"
  end
end
puts ""
puts "To execute (from the conversation-layer agent):"
puts "  1. For each wave in order, batch its subagents into messages of #{opts[:concurrent]} parallel Agent() calls"
puts "  2. Use each subagent_label as the Agent() description, agent_brief as the prompt"
puts "  3. After each wave: ruby #{agg_path}  → mid-batch summary"
puts "  4. After all waves:  ruby #{agg_path}  → final batch report"
