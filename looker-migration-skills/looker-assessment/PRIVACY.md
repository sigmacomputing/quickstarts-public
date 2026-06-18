# Privacy posture — looker-assessment

**Surface this to the customer before running.**

## What it reads
- **Instance metadata** via the Looker REST API 4.0: LookML models (+ explores),
  projects, connections (name / dialect / database / host), Looks, dashboards
  (title / owner / folder / kind), users, groups, folders.
- **Usage** via Looker's **System Activity** model (`system__activity`, the `history`
  explore): per-dashboard / per-Look run counts and active-user counts over the
  selected window. Aggregate counts only — no per-user content rows.
- **Per-dashboard tile definitions** (deep mode, default): vis types, pivots, table
  calcs (`dynamic_fields`), filters, merged-result references, Liquid usage — to
  bucket migration complexity. No business **data rows** are read.

## What it does NOT do
- **No writes of any kind.** Only `GET` requests and System Activity inline queries
  (`POST /queries/run/json` is a read against the system model — it creates no saved
  object). Nothing in Looker is created, edited, or deleted. Contrast with
  `qlik-assessment`, which briefly creates a temporary object; this skill does not.
- Reads no warehouse content rows; runs no content query; reads no PDT/cache data.
- Transmits nothing to third parties; output stays local.

> Like every Claude Code skill, what the scan reads is sent through the Anthropic API
> to Claude. This is a weaker posture than a tool that keeps everything inside your
> warehouse. The user should be told this before running.

## What it produces
`<out>/inventory.json` + `<out>/readout.md` + `<out>/readout.html` locally. Nothing is
uploaded — the user decides what to share.

## Sensitive fields
- The users list and System Activity counts may carry personal data (names, run
  counts) — treat as confidential; delete after the engagement if policy requires.
- Connection `host` / `database` identify warehouse endpoints (not credentials) —
  flagged for the dialect mapping, never the secret.

## Credentials
Looker API3 client credentials in `~/.looker/looker.ini` (`base_url` on `:19999`,
`client_id`, `client_secret`). Never commit the secret; create the ini in your own
environment. The System Activity queries need a role with
`see_system_activity` (admin or equivalent); without it, usage degrades to a
tile-count proxy and the rest of the assessment still runs.
