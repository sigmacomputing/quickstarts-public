# MicroStrategy Assessment — privacy disclosure

Share this with the customer's privacy / security reviewer before running the
skill against a live MicroStrategy environment.

## What this skill does

It logs in (`POST /api/auth/login` — the only POST, it creates a session) and
then issues **read-only `GET` requests** to the MicroStrategy REST API to
count reports/documents, fetch dossier definitions, and list datasources. It
then scores everything locally and renders a markdown readout. It **never**
modifies, executes, or deletes anything in MicroStrategy, **never runs a
report or warehouse query**, and never touches Sigma.

## What crosses the LLM (Anthropic) API

Like every Claude Code skill, the content it reads is sent through the
Anthropic API to Claude so the assessment can be produced:

| Crosses the API | Stays in MicroStrategy / local only |
|---|---|
| Aggregate counts (report / document / dossier / datasource counts) | Warehouse rows — never queried |
| Object names and ids (projects, reports, dossiers, datasources) | Database credentials (the endpoints used never return them) |
| Dossier definitions: chapter/page names, visualization types, panel-stack structure, dataset attribute/metric names | Report *results* / metric values (no report is executed) |
| Datasource database types (e.g. `snow_flake`) | Connection strings / logins |

## Where outputs go

A local directory (`/tmp/mstr-assessment-<env>/` by default):
`inventory.json` + `readout.md`. Nothing is uploaded anywhere; sharing the
readout is a deliberate user action.

## Auth handling

`MSTR_USERNAME` / `MSTR_PASSWORD` are read from environment variables (or
`~/.sigma-migration/env`) and used only for the login call. The session token
lives in process memory; credentials are not stored and not written to any
output file.

## How to run it more privately

- Use a **low-privilege account** — MicroStrategy's own object security bounds
  what the walk can see.
- Cap the per-dossier fetches with `--max-dossiers`.
- Scope to one project with `--project`.
