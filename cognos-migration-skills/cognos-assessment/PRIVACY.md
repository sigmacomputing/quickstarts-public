# Cognos Assessment — privacy disclosure

Share this with the customer's privacy / security reviewer before running the
skill against a live Cognos environment.

## What this skill does

It issues **read-only `GET` requests** to the Cognos Analytics REST layer
(`/bi/v1`) to inventory the content estate and fetch the spec definitions of
Data Modules and reports, then scores them locally for migration readiness and
renders an HTML report. It **never** POSTs, modifies, runs, schedules, or deletes
anything in Cognos, and it never touches Sigma.

## What crosses the LLM (Anthropic) API

Like every Claude Code skill, the content it reads is sent through the Anthropic
API to Claude so the assessment can be produced:

| Crosses the API | Stays in Cognos / local only |
|---|---|
| Aggregate counts (module / report / folder counts) | Warehouse rows — never queried |
| Object names, owner, content-tree path, type | Database credentials |
| Data Module JSON: query subjects, items, **calc expressions**, joins | The customer's actual report *values* / result sets |
| Report-spec XML: queries, data-item expressions, viz types, prompts, filter expressions | Uploaded source files (`.xlsx` / proprietary `.pq` — not re-downloadable via REST anyway) |

Calc and filter **expressions** (which can embed business logic and sometimes
literal threshold values, e.g. `[Year] = 2023`) are part of the spec and do
cross the API. They do not include row-level warehouse data.

## Where outputs go

The skill writes to a local directory (`/tmp/cognos-assessment-<env>/` by
default): `inventory.json`, the fetched specs under `specs/`, `coverage.json`,
and `readout.html`. Nothing is uploaded anywhere. Sharing the readout with a
Sigma rep is a deliberate action by the user, not automatic.

## Auth handling

The skill reads the CA session cookie and `X-XSRF-Token` from environment
variables the user sets (`COGNOS_COOKIE`, `COGNOS_XSRF`). These are short-lived
session credentials, not stored, and are used only as request headers. They are
not written to any output file.

## How to run it more privately

- Run in **offline mode** against module/report files already exported to disk —
  no live Cognos connection is made at all.
- Scope the walk to a single folder (`--root <folderId>`) instead of the whole
  content store.
