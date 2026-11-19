#!/usr/bin/env python3
"""Idaho 511 road data -> data/parts/idaho511.json (per region: winter road conditions, closures/incidents, mountain passes).
Needs IDAHO511_API_KEY (set in ~/API/idahoconditions.env). The API allows 10 calls per 60 s; this makes 4, 7 s apart.

The exact field names of Idaho's responses are not confirmed until the first real run (docs/data-sources.md), so every
normalizer reads several likely names and keeps a trimmed copy of the original scalar fields under "fields". Run
`python3 scripts/probe_sources.py idaho511` first to save raw samples, and check the output before turning roads on in
build_conditions.py (ROADS_LIVE).
Required: winterroads and event (a failure keeps the previous data and marks it stale). Best effort: mountainpasses, alerts.
The key is never printed."""
from ic_common import *
import datetime as _dt
import re

BASE = "https://511.idaho.gov/api/v2/get/"
PAUSE = 7  # seconds between calls: 10 per 60 s limit
CLEAR_WORDS = ("dry", "clear", "normal", "good", "wet", "no report", "no condition", "unknown", "")


def pick(d, *keys):
    """First present, non-empty value among the key names (the API's spelling varies between 511 systems)."""
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    # Fallback: compare names ignoring case, spaces, hyphens and underscores ("Overall Status" == "OverallStatus").
    flat = {"".join(c for c in str(a).lower() if c.isalnum()): b for a, b in d.items()}
    for k in keys:
        v = flat.get("".join(c for c in k.lower() if c.isalnum()))
        if v not in (None, "", []):
            return v
    return None


def as_list(data):
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def decode_polyline(s):
    """Google encoded polyline (precision 5) -> [(lat, lon), ...]."""
    pts, i, lat, lon = [], 0, 0, 0
    try:
        while i < len(s):
            for which in (0, 1):
                shift = result = 0
                while True:
                    b = ord(s[i]) - 63
                    i += 1
                    result |= (b & 0x1F) << shift
                    shift += 5
                    if b < 0x20:
                        break
                d = ~(result >> 1) if result & 1 else result >> 1
                if which == 0:
                    lat += d
                else:
                    lon += d
            pts.append((lat / 1e5, lon / 1e5))
    except (IndexError, TypeError):
        pass
    return pts


def location(d):
    """(lat, lon) of an item: its own coordinates, else the middle of its polyline."""
    try:
        la, lo = pick(d, "Latitude", "latitude", "Lat"), pick(d, "Longitude", "longitude", "Lon", "Lng")
        if la is not None and lo is not None and float(la) != 0 and float(lo) != 0:
            return float(la), float(lo)
    except (TypeError, ValueError):
        pass
    pl = pick(d, "EncodedPolyline", "Polyline")
    pts = decode_polyline(pl) if isinstance(pl, str) else []
    return pts[len(pts) // 2] if pts else (None, None)


def iso(v):
    """Epoch seconds, epoch milliseconds or an ISO string -> ISO UTC string (None when unreadable)."""
    try:
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
            n = float(v)
            n = n / 1000 if n > 1e11 else n
            return _dt.datetime.fromtimestamp(n, _dt.timezone.utc).isoformat(timespec="seconds")
        if isinstance(v, str) and v:
            return _dt.datetime.fromisoformat(v.replace("Z", "+00:00")).isoformat(timespec="seconds")
    except (ValueError, OverflowError, OSError):
        pass
    return None


def scalars(d, n=14):
    """Trimmed copy of the original scalar fields, so nothing is lost if a field name was guessed wrong."""
    out = {}
    for k, v in d.items():
        if isinstance(v, (str, int, float, bool)) and v != "" and k not in ("EncodedPolyline", "Polyline"):
            out[k] = v[:200] if isinstance(v, str) else v
        if len(out) >= n:
            break
    return out


def norm_winter(d):
    la, lo = location(d)
    cond = pick(d, "Primary-Condition", "PrimaryCondition", "Primary-Status", "OverallStatus", "Overall-Status", "Condition", "RoadCondition", "RoadStatus", "Status")
    return {"id": str(pick(d, "Id", "ID") or ""), "name": pick(d, "RoadwayName", "Roadway", "LocationDescription", "AreaName") or "",
            "where": pick(d, "LocationDescription", "AreaName") or "", "condition": cond or "",
            "secondary": pick(d, "Secondary-Conditions", "SecondaryConditions", "SpecialConditions", "Special-Conditions", "Visibility") or "",
            "weather": pick(d, "WeatherConditions", "Weather-Conditions", "Weather") or "",
            "updated": iso(pick(d, "LastUpdated", "Updated")), "lat": la, "lon": lo, "fields": scalars(d)}


HWY = re.compile(r"^(I|US|SH|ID)[- ]?\d", re.I)   # interstates, US and state highways; county/city roads are not
UNPLANNED = ("closed", "crash", "slide", "avalanche", "flood", "washout", "rockfall", "fire", "hazmat", "spill")


def norm_event(d):
    la, lo = location(d)
    nm = pick(d, "RoadwayName", "Roadway") or ""
    et, st = pick(d, "EventType") or "", pick(d, "EventSubType") or ""
    unp = et == "accidentsAndIncidents" or any(w in st.lower() for w in UNPLANNED)
    return {"highway": bool(HWY.match(nm.strip())), "unplanned": unp, "id": str(pick(d, "ID", "Id") or ""), "name": pick(d, "RoadwayName", "Roadway") or "", "direction": pick(d, "DirectionOfTravel") or "",
            "type": pick(d, "EventType") or "", "subType": pick(d, "EventSubType") or "", "fullClosure": bool(d.get("IsFullClosure")) or ("all lanes" in str(d.get("LanesAffected") or "").lower() and any(w in str(d.get("LanesAffected")).lower() for w in ("closed", "blocked"))),
            "severity": pick(d, "Severity") or "", "description": pick(d, "Description", "Comment") or "",
            "updated": iso(pick(d, "LastUpdated", "Reported")), "end": iso(pick(d, "PlannedEndDate")), "lat": la, "lon": lo, "fields": scalars(d)}


def norm_pass(d):
    la, lo = location(d)
    return {"id": str(pick(d, "Id", "ID", "WtaId") or ""), "name": pick(d, "Name", "PassName", "Title", "RoadwayName", "Roadway") or "",
            "where": pick(d, "Direction", "Location", "LocationDescription") or "",
            "condition": pick(d, "RoadCondition", "Condition", "Status", "Primary-Condition") or "",
            "updated": iso(pick(d, "LastUpdated", "Updated")), "lat": la, "lon": lo, "fields": scalars(d)}


def norm_alert(d):
    la, lo = location(d)
    return {"id": str(pick(d, "Id", "ID") or ""), "message": pick(d, "Message", "Description", "Title", "Comment") or "",
            "updated": iso(pick(d, "LastUpdated", "StartTime", "Start")), "lat": la, "lon": lo, "fields": scalars(d)}


def interesting_winter(w):
    """Keep road segments that are not plainly clear: drop dry/clear/normal ones to keep the file small."""
    c = str(w["condition"]).strip().lower()
    if not c:  # unreadable condition: keep it so the debug sample shows what the API really sends
        return True
    return c not in CLEAR_WORDS


def call(endpoint, key):
    return as_list(http_json(q(BASE + endpoint, key=key, format="json")))


def fetch():
    key = os.environ.get("IDAHO511_API_KEY")
    if not key:
        raise RuntimeError("IDAHO511_API_KEY not set")
    where = region_finder()
    regions = {rid: {"roads": {"winter": [], "closures": [], "passes": [], "restrictions": [], "alerts": [], "counts": {}}}
               for rid in ("panhandle", "clearwater", "southwest", "magic-valley", "southeast", "upper-snake", "salmon")}
    unplaced = {}

    def add(kind, item):
        rid = where(item["lon"], item["lat"]) if item["lat"] is not None else None
        if rid in regions:
            regions[rid]["roads"][kind].append(item)
        else:
            unplaced[kind] = unplaced.get(kind, 0) + 1

    winter = [norm_winter(d) for d in call("winterroads", key)]
    time.sleep(PAUSE)
    events = [norm_event(d) for d in call("event", key)]
    time.sleep(PAUSE)
    total = {"winterSegments": len(winter), "events": len(events)}
    for w in winter:
        if interesting_winter(w):
            add("winter", w)
    # Closures and incidents only; roadwork is the WZDx feed's job and would swamp the list.
    for e in events:
        if e["fullClosure"] or e["type"] in ("closures", "accidentsAndIncidents"):
            add("closures", e)
    for kind, endpoint, normer in (("passes", "mountainpasses", norm_pass), ("alerts", "alerts", norm_alert)):
        try:
            items = [normer(d) for d in call(endpoint, key)]
            total[kind] = len(items)
            for it in items:
                add(kind, it)
        except Exception as ex:  # best effort: say why, keep the required data
            print(f"511: {endpoint} skipped: {type(ex).__name__}: {str(ex)[:120]}")
        time.sleep(PAUSE)
    reporting = {rid: 0 for rid in regions}  # segments with a real status (not "No Report"): the denominator for the snow-share rule
    for w in winter:
        if w["lat"] is not None and str(w["condition"]).strip().lower() not in ("", "no report", "no condition", "unknown"):
            rid = where(w["lon"], w["lat"])
            if rid in reporting:
                reporting[rid] += 1
    for rid, v in regions.items():
        r = v["roads"]
        r["counts"] = {k: len(r[k]) for k in ("winter", "closures", "passes", "alerts")}
        r["counts"]["winterReporting"] = reporting[rid]
        r["asOf"] = now_utc().isoformat(timespec="seconds")
    try:  # debug sample for field-name review; no key, small
        dbg = {"totals": total, "winterConditionValues": sorted({str(w["condition"]) for w in winter})[:40],
               "winterSample": [w["fields"] for w in winter[:4]],
               "eventTypes": sorted({(e["type"], e["subType"], e["fullClosure"]) for e in events}, key=str),
               "closureUpdated": sorted(str(e["updated"])[:10] for e in events if e["fullClosure"])}
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "probes")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "idaho511_last_run.json"), "w") as f:
            json.dump(dbg, f, indent=1, default=str)
    except Exception as ex:
        print("511: debug sample skipped:", type(ex).__name__)
    print("511 totals:", total, "| not placed in a region:", unplaced or "none")
    if not winter and not events:
        raise RuntimeError("winterroads and event both came back empty; treating as a failed fetch")
    return regions


if __name__ == "__main__":
    run_part("idaho511", fetch)
