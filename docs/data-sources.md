# Data sources and coverage

Status: **probed live on 2026-11-15** (`scripts/probe_sources.py`, run locally; raw samples in `docs/probes/2026-11-15/`). Idaho 511's keyed endpoints are not probed yet (key pending). The cloud sandbox cannot reach these hosts (policy block), so probes run locally.

## 1. Source summary

| Source | Gives us | Key | Limits / cadence (observed + docs) | Terms notes | Verified |
|---|---|---|---|---|---|
| **NWS** api.weather.gov | 12-hr forecasts (14 periods), alerts by state/zone, grid data | No; User-Agent with contact | Limit unpublished; responses cache about 5 s | Open data | **yes** (11 points, ID alerts) |
| **AirNow** | Current AQI per pollutant by lat/long (new service) | Yes (have it) | Observations hourly; ~280 ms/call | Label preliminary, credit agencies, don't alter AQI values/colors (plan) | **yes** |
| **NRCS AWDB** | SNOTEL snow depth, SWE, precip, temp; daily + hourly; 1991-2020 medians | No | Whole-state latest values in one call (~3.5 s) | Public domain | **yes** |
| **USGS Water Data** | Streamflow (cfs), latest + daily + continuous; site metadata | Optional; works without | `latest-continuous` returns no-cache; `daily` caches 1 hr | Federal data; values marked Provisional | **yes** (no key used) |
| **NIFC WFIGS** | Fire incident points and perimeters | No | Cache 5 min | Open data | **yes** |
| **Idaho 511** | Roads, passes, events, alerts, cameras, weather stations (keyed); WZDx work zones (keyless) | Key received 2026-11-17; fetcher written (scripts/fetch_511.py), not yet run live | 10 calls / 60 s | Terms appear at signup | WZDx **yes**; keyed: pending |

## 2. What the probe taught us

**NWS**
- Forecast zones, counties and offices per test point: Coeur d'Alene IDZ002 (office OTX Spokane), Lewiston IDZ026 (OTX), Boise IDZ014 (BOI), McCall IDZ011 (BOI), Twin Falls IDZ016 (BOI), Ketchum IDZ073 (PIH Pocatello), Pocatello IDZ054 (PIH), Idaho Falls IDZ053 (PIH), Island Park IDZ066 (PIH), Salmon IDZ010 (MSO Missoula), Stanley IDZ072 (PIH). Forecast offices do not follow the Fish and Game regions, so region cards must be built from chosen points or zones.
- Alerts are zone-based: at 10:49 AM two Winter Weather Advisories were active (Southern Clearwater Mountains IDZ006; Lemhi County IDZ009/IDZ010, both until Nov 17 11 PM). At 10:43 AM the same query returned none, so the alert list changes within minutes. Fields: event, severity, urgency, headline, areaDesc, onset, ends, affectedZones.

**AirNow**
- New service `/aq/observation/current/ziplatlong/` works with `latitude`, `longitude`, `format`, `API_KEY`. The old `/latLong/current/` returns HTTP 410 "retired".
- Returns one row per pollutant (PM2.5, PM10, OZONE) with `nowcastAQI`, category, site name, agency, hour and `localTimeZone` (PST in the north, MST elsewhere).
- Coverage varies: McCall, Boise, Twin Falls, Ketchum, Pocatello, Idaho Falls, Salmon, Lewiston and Coeur d'Alene have PM2.5. Stanley borrows Ketchum's monitor (within the 50-mile lookup). **Island Park returns only a Yellowstone ozone reading, no PM2.5**, so smoke can't be judged there. Some rows come from Washington or Yellowstone monitors.
- Today: Coeur d'Alene PM2.5 53 and Salmon 53 (Moderate); most others Good.

**SNOTEL (AWDB)**
- 87 active Idaho SNOTEL stations once filtered to `:ID:SNTL`. The `networkCodes` filter did not work (4,396 stations returned, including snow courses), so the fetcher must filter by triplet suffix.
- `/data` accepts a comma list of stations and several elements in one call (all 87 stations for 3 days: 61 KB). Daily values lag by a day (latest was Nov 14). Hourly SNWD/TOBS works. `centralTendencyType=MEDIAN` returns daily median plus median peak/onset/meltout dates.
- Some listed stations have no daily data (e.g. snow-course sites ending `:SNOW`).
- Snow today is early-season. Top depths: Smiley Mountain (Salmon) 15", Galena Summit (Magic Valley) 13", Dollarhide Summit 9", Trinity Mtn. (Southwest) 7". Brundage Reservoir and Bogus Basin 3". The mockup's "Brundage 18 in" and "92% of median" were placeholders.

**USGS**
- Works with no key (`X-Api-Key` header is available when we get one). Response uses `/ogcapi/v0`. Collections include `latest-continuous`, `continuous`, `latest-daily`, `daily`, `monitoring-locations` and about 30 others.
- All 10 candidate gauges returned values. Examples at about 10:50 AM: SF Payette at Lowman 313 cfs, Payette near Emmett 857, Salmon at White Bird 3,870, Clearwater at Spalding 3,430. Values are strings and all marked Provisional.
- Staleness is real: Salmon at Salmon and Snake near Twin Falls last reported Nov 14 (about 32 h old), and some other gauges are years out of date. Rules for "too old to show" are needed.
- Gauge 13246000 (the mockup's) exists (255 cfs) but I haven't got its name yet. Per-region gauge counts need the corrected name lookup in the next probe run.

**NIFC**
- Idaho today: 12 incident records (10 prescribed burns, 2 wildfires: Moose Mountain 90% contained and Silver 100% contained, both from summer). Includes Sloans Point prescribed burn (Valley County, discovered Nov 9). The "current" layers keep old records (a January pile burn, fire perimeters from September), so we need filters: incident type (WF vs RX), containment, and last-modified date.
- The Idaho bounding box also catches Montana and Oregon incidents (30 MT Rx, 4 MT WF, 2 OR WF in this run). Filter on `POOState = US-ID` (field exists and works).

**Idaho 511**
- WZDx (construction work zones) works with no key but is 2.7 MB; start and end dates in the sample were inconsistent (start after end), so validate before showing. It covers work zones only, not winter road conditions.
- Winter roads, mountain passes, events, alerts and cameras still need the key.

## 3. Endpoints in use (confirmed unless noted)

| Source | Endpoint |
|---|---|
| NWS | `/points/{lat},{lon}` then `forecast` URL; `/alerts/active?area=ID` |
| AirNow | `https://www.airnowapi.org/aq/observation/current/ziplatlong/?latitude=&longitude=&format=application/json&API_KEY=` |
| AWDB | `.../awdbRestApi/services/v1/stations?stateCodes=ID&activeOnly=true` (filter `:SNTL` ourselves); `/data?stationTriplets=...&elements=SNWD,WTEQ&duration=DAILY&beginDate=&endDate=` |
| USGS | `https://api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous/items?monitoring_location_id=USGS-########&parameter_code=00060&f=json` |
| NIFC | `services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0/query` and `WFIGS_Interagency_Perimeters_Current` |
| Idaho 511 | `https://511.idaho.gov/api/v2/get/{mountainpasses,winterroads,event,alerts,cameras,weatherstations}?key=` (unconfirmed until key arrives); WZDx `https://511.idaho.gov/api/wzdx` (confirmed) |

## 4. Region coverage table (from the probe)

Region membership should come from IDFG's official region polygons (gis.idfg.idaho.gov Boundaries MapServer layer 0), not county lists: IDFG notes its regions differ slightly from county lines. The SNOTEL counts below used a county grouping from memory, so treat them as **approximate** until `scripts/region_tools.py` assigns each station by location. IDFG's Hunt Planner lists a hunt area with exactly my Southwest grouping (Ada, Adams, Boise, Canyon, Elmore, Gem, Owyhee, Payette, Valley, Washington), which is consistent with it but not an explicit region definition; I could not find official county lists for the other six regions.

| Region | Weather (NWS) | Snow (SNOTEL stations; with snow today) | Rivers (USGS) | Air (AirNow) | Fire (NIFC) | Roads (511) |
|---|---|---|---|---|---|---|
| 1 Panhandle | Auto (OTX) | 11; 5 | Auto; at least 18 gauges incl. Kootenai, Moyie | PM2.5 (Coeur d'Alene, Moderate 53) | Auto; filter | Pending key |
| 2 Clearwater | Auto (OTX); advisory active | 11; 2 | Auto (Clearwater at Spalding 3,430 cfs) | PM2.5 (Lewiston) | Auto; Moose Mtn (90%) | Pending key |
| 3 Southwest | Auto (BOI) | 23; 7 (Trinity 7", Brundage 3", Bogus 3") | Auto (Boise, Payette gauges) | PM2.5 Boise and McCall | Auto; Sloans Point Rx (Valley) | Pending key |
| 4 Magic Valley | Auto (BOI/PIH) | 16; 9 (Galena Summit 13") | Auto (Snake near Twin Falls stale) | PM2.5 Twin Falls, Ketchum | Auto | Pending key |
| 5 Southeast | Auto (PIH) | 10; 2 | Auto; at least 7 gauges incl. Bear River | PM2.5 Pocatello | Auto | Pending key |
| 6 Upper Snake | Auto (PIH) | 4; 3 | Auto (Snake near Heise 2,020 cfs) | PM2.5 Idaho Falls; **none at Island Park** | Auto | Pending key |
| 7 Salmon | Auto (MSO/PIH); advisory active | 12; 8 (Smiley Mtn 15") | Auto (Salmon at Salmon stale) | PM2.5 Salmon (Moderate 53); Stanley uses Ketchum | Auto | Pending key |

Not yet covered by any feed we tested: avalanche (permission), ski status (manual/link), Forest Service road and campground status (manual/link), hot springs (Hot Springs West, untested).

## 5. Design implications
1. **Freshness rules are required.** Every value needs its own timestamp and an "too old" cutoff per source (gauges can go a day or more stale; NIFC keeps old records).
2. **Region cards need chosen inputs:** representative NWS point/zone, SNOTEL stations, USGS gauges, AirNow point, and an NWS-zone-to-region mapping for alerts.
3. **Label provisional data** (USGS, AirNow) and show source and hour.
4. **Fire block:** show active wildfires and, separately, prescribed burns; hide contained and old records.
5. **AQI gaps:** show "no nearby monitor" instead of a value where none exists.
6. **Time zones:** AirNow and gauges report PST in the north and MST elsewhere; show the source's local time.
7. **Batching:** SNOTEL and USGS can fetch many stations per call, so the build job can stay small.

## 6. Open questions
- Download IDFG region polygons and assign stations/gauges by location (`region_tools.py fetch`, then `assign`); then map NWS zones to regions.
- Idaho 511 keyed endpoints, commercial-use terms and camera image reuse (key pending).
- Corrected USGS name lookup (`state_code=16`) so we can count and choose gauges per region; rerun the probe.
- NWS User-Agent contact: set via `IC_USER_AGENT` (done locally; keep out of the repo).
- Avalanche, ski, Forest Service and campground sources (permissions / manual).

## Sources (docs consulted 2026-11-15)
- [AirNow API: June 2026 update notice](https://docs.airnowapi.org/docs/AirNowAPIUpdates2026June.pdf), [AirNow FAQ](https://docs.airnowapi.org/faq)
- [NWS API documentation](https://weather.gov/documentation/services-web-api)
- [NRCS AWDB REST](https://www.nrcs.usda.gov/programs-initiatives/sswsf-snow-survey-and-water-supply-forecasting-program/snow-and-water-products)
- [USGS Water Data APIs](https://api.waterdata.usgs.gov/docs/agents/)
- [Idaho 511 API documentation](https://511.idaho.gov/developers/doc)
- [NIFC open data](https://data-nifc.opendata.arcgis.com/)
- Business plan: `docs/Idaho_Conditions_Business_Plan.pdf`
