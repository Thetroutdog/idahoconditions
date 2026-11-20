#!/bin/bash
# Run every fetcher IN PARALLEL (they are independent: each reads fixed inputs and writes its own data/parts/*.json),
# then rebuild data/conditions.json. One failing fetcher does not stop the others. Each fetcher's output is shown as a block, in order.
# Setup first (same Terminal window): set -a; source <your local env file>; set +a; export IC_USER_AGENT="..."
cd "$(dirname "$0")/.." || exit 1
[ -z "$IC_USER_AGENT" ] && echo "!! WARNING: IC_USER_AGENT is not set. NWS wants a contact in the User-Agent; alerts may be refused."
LOGS=$(mktemp -d); trap 'rm -rf "$LOGS"' EXIT
FETCHERS="fetch_nws fetch_snotel fetch_usgs fetch_noaa fetch_airnow fetch_nifc fetch_511"
for s in $FETCHERS; do
  ( python3 scripts/$s.py >"$LOGS/$s.log" 2>&1 || echo "!! $s failed" >>"$LOGS/$s.log" ) &
done
wait
for s in $FETCHERS; do echo "== $s"; cat "$LOGS/$s.log"; done
echo "== build"; python3 scripts/build_conditions.py
