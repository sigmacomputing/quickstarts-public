#!/usr/bin/env bash
# Cognos Analytics REST discovery helper.
#
#   export COGNOS_BASE="https://<host>/bi/v1"
#   export COGNOS_COOKIE="<full Cookie header from a logged-in session>"
#   export COGNOS_XSRF="<X-XSRF-Token header value>"
#
#   cognos-discover.sh list   <folderId>     # list items in a folder (id,type,name)
#   cognos-discover.sh module <moduleId>     # Data Module JSON  → stdout
#   cognos-discover.sh report <reportId>     # report-spec XML   → stdout
#
# Grab COGNOS_COOKIE + COGNOS_XSRF from the browser: DevTools → Network → any
# `coreBundle.js`-initiated `bi/v1/...` request → Copy as cURL (the -b cookie and
# the X-XSRF-Token header). Session is short-lived; re-grab when it 401s.
#
# MORE THAN A COUPLE OF OBJECTS? Use cognos-batch-fetch.sh instead — it pulls
# the WHOLE estate in one hot-session window (4-wide, resumable disk cache) and
# its `one` mode serves single module/report fetches from that cache when the
# modificationTime is unchanged (1 request instead of a re-fetch).
set -euo pipefail
: "${COGNOS_BASE:?set COGNOS_BASE}"; : "${COGNOS_COOKIE:?set COGNOS_COOKIE}"; : "${COGNOS_XSRF:?set COGNOS_XSRF}"
cmd="${1:-}"; id="${2:-}"
req() { curl -s "$COGNOS_BASE$1" -H 'Accept: application/json' -H "X-XSRF-TOKEN: $COGNOS_XSRF" -H 'X-Requested-With: XMLHttpRequest' -b "$COGNOS_COOKIE"; }
case "$cmd" in
  list)
    req "/objects/$id/items?fields=defaultName,type,id" | python3 -c '
import sys,json
d=json.load(sys.stdin); items=d.get("data") or d.get("content") or d.get("items") or []
for i in items: print(f"{i.get(\"type\",\"?\"):14} {i.get(\"id\")}  {i.get(\"defaultName\") or i.get(\"name\")}")' ;;
  module) req "/metadata/modules/$id" ;;
  report) req "/objects/$id?fields=specification" | python3 -c 'import sys,json;o=(json.load(sys.stdin).get("data") or [{}])[0];print(o.get("specification") or "")' ;;
  *) echo "usage: cognos-discover.sh {list <folderId> | module <id> | report <id>}" >&2; exit 1 ;;
esac
