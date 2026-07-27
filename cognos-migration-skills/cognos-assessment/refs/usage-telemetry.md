# Usage telemetry on Cognos Analytics — an honest investigation

The universal weak spot of every BI migration assessment is **usage**: which
content is actually run/viewed, so you can rank a migration shortlist by audience
value and confidently retire dead content. Here is what CA does — and does not —
expose, and what to do about it.

## What the REST surface this skill uses does NOT give you

The `/bi/v1/objects/{id}/items` + `/metadata/modules/{id}` + `objects/{id}?fields=specification`
endpoints return **content metadata and spec definitions only**. They do not
include:

- Per-report / per-dashboard **run counts** or **view counts**.
- **Last-run** timestamps for a report (`modificationTime` is *last edited*, not
  *last run* — the skill records it as a weak proxy and labels it `lastRun`, but
  it is not a true execution timestamp).
- **Per-user** access maps.

So unlike the Tableau assessment (which reads `TS Events` from Admin Insights for
real per-workbook usage), this skill cannot rank by popularity from REST alone.
The shortlist is ranked by **conversion effort** (`value/(1+cost)`), not usage.
This is stated plainly in the readout's next-steps.

## Where the usage data actually lives in Cognos

Usage *is* captured by Cognos — just not on the modern content REST surface:

1. **Audit database / audit logging.** When the administrator enables Audit
   logging (Manage → Configuration → System → Audit), CA writes run events
   (`COGIPF_RUNREPORT`, `COGIPF_VIEWREPORT`, user, timestamp, duration) to a
   relational **audit database**. This is the authoritative source. It is a
   direct DB query, not a public REST endpoint — and requires admin access to
   the audit DB connection.
2. **Audit / Activity sample reports.** IBM ships an "Audit" sample package and
   "Activity reports" that run *on top of* the audit DB. An admin can run these
   and export run/view counts per report — the realistic way to get usage
   without direct DB access.
3. **Content store** (`SELECT` against the CM tables) holds `lastModified` and
   some access bookkeeping, but not a clean run-count series, and querying it
   directly is unsupported / discouraged by IBM.
4. **Activity APIs** (`/bi/v1/...`) on some CA versions expose *current/running*
   sessions and the schedule/monitor activity list — useful for "what's
   scheduled" but not a historical run-count series for ranking.

## Recommendation (what the readout tells the user)

> **Request usage telemetry from your Cognos admin.** CA does not expose
> per-report run/view counts via the REST surface this scan uses. Ask the admin
> to either (a) run the Audit Activity reports and export run counts per report,
> or (b) grant a read-only query against the audit database. Merge that into the
> shortlist to rank by real audience value and confirm retirement candidates.

If/when the admin provides a usage CSV (`report_id, runs, distinct_users,
last_run`), the scorer's `value` term can be upgraded from the
`10·n_features` proxy to `runs · sqrt(distinct_users)` — the same value formula
the Tableau and Qlik assessments use — without changing anything else in the
pipeline.
