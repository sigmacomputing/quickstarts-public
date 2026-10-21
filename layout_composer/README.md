# Layout Composer

Sample application for the Sigma QuickStart "Layout Composer". Users pick elements from a library workbook, place them in zones on a canvas preset, and generate a real Sigma workbook with workbook as code. The generated workbook renders in a single embedded iframe, and users can save copies as their own.

The sample runs standalone so the pattern is easy to follow. It is intended to be one page inside your own application.

## Requirements

- Node.js (LTS)
- A Sigma organization with the QuickStart's data model and element library workbook
- Sigma client credentials with REST API and Embedding access

## Setup

```
npm install
cp .env.example .env
```

Edit `.env`:

| Key | Purpose |
| --- | --- |
| `SIGMA_BASE_URL` | API host for your Sigma cloud, for example `https://api.us-a.aws.sigmacomputing.com` |
| `CLIENT_ID`, `SECRET` | Sigma client credentials (REST API and Embedding) |
| `LIBRARY_WORKBOOK_ID` | ID at the end of the element library workbook URL |
| `TARGET_FOLDER_ID` | ID at the end of the folder URL where the generated workbook is created |
| `ORG_SLUG` | Organization slug from your Sigma URL |
| `EMBED_EMAIL` | Email of the embed user |
| `EMBED_ACCOUNT_TYPE` | Embed user account type, for example `View` |
| `EMBED_TEAMS` | Team the embed user joins (must have view access to the target folder) |
| `PORT` | Local port (default 3000) |

The IDs can be copied directly from the browser address bar. The app resolves them to API IDs at startup.

## Run

```
npm start
```

Open `http://localhost:3000`.

## Project structure

| Path | Purpose |
| --- | --- |
| `server/server.js` | Express server and static file hosting |
| `routes/api.js` | API endpoints: presets, library, generate, save, saved list, embed URL |
| `helpers/sigma.js` | Authentication, API calls, ID resolution, embed user lookup |
| `helpers/presets.js` | Canvas presets as 24-column grid zones |
| `helpers/spec.js` | Builds the workbook document from the library and the user's selections |
| `library/` | Reference copy of the element library workbook's specification |
| `public/` | Canvas page, styles and element icons |

## Notes

- `.generated.json` stores the ID of the workbook the app creates (`Layout Composer Result`). It is created automatically and is not committed.
- Saved workbooks are copied into the embed user's My Documents.
