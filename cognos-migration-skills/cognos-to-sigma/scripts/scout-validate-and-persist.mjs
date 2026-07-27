#!/usr/bin/env node
// scout-validate-and-persist.mjs — the gap-scout's terminal step.
// Given a candidate Sigma formula + the gap context, validate it against the customer's
// Sigma site (POST a throwaway probe data model whose one calc column IS the candidate,
// check it resolves to a concrete type), then PERSIST the rule on success or report an
// escalation command on failure. The subagent does the reasoning (proposing the
// candidate); this script does the deterministic POST/validate/write.
//
// Usage:
//   eval "$(scripts/get-token.sh)"
//   node scripts/scout-validate-and-persist.mjs \
//     --feature 'running-total' \
//     --pattern '\brunning-total\s*\(\s*\[([^\]]+)\]\s*\)' \
//     --template 'CumulativeSum([$1])' \
//     --test-formula 'CumulativeSum([Net Revenue])' \
//     --connection <connId> --table-path DEMO_DB.DEMO.ORDER_FACT \
//     --folder <folderId> [--description '...'] [--hint '...'] \
//     [--gap-id '<expr:... from migrate-cognos.mjs GAP-SCOUT REQUIRED>'] [--workdir <dir>]
//
// --gap-id + --workdir feed the run-each-time gap-scout gate (bead beads-sigma-5l5e):
// the result (validated|escalated) is appended to <workdir>/scout-ledger.jsonl keyed
// by --gap-id, so migrate-cognos.mjs's OPEN-QUESTIONS gate sees the flagged
// expression as scouted and stops blocking it on the re-run.
//
// Output (JSON): { status: "validated"|"escalated", rule_path?, escalation? , ... }
import { homedir } from 'node:os';
import { join } from 'node:path';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { api, extractId, parseArgs } from './lib/sigma-rest.mjs';
import * as scoutGate from './lib/scout_gate.mjs';

const a = parseArgs(process.argv.slice(2));
for (const k of ['feature', 'template', 'test-formula', 'connection', 'table-path', 'folder']) {
  if (!a[k]) { console.error(`need --${k}`); process.exit(2); }
}
const [db, schema, ...t] = a['table-path'].split('.');
const table = t.join('.');
const RULES = join(homedir(), '.cognos-to-sigma', 'learned-rules.json');

// minimal probe DM: a warehouse-table element exposing the raw columns the candidate
// references (bare `[Name]` refs → raw cols `[TABLE/Name]`), plus the candidate calc col.
const tail = table.toUpperCase();
const refNames = [...new Set([...a['test-formula'].matchAll(/\[([^\]\/]+)\]/g)].map((m) => m[1]))];
const rawCols = refNames.map((nm, i) => ({ id: `r${i}`, name: nm, formula: `[${tail}/${nm}]` }));
const cols = [...rawCols, { id: 'c1', name: 'scout_candidate', formula: a['test-formula'] }];
const probe = {
  folderId: a.folder, name: `GAPSCOUT PROBE ${a.feature} ${Date.now()}`, schemaVersion: 1,
  pages: [{ id: 'p1', name: 'P', elements: [{
    id: 'e1', kind: 'table', name: 'Probe',
    source: { connectionId: a.connection, kind: 'warehouse-table', path: [db, schema, table] },
    columns: cols, order: cols.map((c) => c.id),
  }] }],
};
const post = await api('POST', '/v2/dataModels/spec', probe);
const id = extractId(post, 'dataModelId');
let resolved = false, detail = '', probeBody = '';
if (id) {
  const cols = await api('GET', `/v2/dataModels/${id}/columns`);
  probeBody = cols.text || ''; // raw columns-readback → hashed into the probe evidence
  const list = cols.json?.entries || cols.json?.columns || (Array.isArray(cols.json) ? cols.json : []);
  const cand = (Array.isArray(list) ? list : []).find((c) => (c.name || c.columnName) === 'scout_candidate');
  const type = cand && (cand.type?.type || cand.columnType || cand.type);
  resolved = !!type && String(type).toLowerCase() !== 'error';
  detail = `column type=${type || 'missing'}`;
  await api('DELETE', `/v2/files/${id}`); // always clean up the probe
} else {
  detail = `POST rejected: ${post.text.slice(0, 200)}`;
}

if (resolved) {
  let rules = [];
  try { rules = JSON.parse(readFileSync(RULES, 'utf8')); rules = Array.isArray(rules) ? rules : (rules.rules || []); } catch {}
  rules = rules.filter((r) => r.feature !== a.feature);
  rules.push({ feature: a.feature, pattern: a.pattern || a['test-formula'], template: a.template, flags: 'gi', description: a.description || '', hint: a.hint || '', validatedAt: new Date().toISOString() });
  mkdirSync(join(homedir(), '.cognos-to-sigma'), { recursive: true });
  writeFileSync(RULES, JSON.stringify(rules, null, 2));
  // Record to the run-each-time gap-scout ledger (bead beads-sigma-5l5e) so
  // migrate-cognos.mjs's OPEN-QUESTIONS gate sees this gap as scouted. A
  // 'validated' row MUST carry live-probe evidence (issue #458): the real Sigma
  // probe data-model id this POST created + a SHA-256 of the live columns-readback
  // + the probe timestamp. scout_gate signs the row (per-conversion
  // .scout-ledger.key) so the gate (migrate-cognos.mjs -> scoutGate.classify)
  // honors ONLY a signed, evidenced 'validated'; a hand-written line cannot forge
  // this probe.
  const evidence = {
    workbook_id: String(id || ''),
    response_sha256: createHash('sha256').update(probeBody, 'utf8').digest('hex'),
    phase: 'columns',
    probed_at: new Date().toISOString(),
  };
  scoutGate.record(a.workdir, { gapId: a['gap-id'], feature: a.feature, status: 'validated', evidence });
  console.log(JSON.stringify({ status: 'validated', feature: a.feature, rule_path: RULES, detail }, null, 2));
  process.exit(0);
}

// escalation (opt-in; this script does NOT file — it hands back the command)
const dry = `python3 scripts/escalate-gap.py --skill cognos-to-sigma --category converter --feature ${JSON.stringify(a.feature)} --description ${JSON.stringify(a.description || '')} --source-pattern ${JSON.stringify(a.pattern || '')} --template-attempted ${JSON.stringify(a.template)} --test-formula ${JSON.stringify(a['test-formula'])} --sigma-response ${JSON.stringify(detail)}`;
scoutGate.record(a.workdir, { gapId: a['gap-id'], feature: a.feature, status: 'escalated' });
console.log(JSON.stringify({ status: 'escalated', feature: a.feature, detail, escalation: { dry_run_cmd: dry, file_cmd: dry + ' --yes' } }, null, 2));
process.exit(0);
