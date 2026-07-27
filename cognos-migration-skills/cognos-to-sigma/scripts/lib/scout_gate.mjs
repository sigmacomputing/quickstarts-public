// Shared "run-each-time gap-scout gate" (bead beads-sigma-5l5e) — Node side.
//
// Mirrors scout_gate.rb / scout_gate.py EXACTLY, including the integrity fix
// (issue #458). A per-conversion JSONL ledger at <workdir>/scout-ledger.jsonl,
// one row per scouted gap:
//   { "gap_id": ..., "feature": ..., "status": "validated"|"escalated"|"accepted",
//     "at": ..., "evidence": {...}, "sig": ... }
//
// In the Cognos converter both the WRITER (scout-validate-and-persist.mjs →
// record()) and the GATE (migrate-cognos.mjs → classify()) are Node, so this file
// is self-consistent by construction. But the signing serialization is a
// byte-for-byte mirror of scout_gate.rb / scout_gate.py so a `validated` row
// written by ANY of the three languages verifies under ANY of the three gates
// (interop-verified: the SHA-256 over "<secret>\n<canonical_row>" is identical
// across Ruby JSON.generate / Python json.dumps(separators=(",",":")) / Node
// JSON.stringify because all three emit compact JSON with the same FIXED key
// order and the evidence keys SORTED).
//
// INTEGRITY (issue #458): a `validated` status is the only one that lets a
// feature migrate, so it is the one an under-pressure caller is tempted to forge
// by hand-writing a bare {"status":"validated"} line. A `validated` row is
// honored ONLY when it carries live-probe evidence (real Sigma workbook/data-model
// id + SHA-256 of the columns readback + a probe timestamp) AND a signature that
// re-verifies against the per-conversion secret. A hand-written line (no evidence,
// no signature) or an `escalated` row whose status was flipped to `validated`
// (signature no longer matches) falls through to the escalated bucket, so the
// gap-scan gate still blocks. The genuine scout path records evidence + signature
// and passes unchanged. Kept dependency-free (node:fs / node:path / node:crypto
// stdlib only) so it can be vendored into any plugin's scripts/lib/ unchanged.
import { existsSync, statSync, readFileSync, appendFileSync, openSync, writeSync, closeSync } from 'node:fs';
import { join } from 'node:path';
import { createHash, randomBytes } from 'node:crypto';

const LEDGER = 'scout-ledger.jsonl';
// Per-conversion signing secret, written ONCE by the first sanctioned record and
// read back to verify row signatures. A hand-written ledger line carries no
// signature this secret produced, so it cannot pass as `validated`.
const KEYFILE = '.scout-ledger.key';

export function ledgerPath(workdir) {
  return join(String(workdir || ''), LEDGER);
}

export function keyPath(workdir) {
  return join(String(workdir || ''), KEYFILE);
}

// The sanctioned signing secret for this conversion. Created on first use with
// owner-only perms; a concurrent creator wins the race harmlessly (we re-read).
// null only if the workdir is unwritable — which fails safe (an unsignable
// `validated` claim is rejected).
export function loadOrCreateKey(workdir) {
  const p = keyPath(workdir);
  try {
    if (existsSync(p)) return readFileSync(p, 'utf8').trim();
    const secret = randomBytes(32).toString('hex');
    // O_WRONLY | O_CREAT | O_EXCL, 0600 — mirror the Ruby/Python exclusive create.
    const fd = openSync(p, 'wx', 0o600);
    try { writeSync(fd, secret); } finally { closeSync(fd); }
    return secret;
  } catch (e) {
    if (e && e.code === 'EEXIST') {
      try { return readFileSync(p, 'utf8').trim(); } catch { return null; }
    }
    return null;
  }
}

// Read-only key accessor for classify — NEVER creates one. If no sanctioned
// writer ever ran (no key file), a `validated` row cannot verify → rejected.
export function loadKey(workdir) {
  const p = keyPath(workdir);
  try {
    if (!existsSync(p)) return null;
    return readFileSync(p, 'utf8').trim();
  } catch { return null; }
}

// Evidence is stored key-sorted so the signature is stable across JSON round
// trips. Flat string→scalar map (workbook id, response hash, probe timestamp).
export function canonicalEvidence(ev) {
  if (!ev || typeof ev !== 'object' || Array.isArray(ev)) return null;
  const keys = Object.keys(ev);
  if (keys.length === 0) return null;
  const out = {};
  for (const k of keys.map(String).sort()) out[k] = ev[k];
  return out;
}

// Deterministic serialization of the row's SEMANTIC content — a byte-for-byte
// mirror of scout_gate.rb#canonical_row / scout_gate.py#canonical_row (compact
// JSON, FIXED key order). `sig` is excluded so the same call verifies a row that
// already carries one.
export function canonicalRow(row) {
  const obj = {
    gap_id: String(row.gap_id ?? ''),
    feature: String(row.feature ?? ''),
    status: String(row.status ?? ''),
    at: String(row.at ?? ''),
    evidence: canonicalEvidence(row.evidence),
  };
  return JSON.stringify(obj);
}

export function sign(secret, row) {
  return createHash('sha256').update(`${secret}\n${canonicalRow(row)}`, 'utf8').digest('hex');
}

// Does this evidence object actually reference a live probe? The sanctioned
// writer records the real Sigma workbook/data-model id the validation POST created
// plus a hash of the columns-readback response. A bare/empty blob does not qualify.
export function probeEvidence(ev) {
  return !!ev && typeof ev === 'object' &&
    String(ev.workbook_id ?? '').trim() !== '' &&
    String(ev.response_sha256 ?? '').trim() !== '';
}

// A ledger row counts as a genuinely VALIDATED scout result only when it is
// marked validated, carries live-probe evidence, AND its signature verifies
// against the per-conversion secret. The whole integrity check (#458).
export function validatedEvidence(row, secret) {
  if (!row || typeof row !== 'object' || String(row.status) !== 'validated') return false;
  if (!probeEvidence(row.evidence)) return false;
  const sig = String(row.sig ?? '');
  if (sig === '' || String(secret ?? '') === '') return false;
  return sig === sign(secret, row);
}

// Append one scout result. Non-fatal on error — a failed ledger write must never
// crash a scout that otherwise succeeded. `evidence` (required in practice for
// status 'validated') is the live-probe record; every row is signed with the
// sanctioned per-conversion secret so an out-of-band edit is tamper-evident.
// Signature-compatible with scout_gate.rb / scout_gate.py.
export function record(workdir, { gapId, feature, status, evidence } = {}) {
  try {
    if (!workdir || !existsSync(workdir) || !statSync(workdir).isDirectory()) return false;
    const row = {
      gap_id: String(gapId || feature),
      feature: String(feature),
      status: String(status),
      at: new Date().toISOString(),
    };
    const ev = canonicalEvidence(evidence);
    if (ev) row.evidence = ev;
    const secret = loadOrCreateKey(workdir);
    if (secret) row.sig = sign(secret, row);
    appendFileSync(ledgerPath(workdir), JSON.stringify(row) + '\n');
    return true;
  } catch (e) {
    console.error(`scout-ledger write failed (non-fatal): ${e.message}`);
    return false;
  }
}

export function readLedger(workdir) {
  const p = ledgerPath(workdir);
  if (!existsSync(p)) return [];
  const out = [];
  for (const line of readFileSync(p, 'utf8').split('\n')) {
    const t = line.trim();
    if (!t) continue;
    try { out.push(JSON.parse(t)); } catch { /* skip malformed */ }
  }
  return out;
}

// gapIds: string[] — the unhandled gaps the scout was supposed to cover.
// Returns three disjoint buckets of gap-ids (mirrors scout_gate.rb#classify):
//   unscouted — no ledger row at all (scout never ran) → hard STOP
//   escalated — scouted, but no row carries VERIFIED validated evidence
//               (tried-and-escalated, or a forged/unsigned `validated`) → --force
//   validated — has at least one signed, evidence-backed `validated` row
// A `validated` row is only honored when its live-probe evidence + signature
// verify (#458); an unverifiable one is treated as unvalidated, never trusted.
export function classify(workdir, gapIds) {
  const secret = loadKey(workdir);
  const by = {};
  for (const e of readLedger(workdir)) {
    const k = String(e.gap_id);
    (by[k] = by[k] || []).push(e);
  }
  const unscouted = gapIds.filter((id) => !by[String(id)]);
  const rest = gapIds.filter((id) => by[String(id)]);
  const validated = rest.filter((id) => by[String(id)].some((x) => validatedEvidence(x, secret)));
  const escalated = rest.filter((id) => !validated.includes(id));
  return { unscouted, escalated, validated };
}
