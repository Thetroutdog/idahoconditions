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
`scripts/brief/snapshot.py save` writes `conditions-YYYY-MM-DD.json` (forecasts removed, about 100 KB) into the snapshots folder and keeps the newest 12. The folder is outside the repo when `BRIEF_HOME` is set (see below), otherwise `snapshots/` in the repo (git-ignored). `snapshots_git.sh` only matters if a workflow ever keeps snapshots on a git branch again; local runs do not use it.

## Local use
```
set -a; source <your local env file>; set +a; export IC_USER_AGENT="..."
./scripts/refresh_all.sh
python3 scripts/brief/fetch_usgs_stats.py          # once, makes data/usgs_daily_median.json
python3 scripts/brief/snapshot.py save              # once a week, after a refresh
python3 scripts/brief/run_brief.py
python3 scripts/brief/selftest.py                  # no network
```
Where files go (`scripts/brief/paths.py`): set the environment variable `BRIEF_HOME` to a folder outside the repo (for example in your own notes folder; put the export in your shell profile). Then each draft is written to `$BRIEF_HOME/drafts/<send date>/` (the send date is the next Thursday, Boise time, so Wednesday and Thursday runs share a folder) and snapshots to `$BRIEF_HOME/snapshots/`. With `BRIEF_HOME` unset, drafts go to `brief-out/` and snapshots to `snapshots/` in the repo, both git-ignored. `--out`, `--snapshots` and `BRIEF_OUT` override either way. `run_brief.py` prints the output folder when it finishes.

Inputs for local runs: environment variables `BRIEF_EDITOR_NOTE` and `BRIEF_BEST_BET_OVERRIDE`.

## Scheduling
The site refresh is started by a Cloudflare Worker (`workers/refresh-timer/`), not by a GitHub `schedule:`, so GitHub's 60-day auto-disable of scheduled workflows does not apply and no keep-alive workflow is needed (it was removed in v0.14.0). If a Thursday Brief workflow is ever brought back, start it from that Worker too.

## Public repo
The repo is public, so a workflow's run summary and a `snapshots` branch would be readable by anyone, and artifacts by any signed-in GitHub user. That includes the editor's two lines before the send. Another reason to build the draft locally.

## Files
`scripts/brief/`: `run_brief.py` (orchestrator), `snapshot.py`, `snapshots_git.sh`, `diff_week.py`, `best_bet.py`, `build_brief.py`, `preflight.py`, `common.py` (email styles), `paths.py` (where drafts and snapshots live), `brief_config.json` (weights, sections, limits), `fetch_usgs_stats.py`, `selftest.py`, `assets/` (masthead and logo for the HTML). Ported from the Newsletter Writer's demo scripts (GROK_LOG, item 23).
