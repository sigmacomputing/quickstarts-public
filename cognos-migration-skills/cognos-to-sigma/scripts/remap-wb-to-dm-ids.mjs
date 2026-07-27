#!/usr/bin/env node
// remap-wb-to-dm-ids.mjs — wire a Cognos-converted workbook spec to a freshly-posted DM.
//
// The report converter emits each element's `source.elementId` as the query's
// SUBJECT DISPLAY NAME (a placeholder), because the real Sigma element IDs don't
// exist until the DM is POSTed. After you POST the DM, run this to rewrite every
// element's `source.elementId` (and `dataModelId`) to the real IDs, matched by
// element NAME from the DM readback. (This was a manual step in every live test.)
//
// Usage:
//   eval "$(scripts/get-token.sh)"
//   node scripts/remap-wb-to-dm-ids.mjs --wb wb-spec.json --dm-id <dataModelId> [--out wb.remapped.json]
import { readFileSync, writeFileSync } from 'node:fs';
import { api, parseArgs, elementsOf } from './lib/sigma-rest.mjs';

const a = parseArgs(process.argv.slice(2));
if (!a.wb || !a['dm-id']) { console.error('need --wb <spec.json> --dm-id <dataModelId>'); process.exit(2); }
const dmId = a['dm-id'];
const wb = JSON.parse(readFileSync(a.wb, 'utf8'));

const els = elementsOf((await api('GET', `/v2/dataModels/${dmId}/elements`)).json);
if (!els.length) { console.error(`No elements found on data model ${dmId} (token? wrong id?)`); process.exit(1); }
const byName = new Map(els.map((e) => [e.name.toLowerCase(), e.id]));

let remapped = 0; const unresolved = [];
for (const p of wb.pages || []) for (const e of p.elements || []) {
  const s = e.source; if (!s || !('elementId' in s)) continue;
  s.dataModelId = dmId;
  const want = String(s.elementId || '').toLowerCase();
  const real = byName.get(want) || (els.length === 1 ? els[0].id : undefined);
  if (real) { s.elementId = real; remapped++; } else unresolved.push(s.elementId);
}

const out = a.out || a.wb.replace(/\.json$/, '.remapped.json');
writeFileSync(out, JSON.stringify(wb, null, 2));
console.log(JSON.stringify({ dataModelId: dmId, dmElements: els.length, remapped, unresolved, out }, null, 2));
if (unresolved.length) { console.error(`WARN: ${unresolved.length} elementId(s) unresolved — DM has no element named: ${unresolved.join(', ')}`); process.exit(1); }
