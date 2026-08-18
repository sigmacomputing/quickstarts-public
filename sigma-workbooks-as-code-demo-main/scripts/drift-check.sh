#!/usr/bin/env bash
set -euo pipefail

# Compare the live Sigma workbook spec against the git spec.
# Exits 0 if in sync, 1 if drift is detected.
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

echo "Pulling live spec for workbook $WORKBOOK_ID..."

HTTP_CODE=$(curl -s -o /tmp/drift-check-response.yaml -w "%{http_code}" \
  -X GET \
  -H "Authorization: Bearer $SIGMA_API_TOKEN" \
  -H "Accept: application/yaml" \
  "$SIGMA_API_HOST/v2/workbooks/$WORKBOOK_ID/spec")

if [[ "$HTTP_CODE" -lt 200 || "$HTTP_CODE" -ge 300 ]]; then
  echo "FAIL: fetching live spec returned HTTP $HTTP_CODE"
  cat /tmp/drift-check-response.yaml
  exit 1
fi

LIVE_SPEC=$(cat /tmp/drift-check-response.yaml)

# Strip server-generated metadata for comparison
LIVE_NORMALIZED=$(echo "$LIVE_SPEC" | yq -P 'del(.workbookId, .url, .documentVersion, .latestDocumentVersion, .ownerId, .createdBy, .updatedBy, .createdAt, .updatedAt)')
GIT_NORMALIZED=$(yq -P '.' "$SPEC_FILE")

# Compare the document sections (where actual workbook content lives)
LIVE_DOC=$(echo "$LIVE_NORMALIZED" | yq -P '.document')
GIT_DOC=$(echo "$GIT_NORMALIZED" | yq -P '.document')

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
