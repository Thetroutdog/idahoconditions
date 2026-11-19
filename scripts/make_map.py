#!/usr/bin/env python3
"""Build src/data/idaho-map.json (SVG paths for the 7 regions + label and city positions) from the official IDFG region polygons.
    python3 scripts/make_map.py        needs data/idfg_regions.geojson (scripts/region_tools.py fetch)"""
import json, math, os, sys
sys.setrecursionlimit(10000)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from region_tools import region_name

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
W, PAD, TOL = 440.0, 12.0, 0.55   # drawing width, margin, simplification tolerance (map units)
CITIES = [("Coeur d'Alene", -116.780, 47.677, "start"), ("Lewiston", -117.018, 46.416, "start"), ("Boise", -116.202, 43.615, "start"),
          ("McCall", -116.099, 44.911, "start"), ("Salmon", -113.896, 45.176, "start"), ("Idaho Falls", -112.034, 43.492, "start"),
          ("Pocatello", -112.446, 42.871, "end"), ("Twin Falls", -114.461, 42.563, "start"), ("Ketchum", -114.364, 43.680, "start")]


def rings(g):
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    return [r for poly in polys for r in poly[:1]]  # outer rings only


def dp(pts, tol):
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-9
    idx, dmax = 0, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * pts[i][0] - dx * pts[i][1] + x2 * y1 - y2 * x1) / norm
        if d > dmax:
            idx, dmax = i, d
    if dmax > tol:
        return dp(pts[:idx + 1], tol)[:-1] + dp(pts[idx:], tol)
    return [pts[0], pts[-1]]


def centroid(ring):
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0, x1, y1 = *ring[i], *ring[i + 1]
        c = x0 * y1 - x1 * y0
        a += c; cx += (x0 + x1) * c; cy += (y0 + y1) * c
    a *= 0.5
    return (cx / (6 * a), cy / (6 * a)) if a else ring[0]


def main():
    feats = json.load(open(os.path.join(ROOT, "data", "idfg_regions.geojson")))["features"]
    lons = [p[0] for f in feats for r in rings(f["geometry"]) for p in r]
    lats = [p[1] for f in feats for r in rings(f["geometry"]) for p in r]
    lon0, lon1, lat0, lat1 = min(lons), max(lons), min(lats), max(lats)
    k = math.cos(math.radians((lat0 + lat1) / 2))
    s = (W - 2 * PAD) / ((lon1 - lon0) * k)
    proj = lambda lon, lat: (PAD + (lon - lon0) * k * s, PAD + (lat1 - lat) * s)
    H = round(2 * PAD + (lat1 - lat0) * s, 1)
    out = {"width": W, "height": H, "proj": {"lon0": lon0, "lat1": lat1, "k": k, "s": s, "pad": PAD}, "regions": {}, "cities": []}
    for f in feats:
        name = region_name(f["properties"]).replace(" Region", "")
        paths, best = [], None
        for r in rings(f["geometry"]):
            pr = [proj(*p[:2]) for p in r]
            # closed ring: first == last point breaks the line-distance test, so simplify two halves
            mid = len(pr) // 2
            sp = dp(pr[:mid + 1], TOL)[:-1] + dp(pr[mid:], TOL)
            paths.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in sp) + " Z")
            if best is None or len(r) > len(best):
                best = pr
        cx, cy = centroid(best)
        allpts = [proj(*p[:2]) for r in rings(f["geometry"]) for p in r]
        bbox = [round(min(x for x, _ in allpts), 1), round(min(y for _, y in allpts), 1), round(max(x for x, _ in allpts), 1), round(max(y for _, y in allpts), 1)]
        out["regions"][name.lower().replace(" ", "-")] = {"name": name, "d": " ".join(paths), "label": [round(cx, 1), round(cy, 1)], "bbox": bbox}
    for n, lon, lat, anchor in CITIES:
        x, y = proj(lon, lat)
        out["cities"].append({"name": n, "x": round(x, 1), "y": round(y, 1), "anchor": anchor})
    os.makedirs(os.path.join(ROOT, "src", "data"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "src", "data", "idaho-map.json"), "w"))
    kb = os.path.getsize(os.path.join(ROOT, "src", "data", "idaho-map.json")) / 1024
    print(f"wrote src/data/idaho-map.json: {W}x{H}, {kb:.0f} KB, regions: {list(out['regions'])}")


if __name__ == "__main__":
    main()
