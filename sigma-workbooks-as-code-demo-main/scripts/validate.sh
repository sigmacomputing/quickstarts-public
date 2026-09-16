#!/usr/bin/env bash
set -euo pipefail

# Validate a Sigma workbook spec via a dry-run create.
# Usage: ./scripts/validate.sh [spec-file]
#
# Requires:
#   SIGMA_API_HOST  — e.g. https://aws-api.sigmacomputing.com
#   SIGMA_API_TOKEN — a valid bearer token
#
# POST /v2/workbooks with dryRun:true validates the spec without persisting
# anything - this replaced the old dedicated /v2/workbooks/spec/verify
# endpoint, which is being phased out in favor of the workbook representation
# living under a `contents` field rather than a separate `spec` resource.

SPEC_FILE="${1:-workbook.yaml}"

if [[ ! -f "$SPEC_FILE" ]]; then
  echo "ERROR: spec file not found: $SPEC_FILE"
  exit 1
fi

echo "Validating $SPEC_FILE against Sigma API (dry run)..."

BODY=$(yq -o=json '.' "$SPEC_FILE" | jq '. + {dryRun: true}')

HTTP_CODE=$(curl -s -o /tmp/validate-response.json -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $SIGMA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data-binary "$BODY" \
  "$SIGMA_API_HOST/v2/workbooks")

RESPONSE=$(cat /tmp/validate-response.json)

if [[ "$HTTP_CODE" -ge 200 && "$HTTP_CODE" -lt 300 ]]; then
  echo "PASS: spec is valid"
  WARNINGS=$(echo "$RESPONSE" | jq -c '.warnings // []')
  if [[ "$WARNINGS" != "[]" ]]; then
    echo "Warnings:"
    echo "$RESPONSE" | jq '.warnings[]'
  fi
  exit 0
else
  echo "FAIL: validate returned HTTP $HTTP_CODE"
  echo "$RESPONSE" | jq '.errors // .' 2>/dev/null || echo "$RESPONSE"
  exit 1
fi
