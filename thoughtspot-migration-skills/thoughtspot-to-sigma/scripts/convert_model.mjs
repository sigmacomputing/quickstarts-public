#!/usr/bin/env node
// Convert a ThoughtSpot model TML file to a Sigma data-model spec (JSON to stdout).
// Usage: node convert_model.mjs <model.tml>
//   env: SIGMA_CONNECTION_ID, TS_DB, TS_SCHEMA, CONVERTER_PATH (build/thoughtspot.js)
import { readFileSync } from 'fs';
const CONV = process.env.CONVERTER_PATH;  // path to sigma-data-model-mcp build/thoughtspot.js
if (!CONV) { console.error('set CONVERTER_PATH (sigma-data-model-mcp build/thoughtspot.js), or call the convert_thoughtspot_to_sigma MCP tool and pass its JSON to the build step'); process.exit(2); }
const { convertThoughtSpotToSigma } = await import(CONV);
const tml = readFileSync(process.argv[2], 'utf8');
const r = convertThoughtSpotToSigma(tml, {
  connectionId: process.env.SIGMA_CONNECTION_ID,
  database: process.env.TS_DB || '',
  schema: process.env.TS_SCHEMA || '',
});
process.stdout.write(JSON.stringify({ model: r.model, stats: r.stats, warnings: r.warnings }));
