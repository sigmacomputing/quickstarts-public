#!/usr/bin/env bash
# Mint a ThoughtSpot REST v2 bearer token for a repeatable service identity via
# Trusted Authentication — no interactive SSO, no stored password.
#
# Prereqs (admin, one-time): Develop → Customizations → Security Settings →
# enable Trusted Authentication → copy the secret_key.
#
# Usage:  eval "$(TS_HOST=https://x.thoughtspot.cloud TS_USERNAME=svc@you.com \
#                 TS_SECRET_KEY=*** scripts/get-ts-token.sh)"
# Sets TS_TOKEN in the calling shell (24h validity).
set -euo pipefail
: "${TS_HOST:?set TS_HOST (https://<org>.thoughtspot.cloud)}"
: "${TS_USERNAME:?set TS_USERNAME (the service/user to mint a token for)}"
: "${TS_SECRET_KEY:?set TS_SECRET_KEY (Trusted-Auth secret from Security Settings)}"

RESP=$(curl -sf -k -X POST "${TS_HOST%/}/api/rest/2.0/auth/token/full" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"${TS_USERNAME}\",\"secret_key\":\"${TS_SECRET_KEY}\",\"validity_time_in_sec\":86400}") || {
    echo "token request failed — check TS_HOST / TS_USERNAME / TS_SECRET_KEY and that Trusted Auth is enabled" >&2
    exit 1; }

TOKEN=$(echo "$RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])" 2>/dev/null) || true
if [ -z "${TOKEN:-}" ] || [ "$TOKEN" = "null" ]; then
  echo "no token in response: ${RESP:0:200}" >&2; exit 1
fi
echo "export TS_TOKEN=${TOKEN}"
