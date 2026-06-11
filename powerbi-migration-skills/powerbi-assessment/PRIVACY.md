# Privacy & data handling — `powerbi-assessment`

Read this before running the skill, and share it with your privacy / security /
legal team if your organization needs to review tools that send report and
semantic-model metadata through a third-party LLM API.

## What this skill reads and writes

**READ-ONLY.** The skill never writes to Power BI / Fabric and never posts to
Sigma. It connects to **two systems** on your behalf:

1. **Your Power BI / Fabric tenant**, via the Fabric REST API and the Power BI
   REST API, authenticated as **you** through a Microsoft first-party public
   client (device-code sign-in — no Entra app registration, no admin consent).
   The token is cached locally at `/tmp/pbiauth/cache.bin`. The skill reads:
   - Workspace + item listings (counts by type)
   - Per semantic-model **TMSL** (the full model definition) via `getDefinition`
   - Per report **PBIR** (the report definition) via `getDefinition`
   - Refresh history (when the Power BI REST token is available)
   - *(Fabric-admin only, if available)* Activity Events + Scanner API
2. **The Anthropic API**, via Claude Code, to drive the agent.

Everything the skill reads passes through Claude (and therefore the Anthropic
API) on its way to producing the readout. Anthropic's API data handling:
<https://www.anthropic.com/legal/privacy>.

## What crosses the Anthropic API — and why it's RICHER than the Tableau case

| Crosses API | Stays in your environment |
|---|---|
| **Aggregate counts** (workspace / model / report counts, item-type counts) | Warehouse rows (this skill **never** queries the underlying database) |
| **Names**: model names, report names, workspace names | Power BI / Entra credentials (held in the device-code token cache, not surfaced to the agent) |
| **Full TMSL** per semantic model — including **DAX measure expressions**, **calculated-column / calculated-table DAX**, and **RLS role definitions** | The actual cell values your reports display |
| **PBIR** per report — visual configuration, page structure, visual types | `.pbix` binary model blobs (this skill reads the JSON definition, not the binary) |
| Warehouse **host names** parsed from M (e.g. `ymb68310.snowflakecomputing.com`) — not credentials | The warehouse credentials Power BI uses to connect |
| Refresh job results (status, type, timestamps) | |

> **This is a broader, more sensitive data category than the
> `tableau-assessment` skill's `.twb` scan.** Tableau's `.twb` carries
> calc-field formulas and custom SQL. Power BI's **TMSL carries the entire DAX
> model surface plus row-level-security role definitions** (the predicates that
> decide which rows each user role can see), and **PBIR carries the full visual
> layout**. If your RLS roles or DAX encode business-sensitive logic, that text
> crosses the API. Tell stakeholders this before running.

The TMSL and PBIR do **NOT** contain row-level data from your warehouse. The
data the report displays is fetched live (or from an import cache) at view time,
which this skill never triggers.

## What stays local

All outputs are written to a directory of your choice (default
`/tmp/pbi-assessment-<tenant>/`) and are **not uploaded anywhere**. The decoded
TMSL/PBIR live under `raw-tmsl/` and `raw-pbir/`. To share the readout with a
Sigma rep, that's a deliberate action you take (zip and send).

You can delete the decoded model/report definitions after review with no impact
on the already-rendered `readout.md`:

```bash
rm -rf /tmp/pbi-assessment-<tenant>/raw-tmsl /tmp/pbi-assessment-<tenant>/raw-pbir
```

## How to limit exposure

1. **Scope to fewer workspaces.** Pass `--workspaces <id1>,<id2>` to
   `fabric-inventory.py` to inventory only specific workspaces.
2. **Cap models scanned.** `--limit-models N` stops TMSL extraction after N
   models — useful for a sanity pass before committing to a full DAX dump.
3. **Delete the raw definitions immediately after rendering** (command above).
4. **Review the JSON outputs before sharing** — `inventory.json` contains DAX
   measure text and warehouse host names; `shortlist.json` and
   `migration-plan.json` contain names and scores but no DAX bodies.

## Where to direct privacy questions

- Anthropic API privacy: <https://www.anthropic.com/legal/privacy>
- Microsoft Fabric REST API: <https://learn.microsoft.com/en-us/rest/api/fabric/>
- Power BI REST API: <https://learn.microsoft.com/en-us/rest/api/power-bi/>
- This skill's source: every script under `scripts/` runs on your behalf and is
  readable — `fabric-inventory.py` and `probe-admin.py` are the only two that
  touch the network, and both are GET / read-only (plus one read-only
  Scanner-API `POST getInfo` probe with an empty body).
- Sigma privacy policy: <https://www.sigmacomputing.com/privacy-policy>
