// Convert a LookML explore to a Sigma data-model spec file, running the
// converter directly against a source tree (bypasses the deployed MCP build —
// see SKILL.md "Converter-build gotcha").
//
// Usage:
//   LOOKML_DIR=/path/to/lookml-project \
//   CONVERTER_SRC=/path/to/sigma-data-model-mcp/src/lookml.ts \
//     node --import tsx/esm convert_dm.mjs <exploreName> <out.json>
//
// LOOKML_DIR must contain *.view.lkml files — directly or in a views/ subdir.
// A <something>.model.lkml is OPTIONAL: with one, the named explore is
// converted (joins → relationships); without one, the converter runs in
// view-only mode (each view → standalone element; cross-view
// ${view.SQL_TABLE_NAME} refs still resolve across the whole directory, which
// is why you should always pass the WHOLE project dir, not a single file).
// CONVERTER_SRC points at the converter's lookml.ts (so you get the latest
// fixes without waiting for the long-running MCP server to reload).
// SIGMA_CONNECTION_ID is written into the spec as a placeholder; post_dm.py
// swaps in the full UUID.
//
// Outputs: <out.json> (the model) + <out minus .json>-warnings.json (the
// converter's warnings array — migrate-looker.py surfaces 🔶/⚠ entries).
import fs from 'fs';
import path from 'path';
import { pathToFileURL } from 'url';

const explore = process.argv[2] || '';
const out = process.argv[3] || '/tmp/looker_dm.json';

const dir = process.env.LOOKML_DIR;
if (!dir) { console.error('Set LOOKML_DIR=/path/to/lookml-project'); process.exit(1); }
const converterSrc = process.env.CONVERTER_SRC;
if (!converterSrc) { console.error('Set CONVERTER_SRC=/path/to/sigma-data-model-mcp/src/lookml.ts'); process.exit(1); }
const connectionId = process.env.SIGMA_CONNECTION_ID || 'PLACEHOLDER_CONNECTION_ID';

const { convertLookMLToSigma } = await import(pathToFileURL(converterSrc).href);

const files = [];
// ALL model files — multi-model projects are common (the converter merges
// explores across model files; taking only the first hides every explore
// defined in the others).
const modelFiles = fs.readdirSync(dir).filter(f => f.endsWith('.model.lkml')).sort();
for (const f of modelFiles) {
  files.push({ name: f, content: fs.readFileSync(path.join(dir, f), 'utf8') });
}
if (!modelFiles.length) {
  console.error(`No *.model.lkml in ${dir} — converting in VIEW-ONLY mode (standalone elements, no joins)`);
}
const modelFile = modelFiles.length > 0;
// view files: views/ subdir if present, else the dir itself
const viewsDir = fs.existsSync(path.join(dir, 'views')) ? path.join(dir, 'views') : dir;
for (const f of fs.readdirSync(viewsDir)) {
  if (f.endsWith('.view.lkml'))
    files.push({ name: f, content: fs.readFileSync(path.join(viewsDir, f), 'utf8') });
}
if (!files.length) { console.error(`No .lkml files found in ${dir}`); process.exit(1); }

const res = convertLookMLToSigma(files, {
  connectionId,
  exploreName: modelFile ? explore : (explore || undefined),
  joinStrategy: 'relationships',
});
fs.writeFileSync(out, JSON.stringify(res.model, null, 2));   // NOTE: return prop is `.model`, not `.sigmaDataModel`
fs.writeFileSync(out.replace(/\.json$/, '') + '-warnings.json', JSON.stringify(res.warnings, null, 2));
console.error(`explore=${explore || '(view-only)'} -> ${out}`);
console.error('stats:', JSON.stringify(res.stats));
console.error('warnings:', res.warnings.length);
res.warnings.forEach(w => console.error('  ' + w));
