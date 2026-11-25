#!/usr/bin/env python3
"""Fetch NWS forecasts (per region point) and active alerts (statewide, mapped to regions by zone) -> data/parts/nws.json.
Needs data/region_points.json and data/zone_region.json. Set IC_USER_AGENT (NWS requires a contact). Standard library only.
On failure the previous part is kept and marked ok=false so the build shows last-known data as stale."""
import json, os, sys, time, urllib.request, urllib.parse, datetime as dt

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PART = os.path.join(ROOT, "data", "parts", "nws.json")
UA = os.environ.get("IC_USER_AGENT") or "idahoconditions.com (contact@idahoconditions.com)"  # "or": an unset Actions secret arrives as an empty string
MIN_SHARE_SHOW = 0.15   # alert is listed on a region page if the zone has at least this share in the region
MIN_SHARE_LEVEL = 0.30  # ...and counts toward the region's color only at this share or more (or if it is the primary region)


def slug(name):
    return name.lower().replace(" region", "").replace(" ", "-")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def alert_level(props):
    ev, sev = props.get("event") or "", props.get("severity") or ""
    if ev.endswith("Warning") or sev in ("Severe", "Extreme"):
        return "red"
    if ev.endswith(("Advisory", "Watch")) or sev == "Moderate":
        return "amber"
    return None


def afd_url(office):
    """Forecaster discussion (Area Forecast Discussion) page for a forecast office. We link it, not quote it: it is long and written for experts."""
    return f"https://forecast.weather.gov/product.php?site={office}&issuedby={office}&product=AFD" if office else None


def daily(periods):
    """Pair NWS 12-hour periods into calendar days: high (daytime), low (night), short phrase, rain chance, wind, full text. The first day may be tonight only."""
    days, by = [], {}
    for p in periods:
        key = (p.get("startTime") or "")[:10]
        if not key:
            continue
        d = by.get(key)
        if d is None:
            d = by[key] = {"date": key, "name": None, "hi": None, "lo": None, "short": None, "precipChance": None, "wind": None, "detail": None, "nightDetail": None}
            days.append(d)
        pc = (p.get("probabilityOfPrecipitation") or {}).get("value")
        if pc is not None:
            d["precipChance"] = max(pc, d["precipChance"] or 0)
        if p.get("isDaytime"):
            d.update({"name": p["name"], "hi": p["temperature"], "short": p["shortForecast"], "wind": p.get("windSpeed"), "detail": p.get("detailedForecast")})
        else:
            d["lo"] = p["temperature"]
            d["nightDetail"] = p.get("detailedForecast")
            if d["short"] is None:  # a night-only first day
                d.update({"name": p["name"], "short": p["shortForecast"], "wind": p.get("windSpeed"), "detail": p.get("detailedForecast")})
    return days[:7]


def forecasts(points):
    out = {}
    for pt in points:
        try:
            meta = get(f"https://api.weather.gov/points/{pt['lat']},{pt['lon']}")["properties"]
            fc = get(meta["forecast"])["properties"]
            raw = fc["periods"]
            periods = [{"name": p["name"], "temp": p["temperature"], "unit": p["temperatureUnit"], "short": p["shortForecast"],
                        "precipChance": (p.get("probabilityOfPrecipitation") or {}).get("value")} for p in raw[:4]]
            out.setdefault(slug(pt["region"]), {"points": [], "updated": fc.get("updateTime") or fc.get("generatedAt")})
            out[slug(pt["region"])]["points"].append({"id": pt["id"], "name": pt["name"], "office": meta.get("gridId"), "periods": periods,
                                                       "days": daily(raw), "discussion": afd_url(meta.get("gridId"))})
        except Exception as e:
            print("forecast failed:", pt["name"], e)
        time.sleep(0.7)
    return out


_zone_pts = {}


def _inside(x, y, ring):
    ok = False
    for i in range(len(ring) - 1):
        (x1, y1), (x2, y2) = ring[i][:2], ring[i + 1][:2]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            ok = not ok
    return ok


def zone_point(zurl):
    """A lat/lon inside an NWS zone (bbox center if it falls inside the polygon, else a vertex). None if the zone can't be read."""
    if zurl in _zone_pts:
        return _zone_pts[zurl]
    pt = None
    try:
        g = (get(zurl).get("geometry") or {})
        polys = [g["coordinates"]] if g.get("type") == "Polygon" else g.get("coordinates", [])
        ring = max((poly[0] for poly in polys), key=len)
        xs, ys = [c[0] for c in ring], [c[1] for c in ring]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        pt = (cy, cx) if _inside(cx, cy, ring) else (ring[0][1], ring[0][0])
        time.sleep(0.3)
    except Exception as e:
        print("zone point failed:", zurl.rsplit("/", 1)[-1], e)
    _zone_pts[zurl] = pt
    return pt


ALERTS_PAGE = "https://alerts.weather.gov/?area=ID"


def alert_url(p):
    """A page that is about alerts, never a point forecast. NWS's own `web` field when it is a real page (not just the site root),
    else the public Idaho alerts page. (A MapClick forecast page often shows no Special Weather Statement and never shows an expired one.)"""
    web = (p.get("web") or "").strip()
    if web.startswith("http") and "MapClick" not in web and urllib.parse.urlparse(web).path.strip("/"):
        return web
    return ALERTS_PAGE


def clip(text, n):
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def alerts(zone_map):
    feats = get("https://api.weather.gov/alerts/active?area=ID")["features"]
    out = {}
    unmapped = set()
    for f in feats:
        p = f["properties"]
        if p.get("status") != "Actual" or p.get("messageType") == "Cancel":
            continue
        end_s = p.get("ends") or p.get("expires")
        try:
            if end_s and dt.datetime.fromisoformat(end_s) < dt.datetime.now(dt.timezone.utc):
                continue  # already over: a short statement can expire between the NWS list and this build
        except ValueError:
            pass
        if not p.get("id") or not p.get("event"):  # a malformed alert is skipped, not allowed to fail every alert
            print("alert skipped (no id or event):", str(p.get("headline"))[:80])
            continue
        regions = {}  # region slug -> best share
        for zurl in p.get("affectedZones", []):
            z = zone_map.get(zurl.rsplit("/", 1)[-1])
            if not z:
                unmapped.add(zurl.rsplit("/", 1)[-1])
                continue
            for rname, share in z["shares"].items():
                if rname != "outside" and share >= MIN_SHARE_SHOW:
                    regions[slug(rname)] = max(regions.get(slug(rname), 0), share)
            prim = slug(z["primary"])  # a zone's primary region always counts toward the color
            if prim != "outside":
                regions[prim] = 1.0
        item = {"id": p["id"], "event": p["event"], "severity": p.get("severity"), "level": alert_level(p), "onset": p.get("onset") or p.get("effective"),
                "ends": p.get("ends") or p.get("expires"), "headline": p.get("headline"), "gist": clip((p.get("parameters") or {}).get("NWSheadline", [None])[0], 160) or None,
                "summary": clip(p.get("description"), 320) or None, "url": alert_url(p), "_zones": len(p.get("affectedZones", []))}
        if not regions:
            # No Idaho region claims this alert (its zones are unmapped or outside the IDFG regions): keep it for the statewide card
            # instead of dropping it silently. Stored under "_unplaced"; build_conditions turns it into conditions["unplaced"]["weather"].
            out.setdefault("_unplaced", []).append({**item, "countsTowardLevel": False, "event": item["event"]})
        for rid, share in regions.items():
            out.setdefault(rid, []).append({**item, "countsTowardLevel": share >= MIN_SHARE_LEVEL})
    for rid, lst in out.items():  # the same event from two offices or several zone groups shows once: keep the one covering most zones
        best = {}
        for a in lst:
            key = (a["event"], (a.get("ends") or "")[:13])
            if key not in best or a.get("_zones", 0) > best[key].get("_zones", 0):
                best[key] = a
        for a in lst:  # if any copy counts toward the region color, the kept one does
            k = best[(a["event"], (a.get("ends") or "")[:13])]
            k["countsTowardLevel"] = k.get("countsTowardLevel", True) or a.get("countsTowardLevel", True)
        out[rid] = [a for a in lst if best[(a["event"], (a.get("ends") or "")[:13])] is a]
        for a in out[rid]:
            a.pop("_zones", None)
    if unmapped:
        print("alert zones not in zone_region.json:", sorted(unmapped))
    return out


WINTER = {"ski", "nordic", "backcountry", "snowmobile"}  # activities whose conditions depend on elevation: they need a verified point (see usable())
BRIEF_CONFIG = os.path.join(ROOT, "scripts", "brief", "brief_config.json")
BRIEF_DAYS = 7  # the Thursday Brief reaches Saturday and Sunday from a Wednesday or Thursday run


def brief_spots():
    """Spot ids the Thursday Brief reads (its winter ski-area lines), from scripts/brief/brief_config.json. Their grids keep a full week of days;
    every other grid keeps two (the site rows only use today and tomorrow), so the data file stays small. Empty when the config is unreadable."""
    try:
        cfg = json.load(open(BRIEF_CONFIG))
        return {pl["spot"] for se in cfg["seasons"].values() for pl in se.get("places", []) if pl.get("spot")}
    except Exception:
        return set()


def spot_days(raw, full):
    """Two full days for the site rows; for a Brief grid a week, with the long text kept for the first four days (the Brief reads forecast snow before the
    weekend from it on a Tuesday to Thursday run) and dropped after that (date, name, hi, lo, short, rain chance, wind)."""
    days = daily(raw)
    if not full:
        return days[:2]
    return days[:4] + [{k: v for k, v in d.items() if k not in ("detail", "nightDetail")} for d in days[4:BRIEF_DAYS]]


SPOT_MAX_AGE_MIN = 120  # a cell fetched less than this long ago is reused, which keeps a run to a few requests; NWS updates grid forecasts about hourly


def spot_forecasts():
    """Forecast at each winter spot's own coordinates (data/spot_coords.json from scripts/geocode_spots.py; manual file wins).
    NWS forecasts are per 2.5 km grid cell and follow the terrain, so a ski area gets its mountain forecast, not the valley town's.
    Spots in the same cell share one request; the lat/lon -> cell lookup is cached in data/grid_cache.json (cells never move)."""
    cpath = os.path.join(ROOT, "data", "spot_coords.json")
    if not os.path.exists(cpath):
        print("spot forecasts skipped: run scripts/geocode_spots.py first (data/spot_coords.json not found)")
        return {"bySpot": {}, "grids": {}}
    coords = json.load(open(cpath)).get("spots", {})
    mpath = os.path.join(ROOT, "data", "spot_coords_manual.json")
    coords.update(json.load(open(mpath)) if os.path.exists(mpath) else {})
    spots = []
    for f in ("spots.json", "spots_extra.json"):
        spots += json.load(open(os.path.join(ROOT, "data", f)))["spots"]
    def usable(sp):
        """Winter spots (ski, Nordic, backcountry, snowmobile) need a verified point or the forecast would be the valley's: manual coordinates, or a
        name match (precision "place") for a ski or Nordic area. Riding areas and backcountry zones have no single point (geocoders return a school
        or a skate park), so those need a manual coordinate. Every other activity takes any coordinate, even a town-level one: the forecast for
        Kuna beats the one for Boise."""
        c = coords.get(sp["id"]) or {}
        if c.get("lat") is None:
            return False
        if sp["activity"] in WINTER:
            return c.get("precision", "manual") == "manual" or (c.get("precision") == "place" and sp["activity"] in ("ski", "nordic"))
        return True
    spots = [sp for sp in spots if usable(sp)]
    prev = {}
    try:
        prev = json.load(open(PART)).get("spotForecast", {}).get("grids", {})
    except Exception:
        pass
    now_dt = dt.datetime.now(dt.timezone.utc)
    brief = brief_spots()
    gpath = os.path.join(ROOT, "data", "grid_cache.json")
    gcache = json.load(open(gpath)) if os.path.exists(gpath) else {}
    by_spot, grids, names = {}, {}, {}
    for sp in spots:
        c = coords[sp["id"]]
        key = f"{c['lat']:.3f},{c['lon']:.3f}"
        try:
            if key not in gcache:
                m = get(f"https://api.weather.gov/points/{c['lat']:.4f},{c['lon']:.4f}")["properties"]
                gcache[key] = {"office": m["gridId"], "x": m["gridX"], "y": m["gridY"], "forecast": m["forecast"]}
                time.sleep(0.7)
            g = gcache[key]
            gk = f"{g['office']}/{g['x']},{g['y']}"
            full = sp["id"] in brief
            enough = lambda x: not full or len(x.get("days", [])) >= BRIEF_DAYS  # a Brief spot needs the week, so a short cached or shared cell is refetched
            if gk not in grids and gk in prev and prev[gk].get("fetchedAt") and enough(prev[gk]) and (now_dt - dt.datetime.fromisoformat(prev[gk]["fetchedAt"])).total_seconds() < SPOT_MAX_AGE_MIN * 60:
                grids[gk] = prev[gk]
            if gk in grids and not enough(grids[gk]):
                del grids[gk]
            if gk not in grids:
                fc = get(g["forecast"])["properties"]
                el = (fc.get("elevation") or {}).get("value")  # meters
                raw = fc["periods"]
                grids[gk] = {"office": g["office"], "elevationFt": round(el * 3.28084 / 10) * 10 if el is not None else None, "updated": fc.get("updateTime") or fc.get("generatedAt"), "fetchedAt": now_dt.isoformat(timespec="seconds"),
                             "periods": [{"name": p["name"], "temp": p["temperature"], "unit": p["temperatureUnit"], "short": p["shortForecast"],
                                          "precipChance": (p.get("probabilityOfPrecipitation") or {}).get("value")} for p in raw[:4]],
                             "days": spot_days(raw, full), "discussion": afd_url(g["office"])}  # site rows use today and tomorrow; the Brief's grids keep a week
                time.sleep(0.5)
            by_spot[sp["id"]] = gk
            names.setdefault(gk, []).append(sp["name"])
        except Exception as e:
            print("spot forecast failed:", sp["id"], e)
    json.dump(gcache, open(gpath, "w"))
    for gk, g in sorted(grids.items()):  # elevation per cell is printed so a wrong coordinate (a valley point for a ski area) stands out
        print(f"  {gk}: {g['elevationFt']} ft  <- {', '.join(names[gk][:3])}{' ...' if len(names[gk]) > 3 else ''}")
    return {"bySpot": by_spot, "grids": grids}


def main():
    points = json.load(open(os.path.join(ROOT, "data", "region_points.json")))["points"]
    zone_map = json.load(open(os.path.join(ROOT, "data", "zone_region.json")))["zones"]
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    try:
        fc, al = forecasts(points), alerts(zone_map)
        part = {"source": "nws", "fetchedAt": now, "ok": True, "error": None, "forecast": fc, "alerts": al}
        try:
            part["spotForecast"] = spot_forecasts()
        except Exception as e:  # mountain forecasts are an add-on: never fail the whole NWS fetch (alerts, town forecasts) because of them
            print("spot forecasts failed:", e)
    except Exception as e:
        part = json.load(open(PART)) if os.path.exists(PART) else {"source": "nws", "forecast": {}, "alerts": {}, "fetchedAt": None}
        part.update({"ok": False, "error": str(e)[:200]})
        print("FAILED, keeping previous data:", e)
    os.makedirs(os.path.dirname(PART), exist_ok=True)
    json.dump(part, open(PART, "w"), indent=1)
    print("wrote", PART, "| regions with alerts:", {k: len(v) for k, v in part["alerts"].items()}, "| forecast regions:", list(part["forecast"]))


if __name__ == "__main__":
    main()
