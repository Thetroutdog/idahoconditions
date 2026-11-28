# conditions.json: the contract between the fetchers and the site (DRAFT v0.1)

Fetchers (Python) write one `conditions.json`. Astro reads it at build time. Pages never call APIs directly. If a fetcher fails, its section keeps the previous good values and is marked `stale`; it never silently disappears.

## Principles (from rules-proposal.md, approved)
- Every reading is a **Reading**: `{ "value", "unit", "observedAt", "status", "source", "provisional" }`.
  `observedAt` is ISO 8601 with the source's own offset. `status` is `fresh`, `stale` (show last-known, labelled gray) or `missing`. The fetcher computes status from the cutoffs in rules-proposal.md.
- Region `level` is `green`, `amber`, `red` or `gray` (worst fresh input wins; gray when alerts or roads are stale/missing).
- Summaries are templated text produced by the build, not free-form AI.
- Times: store source time with offset; the page formats it in the region's timezone (Panhandle/Clearwater Pacific, rest Mountain).

## Top level
```json
{
  "schemaVersion": "0.1",
  "generatedAt": "2026-11-15T19:30:00Z",
  "sources": {
    "nws":     {"fetchedAt": "...", "ok": true, "error": null},
    "airnow":  {"fetchedAt": "...", "ok": true, "error": null},
    "snotel":  {"fetchedAt": "...", "ok": true, "error": null},
    "usgs":    {"fetchedAt": "...", "ok": true, "error": null},
    "nifc":    {"fetchedAt": "...", "ok": true, "error": null},
    "r2r":     {"fetchedAt": "...", "ok": true, "error": null},   // present only once the fetcher has run
    "idaho511":{"fetchedAt": "...", "ok": false, "error": "no key yet"}
  },
  "alertBar": {"level": "amber", "text": "Winter Weather Advisory: Clearwater, Salmon", "moreCount": 0, "regionIds": ["clearwater","salmon"]},
  "regions": { "<regionId>": { ... } }
}
```
`alertBar` is `null` when there is nothing to show. If `generatedAt` is older than 2 h the site shows its "data may be out of date" bar.

## Region
Region ids: `panhandle`, `clearwater`, `southwest`, `magic-valley`, `southeast`, `upper-snake`, `salmon`. Page URL default `/<regionId>/` (still to confirm).

```json
"southwest": {
  "name": "Southwest", "tz": "America/Boise",
  "level": "amber",
  "levelReasons": [{"kind": "nws-advisory", "text": "Winter Weather Advisory until Mon 11 PM", "zones": ["IDZ011"]}],
  "summary": "Winter Weather Advisory until Mon 11 PM. AQI 53 (Moderate).",
  "alerts": [{"id": "...", "event": "Winter Weather Advisory", "severity": "Moderate", "onset": "...", "ends": "...", "headline": "...", "zones": ["IDZ011"], "url": "..."}],
  "forecast": {"points": [{"id": "mccall", "name": "McCall", "office": "BOI", "periods": [{"name": "Tonight", "temp": 22, "unit": "F", "short": "Snow likely", "precipChance": 70}]}], "updated": "..."},
  "roads": {"status": "missing", "passes": [], "closures": [], "restrictions": []},
  "snow": [{"id": "370:ID:SNTL", "name": "Brundage Reservoir", "elevationFt": 6280, "area": "Brundage (McCall)",
            "swe": Reading, "depth": Reading, "depthChange24h": Reading, "pctOfMedian": Reading}],
  "rivers": [{"id": "USGS-13246000", "name": "NF Payette near Banks", "use": ["paddling"], "flow": Reading, "stage": Reading, "trend": "rising|falling|steady"}],
  "air": {"points": [{"id": "boise", "name": "Boise", "aqi": Reading, "category": "Good", "pollutant": "PM2.5", "provisional": true}], "note": null},
  "fire": {"wildfires": [{"name": "...", "acres": 120, "containmentPct": 40, "modifiedAt": "..."}], "prescribed": [{"name": "...", "acres": 30, "modifiedAt": "..."}]},
  "ski": [{"name": "Brundage", "status": "unknown", "source": "manual", "note": "resort status needs permission or manual entry"}]
}
```
Notes:
- `depthChange24h` is the change in SNOTEL snow depth since the previous day (can be negative as snow settles); it is not a snowfall total.
- `peaks` is `{spot id: [station, ...]}` for the backcountry peaks in `data/peaks.json`, written by `scripts/fetch_snotel.py`. Each station has `id`, `name`, `elevationFt`, `distanceMi`, `bearing`, `feetBelowSummit` and `depth`, `swe`, `depthChange24h` readings. These are nearby SNOTEL sites, not readings on the peak, and are kept off the region Snow card.
- `snow`, `rivers` and `air.points` list only items chosen in `data/selected_stations.json` and `data/region_points.json`.
- `fire.wildfires` and `fire.prescribed` are separate lists (design decision: show prescribed burns as their own line).
- `avalanche` lists the avalanche centers whose forecasts cover the region (`id`, `name`, `url`, `area`), from `data/avalanche_centers.json` (static links, edited by hand; Grok confirmed the eastern Idaho cross-border centers). Top-level `avalanchePoints` maps a forecast point id (e.g. `island-park`) to center ids that override the region list for that town.
- `ski` lists weekly open/closed/opening-soon results per region (ski, nordic and snowmobile areas) from `data/resort_status.json`, written by `scripts/fetch_resort_status.py` locally. Each item: `id`, `name`, `status` (`open`, `closed`, `opening-soon`), `confidence`, `opening`/`openingISO`, `url`, `checkedAt`, `freshness` (`stale` when the crawl is more than 8 days old), `source`. Areas whose status is `unknown` are left out. The site does not display it yet; the Thursday Brief can read it.
- Idaho 511 fills `roads` once the key arrives; until then `roads.status` is `missing` and the region cannot be green (rule: no green when we can't tell) so the page shows gray plus last-known.

## Local conditions (`regions.<id>.local.<source>`)

Sources that belong to one region (or a few). Regions without the source have no key (`local` is `{}`); the site, the Brief and the watcher must tolerate a missing key. A local source never changes the region's alert level.
Every local source carries the shared fields `title`, `verdict`, `tone` (`green` | `amber` | `neutral`), `summary` (one plain line), `asOf` (ISO time of the newest underlying report) and `stale` (re-checked at build time against `asOf`). If the fetcher is failing, `sources.<name>.ok` is false and the item gets `fetchFailing: true` (last data kept).
The site reads them through `src/lib/local.js` (one registry entry per source).

### `regions.southwest.local.r2r` (Ridge to Rivers, part `r2r`, Boise foothills trails)

- Shared fields as above. `verdict` is "Mostly muddy", "Muddy in spots", "Mostly frozen", "Mostly dry", "Mixed conditions" or "No trail reports", from the open, evaluated trails. `asOf` is the newest `last_edited_date` in the layer (real UTC); `ConditionDate` is staff wall-clock time stored as UTC and is only a fallback. `stale` is true when `asOf` is over 72 hours old (not a failure).
- `counts`: trails by code (`muddy`, `mixed`, `dry`, `frozen`, `frozen-am`, `closed`, `unknown`) and `total`. Access roads (subsystem `N/A`) are skipped. `originalText`: the original condition wording seen for each code.
- `subsystems`: per-area counts (`name`, `n`, plus one count per code). `driest`: up to 3 areas, most dry trails first, with at least 5 open trails (dry, frozen, mixed or muddy), 90% or more of them dry, and less than 25% of the area's trails closed. `frozenAreas`: the same test for frozen (snow-covered, usable but not dry). `muddiest`: up to 3 areas with 5 or more muddy trails. `closedAreas`: areas with 25% or more of their trails closed. Each entry is the area's counts, so the site can print "Table Rock (19 muddy, 1 dry)". Areas are named with counts only, never trail by trail.
- `suggestAllWeather`: true when the verdict is "Mostly muddy" or "Muddy in spots"; the site then says to stick to all-weather trails or the Greenbelt. `allWeather`: `count` of all-weather trails that are not muddy, closed or unevaluated, and `areas` (`name`, `count`) listing where they are.
- These are our summary of R2R's trail reports, not R2R recommendations, and the site words them that way ("Driest areas right now"). The summary line includes the not-evaluated count.
- `closed`: groups of closed trails sharing a staff note (`note`, `trails`, `areas`; notes are plain text).
- `url`, `mapUrl`, `credit`: the Ridge to Rivers pages and the required credit line ("Trail conditions, text and photos: City of Boise / Ridge to Rivers").
- Not yet: the written daily report and photo (planned as a second step; they will be added as `report`).

## Still to decide (small)
1. History for sparklines: separate `history.json` (last 7 days per station/gauge) so `conditions.json` stays small.
2. Where "last-known" is stored between runs (Actions cache or a small JSON committed to a data branch).
3. NWS zone to region mapping file `data/zone_region.json` (needs one run locally; see tasks).

## Facts from the points check (2026-11-15) that shape the build
- A region spans several NWS offices: Panhandle and Clearwater are OTX (Spokane); Southwest BOI; Magic Valley BOI and PIH (Ketchum is PIH); Southeast and Upper Snake PIH; Salmon MSO (Missoula). Fetchers must not assume one office per region.
- Alerts are issued by zone, so each region needs the list of NWS zones inside it. Example zones: Coeur d'Alene IDZ002, Lewiston IDZ026, Boise IDZ014, McCall IDZ011, Twin Falls IDZ016, Ketchum IDZ073, Pocatello IDZ054, Idaho Falls IDZ053, Island Park IDZ066, Salmon IDZ010.
- Panhandle and Clearwater points are America/Los_Angeles; all others America/Boise.

## Air quality forecast (`regions.<id>.airForecast`, part `airnow_forecast`)

Forecasts from the state and local air agencies (Idaho DEQ in Idaho), republished by AirNow's reporting-area file. `null` when the region has no current forecast. The site, the Brief and the watcher must tolerate a missing key.
An Action Day is information only: it never changes `level`, the status chips or the alert bar.
- `areas`: one entry per AirNow reporting area inside the region (for example Boise, McCall and Idaho City in Southwest). Each has `name`, `issued` (the date the agency issued the forecast, `YYYY-MM-DD`; the newest across the area's rows), `days`, `actionDay` (any remaining day is flagged) and `discussion` (the forecaster's text, plain, at most 600 characters, may be empty).
- `days[]`: `date` (`YYYY-MM-DD`, region time zone), `cat` (1 Good, 2 Moderate, 3 Unhealthy for Sensitive Groups, 4 Unhealthy, 5 Very Unhealthy, 6 Hazardous), `category` (name), `aqi` (number, or null when the agency gave only a category), `pollutant`, `actionDay`. One entry per date: the worst pollutant that day.
- `source`, `url`: the credit text ("Idaho DEQ forecast, via AirNow") and https://www.airnow.gov/.
- Freshness is decided at build time (`build_conditions.apply_air_forecast_freshness`), not by a stale flag: days before today (region time zone) are dropped; an area is removed when no day remains or it was issued more than 3 days ago. Idaho DEQ mostly forecasts on weekdays, so a Friday forecast still serves the weekend.
- `sources.airnow_forecast.{fetchedAt,ok,error}` follow the usual rules (on failure the last data is kept, then ages out by the rule above).
- Fetcher: `scripts/fetch_airnow_forecast.py`, one keyless download of AirNow's reporting-area file. It does not use `AIRNOW_API_KEY`.
