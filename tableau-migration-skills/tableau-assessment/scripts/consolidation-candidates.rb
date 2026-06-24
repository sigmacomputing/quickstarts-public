#!/usr/bin/env ruby
# Detect Tableau workbooks that could be CONSOLIDATED into one Sigma workbook
# (typically: variants of the same dashboard that differ only by a filter
# value, a year, a region, or a copy/test suffix — in Sigma those become ONE
# workbook plus a control).
#
# Runs AFTER migration-plan.rb (Phase 6). Pure analysis — reads the artifacts
# the assessment already produced; never calls Tableau or Sigma.
#
# Reads (all from <out>/):
#   twb-fetch-results.json  — luid → workbook name        (required)
#   twbs/<luid>.twb         — sheets / filters / fields   (required)
#   shortlist.json          — usage + tags                (optional)
#   complexity.json         — gap-scan feature profile    (optional)
#   migration-plan.json     — recommended_path per wb     (optional; required for --decide)
#
# Writes: <out>/consolidation-candidates.json
#
# Decision recording (Phase 6b handoff — run after the user answers the
# per-group prompt):
#   ruby scripts/consolidation-candidates.rb --out <out> \
#     --decide consolidation-01=consolidate --decide consolidation-02=as-is
# updates migration-plan.json in place: members of a consolidated group get
# recommended_path "consolidate-into-primary" (+ consolidate_into /
# consolidation_group keys; original path preserved in pre_consolidation_path)
# and the plan gains a top-level "consolidation" block the converter skills
# read. "as-is" groups are recorded with decision only — paths untouched.
#
# Scoring is deliberately conservative: a false "consolidate" erodes trust.
# Every group carries its evidence (similarity_drivers + differences) so the
# user can sanity-check the call before answering the prompt.

require 'json'
require 'optparse'
require 'set'

opts = { emit_floor: 0.45, decisions: {} }
OptionParser.new do |p|
  p.on('--out DIR') { |v| opts[:out] = v }
  p.on('--emit-floor F', Float,
       'Minimum pairwise similarity for a pair to be considered at all (default 0.45)') { |v| opts[:emit_floor] = v }
  p.on('--decide GROUP=CHOICE',
       'Record a user decision (choice: consolidate | as-is) into migration-plan.json. Repeatable.') do |v|
    g, c = v.split('=', 2)
    abort("--decide expects GROUP=consolidate|as-is, got #{v}") unless %w[consolidate as-is].include?(c)
    opts[:decisions][g] = c
  end
end.parse!
abort('--out required') unless opts[:out]

OUT = opts[:out]
def load_json(name)
  path = File.join(OUT, name)
  File.exist?(path) ? JSON.parse(File.read(path)) : nil
end

fetch_results = load_json('twb-fetch-results.json') or abort('twb-fetch-results.json missing — run fetch-all-twbs.rb first')
shortlist  = load_json('shortlist.json')  || []
complexity = load_json('complexity.json') || {}
plan       = load_json('migration-plan.json')

usage_by_luid = shortlist.each_with_object({}) { |r, h| h[r['luid'] || r['workbookId']] = r }
plan_by_luid  = plan ? (plan['workbooks'] || []).each_with_object({}) { |w, h| h[w['workbookId']] = w } : {}

# ---------------------------------------------------------------------------
# Per-workbook profile extraction from the cached .twb
# ---------------------------------------------------------------------------

# Generic tokens that distinguish a VARIANT of a workbook rather than a
# different workbook: copy/test/version markers, years, quarters, months,
# and generic BI nouns. Removed before comparing name stems.
VARIANT_TOKENS = Set.new(%w[
  copy copies v1 v2 v3 v4 v5 final draft test testing tests old new backup
  wip tmp temp dev qa uat prod staging republish republished revised updated
  edit edited version archive archived deprecated
  dashboard dashboards report reports workbook workbooks sheet sheets viz
  q1 q2 q3 q4 jan feb mar apr may jun jul aug sep oct nov dec
  january february march april june july august september october november december
]).freeze

def variant_token?(t)
  VARIANT_TOKENS.include?(t) || t =~ /^(19|20)\d{2}$/ || t =~ /^\d+$/
end

def name_tokens(name)
  name.to_s.downcase.scan(/[a-z0-9]+/)
end

def name_stem(name)
  name_tokens(name).reject { |t| variant_token?(t) }
end

# Normalize a Tableau field reference: drop the aggregation/derivation prefix
# (sum:/avg:/none:/yr: ...) and the :nk/:qk/:ok suffix.
def normalize_field(raw)
  f = raw.to_s
  f = f.sub(/\A(none|attr|usr|sum|avg|min|max|cnt|cntd|count|median|stdev|var|yr|qr|mn|dy|hr|tyr|tqr|tmn|tdy|week|wk):/i, '')
  f = f.sub(/:(nk|qk|ok)\z/, '')
  f.downcase.strip
end

# Same warehouse-table extraction convention as migration-plan.rb.
def extract_warehouse_tables(twb)
  out = []
  twb.scan(/<relation\b[^>]*type='table'[^>]*>/).each do |tag|
    raw = tag[/table='([^']*)'/, 1].to_s.gsub(/[\[\]]/, '')
    table =
      if (m = raw.match(/\(([^)]+)\)$/));              m[1]
      elsif (m = raw.match(/[0-9a-f-]{30,}\.(.+)$/i)); m[1]
      else;                                            raw
      end
    out << table.to_s.upcase.strip unless table.to_s.empty?
  end
  out.uniq
end

def build_profile(luid, name, twb_path)
  twb = File.read(twb_path, encoding: 'utf-8', invalid: :replace)

  sheets     = twb.scan(/<worksheet\b[^>]*?name='([^']*)'/).flatten.uniq
  dashboards = twb.scan(/<dashboard\b[^>]*?name='([^']*)'/).flatten.uniq
  zones      = twb.scan(/<zone\b/).size

  # internal-name → caption map from column definitions (GUID names on
  # published datasources, Calculation_NNN names on embedded ones).
  captions = {}
  twb.scan(/<column\b[^>]*>/) do |tag|
    tag = tag.is_a?(Array) ? tag.first : tag
    cap   = tag[/caption='([^']*)'/, 1]
    cname = tag[/name='\[([^\]]*)\]'/, 1]
    captions[cname] = cap if cap && cname
  end
  resolve = lambda do |raw|
    key = normalize_field(raw)
    (captions[raw] || captions[key] || key).downcase.strip
  end
  schema_fields = captions.values.map { |c| c.downcase.strip }.uniq.sort

  # Fields a worksheet actually USES (datasource-dependencies blocks). These
  # are the signal — schema fields only describe the datasource.
  used = Set.new
  twb.scan(%r{<datasource-dependencies\b.*?</datasource-dependencies>}m) do |block|
    block = block.is_a?(Array) ? block.first : block
    block.scan(/<column\b[^>]*?name='\[([^\]]*)\]'/).flatten.each { |cn| used << resolve.call(cn) }
  end

  # Filters: field + the categorical member values selected.
  filters = {}
  twb.scan(%r{(<filter\b[^>]*column='[^']*'[^>]*?(?:/>|>.*?</filter>))}m) do |m|
    el  = m.first
    col = el[/column='([^']*)'/, 1].to_s
    raw = col.gsub(/[\[\]]/, '').sub(/\A[^.]*\./, '')
    field = resolve.call(raw)
    next if field.empty? || field.start_with?('action (')
    values = el.scan(/member='(?:&quot;)?(.*?)(?:&quot;)?'/).flatten
    filters[field] ||= Set.new
    values.each { |v| filters[field] << v }
  end

  published_ids = twb.scan(/<repository-location\b[^>]*\bid='([^']*)'/).flatten.uniq

  # Sub-sheet-level difference signals: calc formulas, reference lines, and
  # RLS functions. Sheet-identical copies often differ exactly here.
  calc_formulas = twb.scan(/<calculation\b[^>]*formula='([^']*)'/).flatten
                     .map { |f| f.strip }.reject(&:empty?).uniq.sort
  refline_count = twb.scan(/<reference-line\b/).size
  has_rls       = twb.match?(/USERNAME\(\)|ISMEMBEROF|USERDOMAIN\(\)|FULLNAME\(\)/)

  {
    'luid'             => luid,
    'name'             => name,
    'sheets'           => sheets,
    'dashboards'       => dashboards,
    'zones'            => zones,
    'used_fields'      => used.to_a.sort,
    'schema_fields'    => schema_fields,
    'filters'          => filters.transform_values { |v| v.to_a.sort },
    'warehouse_tables' => extract_warehouse_tables(twb),
    'published_ids'    => published_ids,
    'calc_formulas'    => calc_formulas,
    'refline_count'    => refline_count,
    'has_rls'          => has_rls,
    'stub'             => used.empty? && sheets.size <= 1
  }
end

profiles = {}
fetch_results.each do |luid, info|
  next if info['error']
  twb_path = File.join(OUT, 'twbs', "#{luid}.twb")
  next unless File.exist?(twb_path)
  profiles[luid] = build_profile(luid, info['name'], twb_path)
end

# ---------------------------------------------------------------------------
# Pairwise similarity
# ---------------------------------------------------------------------------

def jaccard(a, b)
  a = a.to_set; b = b.to_set
  return 0.0 if (a | b).empty?
  (a & b).size.to_f / (a | b).size
end

def levenshtein_ratio(a, b)
  a = a.to_s.downcase; b = b.to_s.downcase
  return 1.0 if a == b
  return 0.0 if a.empty? || b.empty?
  prev = (0..b.size).to_a
  a.each_char.with_index(1) do |ca, i|
    cur = [i]
    b.each_char.with_index(1) do |cb, j|
      cur << [prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca == cb ? 0 : 1)].min
    end
    prev = cur
  end
  1.0 - prev.last.to_f / [a.size, b.size].max
end

# Token match incl. light prefix-stemming (conversion ~ converter).
def tokens_match?(a, b)
  return true if a == b
  return true if [a.size, b.size].min >= 4 && (a.start_with?(b) || b.start_with?(a))
  pre = 0
  pre += 1 while pre < [a.size, b.size].min && a[pre] == b[pre]
  pre >= 6
end

def stem_overlap(stem_a, stem_b)
  return 0.0 if stem_a.empty? || stem_b.empty?
  matched = 0
  remaining = stem_b.dup
  stem_a.each do |t|
    hit = remaining.find { |u| tokens_match?(t, u) }
    next unless hit
    matched += 1
    remaining.delete_at(remaining.index(hit))
  end
  matched.to_f / [stem_a.size, stem_b.size].max
end

def size_ratio(a, b)
  return 1.0 if a.zero? && b.zero?
  return 0.0 if a.zero? || b.zero?
  [a, b].min.to_f / [a, b].max
end

def feature_cosine(fa, fb)
  return nil if fa.nil? || fb.nil?
  va = (fa['features'] || []).each_with_object(Hash.new(0)) { |f, h| h[f['name']] += f['count'].to_i }
  vb = (fb['features'] || []).each_with_object(Hash.new(0)) { |f, h| h[f['name']] += f['count'].to_i }
  return nil if va.empty? || vb.empty?
  keys = (va.keys | vb.keys)
  dot  = keys.sum { |k| va[k] * vb[k] }
  mag  = Math.sqrt(va.values.sum { |x| x * x }) * Math.sqrt(vb.values.sum { |x| x * x })
  mag.zero? ? 0.0 : dot / mag
end

def score_pair(pa, pb, complexity)
  # Field overlap: prefer USED fields; fall back to schema fields for stubs.
  if pa['used_fields'].size >= 4 && pb['used_fields'].size >= 4
    field_overlap = jaccard(pa['used_fields'], pb['used_fields'])
    field_basis   = 'used'
  else
    field_overlap = jaccard(pa['schema_fields'], pb['schema_fields'])
    field_basis   = 'schema'
  end

  sheet_jaccard = jaccard(pa['sheets'], pb['sheets'])
  structure = 0.6 * sheet_jaccard +
              0.25 * size_ratio(pa['sheets'].size, pb['sheets'].size) +
              0.15 * size_ratio(pa['zones'], pb['zones'])

  name_sim = [stem_overlap(name_stem(pa['name']), name_stem(pb['name'])),
              levenshtein_ratio(pa['name'], pb['name'])].max

  fa = pa['filters']; fb = pb['filters']
  filter_sim =
    if fa.empty? && fb.empty?
      1.0 # no filters on either side — trivially identical
    else
      jaccard(fa.keys, fb.keys)
    end
  differing_filter_values = (fa.keys & fb.keys).select { |k| fa[k] != fb[k] && !(fa[k].empty? && fb[k].empty?) }

  fcos = feature_cosine(complexity[pa['luid']], complexity[pb['luid']])

  weights = { field: 0.40, structure: 0.25, name: 0.15, filter: 0.10, feature: 0.10 }
  components = { field: field_overlap, structure: structure, name: name_sim, filter: filter_sim, feature: fcos }
  # Re-normalize when a component is unavailable (e.g. no complexity data).
  avail = components.reject { |_, v| v.nil? }
  total_w = avail.keys.sum { |k| weights[k] }
  score = avail.sum { |k, v| weights[k] * v } / total_w

  {
    'score'                   => score.round(3),
    'field_overlap'           => field_overlap.round(3),
    'field_basis'             => field_basis,
    'sheet_jaccard'           => sheet_jaccard.round(3),
    'structure'               => structure.round(3),
    'name_similarity'         => name_sim.round(3),
    'filter_similarity'       => filter_sim.round(3),
    'feature_cosine'          => fcos&.round(3),
    'differing_filter_values' => differing_filter_values,
    'shared_sheets'           => (pa['sheets'] & pb['sheets']),
    'shared_tables'           => (pa['warehouse_tables'] & pb['warehouse_tables'])
  }
end

# ---------------------------------------------------------------------------
# Pooling: only compare workbooks that plausibly share a datasource —
# overlapping warehouse tables (ignoring the generic EXTRACT.EXTRACT token)
# or a shared published-datasource repository id.
# ---------------------------------------------------------------------------

GENERIC_TABLES = ['EXTRACT.EXTRACT'].freeze

def pool_key_overlap?(pa, pb)
  ta = pa['warehouse_tables'] - GENERIC_TABLES
  tb = pb['warehouse_tables'] - GENERIC_TABLES
  return true if (ta & tb).any?
  (pa['published_ids'] & pb['published_ids']).any?
end

luids = profiles.keys
pairs = []
luids.combination(2) do |a, b|
  pa = profiles[a]; pb = profiles[b]
  next unless pool_key_overlap?(pa, pb)
  s = score_pair(pa, pb, complexity)
  next if s['score'] < opts[:emit_floor]
  pairs << { 'a' => a, 'b' => b }.merge(s)
end

# ---------------------------------------------------------------------------
# Grouping: complete-linkage clustering. Two clusters merge only when EVERY
# cross-pair between them scores >= GROUP_LINK — this prevents the
# chain-of-weak-links effect where A~B and B~C drags an unrelated C into A's
# group. Pairs above the emit floor that never reach GROUP_LINK surface as
# two-workbook "keep-separate" groups (considered, rejected, with evidence).
# ---------------------------------------------------------------------------

CONSOLIDATE_MIN_FIELD  = 0.70
CONSOLIDATE_MIN_SHEETS = 0.60
REVIEW_MIN_SCORE       = 0.55
GROUP_LINK             = 0.55

pair_score = {}
pairs.each { |p| pair_score[[p['a'], p['b']].sort] = p['score'] }

clusters = pairs.flat_map { |p| [p['a'], p['b']] }.uniq.map { |l| [l] }
pairs.sort_by { |p| -p['score'] }.each do |p|
  next if p['score'] < GROUP_LINK
  ca = clusters.find { |c| c.include?(p['a']) }
  cb = clusters.find { |c| c.include?(p['b']) }
  next if ca.equal?(cb)
  # complete linkage: every cross-pair must exist and clear GROUP_LINK
  mergeable = ca.all? { |x| cb.all? { |y| (pair_score[[x, y].sort] || 0.0) >= GROUP_LINK } }
  next unless mergeable
  clusters.delete(cb)
  ca.concat(cb)
end

groups_members = clusters.select { |c| c.size >= 2 }

# Leftover near-miss pairs between still-ungrouped workbooks → keep-separate
# evidence groups (one group per workbook, best pair first).
grouped = Set.new(groups_members.flatten)
pairs.sort_by { |p| -p['score'] }.each do |p|
  next if grouped.include?(p['a']) || grouped.include?(p['b'])
  groups_members << [p['a'], p['b']]
  grouped << p['a'] << p['b']
end

groups = []
groups_members.sort_by { |m| -m.size }.each_with_index do |members, idx|
  members = members.sort_by { |l| [-(usage_by_luid.dig(l, 'accesses') || 0), -profiles[l]['sheets'].size] }
  gid = format('consolidation-%02d', idx + 1)
  gpairs = pairs.select { |p| members.include?(p['a']) && members.include?(p['b']) }

  min_field    = gpairs.map { |p| p['field_overlap'] }.min
  min_sheets   = gpairs.map { |p| p['sheet_jaccard'] }.min
  min_score    = gpairs.map { |p| p['score'] }.min
  field_basis  = gpairs.any? { |p| p['field_basis'] == 'schema' } ? 'schema' : 'used'
  all_stubs    = members.all? { |l| profiles[l]['stub'] }
  shared_tables = (members.map { |l| profiles[l]['warehouse_tables'].to_set }.reduce(:&).to_a.sort - GENERIC_TABLES)
  diff_filter_fields = gpairs.flat_map { |p| p['differing_filter_values'] }.uniq

  # Differences in sheet structure (per member, sheets nobody else has)
  all_sheets = members.flat_map { |l| profiles[l]['sheets'] }
  sheet_counts = all_sheets.each_with_object(Hash.new(0)) { |s, h| h[s] += 1 }
  unique_sheets = members.to_h { |l| [profiles[l]['name'], profiles[l]['sheets'].select { |s| sheet_counts[s] == 1 }] }

  # Name evidence: do the variant tokens look like a parameterizable dimension?
  variant_diff_tokens = members.flat_map { |l| name_tokens(profiles[l]['name']).select { |t| variant_token?(t) } }.uniq

  # Proposed controls (what replaces the variants in ONE Sigma workbook)
  proposed_controls = diff_filter_fields.map do |f|
    values = members.flat_map { |l| profiles[l]['filters'][f] || [] }.uniq.sort
    { 'column' => f, 'kind' => 'list-control', 'values_observed' => values }
  end
  if proposed_controls.empty? && variant_diff_tokens.any? { |t| t =~ /^(19|20)\d{2}$/ }
    proposed_controls << { 'column' => '(date field)', 'kind' => 'date-range-control',
                           'values_observed' => variant_diff_tokens.grep(/^(19|20)\d{2}$/) }
  end

  # Sub-sheet-level mismatches: RLS markers and calc-formula divergence.
  rls_flags    = members.map { |l| profiles[l]['has_rls'] }.uniq
  rls_mismatch = rls_flags.size > 1
  calc_sets    = members.map { |l| profiles[l]['calc_formulas'].to_set }
  calc_diff    = (calc_sets.reduce(:|) - calc_sets.reduce(:&)).size
  refline_counts = members.map { |l| profiles[l]['refline_count'] }.uniq
  secondaries_unused = members.size > 1 && members[1..-1].all? { |l| (usage_by_luid.dig(l, 'accesses') || 0).zero? }

  # --- recommendation (conservative) ---
  recommendation, reason =
    if all_stubs
      ['review', 'All members are near-empty publish-test stubs (no fields used, single blank sheet). ' \
                 'Nothing to consolidate — keep one (or retire all) rather than migrating each.']
    elsif rls_mismatch
      ['review', 'The variants differ in row-level-security functions (USERNAME()/ISMEMBEROF) — consolidating ' \
                 'could change who sees what. Verify the RLS intent before merging.']
    elsif field_basis == 'used' && min_field >= CONSOLIDATE_MIN_FIELD && min_sheets >= CONSOLIDATE_MIN_SHEETS
      detail =
        if proposed_controls.any?
          "the only differences map to #{proposed_controls.size} control(s)"
        elsif secondaries_unused
          'the non-primary variants have no usage — keep the primary, retire the copies'
        else
          'the variants are near-identical — keep one'
        end
      ['consolidate', "High overlap in actually-used fields (#{(min_field * 100).round}%+) and sheet structure; #{detail}."]
    elsif min_score >= REVIEW_MIN_SCORE
      ['review', 'Same datasource and meaningful overlap, but the variants differ in structure or field usage ' \
                 'beyond what a control parameterizes — eyeball them side-by-side before consolidating.']
    else
      ['keep-separate', 'Workbooks share a datasource but diverge in content — migrate separately.']
    end

  drivers = []
  drivers << if field_basis == 'schema'
               "schema field overlap #{(min_field * 100).round}% (members use too few fields to compare actual usage)"
             else
               "actually-used field overlap #{(min_field * 100).round}%"
             end
  drivers << "shared sheets: #{gpairs.flat_map { |p| p['shared_sheets'] }.uniq.size} (sheet-set similarity #{(min_sheets * 100).round}%)"
  drivers << "shared warehouse tables: #{shared_tables.join(', ')}" if shared_tables.any?
  drivers << "name stem overlap (variant tokens: #{variant_diff_tokens.join(', ')})" if variant_diff_tokens.any?
  drivers << "same filter fields, values differ on: #{diff_filter_fields.join(', ')}" if diff_filter_fields.any?

  differences = []
  unique_sheets.each do |wb, uniq|
    differences << "#{wb} has #{uniq.size} sheet(s) not in the others: #{uniq.first(5).join(', ')}#{uniq.size > 5 ? ', …' : ''}" if uniq.any?
  end
  diff_filter_fields.each do |f|
    per = members.map { |l| "#{profiles[l]['name']}=#{(profiles[l]['filters'][f] || []).join('/')}" }
    differences << "filter '#{f}' values: #{per.join(' · ')}"
  end
  if rls_mismatch
    with_rls = members.select { |l| profiles[l]['has_rls'] }.map { |l| profiles[l]['name'] }
    differences << "row-level-security functions present only in: #{with_rls.join(', ')}"
  end
  if calc_diff.positive?
    per_calc = members.map { |l| "#{profiles[l]['name']}=#{profiles[l]['calc_formulas'].size}" }
    differences << "calculated-field formulas differ (#{calc_diff} formula(s) not shared; #{per_calc.join(' · ')})"
  end
  if refline_counts.size > 1
    per_rl = members.map { |l| "#{profiles[l]['name']}=#{profiles[l]['refline_count']}" }
    differences << "reference-line counts differ: #{per_rl.join(' · ')}"
  end
  differences << 'no structural differences detected' if differences.empty?

  primary = members.first
  groups << {
    'group_id'              => gid,
    'recommendation'        => recommendation,
    'recommendation_reason' => reason,
    'workbooks'             => members.map do |l|
      pr = profiles[l]
      {
        'workbookId'       => l,
        'name'             => pr['name'],
        'accesses'         => usage_by_luid.dig(l, 'accesses') || 0,
        'sheets'           => pr['sheets'].size,
        'dashboards'       => pr['dashboards'].size,
        'used_fields'      => pr['used_fields'].size,
        'priority_tier'    => usage_by_luid.dig(l, 'tag'),
        'recommended_path' => plan_by_luid.dig(l, 'recommended_path')
      }
    end,
    'primary'            => { 'workbookId' => primary, 'name' => profiles[primary]['name'] },
    'shared_datasource'  => {
      'warehouse_tables' => shared_tables,
      'published_ids'    => members.map { |l| profiles[l]['published_ids'] }.reduce(:&)
    },
    'field_overlap_pct'  => (min_field * 100).round,
    'field_basis'        => field_basis,
    'similarity_drivers' => drivers,
    'differences'        => differences,
    'proposed_controls'  => proposed_controls,
    'pairwise'           => gpairs.map { |p|
      p.merge('a_name' => profiles[p['a']]['name'], 'b_name' => profiles[p['b']]['name'])
       .slice('a_name', 'b_name', 'score', 'field_overlap', 'field_basis', 'sheet_jaccard',
              'name_similarity', 'filter_similarity', 'feature_cosine', 'differing_filter_values')
    },
    'estimated_savings'  => recommendation == 'consolidate' ? { 'conversions_avoided' => members.size - 1 } : nil
  }
end

result = {
  'generated_at' => Time.now.strftime('%Y-%m-%d'),
  'params' => {
    'emit_floor'                    => opts[:emit_floor],
    'consolidate_min_field_overlap' => CONSOLIDATE_MIN_FIELD,
    'consolidate_min_sheet_jaccard' => CONSOLIDATE_MIN_SHEETS,
    'review_min_score'              => REVIEW_MIN_SCORE
  },
  'summary' => {
    'workbooks_analyzed'    => profiles.size,
    'groups_total'          => groups.size,
    'consolidate'           => groups.count { |g| g['recommendation'] == 'consolidate' },
    'review'                => groups.count { |g| g['recommendation'] == 'review' },
    'keep_separate'         => groups.count { |g| g['recommendation'] == 'keep-separate' },
    'conversions_avoidable' => groups.sum { |g| g.dig('estimated_savings', 'conversions_avoided') || 0 }
  },
  'groups' => groups
}

out_path = File.join(OUT, 'consolidation-candidates.json')
File.write(out_path, JSON.pretty_generate(result))
puts "wrote #{out_path}"
puts "  workbooks analyzed:     #{profiles.size}"
puts "  candidate groups:       #{groups.size} " \
     "(consolidate: #{result['summary']['consolidate']}, review: #{result['summary']['review']}, keep-separate: #{result['summary']['keep_separate']})"
puts "  conversions avoidable:  #{result['summary']['conversions_avoidable']}"
groups.each do |g|
  puts "  #{g['group_id']} [#{g['recommendation']}] #{g['workbooks'].map { |w| w['name'] }.join(' + ')}"
end

# ---------------------------------------------------------------------------
# --decide: record user decisions into migration-plan.json
# ---------------------------------------------------------------------------
unless opts[:decisions].empty?
  abort('migration-plan.json missing — run migration-plan.rb before --decide') unless plan
  by_gid = groups.each_with_object({}) { |g, h| h[g['group_id']] = g }
  decisions_out = []
  opts[:decisions].each do |gid, choice|
    g = by_gid[gid] or abort("unknown group #{gid} (have: #{by_gid.keys.join(', ')})")
    decisions_out << { 'group_id' => gid, 'decision' => choice,
                       'workbooks' => g['workbooks'].map { |w| w['workbookId'] },
                       'primary'   => g['primary']['workbookId'],
                       'proposed_controls' => g['proposed_controls'] }
    next unless choice == 'consolidate'
    primary_id = g['primary']['workbookId']
    (plan['workbooks'] || []).each do |w|
      next unless g['workbooks'].any? { |m| m['workbookId'] == w['workbookId'] }
      w['consolidation_group'] = gid
      if w['workbookId'] == primary_id
        w['consolidation_role']     = 'primary'
        w['consolidation_controls'] = g['proposed_controls']
      else
        w['consolidation_role']        = 'merged'
        w['pre_consolidation_path'] ||= w['recommended_path']
        w['recommended_path']          = 'consolidate-into-primary'
        w['consolidate_into']          = primary_id
      end
    end
  end
  plan['consolidation'] = {
    'decided_at' => Time.now.strftime('%Y-%m-%d'),
    'decisions'  => decisions_out
  }
  plan_path = File.join(OUT, 'migration-plan.json')
  File.write(plan_path, JSON.pretty_generate(plan))
  puts
  puts "recorded #{decisions_out.size} decision(s) into #{plan_path}"
  decisions_out.each { |d| puts "  #{d['group_id']} → #{d['decision']}" }
end
