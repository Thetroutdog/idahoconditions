#!/bin/bash
# Keeps weekly snapshots on a separate `snapshots` branch so they never touch main or the deployed site.
#   scripts/brief/snapshots_git.sh open   check the branch out as ./snapshots (creates it, empty, the first time)
#   scripts/brief/snapshots_git.sh push   commit whatever is new in ./snapshots and push the branch
# Used by .github/workflows/brief.yml. Needs a repo whose `origin` accepts pushes (GITHUB_TOKEN with contents: write).
set -euo pipefail
cd "$(dirname "$0")/../.."
case "${1:-}" in
  open)
    if git fetch --quiet --depth=1 origin snapshots 2>/dev/null; then
      git worktree add -B snapshots snapshots FETCH_HEAD
    else
      echo "no snapshots branch yet: creating an empty one"
      empty=$(git hash-object -t tree /dev/null)
      c=$(git -c user.name="idahoconditions-bot" -c user.email="bot@idahoconditions.com" commit-tree "$empty" -m "Start snapshots branch")
      git worktree add -B snapshots snapshots "$c"
    fi
    ;;
  push)
    cd snapshots
    git add -A
    if git diff --cached --quiet; then echo "nothing new to commit"; exit 0; fi
    git -c user.name="idahoconditions-bot" -c user.email="bot@idahoconditions.com" commit -q -m "Snapshot $(date -u +%F)"
    git push origin HEAD:refs/heads/snapshots
    ;;
  *) echo "usage: $0 open|push" >&2; exit 2 ;;
esac
