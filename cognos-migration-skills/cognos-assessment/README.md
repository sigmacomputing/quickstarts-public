# cognos-assessment

Read-only migration-readiness assessment for an IBM Cognos Analytics estate →
Sigma. Mirrors the `tableau-assessment` pattern: inventory the content tree,
score each Data Module / report against the **exact** coverage of the
`cognos-to-sigma` converter, roll up an estate auto-migration %, name every gap,
and render a branded HTML readout.

```
SKILL.md                      phased workflow (Connect → Discover → Score → Effort → Render)
PRIVACY.md                    customer-facing data-handling disclosure
scripts/
  discover-cognos.sh          walk CA /bi/v1 content tree, fetch specs, emit inventory.json (read-only)
  score-coverage.mjs          classify auto/hint/manual/unhandled vs. converter gaps; per-artifact + roll-up (zero-dep)
  render-report.mjs           branded standalone readout.html (zero-dep)
refs/
  ca-rest.md                  endpoints + auth used
  scoring-rubric.md           every gap signal → bucket → remediation
  usage-telemetry.md          honest take on CA usage stats (REST doesn't expose them)
```

## Quick start (offline, against the bundled samples)

```bash
node scripts/score-coverage.mjs --in ~/cognos-samples --out /tmp/cognos-assessment-sample
node scripts/render-report.mjs  --out /tmp/cognos-assessment-sample
open /tmp/cognos-assessment-sample/readout.html
```

## Live

```bash
export COGNOS_BASE="https://<host>/bi/v1"
export COGNOS_COOKIE="<Cookie header>"
export COGNOS_XSRF="<X-XSRF-Token>"
bash scripts/discover-cognos.sh --root .public_folders --out /tmp/cognos-assessment-<env>
node scripts/score-coverage.mjs --in /tmp/cognos-assessment-<env>/specs --out /tmp/cognos-assessment-<env>
node scripts/render-report.mjs  --out /tmp/cognos-assessment-<env>
```

Read-only and all-free. Tableau is the reference point. Not a replacement for a
deeper hands-on engagement.
