#!/usr/bin/env bash
set -euo pipefail

# Deploy a workbook spec to Sigma by updating an existing workbook.
# Usage: ./scripts/deploy.sh [spec-file] [workbook-id]
#
# Requires:
#   SIGMA_API_HOST  — e.g. https://aws-api.sigmacomputing.com
#   SIGMA_API_TOKEN — a valid bearer token

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

HTTP_CODE=$(curl -s -o /tmp/deploy-response.json -w "%{http_code}" \
  -X PUT \
  -H "Authorization: Bearer $SIGMA_API_TOKEN" \
  -H "Content-Type: application/yaml" \
  -H "Accept: application/json" \
  --data-binary @"$SPEC_FILE" \
  "$SIGMA_API_HOST/v2/workbooks/$WORKBOOK_ID/spec")

if [[ "$HTTP_CODE" -ge 200 && "$HTTP_CODE" -lt 300 ]]; then
  echo "SUCCESS: workbook updated (HTTP $HTTP_CODE)"
  cat /tmp/deploy-response.json | jq '.' 2>/dev/null || cat /tmp/deploy-response.json
else
  echo "FAIL: deploy returned HTTP $HTTP_CODE"
  cat /tmp/deploy-response.json | jq '.' 2>/dev/null || cat /tmp/deploy-response.json
  exit 1
fi
