#!/usr/bin/env python3
"""Find lat/lon for every catalog spot -> data/spot_coords.json. Run locally (needs internet): python3 scripts/geocode_spots.py
Uses OpenStreetMap Nominatim (free; asks for 1 request/second and a contact in the User-Agent: set IC_USER_AGENT).
Each spot tries, in order: "name, town, Idaho" then "name, Idaho" then the town alone. A hit only counts if it is inside Idaho
and inside the spot's own IDFG region; otherwise the next query is tried. precision is "place" (found by name) or "town" (fallback).
Spots that end up as "town", or with no hit, are listed in the report so you can fix them by hand in data/spot_coords_manual.json
(same format; manual entries always win and are never overwritten). Answers are cached in data/geocode_cache.json, so reruns are fast.
Standard library only."""
import json, os, re, sys, time, urllib.parse, urllib.request

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
D = lambda *a: os.path.join(ROOT, "data", *a)
UA = os.environ.get("IC_USER_AGENT") or "idahoconditions.com (contact@idahoconditions.com)"
ID_BBOX = (41.9, 49.1, -117.3, -111.0)  # lat min/max, lon min/max


def load(path, default):
    return json.load(open(path)) if os.path.exists(path) else default


def inside(lon, lat, ring):
    ok = False
    for i in range(len(ring) - 1):
        (x1, y1), (x2, y2) = ring[i][:2], ring[i + 1][:2]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            ok = not ok
    return ok


def in_geom(lon, lat, geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return any(inside(lon, lat, p[0]) and not any(inside(lon, lat, h) for h in p[1:]) for p in polys)


def region_polys():
    out = {}
    for f in json.load(open(D("idfg_regions.geojson")))["features"]:
        out[f["properties"]["NAME"].lower().replace(" region", "").replace(" ", "-")] = f["geometry"]
    return out


_last = [0.0]


def nominatim(q, cache):
    if q in cache:
        return cache[q]
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 3, "countrycodes": "us"})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
            res = [{"lat": float(x["lat"]), "lon": float(x["lon"]), "name": x.get("display_name", "")[:120]} for x in json.loads(r.read())]
    except Exception as e:
        print("  request failed:", q, e)
        return []  # not cached, so a rerun retries it
    _last[0] = time.time()
    cache[q] = res
    return res


def clean(name):
    return re.sub(r"\s*\(.*?\)", "", name).strip()


def parts(town):
    return [p.strip() for p in re.split(r"\s*/\s*|,", town or "") if p.strip()]


def queries(sp):
    n, towns = clean(sp["name"]), parts(sp.get("town"))
    qs = []
    if towns:
        qs.append(("place", f"{n}, {towns[0]}, Idaho"))
    qs.append(("place", f"{n}, Idaho"))
    qs += [("town", f"{t}, Idaho") for t in towns]
    return qs


def locate(sp, polys, cache):
    geom = polys.get(sp["region"])
    for prec, q in queries(sp):
        for h in nominatim(q, cache):
            if not (ID_BBOX[0] <= h["lat"] <= ID_BBOX[1] and ID_BBOX[2] <= h["lon"] <= ID_BBOX[3]):
                continue
            ok = bool(geom) and in_geom(h["lon"], h["lat"], geom)
            if ok or prec == "town":  # a town just outside its region's edge still beats no point at all; regionOk records it
                return {"lat": round(h["lat"], 5), "lon": round(h["lon"], 5), "precision": prec, "regionOk": ok, "query": q, "matched": h["name"]}
    return None


def main():
    spots = load(D("spots.json"), {"spots": []})["spots"] + load(D("spots_extra.json"), {"spots": []})["spots"]
    manual = load(D("spot_coords_manual.json"), {})
    cache = load(D("geocode_cache.json"), {})
    out = load(D("spot_coords.json"), {"spots": {}})["spots"]
    polys = region_polys()
    todo = [s for s in spots if s["id"] not in manual and s["id"] not in out]
    print(f"{len(spots)} spots, {len(manual)} manual, {len(out)} already done, {len(todo)} to look up (about {len(todo) * 2 // 60 + 1} min)")
    for i, sp in enumerate(todo, 1):
        res = locate(sp, polys, cache)
        out[sp["id"]] = res or {"lat": None, "lon": None, "precision": "none"}
        print(f"[{i}/{len(todo)}] {sp['id']}: {res['precision'] + ' ' + str(res['lat']) + ',' + str(res['lon']) if res else 'NO HIT'}", flush=True)
        if i % 20 == 0:
            save(out, cache)
    for k, v in manual.items():
        out[k] = {**v, "precision": v.get("precision", "manual"), "regionOk": True}
    save(out, cache)
    byid = {s["id"]: s for s in spots}
    weak = [(k, v) for k, v in out.items() if k in byid and (v["precision"] in ("town", "none") or v.get("regionOk") is False)]
    print(f"\nDone. place-level: {sum(1 for v in out.values() if v['precision'] == 'place')}, town-level: {sum(1 for v in out.values() if v['precision'] == 'town')}, none: {sum(1 for v in out.values() if v['precision'] == 'none')}")
    print(f"{len(weak)} worth a look (town-level, no hit, or outside its region) -> data/spot_coords_review.txt")
    with open(D("spot_coords_review.txt"), "w") as f:
        for k, v in sorted(weak, key=lambda kv: (byid[kv[0]]["activity"], kv[0])):
            f.write(f"{k}\t{byid[k]['name']}\t{byid[k].get('town')}\t{v['precision']}\tregionOk={v.get('regionOk')}\t{v.get('lat')},{v.get('lon')}\t{v.get('matched', '')}\n")


def save(out, cache):
    json.dump({"note": "Generated by scripts/geocode_spots.py. Edit data/spot_coords_manual.json, not this file.", "spots": out}, open(D("spot_coords.json"), "w"), indent=0)
    json.dump(cache, open(D("geocode_cache.json"), "w"))


if __name__ == "__main__":
    main()
