#!/usr/bin/env bash
set -euo pipefail

# Compare the live Sigma workbook contents against the git spec.
# Exits 0 if in sync, 1 if drift is detected.
#
# Requires:
#   SIGMA_API_HOST  — e.g. https://aws-api.sigmacomputing.com
#   SIGMA_API_TOKEN — a valid bearer token
#
# GET /v2/workbooks/{id}?includeContents=true replaces the old
# GET /v2/workbooks/{id}/spec endpoint. Comparison is JSON-structural (jq -S
# on both sides), not a text/YAML diff - this avoids false "drift detected"
# results from cosmetic re-serialization differences (key order, quote
# style, whitespace) that don't reflect an actual content change.

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

echo "Pulling live contents for workbook $WORKBOOK_ID..."

HTTP_CODE=$(curl -s -o /tmp/drift-check-response.json -w "%{http_code}" \
  -X GET \
  -H "Authorization: Bearer $SIGMA_API_TOKEN" \
  -H "Accept: application/json" \
  "$SIGMA_API_HOST/v2/workbooks/$WORKBOOK_ID?includeContents=true")

if [[ "$HTTP_CODE" -lt 200 || "$HTTP_CODE" -ge 300 ]]; then
  echo "FAIL: fetching live workbook returned HTTP $HTTP_CODE"
  cat /tmp/drift-check-response.json
  exit 1
fi

LIVE_DOC=$(jq -S '.contents' /tmp/drift-check-response.json)
GIT_DOC=$(yq -o=json '.contents' "$SPEC_FILE" | jq -S '.')

if [[ "$LIVE_DOC" == "$GIT_DOC" ]]; then
  echo "IN SYNC: live workbook matches git spec"
  exit 0
else
  echo "DRIFT DETECTED: live workbook differs from git spec"
  echo ""
  echo "--- git spec"
  echo "+++ live workbook"
  diff <(echo "$GIT_DOC") <(echo "$LIVE_DOC") || true
  exit 1
fi
