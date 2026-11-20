#!/usr/bin/env python3
"""Official Idaho Fish and Game region boundaries: download them and assign stations/gauges to regions.

Run locally (cloud sandbox cannot reach these hosts). Standard library only.
    python3 scripts/region_tools.py fetch      # saves data/idfg_regions.geojson
    python3 scripts/region_tools.py assign     # reads latest docs/probes/<date>/*_digest.json, writes region_assignment.json
    python3 scripts/region_tools.py selftest   # offline check of the point-in-polygon code

Source layer: IDFG "Administrative Regions" (gis.idfg.idaho.gov Boundaries MapServer layer 0). IDFG notes the layer
differs slightly from county lines and from game-management boundaries; use as the authority for region membership.
"""
import json, os, sys, glob, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
GEOJSON = os.path.join(ROOT, "data", "idfg_regions.geojson")
URL = "https://gis.idfg.idaho.gov/server/rest/services/Boundaries/MapServer/0/query"
UA = os.environ.get("IC_USER_AGENT", "idahoconditions-probe/0.1")


# Tried in order; the first that returns features wins. IDFG's own server first, then the hosted copy.
URLS = [
    "https://gis.idfg.idaho.gov/server/rest/services/Boundaries/MapServer/0/query",
    "https://services1.arcgis.com/CD5mKowwN6nIaqd8/ArcGIS/rest/services/IDFG_AdministrativeRegions_HERS/FeatureServer/0/query",
    "https://gisportal-idfg.idaho.gov/hosting/rest/services/WC_Regions/MapServer/0/query",
]


def fetch():
    params = {"where": "1=1", "outFields": "*", "outSR": "4326", "f": "geojson"}
    data = None
    for base in URLS:
        url = base + "?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            if d.get("features"):
                data = d
                print("ok:", base)
                break
            print("no features from", base, str(d)[:200])
        except Exception as e:
            print("failed:", base, e)
    if not data:
        sys.exit("all sources failed; send me the lines above")
    os.makedirs(os.path.dirname(GEOJSON), exist_ok=True)
    with open(GEOJSON, "w") as f:
        json.dump(data, f)
    feats = data["features"]
    print(f"saved {len(feats)} features to {GEOJSON}")
    for ft in feats:
        print(" ", ft.get("properties"))


def ring_contains(ring, x, y):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def polygon_contains(poly, x, y):  # poly = [outer, hole1, ...]
    if not ring_contains(poly[0], x, y):
        return False
    return not any(ring_contains(h, x, y) for h in poly[1:])


def geometry_contains(geom, x, y):
    if geom["type"] == "Polygon":
        return polygon_contains(geom["coordinates"], x, y)
    if geom["type"] == "MultiPolygon":
        return any(polygon_contains(p, x, y) for p in geom["coordinates"])
    return False


def region_name(props):
    for k in ("NAME", "Name", "name", "REGION", "Region", "REGION_NAME"):
        if props.get(k):
            return str(props[k])
    return json.dumps(props)[:60]


def find_region(feats, lon, lat):
    for ft in feats:
        if geometry_contains(ft["geometry"], lon, lat):
            return region_name(ft["properties"])
    return None


def assign():
    data = json.load(open(GEOJSON))
    feats = data["features"]
    dirs = sorted(glob.glob(os.path.join(ROOT, "docs", "probes", "2*")))
    d = dirs[-1]
    out = {"probe_dir": d, "regions": {}}
    for fn in ("snotel_digest.json", "usgs_digest.json", "nifc_digest.json"):
        p = os.path.join(d, fn)
        if not os.path.exists(p):
            continue
        for blk in json.load(open(p)):
            rows = blk["digest"]
            for r in rows:
                lon = r.get("longitude", r.get("lon")); lat = r.get("latitude", r.get("lat"))
                if lon is None or lat is None:
                    continue
                reg = find_region(feats, float(lon), float(lat)) or "outside Idaho regions"
                key = r.get("stationTriplet") or r.get("id") or r.get("IncidentName")
                out["regions"].setdefault(reg, {}).setdefault(blk["label"], []).append(
                    {"id": key, "name": r.get("name"), "lat": lat, "lon": lon})
    with open(os.path.join(d, "region_assignment.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("wrote", os.path.join(d, "region_assignment.json"))
    for reg, blocks in out["regions"].items():
        print(reg, {b: len(v) for b, v in blocks.items()})


def selftest():
    sq = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]]}
    assert geometry_contains(sq, 2, 2) and not geometry_contains(sq, 5, 5) and not geometry_contains(sq, 11, 5)
    mp = {"type": "MultiPolygon", "coordinates": [sq["coordinates"], [[[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]]]]}
    assert geometry_contains(mp, 25, 25) and not geometry_contains(mp, 15, 15)
    print("selftest ok")


if __name__ == "__main__":
    {"fetch": fetch, "assign": assign, "selftest": selftest}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
