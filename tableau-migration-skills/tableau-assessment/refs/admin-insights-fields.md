# Admin Insights field reference

Verified field names on each Admin Insights datasource. The field names are
inconsistent across datasources (some say `LUID`, some say `Id`, some use spaces)
and a typo silently fails the query.

## Site LUIDs (resolve fresh per site — do NOT hardcode)

The Admin Insights datasource LUIDs are unique per Tableau site. Resolve them at
runtime with:

```
mcp__tableau__search-content   terms="Admin Insights"   filter.contentTypes=["datasource"]
# Filter results to `containerName == "Admin Insights"`; keep luid + name.
```

Expected datasource names: `TS Users`, `TS Events`, `Permissions`,
`Subscriptions`, `Groups`, `Job Performance`, `Tokens`, `Viz Load Times`,
`Site Content`, `Job Performance`.

## TS Users — license + activity per user

| Field | Type | Use |
|---|---|---|
| `User LUID` | dim | unique user ID; pair with COUNTD |
| `User License Type` | dim | `Creator` / `Explorer` / `Viewer` / `Unlicensed` |
| `User Site Role` | dim | finer-grained role (e.g., `Site Administrator Creator`) |
| `User Email` | dim | for joining to ownership data |
| `Days Since Last Login` | measure | numeric — average over a license cohort |
| `Last Login Date` | dim (datetime) | for cold-user detection |
| `Workbooks` | measure | count of workbooks owned by the user |
| `Views` | measure | count of views owned by the user |
| `Data Sources ` | measure | **note trailing space in field name** — count of published datasources owned |
| `Occupied Creator Licenses` | measure (calc) | already-built FIXED LOD |
| `Occupied Explorer Licenses` | measure (calc) | already-built |
| `Occupied Viewer Licenses` | measure (calc) | already-built |
| `Total Occupied Licenses` | measure (calc) | sum of the above |
| `Total Allowed Licenses` | measure | site cap |
| `Total Remaining Licenses` | measure (calc) | allowed minus occupied |

> **Field name gotcha**: `Data Sources ` has a trailing space in the published
> datasource. Most clients normalize this but the VDS query tool does NOT — pass
> the exact name including the trailing space, or aliasing won't resolve.

## TS Events — audit log

| Field | Type | Use |
|---|---|---|
| `Event Id` | dim | unique event id — **NOT `Event LUID`** (that name doesn't exist) |
| `Event Date` | dim (datetime) | when |
| `Event Type` | dim | `Access` / `Publish` / `Update` / `Create` / `Delete` |
| `Event Name` | dim | finer-grained event name |
| `Item Type` | dim | `View` / `Workbook` / `Data Source` / `FlowRunSpec` / null |
| `Item LUID` | dim | LUID of the affected item |
| `Item Name` | dim | current name of the affected item |
| `Workbook Name` | dim | parent workbook name (set even for view events) |
| `Project Name` | dim | current project |
| `Actor User Id` | dim | who fired the event |
| `Actor User Name` | dim | email of the actor |
| `Actor License Role` | dim | actor's license type at event time |
| `Item Owner Email` | dim | current owner of the item |
| `Number of Events` | measure (calc) | always 1 per row; SUM for counts |
| `Count of Distinct Actors` | measure (calc) | COUNTD wrapper on `Actor User Name` |

## Site Content — workbooks, views, datasources, projects

| Field | Type | Use |
|---|---|---|
| `Item LUID` | dim | unique id of content item |
| `Item Name` | dim | display name |
| `Item Type` | dim | `Workbook` / `View` / `Datasource` / `Flow` / `Project` / `Metric` / `Metric Definition` |
| `Item Hyperlink` | dim | full URL — useful for hand-off |
| `View Type` | dim | when Item Type=View: `dashboard` / `view` / `story` |
| `View Workbook Name` | dim | parent workbook of a view |
| `Owner Email` | dim | content owner |
| `Top Parent Project Name` | dim | top-level project (null for content at root) |
| `Item Parent Project Name` | dim | direct parent project |
| `Size (MB)` | measure | item size in MB |
| `Total Size (MB)` | measure | rolled-up size for projects |
| `Is Data Extract` | dim (boolean) | whether the workbook/datasource contains an extract |
| `Has Refresh Scheduled` | dim (boolean) | whether the item is on a refresh schedule |
| `Data Source Content Type` | dim | `Published` / `Embedded` (null if not a datasource) |
| `Data Source Database Type` | dim | `hyper` / `sqlproxy` / `excel-direct` / `publishedConnection` / `federated` / `textscan` / `googledrive` / ... |
| `Data Source Is Certified` | dim (boolean) | governance signal |
| `Created At` / `Last Accessed At` / `Last Published At` | dim (datetime) | age signals |
| `Extracts Refreshed At` | dim (datetime) | last refresh completion |

## Job Performance — refresh + flow job history

| Field | Type | Use |
|---|---|---|
| `Job ID` | dim | unique job id; pair with COUNTD |
| `Job LUID` | dim | string LUID |
| `Job Type` | dim | `Refresh Extracts` / `RunFlow` / `Subscription` / `DataAlert` / `Metric` |
| `Job Result` | dim | `Succeeded` / `Failed` / `Sent to Bridge` (Bridge passthrough) |
| `Final Job Result` | dim (calc) | resolves Bridge passthrough → final outcome |
| `Job Duration` | measure | total seconds |
| `Job Execution Duration` | measure | seconds running after start |
| `Job Queued Duration` | measure | seconds waiting in queue |
| `Item Type` / `Item Name` / `Item LUID` | dim | what the job ran against |
| `Owner Email` | dim | item owner |
| `Schedule Name` / `Schedule LUID` | dim | the schedule that fired the job |
| `Created At` / `Started At` / `Completed At` | dim (datetime) | timeline (with `*_local` variants) |
| `Was Manual Run` | dim (boolean) | one-off Run Now vs. scheduled |
| `Error Message` | dim | runtime error detail (long string) |

## Common field-name mistakes

| Wrong | Right | On |
|---|---|---|
| `Event LUID` | `Event Id` | TS Events |
| `Datasource Name` | `Item Name` (with `Item Type` filter) | Site Content |
| `Site Role` | `User Site Role` | TS Users |
| `License Type` | `User License Type` | TS Users |
| `Data Sources` *(no trailing space)* | `Data Sources ` *(trailing space)* | TS Users — yes really |
| `View Count` | use TS Events SUM(Number of Events) | TS Events |
| `Hits` | use TS Events `Event Type=Access` | TS Events |
| `Is Archived` | **does not exist** on Tableau Cloud Admin Insights Site Content. Use `Top Parent Project Name != "Personal Space"` to drop the per-user sandbox; the REST `/workbooks` endpoint already hides truly deleted/archived items server-side. | Site Content |

## VizQL session contention

`get-datasource-metadata` and `query-datasource` will 401 under parallel fan-out.
**Serialize all Admin Insights calls.** The slowdown is small (~8 calls × ~1.5s = ~12s)
and it avoids the silent failure mode.
