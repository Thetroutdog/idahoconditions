# secrets/

Real API keys are NOT stored in this project or in the GitHub repo.
They live in a local-only file on Eric's Mac: `~/API/idahoconditions.env`

Code loads keys from environment variables. To run locally:
    set -a; source ~/API/idahoconditions.env; set +a
For GitHub Actions, add each key as a repository secret with the same name.

`.env.example` is the template (names only, no values).

| Service | Env var | Where to request | Status |
|---|---|---|---|
| Idaho 511 | IDAHO511_API_KEY | 511.idaho.gov (developer resources) | Received 2026-11-17 |
| USGS | USGS_API_KEY | api.data.gov (optional, raises limits) | Not requested |
| AirNow | AIRNOW_API_KEY | docs.airnowapi.org | Received 2026-11-14 |

Rules: never paste keys into source files, chat, or screenshots.
