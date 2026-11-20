# Idaho Conditions

Roads, snow, rivers, air quality and fire for Idaho, organized by the seven Idaho Fish and Game regions and by activity.
Live at https://idahoconditions.com. A short Thursday email, the Brief, goes with it.

## How it works

1. **Fetchers** (`scripts/fetch_*.py`) pull public data: National Weather Service, Idaho 511, USGS and NOAA water gauges, NRCS SNOTEL, AirNow, NIFC.
2. `scripts/build_conditions.py` merges them into `data/conditions.json`, applying the alert-level and freshness rules (see `docs/`).
3. **Astro** (`src/`) builds a static site from that file. No server runs at request time.
4. A **GitHub Actions** workflow (`.github/workflows/refresh.yml`) repeats steps 1-3 and deploys to Cloudflare Pages. A Cloudflare Worker (`workers/refresh-timer/`) starts it every 30 minutes; see "The refresh timer" below.

If a source fails, the last good data is kept and the pages say it is out of date.

## Run it locally

```
npm install
set -a; source your-local-env-file; set +a   # your own keys; see secrets/.env.example
./scripts/refresh_all.sh                            # fetch data and build data/conditions.json
npm run dev                                         # http://localhost:4321
```

Python 3.11+ and Node 22 are expected. Without keys, those fetchers fail and the site shows the source as unavailable.

## Layout

- `src/` Astro pages, components and styles
- `workers/refresh-timer/` the Cloudflare Worker that starts the refresh every 30 minutes
- `scripts/` fetchers, the conditions builder and one-off data tools
- `data/` spot catalog, region geometry and generated data
- `docs/` data sources and the conditions file format
- `secrets/` the key template only (real keys never live in this repo)

## The refresh timer (Cloudflare Worker)

The 30-minute timer is **not** GitHub's scheduler (it skipped most runs). It is a small Cloudflare Worker, `workers/refresh-timer/`, with the cron `7,37 * * * *`. Each time it fires it asks GitHub to run `refresh.yml` (a `workflow_dispatch`). The workflow also still runs on every push to `main` or `dev` and can be started by hand from the Actions tab. `refresh.yml` has no `schedule:` on purpose; adding one would double the runs.

**Pause it:** Cloudflare dashboard > Workers & Pages > `ic-refresh-timer` > Settings > Triggers > remove the cron trigger. (Or set `crons = []` in `workers/refresh-timer/wrangler.toml` and run `npx wrangler deploy`.) Put the cron back to resume.

**Health:** Worker logs (dashboard > `ic-refresh-timer` > Logs, or `npx wrangler tail`) show "dispatch ok (204)" each time; anything else is logged as `dispatch FAILED: HTTP <status>` (401 = token expired or wrong, 403 = missing Actions permission, 404 = wrong repo or workflow name). The Actions tab should show a `workflow_dispatch` run at about :07 and :37.

**GitHub token:** the Worker needs the secret `GH_DISPATCH_TOKEN`: a fine-grained personal access token for the `idahoconditions` repo only, permission *Actions: Read and write* (nothing else). It expires (maximum one year), so note the date; an expired token means HTTP 401 in the logs and a stale site.

**First-time deploy** (needs Node, which the site already uses; wrangler is run with `npx`, so nothing is added to the repo):
1. Create the token: github.com > profile picture > Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token. Resource owner: Thetroutdog. Repository access: *Only select repositories* > `idahoconditions`. Repository permissions: *Actions: Read and write* (Metadata: Read-only is added automatically; leave everything else at No access). Choose the longest expiration, generate, and copy the token (starts with `github_pat_`).
2. In Terminal: `cd workers/refresh-timer` (from the repo folder)
3. `npx wrangler login` (a browser window opens; sign in to the Cloudflare account that has the idahoconditions Pages project and click Allow). If asked to install wrangler, answer yes.
4. `npx wrangler deploy` (creates the Worker and its cron trigger).
5. `npx wrangler secret put GH_DISPATCH_TOKEN`, then paste the token when prompted and press Return. (Or in the dashboard: Workers & Pages > ic-refresh-timer > Settings > Variables and Secrets > Add > type Secret.)
6. Check it: within 30 minutes the Actions tab shows a run started by `workflow_dispatch`. Watch the Worker's logs with `npx wrangler tail` (leave it running until the next :07 or :37); you should see "dispatch ok (204)".
7. Only after you see a successful timer run, push the v0.14.0 change that removes GitHub's schedule (or push it first and start runs by hand until the Worker is live).

## Notes

- Not safety guidance. This project is independent and not affiliated with the agencies whose data it shows.
- All rights reserved unless a license file says otherwise.
- Version history: kept outside the repo, in the project notes folder (`CHANGELOG.md` next to `project.md`).
