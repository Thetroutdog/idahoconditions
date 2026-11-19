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
            {"attributes": {**base, "IncidentName": "TEST FIRE", "IncidentTypeCategory": "WF", "IncidentSize": 120}, "geometry": {"x": -116.1, "y": 44.9}},
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
assert snow and snow[0]["depth"]["value"] == 9 and snow[0]["depthChange24h"]["value"] == 3 and snow[0]["pctOfMedian"]["value"] == 125, snow[0]
riv = [e for r in parts["usgs"]["regions"].values() for e in r["rivers"]]
assert len(riv) == len(sel["rivers"]) and riv[0]["flow"]["value"] == 255.0 and riv[0]["use"], riv[0]
air = parts["airnow"]["regions"]
assert air["southwest"]["air"]["points"][0]["aqi"]["value"] == 118 and air["upper-snake"]["air"]["points"][-1]["aqi"]["value"] is None
fire = parts["nifc"]["regions"]["southwest"]["fire"]
assert [f["name"] for f in fire["wildfires"]] == ["Test Fire"] and [f["name"] for f in fire["prescribed"]] == ["Burn One"], fire
assert "montana" not in json.dumps(parts["nifc"]).lower()
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
assert "MapClick.php?lat=" in _nws.alert_url(["https://api.weather.gov/zones/forecast/TEST"])
print("alert zone point ok")
