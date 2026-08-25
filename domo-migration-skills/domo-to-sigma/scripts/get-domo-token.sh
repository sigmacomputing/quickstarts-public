#!/usr/bin/env bash
# Obtain a Domo PUBLIC-API bearer token via OAuth2 client-credentials.
# Usage:  eval "$(scripts/get-domo-token.sh)"
# Sets DOMO_ACCESS_TOKEN in the calling shell.
#
# Requires DOMO_CLIENT_ID and DOMO_CLIENT_SECRET (create at
# https://developer.domo.com/manage-clients or Admin > API Clients).
# Token TTL is ~3599s; lib/domo_rest.rb auto-refreshes on 401.
#
# This only covers the PUBLIC API (api.domo.com). The PRIVATE API
# ({instance}.domo.com/api/...) uses DOMO_DEV_TOKEN directly as a header —
# no token exchange needed. See refs/connection.md.

set -euo pipefail

: "${DOMO_CLIENT_ID:?Set DOMO_CLIENT_ID — create a client at developer.domo.com/manage-clients}"
: "${DOMO_CLIENT_SECRET:?Set DOMO_CLIENT_SECRET}"

SCOPE="${DOMO_SCOPE:-data user account dashboard}"
SCOPE_ENC="${SCOPE// /%20}"

RESPONSE=$(curl -sS -u "${DOMO_CLIENT_ID}:${DOMO_CLIENT_SECRET}" \
  "https://api.domo.com/oauth/token?grant_type=client_credentials&scope=${SCOPE_ENC}")

TOKEN=$(printf '%s' "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(2)
if 'access_token' not in d:
    sys.exit(3)
print(d['access_token'])
" 2>/dev/null) || {
  echo "Domo OAuth token request failed. Raw response:" >&2
  printf '%s\n' "$RESPONSE" >&2
  exit 1
}

printf 'export DOMO_ACCESS_TOKEN=%q\n' "$TOKEN"
