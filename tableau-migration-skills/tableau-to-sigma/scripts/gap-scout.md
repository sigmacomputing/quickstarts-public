# gap-scout subagent — guide for the main agent

When `scan-workbook-gaps.rb` flags an ❌ Unhandled (or high-volume ⚠️ Hint)
feature in the customer's workbook, spawn a separate subagent — the "gap
scout" — to figure out a Sigma translation that works against the customer's
actual Sigma site.

The scout writes successful translations to `~/.tableau-to-sigma/learned-rules.yaml`
(in the customer's home dir, NOT the skill repo, so `git pull` of the skill
never clobbers them). Subsequent conversions on the same machine apply the
rule automatically.

## When to spawn

After Phase 0a's gap report is produced. For each `:unhandled` row, OR for
any `:hint` row whose count is high enough to be worth automating, spawn ONE
scout per gap. Run them in parallel where possible — they're independent.

## How to spawn (from the main agent)

Use the Agent tool with `subagent_type: 'general-purpose'`. Self-contained
prompt:

```
You are a translation scout. Your job: propose a Sigma formula that
replaces a Tableau pattern, validate it against Sigma's API, and persist
the rule if it works.

INPUTS
- Tableau feature: <feature name, e.g. "WINDOW_AVG">
- Sample formulas: <3-5 grep'd examples from the customer's .twb>
- Sigma data-model id: <dm-id>
- Sigma master element id: <element-id>
- Sigma folder id: <folder-id>

PROCEDURE
1. Read the relevant skill docs:
   - tableau-to-sigma/refs/data-model-spec.md
   - tableau-to-sigma/refs/workbook-layout.md
   - tableau-to-sigma/scripts/lib/sigma_functions.rb (the whitelist —
     anything outside ALL_SET silently errors)
2. Propose ONE candidate Sigma formula. Prefer functions in the whitelist.
   For window/rank/cumulative functions, remember they silently error in
   workbook-master grouping-table calc cols AND in DM-element calc cols
   — route to a non-grouping context (workbook scratchpad calc) or a
   Custom SQL DM element with explicit OVER(...).
3. Run:
   ruby scripts/scout-validate-and-persist.rb \
     --feature '<feature>' \
     --pattern '<Tableau regex, capture groups for column refs>' \
     --template '<Sigma template using \1, \2 for captures>' \
     --test-formula '<the candidate with REAL column names from this DM>' \
     --data-model-id <dm-id> \
     --master-element-id <element-id> \
     --folder-id <folder-id> \
     --description '<one-line>' \
     --hint '<post-publish caveat, e.g., "non-grouping context only">' \
     --example-from '<which workbook/line>'
4. Parse the JSON result.
   - status=validated  → success; rule is now in the customer's local YAML
   - status=escalated  → propose a different candidate (up to 3 attempts)
                          OR escalate via `gh issue create` if `gh` works

OUTPUT
Return a one-paragraph summary: feature, candidate, status (validated /
escalated / abandoned-after-N-attempts), and the workbook_id of the test
spec for cleanup later.
```

## What the scout depends on

- `scripts/validate-sigma-formula.rb` — primitive that POSTs a minimal test
  workbook + runs the column-type guard. Returns JSON.
- `scripts/scout-validate-and-persist.rb` — wraps validate-sigma-formula and
  on success appends to `~/.tableau-to-sigma/learned-rules.yaml`; on failure
  writes a structured escalation to `~/.tableau-to-sigma/escalations/`.
- `scripts/learned-rules.rb` — the loader the main build script uses. The
  customer never edits this; the scout writes it.

## File locations (CRITICAL)

| File | Path | Why |
|---|---|---|
| Learned rules | `~/.tableau-to-sigma/learned-rules.yaml` | Customer home. `git pull` cannot clobber. |
| Escalations | `~/.tableau-to-sigma/escalations/*.yaml` | Same — customer-local. |
| Override for testing | `$TABLEAU_TO_SIGMA_HOME` env var | Points at a sandbox path for CI. |

The `.gitignore` in this repo also blocks `.tableau-to-sigma/` from being
committed if someone accidentally creates it inside the repo.

## Why a separate subagent

- **Context isolation**: each Sigma POST response is verbose. Keeping the
  reasoning + validation loops out of the main conversion's context is
  critical for large multi-workbook migrations.
- **Bounded budget**: capped at N attempts per gap. Failure doesn't block
  the main conversion — failed gaps just remain as `WARN` lines telling the
  agent to handle manually post-publish.
- **Compounds across customers**: every customer who runs the scout
  contributes to their local rules library. If we ever decide to bless a
  rule for the global skill, it gets promoted from `confidence: validated`
  to a built-in regex in `build-charts-from-signals.rb`.

## Status

| Phase | Status | Path |
|---|---|---|
| 1: pre-flight gap scanner | ✅ shipped commit 8016adf | `scripts/scan-workbook-gaps.rb` |
| 2: scout subagent design  | ✅ this file (current commit) | `scripts/gap-scout.md` |
| 3a: validation primitive  | ✅ this commit | `scripts/validate-sigma-formula.rb` |
| 3b: scout wrapper script  | ✅ this commit | `scripts/scout-validate-and-persist.rb` |
| 3c: learned-rules loader  | ✅ this commit | `scripts/learned-rules.rb` |
| 3d: build-script integration | ✅ this commit | `build-charts-from-signals.rb` reads via `LearnedRules.load`/`apply` |
| 4: auto-file GitHub/beads issues on escalation | ⏳ TODO (beads-sigma-0b3) | — |
| 5: promote-rule-to-built-in flow | ⏳ TODO (future) | — |

End-to-end validation: scout validated `WINDOW_AVG(SUM([Sales]))` → `Avg([Master/Sales])`
against the Orders DM, wrote rule to local YAML, build script automatically
applied the rule on a synthetic `.twb` with that formula (no maintainer
intervention).
