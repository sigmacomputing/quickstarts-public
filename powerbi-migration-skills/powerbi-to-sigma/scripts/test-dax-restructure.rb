#!/usr/bin/env ruby
# test-dax-restructure.rb — unit smoke test for dax-restructure-patterns.rb (bead bjd).
# Verifies classify() routes each DAX shape and each generator emits a well-formed
# Sigma element/column. Pure, no network. Run: ruby scripts/test-dax-restructure.rb
require_relative 'dax-restructure-patterns'

$fail = 0
def ok(name, cond); puts((cond ? "  ok  " : "FAIL  ") + name); $fail += 1 unless cond; end

# ---- classify() ----
ok 'classify CONCATENATEX', DaxRestructure.classify('CONCATENATEX(VALUES(EMPLOYEES[ROLE]), EMPLOYEES[ROLE], ", ")') == :concatenatex_listagg
ok 'classify TREATAS',      DaxRestructure.classify('CALCULATE(SUM(B[H]), TREATAS(VALUES(A[K]), B[K]))') == :treatas_virtual_rel
ok 'classify EARLIER',      DaxRestructure.classify('COUNTROWS(FILTER(T, T[p]=EARLIER(T[p]) && T[m]>EARLIER(T[m])))+1') == :earlier_rank
ok 'classify GENERATESERIES band', DaxRestructure.classify('GENERATESERIES(0,100000,10000) -- Band') == :banded_grouping
ok 'classify SUMX(TOPN)',   DaxRestructure.classify('SUMX(TOPN(5, VALUES(EMPLOYEES[ROLE]), [Total Salary], DESC), [Total Salary])') == :topn_sumx
ok 'classify mechanical fallback', DaxRestructure.classify('SUM(EMPLOYEES[ANNUAL_SALARY])') == :mechanical_or_flag
ok 'classify SAMEPERIODLASTYEAR', DaxRestructure.classify('CALCULATE(SUM(F[Net]),SAMEPERIODLASTYEAR(D[Date]))') == :time_prior_period
ok 'classify DATEADD year',       DaxRestructure.classify('CALCULATE(SUM(F[Net]),DATEADD(D[Date],-1,YEAR))') == :time_prior_period
ok 'classify hand-rolled PY',     DaxRestructure.classify('VAR cy=SELECTEDVALUE(DATE_DIM[Year]) RETURN CALCULATE(SUM(ORDER_FACT[Net Revenue]),ALL(DATE_DIM[Year]),DATE_DIM[Year]=cy-1)') == :time_prior_period
ok 'classify TOTALYTD',           DaxRestructure.classify('TOTALYTD(SUM(F[Net]),D[Date])') == :time_ytd
ok 'classify running-total YTD',  DaxRestructure.classify('CALCULATE(SUM(F[Net]),FILTER(ALL(D[Month Number]),D[Month Number]<=MAX(D[Month Number])))') == :time_ytd

# ---- prior_period_element (DateLookback) ----
el = DaxRestructure.prior_period_element(name:'Revenue by Year', parent_id:'P1',
       date_ref:'[OFV/Full Date]', value_formula:'Sum([OFV/Net Revenue])', value_name:'Net Revenue')
ok 'prior_period source/levels', el.dig('source','elementId')=='P1' && el['groupings'].size==1
ok 'prior_period DateLookback',  el['columns'].any? { |c| c['formula']=='DateLookback([Net Revenue], [Year], 1, "year")' }
ok 'prior_period YoY calc',      el['columns'].any? { |c| c['name']=='Net Revenue YoY %' }

# ---- ytd_element (CumulativeSum, TWO grouping levels) ----
el = DaxRestructure.ytd_element(name:'Revenue YTD', parent_id:'P1',
       date_ref:'[OFV/Full Date]', value_formula:'Sum([OFV/Net Revenue])', value_name:'Net Revenue')
ok 'ytd two grouping levels',  el['groupings'].size==2 && el['groupings'][0]['calculations'].nil?
ok 'ytd CumulativeSum',        el['columns'].any? { |c| c['formula']=='CumulativeSum([Net Revenue])' }

# ---- concatenatex_listagg ----
el = DaxRestructure.concatenatex_listagg(name:'RolesInDept', conn:'C1', db:'CSA', schema:'TJ',
       table:'EMPLOYEES', group_col:'DEPARTMENT', text_col:'ROLE', sep:', ')
ok 'concatenatex kind/source', el['kind']=='table' && el.dig('source','kind')=='sql' && el.dig('source','connectionId')=='C1'
ok 'concatenatex LISTAGG sql', el.dig('source','statement') =~ /LISTAGG\(DISTINCT ROLE/ && el.dig('source','statement') =~ /GROUP BY DEPARTMENT/
ok 'concatenatex columns',     el['columns'].size==3 && el['columns'].all? { |c| c['id'] && c['formula'] }

# ---- treatas_virtual_rel ----
el = DaxRestructure.treatas_virtual_rel(name:'AbsByDept', conn:'C1', db:'CSA', schema:'TJ',
       fact:'ABSENCE_RECORDS', fact_key:'EMPLOYEE_ID', dim:'EMPLOYEES', dim_key:'EMPLOYEE_ID',
       group_col:'DEPARTMENT', agg:'SUM(b.HOURS)', agg_alias:'ABS_HOURS')
ok 'treatas explicit JOIN', el.dig('source','statement') =~ /JOIN CSA\.TJ\.EMPLOYEES a ON b\.EMPLOYEE_ID = a\.EMPLOYEE_ID/
ok 'treatas group + alias',  el.dig('source','statement') =~ /GROUP BY a\.DEPARTMENT/ && el.dig('source','statement') =~ /AS ABS_HOURS/

# ---- banded_grouping ----
el = DaxRestructure.banded_grouping(name:'SalaryBands', conn:'C1', db:'CSA', schema:'TJ',
       table:'EMPLOYEES', value_col:'ANNUAL_SALARY', bands:[0,50000,100000,150000])
ok 'banded VALUES spine', el.dig('source','statement') =~ /VALUES \(0\),\(50000\),\(100000\),\(150000\)/
ok 'banded count per band', el.dig('source','statement') =~ /COUNT\(\*\) AS N/ && el.dig('source','statement') =~ /GROUP BY b\.BANDFLOOR/

# ---- earlier_rank_column ----
col = DaxRestructure.earlier_rank_column(name:'Dept Salary Rank',
        value_ref:'[ANNUAL_SALARY]', partition_ref:'[DEPARTMENT]', direction:'desc')
ok 'earlier_rank RankDense', col['formula']=='RankDense([ANNUAL_SALARY], "desc", [DEPARTMENT])'
ok 'earlier_rank has id/name', !col['id'].to_s.empty? && col['name']=='Dept Salary Rank'

# ---- topn_sumx ----
el = DaxRestructure.topn_sumx(name:'Top5RoleSalary', conn:'C1', db:'CSA', schema:'TJ',
       table:'EMPLOYEES', group_col:'ROLE', agg:'SUM(ANNUAL_SALARY)', n:5, agg_alias:'ROLE_TOTAL')
ok 'topn kind/source',  el['kind']=='table' && el.dig('source','kind')=='sql' && el.dig('source','connectionId')=='C1'
ok 'topn group-by agg', el.dig('source','statement') =~ /SUM\(ANNUAL_SALARY\) AS ROLE_TOTAL/ && el.dig('source','statement') =~ /GROUP BY ROLE/
ok 'topn QUALIFY top-n', el.dig('source','statement') =~ /QUALIFY ROW_NUMBER\(\) OVER \(ORDER BY SUM\(ANNUAL_SALARY\) DESC\) <= 5/
ok 'topn columns',      el['columns'].size==2 && el['columns'].all? { |c| c['id'] && c['formula'] =~ /\[Custom SQL\// }

puts($fail.zero? ? "\nALL PASS" : "\n#{$fail} FAILURE(S)")
exit($fail.zero? ? 0 : 1)
