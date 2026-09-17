#!/usr/bin/env bash
set -euo pipefail

# Deploy a workbook spec to Sigma by updating an existing workbook's contents.
# Usage: ./scripts/deploy.sh [spec-file] [workbook-id]
#
# Requires:
#   SIGMA_API_HOST  — e.g. https://aws-api.sigmacomputing.com
#   SIGMA_API_TOKEN — a valid bearer token
#
# PUT /v2/workbooks/{id}/contents replaces the old PUT /v2/workbooks/{id}/spec
# endpoint. It expects a body of exactly {"contents": <the contents object>} -
# name/folderId/description live on the workbook resource itself and aren't
# part of this call.

SPEC_FILE="${1:-workbook.yaml}"
WORKBOOK_ID="${2:-}"

if [[ -z "$WORKBOOK_ID" ]]; then
  if [[ -f sigma.config.yaml ]]; then
    WORKBOOK_ID=$(yq -r '.workbook_id' sigma.config.yaml)
  fi
fi

if [[ -z "$WORKBOOK_ID" ]]; then
  echo "ERROR: workbook_id not provided and not found in sigma.config.yaml"
  exit 1
fi

if [[ ! -f "$SPEC_FILE" ]]; then
  echo "ERROR: spec file not found: $SPEC_FILE"
  exit 1
fi

echo "Deploying $SPEC_FILE to workbook $WORKBOOK_ID..."

BODY=$(yq -o=json '.' "$SPEC_FILE" | jq '{contents: .contents}')

HTTP_CODE=$(curl -s -o /tmp/deploy-response.json -w "%{http_code}" \
  -X PUT \
  -H "Authorization: Bearer $SIGMA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data-binary "$BODY" \
  "$SIGMA_API_HOST/v2/workbooks/$WORKBOOK_ID/contents")

if [[ "$HTTP_CODE" -ge 200 && "$HTTP_CODE" -lt 300 ]]; then
  echo "SUCCESS: workbook updated (HTTP $HTTP_CODE)"
  cat /tmp/deploy-response.json | jq '.' 2>/dev/null || cat /tmp/deploy-response.json
else
  echo "FAIL: deploy returned HTTP $HTTP_CODE"
  cat /tmp/deploy-response.json | jq '.' 2>/dev/null || cat /tmp/deploy-response.json
  exit 1
fi
