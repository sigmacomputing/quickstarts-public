# Privacy & data handling — `tableau-assessment`

Read this section before running the skill, and share it with your privacy /
security / legal team if your organization needs to review tools that send
workbook metadata through a third-party LLM API.

## What this skill reads and writes

This skill connects to **two systems** on your behalf:

1. **Your Tableau Cloud site**, via:
   - The Tableau MCP (OAuth-style auth handled by Claude Code's host), used for
     `mcp__tableau__list-workbooks`, `mcp__tableau__query-datasource`, and
     similar calls against your site's Admin Insights datasources.
   - Optionally, the Tableau REST API via a Personal Access Token (PAT) you
     create — used to download `.twb` files for the per-workbook complexity layer.
2. **The Anthropic API**, via Claude Code, to drive the agent that orchestrates
   the assessment.

Everything the skill reads from Tableau passes through Claude (and therefore
the Anthropic API) on its way to producing the readout. Anthropic's data
handling for the API is at <https://www.anthropic.com/legal/privacy>.

## What crosses the Anthropic API

| Crosses API | Stays in your environment |
|---|---|
| **Aggregate counts** from Admin Insights (workbook count, user count, datasource counts, refresh job counts) | View CSV data (this skill **never** calls `mcp__tableau__get-view-data`) |
| **Names**: workbook names, view names, project names, datasource names | Warehouse rows (this skill does not query underlying databases) |
| **Owner emails**, `User License Type`, `User Site Role`, `Last Login Date` from Admin Insights | The customer database credentials Tableau uses |
| **Refresh job results**, `Final Job Result`, durations, sometimes error messages | The `.hyper` extract files (skipped on download — only `.twb` XML is fetched) |
| **`.twb` XML content** (PAT mode only) — calc-field definitions, custom SQL queries, layout XML, calculated-field formulas | Tableau session tokens (handled by Claude Code's host, not surfaced to the agent) |
| **Workbook hyperlinks**, last-accessed dates, item LUIDs | Per-row report values (this skill does not query at row resolution) |

The `.twb` XML in PAT mode is the broadest data category that crosses the API.
A `.twb` file can include:

- Calculated-field formulas (which can sometimes contain sample values in
  comments, but normally do not)
- Custom SQL queries (which contain the SQL text — the queries themselves, not
  their results)
- Workbook layout XML (positions, titles, text annotations)
- Datasource connection metadata (server names, database names, but not credentials)
- Field aliases and parameter defaults

The `.twb` does **NOT** contain row-level data from your warehouse. The data
that the workbook displays lives in `.hyper` extract files (which the skill
skips during download) or is fetched live from the warehouse at view time
(which this skill never triggers).

## What stays local

All outputs are written to a directory of your choice (default
`/tmp/assessment-<sitename>/`). The skill does NOT upload them anywhere. If you
want to share the readout with a Sigma rep or a Hakkoda engagement, that's a
deliberate `Share` action you take — zip the directory and send it manually.

You can delete the cached `.twb` files after review with no impact on the
already-rendered `readout.md`:

```bash
rm -rf /tmp/assessment-<sitename>/twbs
```

## How this compares to Hakkoda's Assessment App

Hakkoda's Snowflake Marketplace app runs **inside your Snowflake account** —
no data leaves your warehouse. If you're not comfortable with workbook
metadata passing through Anthropic's API, that is the right tool to use
instead. The tradeoff: Hakkoda's app is a 1-hour install, this skill runs in
under 2 minutes.

## How to limit exposure

If you want to run the skill but with the smallest possible data footprint:

1. **Skip PAT mode.** MCP-only mode does not fetch `.twb` files — only the
   aggregate counts cross the API. You lose the per-workbook complexity layer
   and migration shortlist, but you keep environment overview, licenses,
   refresh history, and per-workbook usage.
2. **Delete the cached `.twb` files immediately after rendering** so they
   don't sit on disk:
   ```bash
   rm -rf /tmp/assessment-<sitename>/twbs
   ```
3. **Review the JSON outputs** (`inventory.json`, `complexity.json`,
   `shortlist.json`) before sharing them with anyone — they contain
   workbook names, owner emails, and aggregate counts but no warehouse data.

## Where to direct privacy questions

- Anthropic API privacy: <https://www.anthropic.com/legal/privacy>
- Tableau Admin Insights data dictionary:
  <https://help.tableau.com/current/online/en-us/adminview_insights_manage.htm>
- This skill's source code: <https://github.com/sigmacomputing/quickstarts-public/tree/main/tableau-migration-skills/tableau-assessment>
  (you can read every script that runs on your behalf)
- Sigma privacy policy: <https://www.sigmacomputing.com/privacy-policy>
