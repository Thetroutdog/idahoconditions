#!/usr/bin/env python3
"""Checks region_points.json: (1) IDFG region of each point (data/idfg_regions.geojson), (2) NWS grid/zone ids per point,
(3) distance from each chosen SNOTEL to its ski area. Writes docs/probes/<latest>/points_check.md.
Run locally: set IC_USER_AGENT first (NWS requires a contact in the User-Agent). Standard library only."""
import json, os, glob, math, time, urllib.request, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from region_tools import find_region  # noqa: E402

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
UA = os.environ.get("IC_USER_AGENT", "idahoconditions-probe/0.1")


def km(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def nws(lat, lon):
    req = urllib.request.Request(f"https://api.weather.gov/points/{lat},{lon}", headers={"User-Agent": UA, "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        p = json.loads(r.read())["properties"]
    z = lambda u: (u or "").rsplit("/", 1)[-1]
    return {"office": p.get("gridId"), "grid": f"{p.get('gridX')},{p.get('gridY')}", "forecastZone": z(p.get("forecastZone")),
            "countyZone": z(p.get("county")), "fireZone": z(p.get("fireWeatherZone")), "tz": p.get("timeZone")}


def main():
    cfg = json.load(open(os.path.join(ROOT, "data", "region_points.json")))
    feats = json.load(open(os.path.join(ROOT, "data", "idfg_regions.geojson")))["features"]
    out = ["# Points check\n", "## Points (IDFG region match, NWS zones)\n", "| point | expected | IDFG says | office | grid | forecast zone | county zone | fire zone | tz |", "|---|---|---|---|---|---|---|---|---|"]
    for pt in cfg["points"]:
        reg = (find_region(feats, pt["lon"], pt["lat"]) or "outside").replace(" Region", "")
        try:
            n = nws(pt["lat"], pt["lon"])
        except Exception as e:
            n = {k: f"ERR {e}" if k == "office" else "" for k in ("office", "grid", "forecastZone", "countyZone", "fireZone", "tz")}
        flag = "" if reg == pt["region"] else " **MISMATCH**"
        out.append(f"| {pt['name']} | {pt['region']} | {reg}{flag} | {n['office']} | {n['grid']} | {n['forecastZone']} | {n['countyZone']} | {n['fireZone']} | {n['tz']} |")
        print(pt["name"], reg, n["forecastZone"])
        time.sleep(1)
    sel = json.load(open(os.path.join(ROOT, "data", "selected_stations.json")))
    ski = {s["area"]: s for s in cfg["ski_areas_approx"]}
    out += ["\n## Snow station distance to ski area (ski coordinates are approximate)\n", "| ski area | SNOTEL | km | miles |", "|---|---|---|---|"]
    for s in sel["snow"]:
        a, sn = ski.get(s["area"]), s.get("snotel")
        if not a or not sn:
            out.append(f"| {s['area']} | {s['snotel_text']} | n/a | n/a |")
            continue
        k = km(a["lat"], a["lon"], sn["lat"], sn["lon"])
        out.append(f"| {s['area']} | {sn['name']} | {k:.0f} | {k*0.621:.0f} |")
    d = sorted(glob.glob(os.path.join(ROOT, "docs", "probes", "2*")))[-1]
    p = os.path.join(d, "points_check.md")
    open(p, "w").write("\n".join(out) + "\n")
    print("wrote", p)


if __name__ == "__main__":
    main()
