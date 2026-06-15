# Privacy posture — qlik-assessment

**Surface this to the customer before running.**

## What it reads
- **Tenant metadata** via qlik-cli: app list (+ usage `itemViews`, reload status/time,
  `hasSectionAccess`, `isDirectQueryMode`, size), spaces, users.
- **Per-app (with `--deep`):** the load script, master-measure expressions (via a
  temporary `MeasureList` object), and chart object definitions — to bucket
  migration complexity. No business **data rows** are read.

## What it does NOT do
- No edits to apps' content or data. The only writes are a **temporary `MeasureList`
  object per app** (`--deep`), created then immediately removed, solely to enumerate
  master measures (qlik-cli has no read-only listing for them). It does briefly save
  the app. If even that is unacceptable, run without `--deep` (inventory + usage only).
- Reads no warehouse data; transmits nothing to third parties; output stays local.

## What it produces
`<out>/inventory.json` + `<out>/readout.md` locally. The user decides what to share.

## Sensitive fields
- The users list and `itemViews` may carry personal data (names, view counts) — treat
  as confidential; delete after the engagement if the customer's policy requires.
- Section Access scripts can encode security rules — flagged, not exported verbatim.

## Credentials
qlik-cli context (API key or OAuth M2M) — see `../qlik-to-sigma/refs/connection.md`.
Never commit the key/secret; create the context in your own terminal.
