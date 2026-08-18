# Sigma Workbooks as Code — GitHub CI/CD Demo

Manage a Sigma workbook entirely through code. Edit a YAML spec, open a pull request, and let GitHub Actions validate and deploy it — no manual clicks in the Sigma UI required.

```
workbook.yaml  →  git branch  →  PR (validate)  →  merge to main  →  deploy to Sigma
```

## Why Workbooks as Code?

Traditional BI development happens inside the UI — clicking through menus, dragging elements, configuring charts. That works fine for one-off exploration, but it breaks down when teams need:

- **Version control** — who changed what, when, and why
- **Code review** — peers review workbook changes before they go live
- **CI/CD** — automated validation and deployment, no manual publishing
- **Reproducibility** — spin up identical workbooks across environments (dev, staging, prod)
- **Rollback** — revert a bad change with `git revert`, not manual UI reconstruction

Sigma's Workbooks as Code API lets you define an entire workbook — pages, elements, charts, KPIs, filters, layout — in a single YAML file, and manage it with the same git-based workflow you already use for application code.

## What's in this repo

| File | Purpose |
|------|---------|
| `workbook.yaml` | The workbook spec — single source of truth for the entire workbook |
| `sigma.config.yaml` | Config: target workbook ID and API host |
| `scripts/validate.sh` | Validates the spec against Sigma's API (`POST /v2/workbooks/spec/verify`) |
| `scripts/deploy.sh` | Deploys the spec to update the live workbook (`PUT /v2/workbooks/{id}/spec`) |
| `scripts/drift-check.sh` | Compares the live workbook against the git spec — detects out-of-band UI edits |
| `.github/workflows/validate.yml` | Runs on every PR — blocks merge if the spec is invalid |
| `.github/workflows/deploy.yml` | Runs on merge to `main` — deploys the updated spec to Sigma |
| `.github/workflows/drift-check.yml` | Runs every 6 hours — opens a PR if the live workbook drifts from git |

## The demo workbook

**Plugs Electronics — Sales Overview** — a self-contained dashboard powered by inline SQL (no external data model required):

- 4 KPI cards (Revenue, Profit, Orders, Total Units Sold) with month-over-month comparison
- Monthly revenue trend (bar chart)
- Revenue by Region (horizontal bar) and Revenue by Product Type (donut)
- Filterable sales detail table
- Date range and region controls
- Sample data generated via custom SQL — dates are relative to today so charts always have data

## How it works

### 1. PR opens — spec is validated

When a pull request is opened (or updated), the **Validate Workbook Spec** workflow runs automatically. It authenticates with Sigma's API using client credentials and calls the [spec verify endpoint](https://help.sigmacomputing.com/reference/verifyspec) to check that the YAML compiles correctly — valid element references, valid formulas, valid layout.

If validation fails, the PR is blocked from merging.

### 2. PR merges — workbook is deployed

When the PR merges to `main`, the **Deploy Workbook** workflow runs. It calls the [spec update endpoint](https://help.sigmacomputing.com/reference/updateworkbookspec) to push the new spec to the live Sigma workbook. The published workbook updates in place — same URL, same embeds, same permissions.

### 3. Making a change

```bash
# Create a branch
git checkout -b add-margin-kpi

# Edit the workbook spec
# (add a new KPI, change a chart, update a filter — it's just YAML)
vim workbook.yaml

# Push and open a PR
git push -u origin add-margin-kpi
gh pr create --title "Add gross margin KPI"

# CI validates the spec automatically
# Review, approve, merge — the workbook updates on merge
```

## Handling UI edits (drift detection)

If someone edits the workbook in the Sigma UI and publishes, those changes exist in the live workbook but not in git. The git spec is now stale.

This repo includes a **drift detection** workflow that catches this automatically:

- **Scheduled check** — `drift-check.yml` runs every 6 hours (configurable via cron), pulls the live spec from Sigma, and compares it to `workbook.yaml`
- **Auto-opens a PR** — if drift is detected, a pull request is created with the live changes so a human can review before merging
- **Deduplication** — won't open a second PR if one is already open
- **Manual check** — run `./scripts/drift-check.sh` locally at any time to see the full diff

### Reviewing a drift PR

When a drift PR is opened, here's how to review and test before merging:

```bash
# 1. Check out the drift branch
git fetch origin
git checkout drift/sync-<timestamp>

# 2. Validate the spec compiles
sigma api workbooks spec verify --json "$(yq -o=json workbook.yaml)"

# 3. Create a preview workbook (doesn't touch the live one)
sigma api workbooks spec create --json "$(yq -o=json '.name = "[Preview] " + .name' workbook.yaml)"
# → Returns a workbookId — open it in Sigma to visually confirm the changes

# 4. Once confirmed, delete the preview and merge the PR
sigma api files delete --params '{"inodeId": "<preview-workbook-id>"}'
```

> **Tip:** The diff will contain cosmetic noise (key reordering, quote style changes) from Sigma's spec normalization. Focus on structural changes — element `kind`, formulas, column additions/removals, layout changes.

> **Note:** Drift PRs are created by `github-actions[bot]`, which means the validate workflow won't auto-trigger (GitHub prevents this to avoid recursive loops). Run validation manually: go to **Actions** > **Validate Workbook Spec** > **Run workflow** and select the drift branch — or validate locally with the command above.

### Resolving drift

When a drift PR is opened, you have two options:

1. **Merge the PR** — the UI changes are intentional, pull them into git. Review the diff, approve, merge.

2. **Close the PR and re-deploy** — the UI edit was a mistake. Close the PR, then re-run the deploy workflow to push the git spec back to Sigma and restore the repo's version.

> **Why not auto-merge?** The live spec and the git spec won't be byte-identical even when they represent the same workbook — Sigma normalizes key ordering, letter casing, and adds internal fields during the round-trip. Human review ensures only meaningful changes make it into git.

## Setup guide

### Prerequisites

- A Sigma account with API access
- A GitHub repository (public or private)
- Sigma API client credentials (client ID + secret)

### Step 1: Create API credentials in Sigma

1. Go to **Administration** > **APIs & embed secrets** in your Sigma workspace
2. Click **Create new** under API client credentials
3. Save the **Client ID** and **Client Secret** — you'll need them in the next step

### Step 2: Configure GitHub secrets and variables

In your GitHub repo, go to **Settings** > **Secrets and variables** > **Actions**:

**Secrets** (sensitive, encrypted):
| Name | Value |
|------|-------|
| `SIGMA_CLIENT_ID` | Your Sigma API client ID |
| `SIGMA_CLIENT_SECRET` | Your Sigma API client secret |

**Variables** (non-sensitive):
| Name | Value |
|------|-------|
| `SIGMA_API_HOST` | Your Sigma API host (see below) |

> **Finding your API host:** This depends on your Sigma cloud region. Common values:
> | Cloud | API Host |
> |-------|----------|
> | AWS US | `https://aws-api.sigmacomputing.com` |
> | AWS Canada | `https://api.ca.sigmacomputing.com` |
> | GCP | `https://api.sigmacomputing.com` |
>
> Check **Administration** > **Account** in Sigma to confirm your cloud.

### Step 3: Update the config

Edit `sigma.config.yaml` with your target workbook's ID:

```yaml
workbook_id: "your-workbook-id-here"
api_host: "https://aws-api.sigmacomputing.com"
spec_file: "workbook.yaml"
```

> **Finding your workbook ID:** Open the workbook in Sigma, look at the URL — it contains a short hash. You can also use the Sigma API: `GET /v2/workbooks?search=Your Workbook Name`.

### Step 4: Update the connection ID

The included `workbook.yaml` uses custom SQL with sample data — no external data model required. You just need to replace the `connectionId` in the spec with your own Sigma connection UUID:

```yaml
source:
  kind: sql
  connectionId: "your-connection-id-here"  # ← replace this
  statement: |
    ...
```

> **Finding your connection ID:** Go to **Administration** > **Connections** in Sigma, click your connection, and grab the UUID from the URL. Or use the API: `GET /v2/connections`.

## Spec structure reference

```yaml
name: "My Workbook"
description: "Managed via GitHub"
document:
  kind: workbook
  schemaVersion: 1
  pages:
    - id: page-data
      name: Data
      visibility: hidden          # Hidden pages hold source tables
      elements:
        - id: my-source
          kind: table
          name: My Data
          source:
            kind: sql             # Custom SQL — runs on any warehouse connection
            connectionId: "..."   # Your Sigma connection UUID
            statement: |
              SELECT DATE '2024-01-01' AS "Date", 100.00 AS "Revenue"
              UNION ALL SELECT DATE '2024-02-01', 200.00
          columns:
            - id: col-revenue
              name: Revenue
              formula: "[Custom SQL/Revenue]"  # SQL sources use [Custom SQL/...] prefix

    - id: page-main
      name: Dashboard
      elements:
        - id: revenue-kpi
          kind: kpi-chart
          name: Total Revenue
          source:
            kind: table
            elementId: my-source    # References the hidden source table
          columns:
            - id: kpi-val
              name: Revenue
              formula: "Sum([My Data/Revenue])"  # Downstream elements use [ElementName/...]
              format:
                kind: number
                formatString: "$,.0f"
          value: { columnId: kpi-val }

  layout: |
    <?xml version="1.0" encoding="utf-8"?>
    <Page type="grid" gridTemplateColumns="repeat(24, 1fr)" id="page-main">
      <LayoutElement elementId="revenue-kpi" gridColumn="1 / 13" gridRow="1 / 6"/>
    </Page>
```

### Key concepts

| Concept | Details |
|---------|---------|
| **Data source** | Use `kind: sql` with a `connectionId` and `statement` for custom SQL, or `kind: data-model` to reference an existing Sigma data model |
| **SQL column formulas** | On the SQL source element itself, reference columns with `[Custom SQL/ColumnName]` |
| **Cross-element formulas** | Downstream elements reference the source by name: `[ElementName/ColumnName]` |
| **Layout grid** | 24-column grid. `gridColumn: "1 / 13"` = left half, `"13 / 25"` = right half |
| **Containers** | Use `kind: container` + `GridContainer` in layout XML to group elements |
| **Controls** | `kind: control` for filters — supports `date-range`, `list`, `text`, `boolean` types |
| **Hidden pages** | Set `visibility: hidden` on data pages so end users only see dashboards |

## Local development

If you have the [Sigma CLI](https://help.sigmacomputing.com/docs/sigma-cli) installed, you can validate and deploy without CI:

```bash
# Validate
sigma api workbooks spec verify --json "$(yq -o=json workbook.yaml)"

# Deploy
sigma api workbooks spec update \
  --params '{"workbookId": "your-workbook-id"}' \
  --json "$(yq -o=json workbook.yaml)"

# Preview (create a throwaway workbook to test changes without affecting prod)
sigma api workbooks spec create --json "$(yq -o=json '.name = "[Preview] " + .name' workbook.yaml)"

# Check for drift
./scripts/drift-check.sh workbook.yaml
```

## Adapting this template

1. **Fork or clone** this repo
2. **Add** your Sigma API credentials as GitHub secrets and set the API host variable
3. **Update** the `connectionId` in `workbook.yaml` with your Sigma connection UUID
4. **Deploy** — run the deploy workflow manually to create the workbook in your org
5. **Update** `sigma.config.yaml` with the new workbook ID
6. **Push** — CI/CD handles the rest

The included spec works out of the box with any Snowflake connection — the sample data is generated via SQL, no external tables needed. To use your own data, replace the custom SQL source with a `kind: data-model` reference or your own SQL query.

## Resources

- [Workbooks as Code documentation](https://help.sigmacomputing.com/docs/workbooks-as-code)
- [Sigma REST API reference](https://help.sigmacomputing.com/reference)
- [Sigma CLI](https://help.sigmacomputing.com/docs/sigma-cli)
- [API authentication](https://help.sigmacomputing.com/reference/token)
