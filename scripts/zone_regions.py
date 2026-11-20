#!/usr/bin/env python3
"""Assign every NWS public forecast zone in Idaho to IDFG region(s), writing data/zone_region.json.
Method: sample a 7x7 grid over each zone's bounding box, keep samples inside the zone, count which IDFG region each lands in.
A zone gets `primary` (largest share) and `regions` (every region with at least 15% of samples) so alerts on border zones
can appear on more than one region page. Run locally with IC_USER_AGENT set. Standard library only.
    python3 scripts/zone_regions.py            # fetch zones + assign
    python3 scripts/zone_regions.py selftest   # offline check"""
import json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from region_tools import geometry_contains, region_name  # noqa: E402

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
UA = os.environ.get("IC_USER_AGENT", "idahoconditions-probe/0.1")
N = 7
MIN_SHARE = 0.15


def coords(geom):
    if geom["type"] == "Polygon":
        yield from (pt for ring in geom["coordinates"] for pt in ring)
    else:
        yield from (pt for poly in geom["coordinates"] for ring in poly for pt in ring)


def bbox(geom):
    xs, ys = zip(*[(p[0], p[1]) for p in coords(geom)])
    return min(xs), min(ys), max(xs), max(ys)


def shares(zone_geom, regions):
    x0, y0, x1, y1 = bbox(zone_geom)
    hits = {}
    total = 0
    for i in range(N):
        for j in range(N):
            x = x0 + (x1 - x0) * (i + 0.5) / N
            y = y0 + (y1 - y0) * (j + 0.5) / N
            if not geometry_contains(zone_geom, x, y):
                continue
            total += 1
            for name, g, bb in regions:
                if bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] and geometry_contains(g, x, y):
                    hits[name] = hits.get(name, 0) + 1
                    break
            else:
                hits["outside"] = hits.get("outside", 0) + 1
    return {k: v / total for k, v in hits.items()} if total else {}


def main():
    feats = json.load(open(os.path.join(ROOT, "data", "idfg_regions.geojson")))["features"]
    regions = [(region_name(f["properties"]).replace(" Region", ""), f["geometry"], bbox(f["geometry"])) for f in feats]
    out = {}
    zones = []
    for ztype in ("forecast", "fire", "county"):
        url = f"https://api.weather.gov/zones?type={ztype}&area=ID&include_geometry=true"
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/geo+json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            got = json.loads(r.read())["features"]
        print(ztype, len(got), "zones")
        for z in got:
            z["_type"] = ztype
        zones += got
    for z in zones:
        p, g = z["properties"], z.get("geometry")
        if not g:  # the zone list omits geometry; the single-zone endpoint includes it
            try:
                dreq = urllib.request.Request(f"https://api.weather.gov/zones/{z['_type']}/{p['id']}", headers={"User-Agent": UA, "Accept": "application/geo+json"})
                with urllib.request.urlopen(dreq, timeout=60) as dr:
                    dz = json.loads(dr.read())
                g = dz.get("geometry")
                p = {**p, **dz.get("properties", {})}
            except Exception as e:
                print("fetch failed:", p.get("id"), e)
            time.sleep(0.5)
        if not g:
            print("no geometry:", p.get("id"))
            continue
        s = shares(g, regions)
        if not s:
            print("no samples inside:", p.get("id"), p.get("name"))
            continue
        regs = sorted([k for k, v in s.items() if v >= MIN_SHARE and k != "outside"], key=lambda k: -s[k])
        primary = max(s, key=s.get)
        out[p["id"]] = {"type": z["_type"], "name": p.get("name"), "office": (p.get("cwa") or [None])[0], "primary": primary,
                        "regions": regs, "shares": {k: round(v, 2) for k, v in s.items()}}
        print(p["id"], p.get("name"), "->", primary, regs)
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    json.dump({"generated": time.strftime("%Y-%m-%d"), "zones": out}, open(os.path.join(ROOT, "data", "zone_region.json"), "w"), indent=1)
    print("wrote data/zone_region.json")


def selftest():
    sq = lambda a, b, c, d: {"type": "Polygon", "coordinates": [[[a, b], [c, b], [c, d], [a, d], [a, b]]]}
    regs = [("A", sq(0, 0, 5, 10), (0, 0, 5, 10)), ("B", sq(5, 0, 10, 10), (5, 0, 10, 10))]
    s = shares(sq(2, 2, 8, 8), regs)
    assert abs(s["A"] - s["B"]) < 0.2, s
    assert shares(sq(1, 1, 3, 3), regs) == {"A": 1.0}
    print("selftest ok")


if __name__ == "__main__":
    selftest() if len(sys.argv) > 1 and sys.argv[1] == "selftest" else main()
