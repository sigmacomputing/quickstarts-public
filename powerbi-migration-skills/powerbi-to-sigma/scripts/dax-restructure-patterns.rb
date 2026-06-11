#!/usr/bin/env ruby
# dax-restructure-patterns.rb — reusable (b)-bucket DAX→Sigma element generators.
#
# The (a)-bucket (mechanical DAX→formula) is handled by convert_powerbi_to_sigma.
# This library handles the (b)-bucket: DAX whose semantics need a *new Sigma
# element* (custom-SQL or a child grouped table), not just a formula rewrite.
# Each generator returns a Sigma data-model `table` element (kind:"sql" source,
# or a grouped child element) ready to splice into a DM spec's pages[].elements.
#
# Patterns implemented (each maps a recognizable DAX shape → a faithful Sigma element):
#   1. concatenatex_listagg   CONCATENATEX(VALUES(T[grp]), T[txt], sep, ...)
#                             -> SQL: LISTAGG(DISTINCT txt, sep) WITHIN GROUP (ORDER BY ..) GROUP BY grp
#   2. banded_grouping        a disconnected GENERATESERIES "bands" table + a "% in band" intent
#                             -> SQL: range-join fact into bands, COUNT per band + PercentOfTotal
#   3. treatas_virtual_rel    CALCULATE(<agg on B>, TREATAS(VALUES(A[k]), B[k]))
#                             -> SQL: explicit JOIN A->B on k, agg grouped (a real relationship)
#   4. earlier_rank           COUNTROWS(FILTER(T, T[p]=EARLIER(T[p]) && T[m]>EARLIER(T[m])))+1
#                             -> calc col: RankDense([m],"desc",[p])  (partitioned window)
#   5. topn_sumx              SUMX(TOPN(n, VALUES(T[grp]), [m], DESC), [m])
#                             -> SQL: GROUP BY grp + QUALIFY ROW_NUMBER() OVER (ORDER BY agg DESC)<=n,
#                                summed via GrandTotal(Sum(kept)) in the viz
#
# Each generator is pure (spec in -> spec element out), so it is unit-testable and
# reusable across conversions. The agent picks the generator from the DAX shape;
# `classify(dax)` does best-effort shape detection so this can run unattended.
#
# Usage (library):
#   require_relative 'dax-restructure-patterns'
#   el = DaxRestructure.concatenatex_listagg(
#          name:"RolesInDept", conn:CONN, db:"CSA", schema:"TJ", table:"EMPLOYEES",
#          group_col:"DEPARTMENT", text_col:"ROLE", sep:", ")
#
# Usage (CLI, classify a measure):
#   ruby dax-restructure-patterns.rb --classify 'CONCATENATEX(VALUES(EMPLOYEES[ROLE]), ...)'

require 'json'

module DaxRestructure
  module_function

  def _sql_el(name, conn, statement, columns)
    { 'id' => name.gsub(/[^a-zA-Z0-9]/, '')[0, 18] + 'El',
      'kind' => 'table', 'name' => name,
      'source' => { 'kind' => 'sql', 'connectionId' => conn, 'statement' => statement },
      'columns' => columns }
  end

  # 1. CONCATENATEX -> LISTAGG custom-SQL element (one row per group).
  def concatenatex_listagg(name:, conn:, db:, schema:, table:, group_col:, text_col:, sep: ', ')
    stmt = "SELECT #{group_col}, " \
           "LISTAGG(DISTINCT #{text_col}, '#{sep}') WITHIN GROUP (ORDER BY #{text_col}) AS #{text_col}_LIST, " \
           "COUNT(DISTINCT #{text_col}) AS #{text_col}_COUNT " \
           "FROM #{db}.#{schema}.#{table} GROUP BY #{group_col}"
    _sql_el(name, conn, stmt, [
      { 'id' => 'grp', 'formula' => "[Custom SQL/#{group_col}]", 'name' => group_col.split('_').map(&:capitalize).join(' ') },
      { 'id' => 'lst', 'formula' => "[Custom SQL/#{text_col}_LIST]", 'name' => "#{text_col.capitalize}s" },
      { 'id' => 'cnt', 'formula' => "[Custom SQL/#{text_col}_COUNT]", 'name' => "#{text_col.capitalize} Count" }
    ])
  end

  # 2. Banded grouping: range-join a fact's measure column into a band spine,
  #    emit count-per-band (the faithful "% in band" needs PercentOfTotal in the viz).
  #    `bands` = array of numeric floors (ascending). Mirrors GENERATESERIES bands.
  def banded_grouping(name:, conn:, db:, schema:, table:, value_col:, bands:, label_fmt: '$%dk+', label_div: 1000)
    floors = bands.map { |b| "(#{b})" }.join(',')
    # assign each fact row to the highest band floor <= value; label via FLOOR(value/div)
    stmt = "WITH bands AS (SELECT v AS BANDFLOOR FROM (VALUES #{floors}) AS t(v)) " \
           "SELECT '$' || FLOOR(b.BANDFLOOR/#{label_div}) || 'k+' AS BAND, b.BANDFLOOR, COUNT(*) AS N " \
           "FROM #{db}.#{schema}.#{table} f " \
           "JOIN bands b ON f.#{value_col} >= b.BANDFLOOR " \
           "AND b.BANDFLOOR = (SELECT MAX(b2.BANDFLOOR) FROM bands b2 WHERE f.#{value_col} >= b2.BANDFLOOR) " \
           "GROUP BY b.BANDFLOOR ORDER BY b.BANDFLOOR"
    _sql_el(name, conn, stmt, [
      { 'id' => 'band', 'formula' => '[Custom SQL/BAND]', 'name' => 'Band' },
      { 'id' => 'floor', 'formula' => '[Custom SQL/BANDFLOOR]', 'name' => 'Band Floor' },
      { 'id' => 'n', 'formula' => '[Custom SQL/N]', 'name' => 'In Band' }
    ])
  end

  # 3. TREATAS virtual relationship -> explicit JOIN element. Pushes A[key]'s set
  #    onto B and aggregates B. `agg` e.g. "SUM(b.HOURS)". Materializes the
  #    virtual relationship as a real join (what TREATAS simulates per-eval).
  def treatas_virtual_rel(name:, conn:, db:, schema:, fact:, fact_key:, dim:, dim_key:,
                          group_col:, agg:, agg_alias:, fact_alias: 'b', dim_alias: 'a')
    stmt = "SELECT #{dim_alias}.#{group_col}, #{agg} AS #{agg_alias} " \
           "FROM #{db}.#{schema}.#{fact} #{fact_alias} " \
           "JOIN #{db}.#{schema}.#{dim} #{dim_alias} ON #{fact_alias}.#{fact_key} = #{dim_alias}.#{dim_key} " \
           "GROUP BY #{dim_alias}.#{group_col}"
    _sql_el(name, conn, stmt, [
      { 'id' => 'grp', 'formula' => "[Custom SQL/#{group_col}]", 'name' => group_col.split('_').map(&:capitalize).join(' ') },
      { 'id' => 'val', 'formula' => "[Custom SQL/#{agg_alias}]", 'name' => agg_alias }
    ])
  end

  # 5. SUMX(TOPN(n, VALUES(T[grp]), [measure], DESC), [measure]) -> a group-by-grp
  #    custom-SQL element ranking by the measure DESC and keeping only the top-n
  #    groups, summed and surfaced via GrandTotal(Sum(kept)) in the viz.
  #    `agg` is the per-group aggregate of the DAX measure, e.g. "SUM(ANNUAL_SALARY)".
  #    Validated shape for "Top 5 Role Salary": same 5 ROLEs / same rank order as PBI.
  #    (beads-sigma-ntl)
  def topn_sumx(name:, conn:, db:, schema:, table:, group_col:, agg:, n:, agg_alias: 'GRP_TOTAL', direction: 'DESC')
    dir = direction.to_s.upcase == 'ASC' ? 'ASC' : 'DESC'
    stmt = "SELECT #{group_col}, #{agg} AS #{agg_alias} " \
           "FROM #{db}.#{schema}.#{table} " \
           "GROUP BY #{group_col} " \
           "QUALIFY ROW_NUMBER() OVER (ORDER BY #{agg} #{dir}) <= #{n}"
    _sql_el(name, conn, stmt, [
      { 'id' => 'grp', 'formula' => "[Custom SQL/#{group_col}]", 'name' => group_col.split('_').map(&:capitalize).join(' ') },
      { 'id' => 'tot', 'formula' => "[Custom SQL/#{agg_alias}]", 'name' => agg_alias.split('_').map(&:capitalize).join(' ') }
    ])
  end

  # 6. Time-intelligence PRIOR PERIOD (SAMEPERIODLASTYEAR / DATEADD(-1,YEAR) /
  #    hand-rolled SELECTEDVALUE+CALCULATE+ALL(Year),Year=cy-1) -> a grouped child
  #    element on `parent_id` (the denormalized fact/view), grouped by the date,
  #    with the prior-period value via DateLookback and an optional YoY %.
  #    DM-native: works as a leveled DM element (verified 2026-06-02, exact vs PBI).
  #    `date_ref`/`value_formula` reference the PARENT element's columns, e.g.
  #    date_ref:"[ORDER_FACT View/Full Date (DATE_DIM)]",
  #    value_formula:"Sum([ORDER_FACT View/Net Revenue])".
  def prior_period_element(name:, parent_id:, date_ref:, value_formula:, value_name:,
                           amount: 1, period: 'year', with_yoy: true)
    base = name.gsub(/[^a-zA-Z0-9]/, '')[0, 14]
    per = period.capitalize           # grouping column display name (Year/Quarter/Month)
    prior = "#{value_name} (Prior #{per})"
    cols = [
      { 'id' => "#{base}_d", 'formula' => %(DateTrunc("#{period}", #{date_ref})), 'name' => per },
      { 'id' => "#{base}_v", 'formula' => value_formula, 'name' => value_name },
      { 'id' => "#{base}_p", 'formula' => %(DateLookback([#{value_name}], [#{per}], #{amount}, "#{period}")), 'name' => prior }
    ]
    calc = ["#{base}_v", "#{base}_p"]
    if with_yoy
      cols << { 'id' => "#{base}_y", 'name' => "#{value_name} YoY %",
                'formula' => "([#{value_name}] - [#{prior}]) / [#{prior}]",
                'format' => { 'kind' => 'number', 'formatString' => ',.1%' } }
      calc << "#{base}_y"
    end
    { 'id' => "#{base}PP", 'kind' => 'table', 'name' => name,
      'source' => { 'kind' => 'table', 'elementId' => parent_id },
      'columns' => cols, 'order' => cols.map { |c| c['id'] },
      'groupings' => [{ 'id' => "#{base}_g", 'groupBy' => ["#{base}_d"], 'calculations' => calc }] }
  end

  # 7. Time-intelligence YTD (TOTALYTD / DATESYTD) -> a grouped child element with
  #    CumulativeSum. CRITICAL: TWO grouping LEVELS — `outer` (e.g. year) as its
  #    own level so CumulativeSum RESETS per outer period; `inner` (e.g. month) the
  #    detail level. A single groupBy:[outer,inner] does NOT reset (verified).
  def ytd_element(name:, parent_id:, date_ref:, value_formula:, value_name:,
                  outer: 'year', inner: 'month')
    base = name.gsub(/[^a-zA-Z0-9]/, '')[0, 14]
    oc, ic = outer.capitalize, inner.capitalize
    cols = [
      { 'id' => "#{base}_o", 'formula' => %(DateTrunc("#{outer}", #{date_ref})), 'name' => oc },
      { 'id' => "#{base}_i", 'formula' => %(DateTrunc("#{inner}", #{date_ref})), 'name' => ic },
      { 'id' => "#{base}_v", 'formula' => value_formula, 'name' => value_name },
      { 'id' => "#{base}_c", 'formula' => "CumulativeSum([#{value_name}])", 'name' => "#{value_name} #{oc[0]}TD" }
    ]
    { 'id' => "#{base}YT", 'kind' => 'table', 'name' => name,
      'source' => { 'kind' => 'table', 'elementId' => parent_id },
      'columns' => cols, 'order' => cols.map { |c| c['id'] },
      'groupings' => [
        { 'id' => "#{base}_go", 'groupBy' => ["#{base}_o"] },                                    # outer level (reset point)
        { 'id' => "#{base}_gi", 'groupBy' => ["#{base}_i"], 'calculations' => ["#{base}_v", "#{base}_c"] }
      ] }
  end

  # 4. EARLIER-rank calc column -> partitioned RankDense (a DM calc column, not an element).
  #    Returns just the column hash to append to the base element's `columns`.
  def earlier_rank_column(name:, value_ref:, partition_ref:, direction: 'desc', id: nil)
    { 'id' => (id || name.gsub(/[^a-zA-Z0-9]/, '')[0, 16]),
      'name' => name,
      'formula' => "RankDense(#{value_ref}, \"#{direction}\", #{partition_ref})" }
  end

  # Best-effort DAX shape classifier -> which generator to use.
  def classify(dax)
    d = dax.to_s
    # Time-intelligence — emit grouped/leveled elements (DateLookback / CumulativeSum).
    return :time_ytd            if d =~ /\bTOTALYTD\s*\(|\bDATESYTD\s*\(/i
    # running-total idiom: CALCULATE(agg, FILTER(ALL(T[period]), T[period] <= MAX(T[period])))
    return :time_ytd            if d =~ /FILTER\s*\(\s*ALL\s*\([^)]*\)\s*,[^<]*<=\s*MAX\s*\(/i
    return :time_prior_period   if d =~ /\bSAMEPERIODLASTYEAR\s*\(/i
    return :time_prior_period   if d =~ /\bDATEADD\s*\([^,]+,\s*-?\d+\s*,\s*(YEAR|QUARTER|MONTH|WEEK|DAY)/i
    # hand-rolled prior-year: SELECTEDVALUE(Date[Year]) ... ALL(Date[Year]) ... [Year] = cy-1
    return :time_prior_period   if d =~ /SELECTEDVALUE\s*\([^)]*\[Year\]/i && d =~ /ALL\s*\([^)]*\[Year\]/i && d =~ /-\s*1\b/
    return :topn_sumx           if d =~ /\bSUMX\s*\(\s*TOPN\s*\(/i
    return :concatenatex_listagg if d =~ /\bCONCATENATEX\s*\(/i
    return :treatas_virtual_rel  if d =~ /\bTREATAS\s*\(/i
    return :earlier_rank         if d =~ /\bEARLIER\s*\(/i
    return :banded_grouping      if d =~ /\bGENERATESERIES\s*\(/i && d =~ /Band/i
    :mechanical_or_flag
  end
end

if __FILE__ == $0
  require 'optparse'
  opts = {}
  OptionParser.new { |p| p.on('--classify DAX') { |v| opts[:c] = v } }.parse!
  if opts[:c]
    puts DaxRestructure.classify(opts[:c])
  else
    warn 'library; require_relative or use --classify <dax>'
  end
end
