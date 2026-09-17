# API Calling Sigma Agents QuickStart

## Overview
This QuickStart demonstrates Sigma's Agent API (Public Beta): calling a Sigma agent directly over REST instead of through a chat element or a workbook action. It covers listing agents, running one non-streaming or streaming, and requesting structured JSON output via `responseFormat`.

Reference: https://help.sigmacomputing.com/docs/call-agents-with-the-api

## Features
- List every agent accessible across the org (`GET /v2/workbookAgents`)
- List agents scoped to a specific workbook (`GET /v2/workbooks/{workbookId}/agents`)
- Call an agent and get a single JSON response back
- Call an agent with `stream: true` and watch the response arrive incrementally
- Request structured output by supplying a JSON Schema for `responseFormat`

## API Endpoints Used
- `GET /api/agents/all` — proxies `GET /v2/workbookAgents`
- `GET /api/agents/workbook/:workbookId` — proxies `GET /v2/workbooks/{workbookId}/agents`
- `POST /api/agents/:workbookId/:agentId/run` — proxies `POST /v2/workbooks/{workbookId}/agents/{agentId}`, forwarding the request body as-is (`messages`, `stream`, `responseFormat`, `maxTurns`, etc.) and piping the upstream response straight through — as a stream when `stream: true`, as JSON otherwise.
- `GET /api/workbooks` — existing endpoint reused here to populate the workbook picker

## File Structure
```
api-embed-agents/
├── index.html          # Workbook/agent picker, call form, response panel
└── README.md            # This documentation
```

## Technical Notes
- No iframe/JWT embed is involved here — this page calls the agent API directly rather than rendering embedded Sigma content, so it skips the JWT flow other pages in this project use.
- The route is a thin proxy: it doesn't reshape the request or response body, so the browser's JSON/schema input maps directly to what Sigma's API expects. This keeps the sample honest about the real request/response shape rather than hiding it behind app-specific transformations.
- Streaming responses are displayed as raw incoming text, appended to the response panel as chunks arrive. This endpoint is Public Beta — verify the exact streaming event format against the current docs before building anything beyond a demo on top of it.
- An agent must already exist on the workbook you select (build one via the workbook's `Agents` panel) — this project only calls agents, it doesn't create them.
