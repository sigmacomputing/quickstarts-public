# gap-scout subagent — guide for the main agent

When the Cognos converter can't translate an expression into a Sigma formula, it
**flags** it (never fakes it). For a flagged expression that you want to actually
resolve, spawn a separate subagent — the **gap scout** — to find a Sigma
translation that validates against the customer's real Sigma site, and persist it.

The scout writes successful rules to `~/.cognos-to-sigma/learned-rules.json` (the
customer's home dir, NOT the skill repo, so a `git pull` never clobbers them). The
converter CLI loads them via `loadLearnedRules()` and applies them *before* the
built-in translator (`applyLearnedRules` in `converter/cognos.ts`), so a customer's
discovered rule wins.

## When to spawn

After conversion emits a warning for an untranslated construct — typically:
- runtime **macros** (`#…# prompt(…,'token',…)` — dynamic column/SQL building)
- **running-total / moving-* / rank / lag / lead** (window/running calcs)
- **GetResourceString** (localization), composite / non-equi **joins**
- a **nested / non-standard CASE** the built-in CASE→If/Switch couldn't parse
- any `function "X()" has no confirmed Sigma mapping` warning

Spawn ONE scout per distinct feature; run them in parallel where possible — they're
independent.

## How to spawn (from the main agent)

Use the Agent tool with `subagent_type: 'general-purpose'`. Self-contained prompt:

```
You are a translation scout. Your job: propose a Sigma formula that replaces a
Cognos expression, validate it against Sigma's API, and persist the rule if it works.

INPUTS
- Cognos feature: <e.g. "running-total">
- Sample expressions: <2-5 examples from the module/report>
- A real warehouse table on the customer's Sigma connection to test against:
  --connection <connectionId>  --table-path <DB.SCHEMA.TABLE>
- Sigma folder id: <folder-id>
- Gate id + workdir: <expr:... and --workdir from migrate-cognos.mjs's GAP-SCOUT REQUIRED block>

PROCEDURE
1. Read refs/expression-dsl.md (the Cognos→Sigma mapping table) and
   refs/format-shapes.md. Note Sigma window funcs (SumOver/CountOver/…) silently
   error in data-model calc columns — prefer a non-window form or flag it.
2. Propose ONE candidate Sigma formula using a column that exists on --table-path.
3. Validate + persist:
   eval "$(scripts/get-token.sh)"
   node scripts/scout-validate-and-persist.mjs \
     --feature '<feature>' \
     --pattern '<Cognos regex, capture groups for column refs>' \
     --template '<Sigma template using $1,$2 for captures>' \
     --test-formula '<the candidate with a REAL column from --table-path>' \
     --connection <connectionId> --table-path <DB.SCHEMA.TABLE> \
     --folder <folder-id> --description '<one line>' --hint '<caveat>' \
     --gap-id '<expr:... from the GAP-SCOUT REQUIRED list>' --workdir <migration workdir>
4. Parse the JSON result:
   - status=validated → success; rule is now in ~/.cognos-to-sigma/learned-rules.json
   - status=escalated → try a different candidate (≤3 attempts). The last result
     carries `escalation.dry_run_cmd`. Do NOT file anything yourself.

OUTPUT
One paragraph: feature, candidate, status (validated / escalated / abandoned-after-N),
and — if escalated — the `escalation.dry_run_cmd` so the main agent can offer the
user a tracking issue.
```

## Run-each-time gate (bead beads-sigma-5l5e) — why `--gap-id` + `--workdir` matter

A flagged expression surfaces in `migrate-cognos.mjs`'s OPEN QUESTIONS as an
`expression_flagged` decision whose default is "proceed … close via gap-scout
later". To stop `--yes` from silently shipping that placeholder, `migrate-cognos.mjs`
**STOPS** (exit 11) with a `GAP-SCOUT REQUIRED` block listing each unscouted gap's
`--gap-id` (`expr:<first 80 chars of the warning>`) and the `--workdir`, **before**
any Sigma object is created.

`scout-validate-and-persist.mjs` appends its result (`validated` or `escalated`) to
`<workdir>/scout-ledger.jsonl` keyed by that `--gap-id` (via `lib/scout_gate.mjs`,
the Node mirror of the shared `scout_gate.rb`/`.py` JSONL contract). So you MUST pass
the `--gap-id` and `--workdir` the STOP block printed — otherwise the ledger entry
won't match the flagged expression and the re-run will STOP again. The gate cannot be
skipped with `--yes`: an unscouted gap always stops; once every flagged expression is
scouted (validated → translated and persisted, or escalated → genuinely-hard and
flagged) the re-run proceeds to the normal decision checkpoint. Flow: build → STOP →
scout each gap → re-run → proceed.

## Opt-in issue filing

If the scout escalates (no formula validated), it returns a ready-to-run
`scripts/escalate-gap.py … ` command (DRY-RUN by default). **Show it to the user and
ask** before filing — only run it with `--yes` on their go-ahead. It routes
converter gaps to the data-model repos (MCP + browser) with dedupe.
