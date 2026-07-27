#!/usr/bin/env bash
# get-cognos-session.sh — capture a Cognos Analytics on Cloud (CAoC) REST session
# for discovery/extraction. IBMid SSO blocks headless/password login, so the
# practical path is to replay a live BROWSER session.
#
#   AUTH REALITY (read this):
#   • CAoC sessions are SHORT-LIVED and tied to the browser. A copied session can
#     return HTTP 441 "Unauthorized" within minutes — that is CA's SSO re-auth
#     signal (the SPA sends `X-CA-SSO: 441` when re-auth is pending), not a bug
#     in this script. If you get 441: re-login in the browser, do one in-app
#     action, then immediately re-copy (so the session is "hot").
#   • You MUST paste the ENTIRE Cookie header — including the Akamai bot-protection
#     cookies (_abck, bm_sz, bm_sv, ak_bmsc). Dropping them => 441/403 from the WAF.
#   • The DURABLE production path is a CA API key / service credential where the
#     customer's tenant allows it (Manage → … ); prefer that over session replay
#     for a real engagement. Document which the engagement is using.
#
# USAGE — grab from the browser, then point this at the files:
#   1. DevTools → Network → click any `…/bi/v1/…` XHR → Copy → Copy as cURL.
#   2. Save the full Cookie header value to ~/.cognos/cookie.txt (one line).
#   3. export COG_BASE + COG_XSRF (the X-XSRF-TOKEN header value), then:
#        eval "$(scripts/get-cognos-session.sh)"
#   4. Smoke test:  cog_get "/objects/.public_folders/items?fields=defaultName,type,id"
#
# Env it expects:
#   COG_BASE   e.g. https://us3.ca.analytics.ibm.com/bi/v1   (the instance + /bi/v1)
#   COG_XSRF   the XSRF-TOKEN value (also the X-XSRF-TOKEN header)
#   COG_COOKIE_FILE  path to the full cookie (default ~/.cognos/cookie.txt)

: "${COG_BASE:?set COG_BASE=https://<instance>/bi/v1}"
: "${COG_XSRF:?set COG_XSRF=<XSRF-TOKEN value>}"
COG_COOKIE_FILE="${COG_COOKIE_FILE:-$HOME/.cognos/cookie.txt}"
if [ ! -s "$COG_COOKIE_FILE" ]; then
  echo "echo 'Cookie file $COG_COOKIE_FILE missing/empty — paste the FULL browser Cookie header there.' >&2; false" ; exit 0
fi

# Emit a shell function `cog_get` (eval this script's stdout).
cat <<EOF
export COG_BASE='$COG_BASE'
export COG_XSRF='$COG_XSRF'
export COG_COOKIE_FILE='$COG_COOKIE_FILE'
cog_get() {
  # cog_get "<path under /bi/v1>"  → prints body; nonzero on HTTP>=400 (e.g. 441 re-auth)
  local p="\$1" code
  code=\$(curl -s -o /tmp/cog_last.json -w '%{http_code}' "\$COG_BASE\$p" \\
    -H 'Accept: application/json' -H "X-XSRF-TOKEN: \$COG_XSRF" \\
    -H 'X-Requested-With: XMLHttpRequest' -b @"\$COG_COOKIE_FILE")
  if [ "\$code" -ge 400 ]; then
    echo "Cognos GET \$p -> HTTP \$code (441 = session expired, re-login + re-copy)" >&2
    cat /tmp/cog_last.json >&2; echo >&2; return 1
  fi
  cat /tmp/cog_last.json
}
EOF
