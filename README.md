# Idaho Conditions

Roads, snow, rivers, air quality and fire for Idaho, organized by the seven Idaho Fish and Game regions and by activity.
Live at https://idahoconditions.com. A short Thursday email, the Brief, goes with it.

## How it works

1. **Fetchers** (`scripts/fetch_*.py`) pull public data: National Weather Service, Idaho 511, USGS and NOAA water gauges, NRCS SNOTEL, AirNow, NIFC.
2. `scripts/build_conditions.py` merges them into `data/conditions.json`, applying the alert-level and freshness rules (see `docs/`).
3. **Astro** (`src/`) builds a static site from that file. No server runs at request time.
4. A **GitHub Actions** workflow (`.github/workflows/refresh.yml`) repeats steps 1-3 every 30 minutes and deploys to Cloudflare Pages.

If a source fails, the last good data is kept and the pages say it is out of date.

## Run it locally

```
npm install
set -a; source ~/API/idahoconditions.env; set +a   # your own keys; see secrets/README.md
./scripts/refresh_all.sh                            # fetch data and build data/conditions.json
npm run dev                                         # http://localhost:4321
```

Python 3.11+ and Node 22 are expected. Without keys, those fetchers fail and the site shows the source as unavailable.

## Layout

- `src/` Astro pages, components and styles
- `scripts/` fetchers, the conditions builder and one-off data tools
- `data/` spot catalog, region geometry and generated data
- `docs/` data sources and the conditions file format
- `secrets/` the key template only (real keys never live in this repo)

## Notes

- Not safety guidance. This project is independent and not affiliated with the agencies whose data it shows.
- All rights reserved unless a license file says otherwise.
- Version history: kept outside the repo, in the project notes folder (`CHANGELOG.md` next to `project.md`).
