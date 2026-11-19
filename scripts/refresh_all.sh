#!/bin/bash
# Run every fetcher, then rebuild data/conditions.json. One failing fetcher does not stop the others.
# Setup first (same Terminal window): set -a; source ~/API/idahoconditions.env; set +a; export IC_USER_AGENT="..."
cd "$(dirname "$0")/.." || exit 1
[ -z "$IC_USER_AGENT" ] && echo "!! WARNING: IC_USER_AGENT is not set. NWS wants a contact in the User-Agent; alerts may be refused."
for s in fetch_nws fetch_snotel fetch_usgs fetch_noaa fetch_airnow fetch_nifc fetch_511; do
  echo "== $s"; python3 scripts/$s.py || echo "!! $s failed"
done
echo "== build"; python3 scripts/build_conditions.py
