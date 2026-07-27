// Smoke test on the bundled fixtures: node --import tsx/esm test.ts
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { convertCognosToSigma } from './cognos.js';
import { convertCognosReportToSigma } from './cognos-report.js';
import { sigmaDisplayName } from './sigma-ids.js';

const FIX = join(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures');
let fail = 0;

// ── sigmaDisplayName must match Sigma's OWN derivation (incl. letter↔digit splits;
// verified against live DM readbacks 2026-06-10 — beads-sigma-c31q) ──────────────
const NAME_CASES: Array<[string, string]> = [
  ['CY_Q1_REVENUE', 'Cy Q 1 Revenue'],   // the 16-dep-not-found case: Q1 splits to "Q 1"
  ['PY_Q4', 'Py Q 4'],
  ['FY2024', 'Fy 2024'],                  // letters→digits boundary, multi-digit group
  ['REVENUE_FY2024', 'Revenue Fy 2024'],
  ['X2024FY', 'X 2024 Fy'],               // digits→letters boundary
  ['Sheet1_1', 'Sheet 1 1'],
  ['GROSS_PROFIT', 'Gross Profit'],
  ['Province_or_State', 'Province or State'],  // small words stay lowercase (not first)
  ['Month_number', 'Month Number'],
  ['_row_id', 'Row Id'],
];
for (const [input, expected] of NAME_CASES) {
  const got = sigmaDisplayName(input);
  if (got === expected) console.log(`✓ sigmaDisplayName(${JSON.stringify(input).padEnd(20)}) → ${JSON.stringify(got)}`);
  else { fail++; console.log(`✗ sigmaDisplayName(${JSON.stringify(input)}) → ${JSON.stringify(got)} (expected ${JSON.stringify(expected)})`); }
}

// ── go-sales-performance regression: macro→Switch wired by controlId, segmented
// control with values+default, KPI singletons, element filters ───────────────────
{
  const r = convertCognosReportToSigma(readFileSync(join(FIX, 'go-sales-performance.report.xml'), 'utf8'), { dataModelId: 'dm' });
  const els = r.workbook.pages[0].elements as any[];
  const ctl = (r.workbook.controls || []).find((c: any) => c.controlId === 'pColumn') as any;
  const checks: Array<[string, boolean]> = [
    ['pColumn control is segmented', ctl?.controlType === 'segmented'],
    ['pColumn has explicit values', JSON.stringify(ctl?.source?.values) === JSON.stringify(['Revenue', 'Gross Profit'])],
    ['pColumn defaults to Revenue', ctl?.value === 'Revenue'],
    ['pQuarter control registered with Q1-Q4 + default Q4',
      (r.workbook.controls || []).some((c: any) => c.controlId === 'pQuarter' && c.value === 'Q4' && c.source?.values?.length === 4)],
    ['Switch wired by controlId [pColumn]',
      els.some((e) => e.columns?.some((c: any) => /Switch\(\[pColumn\], "Gross Profit", \[Sheet 1\/Gross Profit\], \[Sheet 1\/Revenue\]\)/.test(c.formula)))],
    ['6 KPI singletons converted', els.filter((e) => e.kind === 'kpi-chart').length === 6],
    ['KPI value uses columnId', els.filter((e) => e.kind === 'kpi-chart').every((e) => e.value?.columnId)],
    ['KPI macro → Switch over digit-split refs',
      els.some((e) => e.kind === 'kpi-chart' && e.columns?.some((c: any) => c.formula.includes('[Sheet 1 1/Cy Q 1 Revenue]')))],
    ['detail filters became element filters', r.stats.filters >= 4],
    ['?pQuarter? filter is a boolean match column',
      els.some((e) => e.columns?.some((c: any) => c.formula === '[Quarter Label] = [pQuarter]'))],
    ['lists grouped', els.some((e) => e.kind === 'table' && e.groupings?.length)],
    ['year bound categorically on the line chart',
      els.some((e) => e.kind === 'line-chart' && e.columns?.some((c: any) => /^Text\(/.test(c.formula) && c.name === 'Year'))],
    ['no unresolved Switch placeholders', !els.some((e) => e.columns?.some((c: any) => /map prompt tokens/.test(c.formula)))],
  ];
  for (const [label, ok] of checks) {
    if (ok) console.log(`✓ go-sales: ${label}`);
    else { fail++; console.log(`✗ go-sales: ${label}`); }
  }
}
for (const f of readdirSync(FIX)) {
  try {
    if (f.endsWith('.module.json')) {
      const r = convertCognosToSigma(readFileSync(join(FIX, f), 'utf8'), { connectionId: 'c', database: 'DB', schema: 'S' });
      if (!r.model.pages[0].elements.length) throw new Error('no elements');
      console.log(`✓ ${f.padEnd(34)} module → ${r.stats.elements} elems · ${r.stats.columns} cols · ${r.stats.metrics} metrics · ${r.stats.relationships} rels`);
    } else if (f.endsWith('.report.xml')) {
      const r = convertCognosReportToSigma(readFileSync(join(FIX, f), 'utf8'), { dataModelId: 'dm' });
      console.log(`✓ ${f.padEnd(34)} report → ${r.stats.tables} tables · ${r.stats.pivots} pivots · ${r.stats.kpis} kpis · ${r.stats.charts} charts · ${r.stats.maps} maps · ${r.stats.columns} cols · ${r.stats.filters} filters · ${r.stats.controls} controls`);
    }
  } catch (e: any) { fail++; console.log(`✗ ${f} — ${e.message}`); }
}
console.log(fail ? `\n${fail} FAILED` : '\nall fixtures converted ✓');
process.exit(fail ? 1 : 0);
