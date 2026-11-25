# The Thursday Brief builder (v4)

**Draft-only.** Nothing here sends, posts or emails. The scripts build a draft and a PASS/BLOCKED report; the editor pastes the draft into beehiiv by hand. (beehiiv's Free plan has no send API anyway.) There are no beehiiv keys in this repo, and there should not be. There is no scheduled workflow: the Brief is built locally.

## What the Brief is
A short weekly email, about 450 to 550 words (hard cap under 600), that adds what the live site does not: a ranked weekend, what changed since last Thursday, a short dated list, and one thing worth reading. The spec lives in the project's notes folder (`grok/2026-11-23-brief-v4-spec.md`).

## Sections, in this order
Bottom line, From the Desk, What changed, The weekend, Vs. Normal (to date), One more thing, Avalanche, Current conditions by region, Sources. Required: Bottom line, From the Desk, One more thing, Current conditions by region, Sources. The others are skipped when they have nothing to say: What changed shows only with 2 or more items (the Bottom line's Biggest change already covers one), and Avalanche is winter-only. In winter a small "Backcountry" line (Payette, Sawtooth, Panhandle) sits just above Current conditions by region; summer has none. In The weekend, a "Foothills trails" line (Ridge to Rivers, City of Boise credit and link) follows the forecast list when `regions.southwest.local.r2r` is present, fresh and not overwhelmingly dry. Winter ski-area lines are A to Z; Vs. Normal is two short lines (snowpack as the median of each region's SNOTEL sites, lowest and highest region; lowest river vs. its date median). There is no separate "This weekend" or "Coming up".

- **The weekend** is one section: a short Sat/Sun forecast line per place, then a "Coming up:" lead-in and a second list of up to 3 dated items (`datedMax`): editor-supplied lines first, then ski and nordic openings from `regions[].ski` / `data/resort_status.json` (always labeled "unconfirmed"; the editor spot-checks them) and dated highway closures. Routine ramp work is filtered (`datedExclude` in `brief_config.json`); a genuine event such as a parade closure is allowed. Permit windows are not in the data, so they appear only as an editor-supplied dated line.
- **Winter places (November to April, `season` in `brief_config.json`):** the weekend lines come from the ski-area NWS grid forecasts already in `conditions.json` (`spotForecast.bySpot` maps a spot id to a grid, `spotForecast.grids` holds the grid), labeled by ski area, in this order: Schweitzer, Lookout Pass, Bogus Basin, Brundage, Sun Valley, Pomerelle, Grand Targhee, Stanley / Sawtooths. The list is `seasons.winter.places` in `brief_config.json` (label plus spot id); the editor can swap any spot that has a grid without touching code. A line whose grid has no Saturday/Sunday data prints `[CHECK: no weekend forecast]`, and the check blocks the draft. `scripts/fetch_nws.py` reads that same list and keeps a week of days (the long text for the first four days, none after) for just those grids, so a Wednesday or Thursday run reaches Saturday and Sunday; every other grid keeps two days. A town forecast is never relabeled as a mountain. The winter "numbers favor" pick in the Bottom line and the subject options is chosen from the same eight ski areas (`best_bet.py` reads the same list; it reads "Saturday at Bogus Basin"); summer still scores the town points. If no ski-area grid reaches the weekend, the pick falls back to a town and is marked `[CHECK]`, so the draft blocks. Summer keeps the town points (`seasons.summer.places`).
- **Word budgets** are in `wordBudget` (`[budget, hard cap]` per section). The builder drops the lowest-ranked What changed and dated items to stay under a cap; the pre-send check blocks any section over its cap.

## Outputs
Written to `$BRIEF_HOME/drafts/<send date>/` when `BRIEF_HOME` is set (the send date is the next Thursday, Boise time, so Wednesday and Thursday runs share a folder), otherwise `brief-out/` in the repo (git-ignored):

- `brief-draft.html`: the body only, and the file that gets used. Sections are separated by `<hr>`, and the Bottom line, From the Desk and One more thing are `<blockquote>`s (beehiiv's quote style stands in for the mock's boxes). If a paste drops either, the fallback is plain paragraphs. Headings, paragraphs, bold, links and simple lists; no inline styles, colored boxes, custom fonts or layout tables, because beehiiv's Free editor drops them on paste. No masthead, footer, unsubscribe link or hidden preheader: the beehiiv template already has those. Open it in a browser, select all, copy, and paste into the beehiiv body over the template's placeholder.
- `brief-titles.txt`: 2 to 3 title (subject) options and 2 to 3 subtitle (preview) options. The editor picks one of each and pastes them into beehiiv's title and subtitle fields (beehiiv uses the subtitle as the inbox preview). They are also listed in `STATUS.md`. They are never in the body.
- `brief-draft.md`, `brief-draft.txt`: the same body as markdown and plain text.
- `STATUS.md` and `status.json`: PASS or BLOCKED with the reasons. `diff.json`, `best_bet.json`: the inputs the builder used.

## Inputs the editor supplies
- `BRIEF_EDITOR_NOTE`: From the Desk, two lines, with `\n` between them. Required.
- `BRIEF_ONE_MORE_THING`: One more thing, required: `Title | https://link | one-line blurb` (or the three on separate lines joined with `\n`). Or put a file named `one-more-thing.txt` in that week's drafts folder (title, URL and blurb on three lines, or the pipe form). The environment variable wins. The builder never invents this and never pulls it from `conditions.json`; it renders it as one "Worth reading" paragraph and link in the supplied words. Re-runs keep `one-more-thing.txt` and `dated-lines.txt`; every other file in the folder is rebuilt.
- `BRIEF_BEST_BET_OVERRIDE` (optional): replaces the rules-based "The numbers favor" pick.
- `BRIEF_DATED_LINES` (optional, or `dated-lines.txt`): dated lines for The weekend, one per line, like `Dec 5: Christmas tree permit window opens`.

## The pre-send check (`preflight.py`)
BLOCKED if any of these is true:
- a `[CHECK…]`, `[EDITOR…]`, `[OMT…]`, `[DEMO…]`, `TODO` or `FAKE` marker is left in the md, html or txt;
- leaked template text (`{id}`, `None`, `nan`, `undefined`);
- an empty section, or a missing required section (Bottom line, From the Desk, One more thing, Current conditions by region, Sources);
- One more thing is missing, still a placeholder, or has no link;
- a section is over its word cap, or the body is 600 words or more;
- `conditions.json` or any source is older than 18 hours (`maxDataAgeHours`), or a source failed;
- there is no real last-week snapshot 5 to 9 days old. With no snapshot at all the draft is still built, What changed reads `[CHECK: no last-week snapshot]`, and the run stays BLOCKED.
PASS means the automatic checks found nothing, not that the Brief is right: read it before you paste. The exit code is 0 even when BLOCKED; `--strict` makes BLOCKED exit 1.

## Weekly snapshots
`scripts/brief/snapshot.py save` writes `conditions-YYYY-MM-DD.json` (forecasts and `spotForecast` removed, about 100 KB) into the snapshots folder and keeps the newest 12. Forecasts are not diffed, so dropping them is intended. The folder is `$BRIEF_HOME/snapshots/` when `BRIEF_HOME` is set, otherwise `snapshots/` in the repo (git-ignored). Run it once a week after a refresh, after the send: `./scripts/refresh_all.sh`, then `python3 scripts/brief/snapshot.py save`. `snapshots_git.sh` only matters if a workflow ever keeps snapshots on a git branch again.

## Local use
```
set -a; source <your local env file>; set +a; export IC_USER_AGENT="..."
./scripts/refresh_all.sh
python3 scripts/brief/fetch_usgs_stats.py          # once a month, makes data/usgs_daily_median.json (rivers vs. normal)
python3 scripts/brief/snapshot.py save             # once a week, after a refresh
export BRIEF_EDITOR_NOTE='line one\nline two'
export BRIEF_ONE_MORE_THING='Title | https://example.org/page | one-line blurb'
python3 scripts/brief/run_brief.py
python3 scripts/brief/selftest.py                  # no network; uses scripts/brief/fixtures/
```
`run_brief.py` prints the output folder when it finishes. `--out`, `--snapshots` and `BRIEF_OUT` override the folder choices.

## Rehearsal paste (Nov 30 or Dec 1)
The editor pastes a real draft into the beehiiv template, and the HTML is then tuned to whatever survives the paste (headings, lists, links). Until then the output stays plain on purpose: do not rebuild the mockup's colored boxes in the paste. First send: Thursday, Dec 3, 2026.

## Files
`scripts/brief/`: `run_brief.py` (orchestrator: snapshot pick, diff, best bet, build, pre-send check), `snapshot.py`, `snapshots_git.sh`, `diff_week.py`, `best_bet.py`, `build_brief.py`, `preflight.py`, `common.py`, `paths.py` (where drafts and snapshots live), `brief_config.json` (weights, sections, places, titles, word budgets), `fetch_usgs_stats.py`, `selftest.py`, `fixtures/` (a trimmed copy of one real run, for the self-test), `assets/` (no longer used by the body-only HTML).

## Public repo
The repo is public, so keep the draft folder out of it (set `BRIEF_HOME` to a folder elsewhere, or use the git-ignored `brief-out/`). The editor's words and the One more thing pick are not for publishing before the send.
