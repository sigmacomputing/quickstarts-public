#!/usr/bin/env node
// test-scout-ledger-integrity.mjs — the gap-scan gate's ScoutGate ledger must not
// trust a bare "validated" status (issue #458).
//
// Field failure: an agent blocked from the sanctioned --force path hand-wrote a
// {"status":"validated"} line into scout-ledger.jsonl for a gap it had only
// reasoned about — never probed against the live Sigma API. classify() accepted
// it and let the run proceed past the gate as if real verification had happened.
// This test proves the integrity fix, mirroring the resolution-EVIDENCE +
// anchor-immutability-lock patterns:
//   (i)   a genuine scout record (live-probe evidence + signature) -> validated;
//   (ii)  a hand-written bare "validated" line (no evidence, no signature)
//         -> NOT validated (falls to escalated -> the gate still blocks);
//   (iii) an escalated row whose status is flipped to "validated" out of band
//         (signature no longer matches) -> NOT validated;
//   (iv)  a hand-written "validated" line with FORGED evidence but no valid
//         signature -> NOT validated;
//   (v)   a gap with no ledger row at all -> unscouted (unchanged);
//   (vi)  the genuine record round-trips through a JSON read -> still validated;
//   (vii) CROSS-LANGUAGE / interop: the new shared/lib/scout_gate.mjs signs rows
//         byte-for-byte identically to scout_gate.py / scout_gate.rb. A genuine
//         Python-recorded (scout_gate.py) `validated` row MUST verify under this
//         Node gate — proving the canonical .mjs is interop-compatible — and a
//         hand-written line beside it still falls to escalated.
//
// In the Cognos converter both the WRITER (scout-validate-and-persist.mjs ->
// lib/scout_gate.mjs) and the GATE (migrate-cognos.mjs -> lib/scout_gate.mjs#
// classify) are Node, so cases (i)-(vi) cover the whole real chain; (vii) is the
// interop safety net for the shared signing serialization. Deterministic +
// offline (no Sigma creds / network).
//
// Usage: node scripts/test-scout-ledger-integrity.mjs
import { mkdtempSync, appendFileSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import * as ScoutGate from './lib/scout_gate.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fails = [];
function check(cond, msg) {
  if (!cond) fails.push(msg);
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${msg}`);
}
function mkwd() { return mkdtempSync(join(tmpdir(), 'scout-')); }
// Neutral, invented ids — no field/session data.
function genuineEvidence() {
  return { workbook_id: 'wb-abc123', response_sha256: 'a'.repeat(64),
    phase: 'columns', probed_at: new Date().toISOString() };
}

console.log('test-scout-ledger-integrity:');

// (i) genuine scout record -> validated ---------------------------------------
{
  const d = mkwd();
  ScoutGate.record(d, { gapId: 'MEASURE_A', feature: 'MEASURE_A', status: 'validated', evidence: genuineEvidence() });
  const b = ScoutGate.classify(d, ['MEASURE_A']);
  check(JSON.stringify(b.validated) === JSON.stringify(['MEASURE_A']) && b.escalated.length === 0 && b.unscouted.length === 0,
    '(i) genuine scout record (evidence + signature) classifies as validated');
  check(existsSync(ScoutGate.keyPath(d)), '(i) sanctioned record stamped the per-conversion signing key');
}

// (ii) hand-written bare "validated" — no evidence, no signature ---------------
{
  const d = mkwd();
  appendFileSync(ScoutGate.ledgerPath(d), JSON.stringify({ gap_id: 'MEASURE_B', feature: 'MEASURE_B', status: 'validated', at: new Date().toISOString() }) + '\n');
  const b = ScoutGate.classify(d, ['MEASURE_B']);
  check(b.validated.length === 0 && JSON.stringify(b.escalated) === JSON.stringify(['MEASURE_B']),
    '(ii) hand-written bare "validated" is NOT trusted -> falls to escalated (gate blocks)');
}

// (iii) an escalated row's status flipped to "validated" out of band ----------
{
  const d = mkwd();
  ScoutGate.record(d, { gapId: 'MEASURE_C', feature: 'MEASURE_C', status: 'escalated' });
  const row = JSON.parse(readFileSync(ScoutGate.ledgerPath(d), 'utf8').split('\n')[0]);
  // Flip the SIGNED escalated row to validated (and bolt on plausible evidence);
  // the signature was computed over status 'escalated', so it no longer matches.
  row.status = 'validated';
  row.evidence = genuineEvidence();
  writeFileSync(ScoutGate.ledgerPath(d), JSON.stringify(row) + '\n');
  const b = ScoutGate.classify(d, ['MEASURE_C']);
  check(b.validated.length === 0 && JSON.stringify(b.escalated) === JSON.stringify(['MEASURE_C']),
    '(iii) escalated->validated status flip breaks the signature -> NOT validated');
}

// (iv) forged evidence but no valid signature ---------------------------------
{
  const d = mkwd();
  // A genuine record for a DIFFERENT gap creates the key file, so the tamperer
  // even has a key present — but cannot produce a matching signature for a row it
  // invents.
  ScoutGate.record(d, { gapId: 'OTHER', feature: 'OTHER', status: 'validated', evidence: genuineEvidence() });
  appendFileSync(ScoutGate.ledgerPath(d), JSON.stringify({ gap_id: 'FORGED', feature: 'FORGED', status: 'validated', at: new Date().toISOString(), evidence: genuineEvidence(), sig: 'deadbeef'.repeat(8) }) + '\n');
  const b = ScoutGate.classify(d, ['OTHER', 'FORGED']);
  check(JSON.stringify(b.validated) === JSON.stringify(['OTHER']) && JSON.stringify(b.escalated) === JSON.stringify(['FORGED']),
    '(iv) "validated" with forged evidence + bogus signature -> NOT validated');
}

// (v) no ledger row at all -> unscouted (unchanged) ---------------------------
{
  const d = mkwd();
  const b = ScoutGate.classify(d, ['NEVER_RAN']);
  check(JSON.stringify(b.unscouted) === JSON.stringify(['NEVER_RAN']) && b.validated.length === 0,
    '(v) a gap the scout never ran for stays unscouted');
}

// (vi) genuine record survives a JSON write->read round trip ------------------
{
  const d = mkwd();
  ScoutGate.record(d, { gapId: 'MEASURE_D', feature: 'MEASURE_D', status: 'validated', evidence: genuineEvidence() });
  const rows = readFileSync(ScoutGate.ledgerPath(d), 'utf8').split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));
  const reordered = rows.map((r) => Object.keys(r).sort().reduce((h, k) => { h[k] = r[k]; return h; }, {}));
  writeFileSync(ScoutGate.ledgerPath(d), reordered.map((r) => JSON.stringify(r)).join('\n') + '\n');
  const b = ScoutGate.classify(d, ['MEASURE_D']);
  check(JSON.stringify(b.validated) === JSON.stringify(['MEASURE_D']),
    '(vi) genuine validated row survives an honest JSON re-serialization');
}

// (vii) CROSS-LANGUAGE / interop: a genuine Python-recorded (scout_gate.py)
// validated row is honored by this Node gate — proving the shared signing
// serialization is byte-compatible across .mjs / .py / .rb. Cognos itself is a
// Node-only chain, so we exercise the canonical shared/lib/scout_gate.py (found by
// climbing to the repo root); if the interpreter or canonical is unavailable the
// case SKIPs rather than failing.
let PY = null;
for (const c of ['python3', 'python']) {
  try { execFileSync(c, ['--version'], { stdio: 'ignore' }); PY = c; break; } catch { /* not found */ }
}
// Climb from scripts/ to the repo root that holds shared/lib/scout_gate.py.
let pylibDir = null;
for (let up = join(__dirname, '..'); ; up = dirname(up)) {
  if (existsSync(join(up, 'shared', 'lib', 'scout_gate.py'))) { pylibDir = join(up, 'shared', 'lib'); break; }
  if (dirname(up) === up) break; // reached filesystem root
}
if (PY === null) {
  console.log('  SKIP  (vii) cross-language check — no python3 interpreter found');
} else if (pylibDir === null) {
  console.log('  SKIP  (vii) cross-language check — canonical shared/lib/scout_gate.py not found');
} else {
  const d = mkwd();
  const pylib = pylibDir;
  const code = [
    'import sys',
    `sys.path.insert(0, ${JSON.stringify(pylib)})`,
    'import scout_gate',
    'ev = {"workbook_id": "wb-py777", "response_sha256": "e" * 64, "phase": "columns", "probed_at": "2026-01-01T00:00:00+00:00"}',
    `ok = scout_gate.record(${JSON.stringify(d)}, "PY_MEASURE", "PY_MEASURE", "validated", ev)`,
    'sys.exit(0 if ok else 1)',
  ].join('\n');
  let wrote = true;
  try { execFileSync(PY, ['-c', code], { stdio: 'ignore' }); } catch { wrote = false; }
  const b = ScoutGate.classify(d, ['PY_MEASURE']);
  check(wrote && JSON.stringify(b.validated) === JSON.stringify(['PY_MEASURE']) && b.escalated.length === 0,
    '(vii) genuine Python-recorded (scout_gate.py) validated row is honored by the Node gate');
  // And a hand-written line beside the Python row still falls to escalated:
  appendFileSync(ScoutGate.ledgerPath(d), JSON.stringify({ gap_id: 'PY_FORGE', feature: 'PY_FORGE', status: 'validated', at: new Date().toISOString(), evidence: genuineEvidence() }) + '\n');
  const b2 = ScoutGate.classify(d, ['PY_MEASURE', 'PY_FORGE']);
  check(JSON.stringify(b2.validated) === JSON.stringify(['PY_MEASURE']) && JSON.stringify(b2.escalated) === JSON.stringify(['PY_FORGE']),
    '(vii) a hand-written "validated" beside the Python row still falls to escalated');
}

console.log('');
if (fails.length === 0) {
  console.log('ALL PASS — a hand-written/forged "validated" cannot defeat the gap-scan gate');
  process.exit(0);
} else {
  console.log(`${fails.length} FAILED`);
  process.exit(1);
}
