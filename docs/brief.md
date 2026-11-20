# The Thursday Brief pipeline

**Draft-only.** Nothing here sends, posts or emails. The workflow builds a draft and a PASS/BLOCKED report; the editor pastes the draft into beehiiv by hand. (beehiiv's Free plan has no send API anyway.) There are no beehiiv keys in this repo or its workflows, and there should not be.

**Status (Nov 19):** the Thursday GitHub workflow (`brief.yml`) was removed when the repo went public, so nothing builds the Brief automatically. The scripts remain and run locally (see "Local use"). The sections below describe what that workflow did, in case it is brought back (it is in git history if it was ever committed); `snapshots_git.sh` is only needed by a workflow.

## What the removed workflow did
Thursdays 12:17 UTC (5:17 AM MST, 6:17 AM MDT). Steps:
1. `scripts/refresh_all.sh` (fresh data, same secrets as the refresh job).
2. River medians (`data/usgs_daily_median.json`, about 4 minutes, fetched once a month and cached). Missing = the "vs. normal" line skips rivers.
3. Check out the `snapshots` branch into `./snapshots`.
4. `scripts/brief/run_brief.py`: pick last week's snapshot, `diff_week.py`, `best_bet.py`, `build_brief.py`, then `preflight.py`.
5. Put `STATUS.md` in the run summary and upload `brief-out/` as the artifact **brief-draft** (kept 14 days).
6. Scheduled runs (or manual runs with "save snapshot" ticked) save this week's data to the `snapshots` branch, unless the data was stale or a source failed.

## What to do each Thursday
Actions > *Thursday Brief draft* > latest run > read the summary. If it says BLOCKED because of `[EDITOR]`, that is the normal "add your two lines" state: re-run with the **editor_note** input (type `\n` between the two lines) or edit the draft by hand. Optional: **best_bet_override** replaces the rules-based "The numbers favor" pick. Download the artifact, paste `brief-draft.html` into a beehiiv HTML block, and read it before sending. PASS means the automatic checks found nothing, not that the Brief is right.

## The pre-send check (`preflight.py`)
BLOCKED if any of these is true: a `[CHECK…]`, `[EDITOR…]`, `[DEMO…]` or `FAKE` marker is left in the md, html or txt; leaked template text (`{id}`, `None`, `nan`, `undefined`); an empty section; `conditions.json` or any source older than 18 hours (`maxDataAgeHours` in `brief_config.json`); a source that failed; or no real last-week snapshot 5 to 9 days old. The first week has no snapshot, so the first draft is BLOCKED by design.

## Weekly snapshots
`scripts/brief/snapshot.py save` writes `conditions-YYYY-MM-DD.json` (forecasts removed, about 100 KB) to the `snapshots` branch and keeps the newest 12. The branch is separate, so it never touches the deployed site and the site workflow never sees it. `scripts/brief/snapshots_git.sh` does the git work.

## Local use
```
set -a; source <your local env file>; set +a; export IC_USER_AGENT="..."
./scripts/refresh_all.sh
python3 scripts/brief/fetch_usgs_stats.py          # once, makes data/usgs_daily_median.json
python3 scripts/brief/run_brief.py --last-week /path/to/older/conditions.json
python3 scripts/brief/selftest.py                  # no network
```
Output goes to `brief-out/` (git-ignored). Inputs for local runs: environment variables `BRIEF_EDITOR_NOTE` and `BRIEF_BEST_BET_OVERRIDE`.

## Scheduling
The site refresh is started by a Cloudflare Worker (`workers/refresh-timer/`), not by a GitHub `schedule:`, so GitHub's 60-day auto-disable of scheduled workflows does not apply and no keep-alive workflow is needed (it was removed in v0.14.0). If a Thursday Brief workflow is ever brought back, start it from that Worker too.

## Public repo
The repo is public, so a workflow's run summary and a `snapshots` branch would be readable by anyone, and artifacts by any signed-in GitHub user. That includes the editor's two lines before the send. Another reason to build the draft locally.

## Files
`scripts/brief/`: `run_brief.py` (orchestrator), `snapshot.py`, `snapshots_git.sh`, `diff_week.py`, `best_bet.py`, `build_brief.py`, `preflight.py`, `common.py` (email styles), `brief_config.json` (weights, sections, limits), `fetch_usgs_stats.py`, `selftest.py`, `assets/` (masthead and logo for the HTML). Ported from the Newsletter Writer's demo scripts (GROK_LOG, item 23).
