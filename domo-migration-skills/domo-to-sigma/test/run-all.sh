#!/usr/bin/env bash
# Run all domo-to-sigma unit + integration tests. Offline (no network / creds).
#   bash test/run-all.sh
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
for t in test/test-*.rb; do
  echo "### $t"
  if ruby "$t"; then :; else fail=1; fi
  echo
done
if [ "$fail" -eq 0 ]; then echo "== ALL SUITES PASS =="; else echo "== FAILURES =="; fi
exit "$fail"
