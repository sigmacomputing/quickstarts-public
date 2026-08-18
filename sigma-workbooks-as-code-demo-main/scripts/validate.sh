#!/usr/bin/env bash
set -euo pipefail

# Validate a Sigma workbook spec against the API's spec-verify endpoint.
# Usage: ./scripts/validate.sh [spec-file]
#
# Requires:
#   SIGMA_API_HOST  — e.g. https://aws-api.sigmacomputing.com
#   SIGMA_API_TOKEN — a valid bearer token

SPEC_FILE="${1:-workbook.yaml}"

if [[ ! -f "$SPEC_FILE" ]]; then
  echo "ERROR: spec file not found: $SPEC_FILE"
  exit 1
fi

echo "Validating $SPEC_FILE against Sigma API..."

HTTP_CODE=$(curl -s -o /tmp/validate-response.json -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $SIGMA_API_TOKEN" \
  -H "Content-Type: application/yaml" \
  -H "Accept: application/json" \
  --data-binary @"$SPEC_FILE" \
  "$SIGMA_API_HOST/v2/workbooks/spec/verify")

RESPONSE=$(cat /tmp/validate-response.json)

if [[ "$HTTP_CODE" -lt 200 || "$HTTP_CODE" -ge 300 ]]; then
  echo "FAIL: validate endpoint returned HTTP $HTTP_CODE"
  echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
  exit 1
fi

VALID=$(echo "$RESPONSE" | jq -r '.valid')

if [[ "$VALID" == "true" ]]; then
  echo "PASS: spec is valid"
  exit 0
else
  echo "FAIL: spec validation errors:"
  echo "$RESPONSE" | jq '.errors[]' 2>/dev/null || echo "$RESPONSE"
  exit 1
fi
