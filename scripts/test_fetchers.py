#!/usr/bin/env python3
"""Offline tests: run each fetcher against small fake API responses and build conditions from the result.
    python3 scripts/test_fetchers.py     (needs data/idfg_regions.geojson, data/selected_stations.json, data/region_points.json)"""
import json, os, sys, datetime as dt, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_common as c
import fetch_snotel, fetch_usgs, fetch_airnow, fetch_nifc, build_conditions as bc

now = c.now_utc()
mst = now - dt.timedelta(hours=8)  # one hour ago, expressed in MST (UTC-7)
today = mst.date()
HOUR = mst.strftime("%H:00")
sel = c.load_json("data/selected_stations.json")
sn = sel["snow"][0]["snotel"]
rv = sel["rivers"][0]

def fake(url, headers=None, timeout=60):
    if "awdbRestApi" in url and "/data" in url and "duration=HOURLY" in url:
        base = dt.datetime.now().replace(minute=0, second=0, microsecond=0)
        hv = lambda vals: [{"date": (base - dt.timedelta(hours=len(vals) - 1 - i)).strftime("%Y-%m-%d %H:%M"), "value": x} for i, x in enumerate(vals)]
        depth = [5] * 24 + [7] * 6 + [9] * 6   # 36 hours: +4 in over the last 24 h
        return [{"stationTriplet": s, "data": [
            {"stationElement": {"elementCode": "SNWD"}, "values": hv(depth)},
            {"stationElement": {"elementCode": "WTEQ"}, "values": hv([1.5] * 30 + [2.4] * 6)}]} for s in url.split("stationTriplets=")[1].split("&")[0].replace("%3A", ":").replace("%2C", ",").split(",")]
    if "awdbRestApi" in url and "/data" in url:
        med = "centralTendencyType" in url
        v = lambda d, val: {"date": (today - dt.timedelta(days=d)).isoformat(), "value": val, **({"median": 2.0} if med else {})}
        return [{"stationTriplet": s, "data": [
            {"stationElement": {"elementCode": "SNWD"}, "values": [v(2, 6), v(1, 9)]},
            {"stationElement": {"elementCode": "WTEQ"}, "values": [v(2, 1.8), v(1, 2.5)]}]} for s in url.split("stationTriplets=")[1].split("&")[0].replace("%3A", ":").replace("%2C", ",").split(",")]
    if "awdbRestApi" in url and "/stations" in url:
        return [{"stationTriplet": sn["id"], "elevation": 6280}]
    if "waterdata.usgs.gov" in url:
        code = "00060" if "00060" in url else "00065"
        ids = url.split("monitoring_location_id=")[1].split("&")[0].replace("%2C", ",").split(",")
        return {"features": [{"properties": {"monitoring_location_id": i, "time": now.isoformat(), "value": "255.0" if code == "00060" else "3.2",
                                             "approval_status": "Provisional"}} for i in ids if code == "00060"]}
    if "airnowapi" in url:
        if "latitude=44.42" in url:  # Island Park: no monitor
            return []
        return [{"dateObserved": today.isoformat(), "hourObserved": HOUR, "localTimeZone": "MST", "parameterName": "PM2.5", "nowcastAQI": 118,
                 "aqiCategoryName": "Unhealthy for Sensitive Groups", "siteName": "Test"},
                {"dateObserved": today.isoformat(), "hourObserved": HOUR, "localTimeZone": "MST", "parameterName": "OZONE", "nowcastAQI": 20, "aqiCategoryName": "Good", "siteName": "Test"}]
    if "arcgis" in url:
        ms = lambda days: int((now - dt.timedelta(days=days)).timestamp() * 1000)
        base = {"POOCounty": "Valley", "PercentContained": 20, "ModifiedOnDateTime_dt": ms(1), "FireDiscoveryDateTime": ms(3)}
        return {"features": [
            {"attributes": {**base, "IncidentName": "TEST FIRE", "IncidentTypeCategory": "WF", "IncidentSize": 120, "FireCause": "Natural", "POOProtectingUnit": "IDNCF"}, "geometry": {"x": -116.1, "y": 44.9}},
            {"attributes": {**base, "IncidentName": "BURN ONE", "IncidentTypeCategory": "RX", "IncidentSize": 30}, "geometry": {"x": -116.1, "y": 44.9}},
            {"attributes": {**base, "IncidentName": "OLD FIRE", "IncidentTypeCategory": "WF", "ModifiedOnDateTime_dt": ms(40)}, "geometry": {"x": -116.1, "y": 44.9}},
            {"attributes": {**base, "IncidentName": "MONTANA", "IncidentTypeCategory": "WF"}, "geometry": {"x": -112.0, "y": 47.0}}]}
    raise AssertionError("unexpected url " + url)

c.http_json = fake
for m in (fetch_snotel, fetch_usgs, fetch_airnow, fetch_nifc):
    m.http_json = fake
c.PARTS = tempfile.mkdtemp()
fetch_airnow.os.environ["AIRNOW_API_KEY"] = "x"
fetch_airnow.time.sleep = fetch_usgs.time.sleep = lambda s: None
parts = {}
for name, mod in (("snotel", fetch_snotel), ("usgs", fetch_usgs), ("airnow", fetch_airnow), ("nifc", fetch_nifc)):
    parts[name] = c.run_part(name, mod.fetch)
    assert parts[name]["ok"], parts[name]["error"]

snow = [e for r in parts["snotel"]["regions"].values() for e in r["snow"]]
assert snow and snow[0]["basis"] == "hourly" and snow[0]["depth"]["value"] == 9 and snow[0]["depthChange24h"]["value"] == 4 and snow[0]["pctOfMedian"]["value"] == 120, snow[0]   # hourly: depth, change and water content from the same hour
assert snow[0]["depth"]["provisional"] and not snow[0]["depthChange24h"].get("suspect"), snow[0]
_ska = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "ski_areas.json")))["areas"]
_ski = {k: v for r in parts["snotel"]["regions"].values() for k, v in r.get("skiStations", {}).items()}
assert all(a["id"] in _ski for a in _ska if a["stations"]) and not any(a["id"] in _ski for a in _ska if not a["stations"]), _ski.keys()
assert all(len(a["stations"]) <= 2 and all(st["distanceMi"] <= 12 and abs(st["feetVsMid"]) <= 1500 for st in a["stations"]) for a in _ska)
_b = _ski["southwest-brundage-mountain"][0]
assert _b["feetVsMid"] == -210 and _b["distanceMi"] == 2.9 and "depth" in _b, _b   # distance and feet vs mid-mountain travel with the station
riv = [e for r in parts["usgs"]["regions"].values() for e in r["rivers"]]
assert len(riv) == len(sel["rivers"]) and riv[0]["flow"]["value"] == 255.0 and riv[0]["use"], riv[0]
air = parts["airnow"]["regions"]
assert air["southwest"]["air"]["points"][0]["aqi"]["value"] == 118 and air["upper-snake"]["air"]["points"][-1]["aqi"]["value"] is None
fire = parts["nifc"]["regions"]["southwest"]["fire"]
assert [f["name"] for f in fire["wildfires"]] == ["Test Fire"] and [f["name"] for f in fire["prescribed"]] == ["Burn One"], fire
assert "montana" not in json.dumps(parts["nifc"]).lower()
_tf = fire["wildfires"][0]
assert _tf["cause"] == "Natural" and _tf["unit"] == "IDNCF" and _tf["lat"] == 44.9 and _tf["lon"] == -116.1, _tf   # cause, protecting unit and a map point come through
conds = bc.build({"nws": {"source": "nws", "ok": True, "fetchedAt": now.isoformat(), "error": None, "forecast": {}, "alerts": {}}, **parts}, now)
sw = conds["regions"]["southwest"]
assert sw["level"] == "amber" and "AQI 118" in sw["summary"] and any(r["kind"] == "wildfire" for r in sw["levelReasons"]), sw["levelReasons"]
assert conds["regions"]["panhandle"]["level"] == "amber" or conds["regions"]["panhandle"]["level"] == "gray"
assert conds["sources"]["snotel"]["ok"] and sw["rivers"][0]["flow"]["status"] == "fresh"
old = bc.build({"usgs": {**parts["usgs"], "fetchedAt": now.isoformat()}}, now + dt.timedelta(hours=5))
assert old["regions"]["southwest"]["rivers"][0]["flow"]["status"] == "stale"
print("all fetcher tests ok; southwest summary:", sw["summary"])


# NWS alert link: point inside a zone polygon (concave "L" shape whose bbox center is outside it)
import fetch_nws as _nws
_nws.get = lambda url, *a, **k: {"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 1], [1, 1], [1, 10], [0, 10], [0, 0]]]}}
_pt = _nws.zone_point("https://api.weather.gov/zones/forecast/TEST")
assert _pt and _nws._inside(_pt[1], _pt[0], [[0, 0], [10, 0], [10, 1], [1, 1], [1, 10], [0, 10], [0, 0]]), _pt
# alert links: the alert's own page (zone + county from its SAME code), else the issuing office, else the national alerts page; never a point forecast
assert _nws.alert_url({"affectedZones": ["https://api.weather.gov/zones/forecast/IDZ010"], "geocode": {"SAME": ["016059"]}}) == "https://forecast.weather.gov/showsigwx.php?warnzone=IDZ010&warncounty=IDC059"
assert _nws.alert_url({"affectedZones": ["https://api.weather.gov/zones/forecast/MTZ001", "https://api.weather.gov/zones/forecast/IDZ010"], "geocode": {"SAME": ["030001", "016059"]}}).endswith("warnzone=IDZ010&warncounty=IDC059")
assert _nws.alert_url({"affectedZones": ["https://api.weather.gov/zones/forecast/IDZ010"]}, {"IDZ010": {"office": "MSO"}}) == "https://www.weather.gov/mso/"
assert _nws.alert_url({"web": "http://www.weather.gov"}) == _nws.ALERTS_PAGE and "alerts.weather.gov" not in _nws.ALERTS_PAGE
print("alert zone point ok")


# Special Weather Statement mismatch (Nov 25): the details link is an alerts page (never a MapClick forecast), the gist is kept, and an alert whose end time has passed is dropped
_now = dt.datetime.now(dt.timezone.utc)
def _sps(i, expires):
    return {"properties": {"id": f"urn:oid:test.{i}", "event": "Special Weather Statement", "status": "Actual", "messageType": "Alert", "severity": "Minor",
            "effective": (_now - dt.timedelta(hours=1)).isoformat(), "ends": None, "expires": expires, "headline": "Special Weather Statement issued by NWS Spokane WA",
            "web": "http://www.weather.gov", "affectedZones": ["https://api.weather.gov/zones/forecast/IDZ001"], "geocode": {"SAME": ["016021"]}, "severity": "Minor",
            "parameters": {"NWSheadline": ["A WINTRY MIX WILL IMPACT SOUTHERN BOUNDARY AND CENTRAL BONNER COUNTIES UNTIL 630 AM PST"]},
            "description": "At 538 AM PST, a trained spotter reported a wintry mix.\n\nIcy conditions possible on untreated surfaces."}}
_nws.get = lambda url, *a, **k: {"features": [_sps(1, (_now + dt.timedelta(minutes=50)).isoformat()), _sps(2, (_now - dt.timedelta(minutes=5)).isoformat())]}
_zm = {"IDZ001": {"shares": {"Panhandle": 1.0}, "primary": "Panhandle"}}
_out = _nws.alerts(_zm)
_pan = _out.get("panhandle", [])
assert len(_pan) == 1 and _pan[0]["id"] == "urn:oid:test.1", _pan   # the expired statement is gone, the live one stays
assert _pan[0]["url"] == "https://forecast.weather.gov/showsigwx.php?warnzone=IDZ001&warncounty=IDC021", _pan[0]["url"]
# a zone that only touches a region (16% of Eastern Lemhi is in Upper Snake) does not put its alert on that region's page; its primary region still gets it
_zm2 = {"IDZ001": {"shares": {"Salmon": 0.84, "Upper Snake": 0.16}, "primary": "Salmon"}}
_o2 = _nws.alerts(_zm2)
assert "salmon" in _o2 and "upper-snake" not in _o2, list(_o2)
assert _pan[0]["summary"].startswith("At 538 AM PST") and _pan[0]["gist"], _pan[0]
print("nws alert link and expiry tests ok")


# ---- Ridge to Rivers trail status (rows below are trimmed from the real layer, plus synthetic mud) ----
import fetch_r2r as r2r
_n = c.now_utc()
_ms = lambda h: int((_n - dt.timedelta(hours=h)).timestamp() * 1000)
_row = lambda name, sub, cond, h=2, notes=None, aw="No": {"TrailName": name, "Name": "#1 " + name, "TrailSubSystem": sub, "Condition": cond, "ConditionNotes": notes, "ConditionDate": _ms(h), "AllWeather": aw, "R2R_Use": "Multi-use non-motorized"}
_DRY, _MUD = "Dry / Tacky - Enjoy", "Muddy – DO NOT USE"
_MIX = "Dry at start but could be muddy further out – turn around when you encounter mud.  Don’t keep going."
_sample = ([_row(f"Dry{i}", "Polecat Gulch", _DRY) for i in range(6)] + [_row("Hulls Mud", "Camels Back / Hulls Gulch", _MUD)] * 3
           + [_row("Mix", "Table Rock", _MIX), _row("Ice", "Dry Creek", "Frozen/snow covered - Enjoy", aw="Yes"), _row("Owl's Roost", "Camels Back / Hulls Gulch", _DRY, aw="Yes"),
              _row("Mores", "Bogus Basin Area", "CLOSED", notes="These trails are closed for the winter, to allow for Bogus Basin Ski Operations"),
              _row("Sinker", "Bogus Basin Area", "CLOSED", notes="These trails are closed for the winter, to allow for Bogus Basin Ski Operations"),
              _row("Pump Track", "Military Reserve", "Not Evaluated", notes='Visit <a href=https://x.example target="_blank">Boise Bike Park website</a> for current condition report.'),
              _row("8th St Ext", "N/A", "Not Evaluated"), _row("Weird", "Table Rock", "Something new")])
for t, want in [(_MUD, "muddy"), (_MIX, "mixed"), (_DRY, "dry"), ("Frozen/snow covered - Enjoy", "frozen"), ("Frozen early then muddy – BE OFF THE TRAIL BEFORE IT THAWS…", "frozen-am"), ("CLOSED", "closed"), ("Not Evaluated", "unknown"), ("???", "unknown")]:
    assert r2r.code_of(t) == want, (t, r2r.code_of(t))
_r = r2r.summarize(_sample, _n)
assert _r["counts"]["muddy"] == 3 and _r["counts"]["dry"] == 7 and _r["counts"]["closed"] == 2 and _r["counts"]["mixed"] == 1 and _r["counts"]["frozen"] == 1, _r["counts"]
assert _r["counts"]["unknown"] == 2 and _r["total"] == 16, _r["counts"]  # the N/A access road is skipped; "Pump Track" and the new wording are unknown
assert _r["verdict"] == "Mostly dry" and _r["tone"] == "green" and not _r["stale"], _r["verdict"]
assert [a["name"] for a in _r["driest"]] == ["Polecat Gulch"], _r["driest"]  # Hulls Gulch is mostly mud, so it is not named
assert not _r["suggestAllWeather"] and "2 not evaluated" in _r["summary"], _r["summary"]
assert _r["closed"][0]["trails"] == ["Mores", "Sinker"] and _r["closed"][0]["areas"] == ["Bogus Basin Area"] and "<" not in _r["closed"][0]["note"], _r["closed"]
assert _r["allWeather"]["count"] == 2 and _r["allWeather"]["areas"] == [{"name": "Camels Back / Hulls Gulch", "count": 1}, {"name": "Dry Creek", "count": 1}], _r["allWeather"]
assert _r["originalText"]["muddy"] == _MUD
assert "Boise foothills" in _r["title"] and _r["credit"].startswith("Trail conditions, text and photos: City of Boise")
_mud = r2r.summarize([_row(f"m{i}", "Table Rock", _MUD) for i in range(6)] + [_row("d", "Table Rock", _DRY)], _n)
assert _mud["verdict"] == "Mostly muddy" and _mud["tone"] == "amber" and _mud["driest"] == [] and _mud["suggestAllWeather"]
# area lines (driest, frozen, muddiest, mostly closed): rebuilt from a day like Nov 27 2026, when Bogus Basin had 12 frozen trails and 15 closed
_day = ([_row(f"a{i}", "Ada-Eagle Bike Park", _DRY) for i in range(41)] + [_row("am", "Ada-Eagle Bike Park", _MUD)]
        + [_row(f"o{i}", "Oregon Trail Reserve", _DRY) for i in range(6)] + [_row(f"t{i}", "Table Rock", _MUD) for i in range(19)] + [_row("td", "Table Rock", _DRY)]
        + [_row(f"b{i}", "Bogus Basin Area", "Frozen/snow covered - Enjoy") for i in range(12)] + [_row(f"c{i}", "Bogus Basin Area", "CLOSED", notes="closed for the winter") for i in range(15)]
        + [_row(f"u{i}", "Upper Dry Creek", "Frozen/snow covered - Enjoy") for i in range(6)] + [_row(f"s{i}", "Small Area", _DRY) for i in range(4)]
        + [_row(f"x{i}", "Hulls Gulch", _MUD, aw="Yes") for i in range(3)] + [_row(f"w{i}", "Hulls Gulch", _DRY, aw="Yes") for i in range(2)])
_d = r2r.summarize(_day, _n)
assert [a["name"] for a in _d["driest"]] == ["Ada-Eagle Bike Park", "Oregon Trail Reserve"], _d["driest"]  # 41 of 42 dry counts; 4 open trails is too few
assert [a["name"] for a in _d["frozenAreas"]] == ["Upper Dry Creek"], _d["frozenAreas"]  # Bogus is mostly closed, so it is not a frozen-area pick
assert [a["name"] for a in _d["closedAreas"]] == ["Bogus Basin Area"] and _d["closedAreas"][0]["closed"] == 15 and _d["closedAreas"][0]["n"] == 27
assert [a["name"] for a in _d["muddiest"]] == ["Table Rock"], _d["muddiest"]
assert _d["verdict"] == "Mostly dry" and not _d["suggestAllWeather"] and _d["allWeather"]["count"] == 2 and _d["allWeather"]["areas"] == [{"name": "Hulls Gulch", "count": 2}]
assert all(set(a) >= {"name", "n", "dry", "muddy", "frozen", "closed", "unknown"} for a in _d["driest"] + _d["subsystems"])
# "as of" comes from last_edited_date (real UTC), not ConditionDate (wall clock stored as UTC, 7 h early in winter)
_wall = dict(_row("w", "Table Rock", _DRY), ConditionDate=_ms(2 + 7), last_edited_date=_ms(2))
_aw = r2r.summarize([_wall], _n)
assert _aw["asOf"] == r2r.iso(_ms(2)) and not _aw["stale"], _aw["asOf"]
assert r2r.summarize([_row("w", "Table Rock", _DRY)], _n)["asOf"] == r2r.iso(_ms(2)), "falls back to ConditionDate when last_edited_date is missing"
_old = r2r.summarize([_row("a", "Table Rock", _DRY, h=24 * 5)], _n)
assert _old["stale"] and _old["asOf"], _old  # over 72 h old: stale, not a failure
for bad in ([], ):
    try:
        r2r.summarize(bad, _n); raise SystemExit("zero rows should raise")
    except RuntimeError:
        pass
r2r.http_json = lambda url, headers=None, timeout=60: {"error": {"code": 400}}
try:
    r2r.rows(); raise SystemExit("an ArcGIS error body should raise")
except RuntimeError:
    pass
_pages = [{"features": [{"attributes": a} for a in _sample[:5]], "exceededTransferLimit": True}, {"features": [{"attributes": a} for a in _sample[5:]]}]
_seen = []
r2r.http_json = lambda url, headers=None, timeout=60: (_seen.append(url), _pages[len(_seen) - 1])[1]
assert len(r2r.rows()) == len(_sample) and "resultOffset=5" in _seen[1], _seen
r2r.http_json = lambda url, headers=None, timeout=60: {"features": [{"attributes": a} for a in _sample]}
_p = c.run_part("r2r", r2r.fetch)
assert _p["ok"] and _p["regions"]["southwest"]["local"]["r2r"]["verdict"] == "Mostly dry"
_b = bc.build({"nws": {"source": "nws", "ok": True, "fetchedAt": _n.isoformat(), "error": None, "forecast": {}, "alerts": {}}, "r2r": _p}, _n)
assert _b["regions"]["southwest"]["local"]["r2r"]["verdict"] == "Mostly dry" and _b["sources"]["r2r"]["ok"], _b["sources"]
assert _b["regions"]["panhandle"]["local"] == {} and _b["regions"]["southwest"]["level"] == bc.build({"nws": {"source": "nws", "ok": True, "fetchedAt": _n.isoformat(), "error": None, "forecast": {}, "alerts": {}}}, _n)["regions"]["southwest"]["level"]  # a local source never changes the region level
_late = bc.build({"r2r": _p}, _n + dt.timedelta(hours=100))
assert _late["regions"]["southwest"]["local"]["r2r"]["stale"], "build re-checks staleness from asOf"
assert "r2r" not in bc.build({}, _n)["sources"] and bc.build({}, _n)["regions"]["southwest"]["local"] == {}, "the build works with the part missing"
print("r2r trail status tests ok")

# ---- AirNow forecasts (fetch_airnow_forecast.py). The sample lines are SYNTHETIC, written from AirNow's file documentation; the real file
# ---- is checked by running the fetcher once on a real machine (it prints what it found).
import fetch_airnow_forecast as af
_ln = lambda date, typ, area, st, lat, lon, par, aqi, cat, action="No", disc="", prim="Y", issue="11/25/26": "|".join([issue, date, "", "MST", "0", typ, prim, area, st, f"{lat:.4f}", f"{lon:.4f}", par, "" if aqi is None else str(aqi), str(cat), action, disc, "Idaho Department of Environmental Quality"])
_air = "\n".join([
    _ln("11/25/26", "O", "Boise", "ID", 43.6, -116.2, "PM2.5", 52, 2),                                   # observed: ignored
    _ln("11/25/26", "F", "Boise", "ID", 43.6, -116.2, "PM2.5", 60, 2, "", "Stagnant air builds under an inversion."),
    _ln("11/26/26", "F", "Boise", "ID", 43.6, -116.2, "PM2.5", 118, 3, "Yes", ""),
    _ln("11/26/26", "F", "Boise", "ID", 43.6, -116.2, "O3", 30, 1, "", "", "N"),                         # a lesser pollutant the same day: the worse one wins
    _ln("11/27/26", "F", "Boise", "ID", 43.6, -116.2, "PM2.5", None, "Moderate"),                         # category only, empty AQI
    _ln("11/25/26", "F", "Coeur d'Alene", "ID", 47.68, -116.78, "PM2.5", 38, "Good", "No", "Fog and rain.", issue="11/24/26"),
    _ln("11/25/26", "F", "Spokane", "WA", 47.66, -117.4, "PM2.5", 80, 2),                                 # not Idaho: ignored
    "garbage line", ""])
_rows = af.parse(_air)
assert {r["area"] for r in _rows} == {"Boise", "Coeur d'Alene"} and all(r["date"].startswith("2026-11-") for r in _rows), _rows
_o = af.build_regions(_rows)
_b = _o["southwest"]["airForecast"]["areas"][0]
assert _b["name"] == "Boise" and _b["issued"] == "2026-11-25" and _o["panhandle"]["airForecast"]["areas"][0]["issued"] == "2026-11-24" and [d["cat"] for d in _b["days"]] == [2, 3, 2], _b
assert _b["days"][1]["actionDay"] is True and _b["days"][1]["pollutant"] == "PM2.5" and _b["days"][1]["aqi"] == 118 and _b["actionDay"] is True, _b
assert _b["days"][2]["aqi"] is None and _b["days"][2]["category"] == "Moderate", "category-only forecast keeps its category"
assert _b["discussion"].startswith("Stagnant air") and _o["panhandle"]["airForecast"]["areas"][0]["days"][0]["cat"] == 1, _o
assert _o["panhandle"]["airForecast"]["areas"][0]["actionDay"] is False, '"No" is not an Action Day'
for bad in ("", "just some text\nwith no pipes", _ln("11/25/26", "O", "Boise", "ID", 43.6, -116.2, "PM2.5", 52, 2)):
    try:
        af.parse(bad); raise SystemExit("an unrecognised or Idaho-forecast-free file should raise")
    except RuntimeError:
        pass
af.http_text = lambda url, timeout=60: _air
_pa = c.run_part("airnow_forecast", af.fetch)
assert _pa["ok"] and "southwest" in _pa["regions"], _pa
_nw = {"source": "nws", "ok": True, "fetchedAt": _n.isoformat(), "error": None, "forecast": {}, "alerts": {}}
_bb = bc.build({"nws": _nw, "airnow_forecast": _pa}, dt.datetime(2026, 11, 26, 19, 0, tzinfo=dt.timezone.utc))
assert [d["date"] for d in _bb["regions"]["southwest"]["airForecast"]["areas"][0]["days"]] == ["2026-11-26", "2026-11-27"], "today's and later days remain"
assert _bb["sources"]["airnow_forecast"]["ok"] and _bb["regions"]["southwest"]["level"] == bc.build({"nws": _nw}, _n)["regions"]["southwest"]["level"], "Action Day never changes the level"
af.http_text = lambda url, timeout=60: (_ for _ in ()).throw(OSError("down"))
_pf = c.run_part("airnow_forecast", af.fetch)
assert not _pf["ok"] and "southwest" in _pf["regions"], "a failed fetch keeps the last forecast"
assert bc.build({}, _n)["regions"]["southwest"]["airForecast"] is None, "the build works with the part missing"
print("air forecast tests ok")


# hourly snow: a one-hour jump of 10 in (a sensor glitch, like Bogus Basin Nov 27: 21 -> 12) flags the 24 h change instead of trusting it; a gap in the series gives no change
import fetch_snotel as _sn
_base = dt.datetime(2026, 11, 27, 0, 0)
_h = lambda vals, skip=(): {"data": [{"stationElement": {"elementCode": "SNWD"}, "values": [{"date": (_base + dt.timedelta(hours=i)).strftime("%Y-%m-%d %H:%M"), "value": v} for i, v in enumerate(vals) if i not in skip]}]}
_hs = _sn.snow_hourly(_h([21] * 20 + [20, 12, 12, 11]))
assert _hs["depth"] == 11 and _hs["change"] == -10 and _hs["suspect"], _hs
_hs = _sn.snow_hourly(_h([14] * 12 + [15, 16, 17, 18] * 3 + [18] * 3, skip=()))
assert _hs["change"] is not None and not _hs["suspect"], _hs
_hs = _sn.snow_hourly(_h([14] * 30, skip=range(0, 8)))   # the hour a day earlier is missing
assert _hs["change"] is None, _hs
assert _sn.snow_hourly({}) is None
print("hourly snow tests ok")
