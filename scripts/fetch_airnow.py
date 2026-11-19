#!/usr/bin/env python3
"""Current air quality (highest pollutant AQI nearby) for each point in data/region_points.json -> data/parts/airnow.json.
Source: AirNow API (needs AIRNOW_API_KEY). Data is provisional. A point with no monitor within AirNow's search radius shows 'no nearby air monitor'."""
from ic_common import *

URL = "https://www.airnowapi.org/aq/observation/current/ziplatlong/"
TZ = {"PST": "-08:00", "PDT": "-07:00", "MST": "-07:00", "MDT": "-06:00"}


def observed(row):
    off = TZ.get(row.get("localTimeZone"))
    if not off or not row.get("dateObserved"):
        return None
    return f"{row['dateObserved'].strip()}T{row.get('hourObserved', '00:00')}:00{off}"


def fetch():
    key = os.environ.get("AIRNOW_API_KEY")
    if not key:
        raise RuntimeError("AIRNOW_API_KEY not set")
    out, errors, total = {}, 0, 0
    for pt in load_json("data/region_points.json")["points"]:
        total += 1
        rows = http_json(q(URL, latitude=pt["lat"], longitude=pt["lon"], format="application/json", API_KEY=key))
        # AirNow answers with an error object (not a list) for some requests, e.g. a bad key or a rate limit. Treat that as
        # "no reading" for this point, say why, and keep going. (Iterating the error dict used to crash the whole fetch.)
        if not isinstance(rows, list):
            print(f"AirNow: {pt['name']}: unexpected response, treated as no reading: {str(rows)[:160]}")
            errors += 1
            rows = []
        rows = [r for r in rows if isinstance(r, dict) and r.get("nowcastAQI") is not None and r["nowcastAQI"] >= 0]
        if rows:
            top = max(rows, key=lambda r: r["nowcastAQI"])
            entry = {"id": pt["id"], "name": pt["name"], "aqi": reading(top["nowcastAQI"], "AQI", observed(top), "AirNow", True),
                     "category": top.get("aqiCategoryName"), "pollutant": top.get("parameterName"), "siteName": top.get("siteName")}
        else:
            entry = {"id": pt["id"], "name": pt["name"], "aqi": reading(None, "AQI", None, "AirNow", True), "category": None,
                     "pollutant": None, "siteName": None}
        out.setdefault(slug(pt["region"]), {"air": {"points": [], "note": None}})["air"]["points"].append(entry)
        time.sleep(1)
    if total and errors == total:  # bad key or rate limit on every point: keep last-known data, do not say "no monitor"
        raise RuntimeError("AirNow returned an error for every point")
    for rid, v in out.items():
        pts = v["air"]["points"]
        if all(p["aqi"]["value"] is None for p in pts):
            v["air"]["note"] = "No nearby air monitor"
    return out


if __name__ == "__main__":
    run_part("airnow", fetch)
