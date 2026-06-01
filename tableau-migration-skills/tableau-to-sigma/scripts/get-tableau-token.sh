#!/usr/bin/env bash
# Sign in to Tableau via Personal Access Token.
# Usage:  eval "$(scripts/get-tableau-token.sh)"
# Sets TABLEAU_AUTH_TOKEN and TABLEAU_SITE_ID in the calling shell.
#
# IMPORTANT: this makes ONE signin attempt. Tableau invalidates a PAT after
# four consecutive failed signins, so do not wrap this in a retry loop with
# different name/secret combos — fix the credentials and call once.

set -euo pipefail

: "${TABLEAU_SERVER_URL:?Run scripts/setup-tableau.rb to configure credentials}"
: "${TABLEAU_SITE_CONTENT_URL:?Run scripts/setup-tableau.rb to configure credentials}"
: "${TABLEAU_PAT_NAME:?Run scripts/setup-tableau.rb to configure credentials}"
: "${TABLEAU_PAT_SECRET:?Run scripts/setup-tableau.rb to configure credentials}"

API_VER="${TABLEAU_API_VERSION:-3.22}"

RESPONSE=$(curl -sS -X POST \
  -H "Content-Type: application/xml" \
  -H "Accept: application/json" \
  --data "<tsRequest><credentials personalAccessTokenName=\"${TABLEAU_PAT_NAME}\" personalAccessTokenSecret=\"${TABLEAU_PAT_SECRET}\"><site contentUrl=\"${TABLEAU_SITE_CONTENT_URL}\"/></credentials></tsRequest>" \
  "${TABLEAU_SERVER_URL}/api/${API_VER}/auth/signin")

# Parse the response. On success we expect {"credentials":{"token":"...","site":{"id":"..."}, ...}}.
# On failure we get {"error":{"code":"401001",...}}.
TOKEN=$(printf '%s' "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(2)
if 'error' in d:
    sys.exit(3)
print(d['credentials']['token'])
" 2>/dev/null) || {
  CODE=$?
  if [ "$CODE" = "3" ]; then
    ERR_CODE=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error',{}).get('code','?'))" 2>/dev/null || echo '?')
    echo "Tableau signin failed (error code: $ERR_CODE)." >&2
    echo "Response: $RESPONSE" >&2
    if [ "$ERR_CODE" = "401001" ]; then
      echo >&2
      echo "401001 means the PAT name or secret is wrong — OR the token has been invalidated by 4+" >&2
      echo "consecutive failed signins. Create a fresh PAT in Tableau Cloud and re-run setup-tableau.rb." >&2
    fi
    exit 1
  fi
  echo "Tableau signin failed — could not parse response: $RESPONSE" >&2
  exit 1
}

SITE_ID=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['credentials']['site']['id'])")

echo "export TABLEAU_AUTH_TOKEN='${TOKEN}'"
echo "export TABLEAU_SITE_ID='${SITE_ID}'"
echo "export TABLEAU_API_VERSION='${API_VER}'"
