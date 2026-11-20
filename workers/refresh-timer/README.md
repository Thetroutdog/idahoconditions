# ic-refresh-timer

A tiny Cloudflare Worker whose only job is to start the GitHub workflow `.github/workflows/refresh.yml` every 30 minutes (cron `7,37 * * * *`).
GitHub's own scheduler was skipping most runs, so the timer lives here. The workflow still does all the work (fetch, build, deploy).

- Code: `src/index.js` (a `scheduled()` handler; no `fetch` handler, so there is no public endpoint).
- Secret: `GH_DISPATCH_TOKEN`, a fine-grained GitHub token for the `idahoconditions` repo with **Actions: Read and write** and nothing else. Stored as a Worker secret, never in the repo.
- Healthy: GitHub answers 204 and the Worker logs "dispatch ok (204)". Any other answer is logged as `dispatch FAILED: HTTP <status>` (401 = token expired or wrong, 403 = missing permission, 404 = wrong repo or workflow name).
- Pause: remove the cron trigger (Cloudflare dashboard > Workers & Pages > ic-refresh-timer > Settings > Triggers), or set `crons = []` in `wrangler.toml` and run `npx wrangler deploy`. Resume by putting the cron back. You can always start a run by hand from the GitHub Actions tab.
- The token expires (GitHub's maximum for fine-grained tokens is a year). Put the expiry date in your calendar; a dead token shows as HTTP 401 in the Worker logs and the site goes stale.

First-time deploy steps are in the project notes (CHANGELOG v0.14.0) and the repo README.
