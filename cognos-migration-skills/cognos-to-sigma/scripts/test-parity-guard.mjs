#!/usr/bin/env node
// Regression test for the cognos assert-parity empty-check guard (2026-07-10).
//
// Before: `assert-parity.mjs --check` with an empty `expected` ({}) printed
// "PARITY GREEN: 0/0" and exited 0 — so an empty/placeholder workbook (or empty
// in/out) passed vacuously. The guard refuses 0 comparisons. Offline (pure JS).
//
//   node scripts/test-parity-guard.mjs

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const AP = join(HERE, 'assert-parity.mjs');
const d = mkdtempSync(join(tmpdir(), 'cog-'));
const fails = [];
const check = (cond, msg) => { console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${msg}`); if (!cond) fails.push(msg); };

function run(expected, actual) {
  const ef = join(d, 'e.json'), af = join(d, 'a.json');
  writeFileSync(ef, JSON.stringify(expected));
  writeFileSync(af, JSON.stringify(actual));
  try {
    execFileSync('node', [AP, '--check', '--expected', ef, '--actual', af], { stdio: 'pipe' });
    return 0;
  } catch (e) { return e.status ?? 1; }
}

// 1) real non-empty matching → GREEN (exit 0) — happy path intact.
check(run({ Revenue: 1000, Orders: 50 }, { Revenue: 1000, Orders: 50 }) === 0,
  'real matching values => exit 0 (GREEN, not broken)');
// 2) empty expected → NOT clean (exit 1) — vacuous-green hole closed.
check(run({}, {}) === 1, 'empty expected => exit 1 (no vacuous 0/0 GREEN)');
// 3) a genuine mismatch still fails (sanity).
check(run({ Revenue: 1000 }, { Revenue: 5 }) === 1, 'mismatch => exit 1');

console.log();
if (fails.length) { console.log(`${fails.length} FAILURE(S):`); fails.forEach((f) => console.log(`  - ${f}`)); process.exit(1); }
console.log('ALL PASS');
