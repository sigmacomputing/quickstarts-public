# Privacy & data handling — `quicksight-assessment`

Read this before running the skill, and share it with your privacy / security /
legal team if your organization needs to review tools that send analysis and
dataset metadata through a third-party LLM API.

## What this skill reads and writes

**READ-ONLY.** Every call is a `list-*` or `describe-*` (GET-equivalent). The
skill **never** writes to QuickSight and **never** posts to Sigma. It connects to
**two systems** on your behalf:

1. **Your Amazon QuickSight account**, via the **AWS CLI** (`aws quicksight ...`,
   shelled out as a subprocess — no boto3), authenticated as **you** through
   whatever AWS profile you've already configured (`aws sso login`,
   `gimme-aws-creds`, or static creds). QuickSight reads from the **identity
   region** — almost always `us-east-1` even when data lives elsewhere. The skill
   reads:
   - Analysis / dashboard / dataset / data-source listings (counts)
   - Per-analysis **AnalysisDefinition** — visual configuration + **calc-field
     expressions** + parameters + FilterGroups + layout shape
   - Per-dataset **describe-data-set** — physical source kinds, import mode
     (SPICE / DIRECT_QUERY), custom-SQL presence, joins, transform count, RLS/CLS
2. **The Anthropic API**, via Claude Code, to drive the agent.

Everything the skill reads passes through Claude (and therefore the Anthropic
API) on its way to producing the readout. Anthropic's API data handling:
<https://www.anthropic.com/legal/privacy>.

## What crosses the Anthropic API

| Crosses API | Stays in your environment |
|---|---|
| **Aggregate counts** (analysis / dashboard / dataset / data-source counts) | Warehouse rows (this skill **never** queries the underlying database) |
| **Names**: analysis names, dashboard names, dataset names, data-source names | **SPICE in-memory rows** (never read) |
| **AnalysisDefinition** — visual config, **calc-field expressions**, parameter defaults, FilterGroup definitions, layout shape | AWS credentials (held by the AWS CLI, not surfaced to the agent) |
| **Dataset metadata** — physical source kinds, import mode, custom-SQL presence, join/transform counts, **RLS/CLS flags** | The actual cell values your visuals display |
| Data-source connection **types** (Snowflake, Redshift, Athena, …) — not credentials | The warehouse credentials QuickSight uses to connect |

> **Calc-field expressions are the broadest data category that crosses the API.**
> A QuickSight calculated field can encode business-sensitive logic (margin
> formulas, eligibility rules, custom KPIs). When the skill reads an
> AnalysisDefinition, that expression text crosses the Anthropic API. RLS rule
> *configuration flags* cross (whether RLS is on), but the row-level predicate
> values themselves are not pulled at definition time. Tell stakeholders this
> before running.

The AnalysisDefinition and dataset describes do **NOT** contain row-level data
from your warehouse or SPICE. The data your visuals display is fetched live (or
from the SPICE cache) at view time, which this skill never triggers.

## What stays local

All outputs are written to a directory of your choice (default
`/tmp/qs-assessment-<acct>/`) and are **not uploaded anywhere**. The decoded
definitions live under `raw-defs/` (analyses) and `raw-datasets/` (datasets). To
share the readout with a Sigma rep, that's a deliberate action you take (zip and
send).

You can delete the decoded definitions after review with no impact on the
already-rendered `readout.html` / `readout.md`:

```bash
rm -rf /tmp/qs-assessment-<acct>/raw-defs /tmp/qs-assessment-<acct>/raw-datasets
```

## How to limit exposure

1. **Run counts-only.** A **Standard-edition** account rejects the
   `describe-*-definition` / `describe-data-set` APIs, so the skill degrades to
   environment counts only — no calc-field text crosses the API. (This is
   automatic on Standard; on Enterprise the definition scan is the whole point.)
2. **Delete the raw definitions immediately after rendering** (command above).
3. **Review the JSON outputs before sharing** — `inventory.json` and the
   `raw-defs/` decode contain calc-field text; `shortlist.json` and
   `migration-plan.json` contain names and scores but no calc-field bodies.
4. **Scope the AWS profile.** Run under an IAM principal scoped to
   `quicksight:List*` / `quicksight:Describe*` on the account you intend to
   assess — nothing more.

## Where to direct privacy questions

- Anthropic API privacy: <https://www.anthropic.com/legal/privacy>
- Amazon QuickSight API reference:
  <https://docs.aws.amazon.com/quicksight/latest/APIReference/Welcome.html>
- This skill's source: every script under `scripts/` runs on your behalf and is
  readable — `quicksight-inventory.py` is the only one that touches AWS, and
  every call it makes is a read-only `list-*` / `describe-*`.
- Sigma privacy policy: <https://www.sigmacomputing.com/privacy-policy>
