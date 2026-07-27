#!/usr/bin/env node
// assert-parity.mjs — the verification GATE. Two modes.
//
// PLAN: given a posted workbook (or data model) id, emit one mcp-v2 query per
// element so the agent can pull Sigma's actuals and compare to the Cognos source.
//   node scripts/assert-parity.mjs --plan --type workbook --id <workbookId>
//   node scripts/assert-parity.mjs --plan --type datamodel --id <dataModelId>
//
// CHECK: given the agent's saved query results + an expected baseline (the numbers
// from the Cognos report / source warehouse), confirm parity within tolerance.
//   node scripts/assert-parity.mjs --check --actual actual.json --expected expected.json [--tol 0.01]
//   actual.json / expected.json: { "<label>": <number>, ... }  (per-dimension or totals)
//
// A migration is GREEN only when --check passes. Do not declare success on a 200 POST alone.
import { readFileSync } from 'node:fs';
import { api, parseArgs, elementsOf } from './lib/sigma-rest.mjs';

const a = parseArgs(process.argv.slice(2));

if (a.plan) {
  if (!a.id || !a.type) { console.error('need --type workbook|datamodel --id <id>'); process.exit(2); }
  const scope = a.type === 'workbook' ? 'workbook' : 'datamodel';
  const els = elementsOf((await api('GET', a.type === 'workbook' ? `/v2/workbooks/${a.id}/elements` : `/v2/dataModels/${a.id}/elements`)).json);
  console.log(`# Parity plan for ${a.type} ${a.id} — run each query via mcp-v2, then compare to the Cognos source.\n`);
  for (const e of els) {
    console.log(`## ${e.name} (${e.kind || 'element'})  elementId=${e.id}`);
    console.log(`mcp__sigma-mcp-v2__query  type=${scope}  ${a.type === 'workbook' ? 'workbookId' : 'dataModelId'}=${a.id}`);
    console.log(`  sql: SELECT * FROM "${scope}"."${e.id}" LIMIT 50\n`);
  }
  console.log('Then save the per-element totals/dimension values to actual.json and run --check against the Cognos numbers.');
  process.exit(0);
}

if (a.check) {
  if (!a.actual || !a.expected) { console.error('need --actual <json> --expected <json>'); process.exit(2); }
  const actual = JSON.parse(readFileSync(a.actual, 'utf8'));
  const expected = JSON.parse(readFileSync(a.expected, 'utf8'));
  const tol = Number(a.tol ?? 0.01);
  // Empty-check guard: 0 expected values means there is NOTHING to verify — the
  // old loop printed "PARITY GREEN: 0/0" and exited 0, so an empty/placeholder
  // workbook (or empty {} in/out) passed vacuously. A migration with nothing to
  // compare is not parity-clean.
  if (Object.keys(expected).length === 0) {
    console.error('⛔ NOT parity-clean — 0 expected values: nothing to verify. An empty/placeholder '
      + 'workbook cannot pass parity. Build the elements + capture the source numbers, then re-run.');
    process.exit(1);
  }
  const rows = []; let fail = 0;
  for (const k of Object.keys(expected)) {
    const e = Number(expected[k]), av = Number(actual[k]);
    const ok = Number.isFinite(av) && (e === 0 ? av === 0 : Math.abs(av - e) / Math.abs(e) <= tol);
    if (!ok) fail++;
    rows.push(`${ok ? 'PASS' : 'FAIL'}  ${k}: expected ${e}, got ${Number.isFinite(av) ? av : '(missing)'}`);
  }
  console.log(rows.join('\n'));
  console.log(fail ? `\n${fail}/${rows.length} FAILED — not parity-clean.` : `\nPARITY GREEN: ${rows.length}/${rows.length} within ±${tol * 100}%.`);
  process.exit(fail ? 1 : 0);
}

console.error('specify --plan or --check (see header).');
process.exit(2);
