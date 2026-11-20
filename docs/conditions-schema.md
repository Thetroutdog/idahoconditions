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
- `snow`, `rivers` and `air.points` list only items chosen in `data/selected_stations.json` and `data/region_points.json`.
- `fire.wildfires` and `fire.prescribed` are separate lists (design decision: show prescribed burns as their own line).
- `avalanche` lists the avalanche centers whose forecasts cover the region (`id`, `name`, `url`, `area`), from `data/avalanche_centers.json` (static links, edited by hand; Grok confirmed the eastern Idaho cross-border centers). Top-level `avalanchePoints` maps a forecast point id (e.g. `island-park`) to center ids that override the region list for that town.
- `ski` lists weekly open/closed/opening-soon results per region (ski, nordic and snowmobile areas) from `data/resort_status.json`, written by `scripts/fetch_resort_status.py` locally. Each item: `id`, `name`, `status` (`open`, `closed`, `opening-soon`), `confidence`, `opening`/`openingISO`, `url`, `checkedAt`, `freshness` (`stale` when the crawl is more than 8 days old), `source`. Areas whose status is `unknown` are left out. The site does not display it yet; the Thursday Brief can read it.
- Idaho 511 fills `roads` once the key arrives; until then `roads.status` is `missing` and the region cannot be green (rule: no green when we can't tell) so the page shows gray plus last-known.

## Still to decide (small)
1. History for sparklines: separate `history.json` (last 7 days per station/gauge) so `conditions.json` stays small.
2. Where "last-known" is stored between runs (Actions cache or a small JSON committed to a data branch).
3. NWS zone to region mapping file `data/zone_region.json` (needs one run locally; see tasks).

## Facts from the points check (2026-11-15) that shape the build
- A region spans several NWS offices: Panhandle and Clearwater are OTX (Spokane); Southwest BOI; Magic Valley BOI and PIH (Ketchum is PIH); Southeast and Upper Snake PIH; Salmon MSO (Missoula). Fetchers must not assume one office per region.
- Alerts are issued by zone, so each region needs the list of NWS zones inside it. Example zones: Coeur d'Alene IDZ002, Lewiston IDZ026, Boise IDZ014, McCall IDZ011, Twin Falls IDZ016, Ketchum IDZ073, Pocatello IDZ054, Idaho Falls IDZ053, Island Park IDZ066, Salmon IDZ010.
- Panhandle and Clearwater points are America/Los_Angeles; all others America/Boise.
