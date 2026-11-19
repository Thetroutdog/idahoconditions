#!/usr/bin/env python3
"""River flow (and stage where available) for the gauges in data/selected_stations.json -> data/parts/usgs.json.
Source: USGS Water Data OGC API latest-continuous (works without a key; USGS_API_KEY optional). Data is provisional."""
import os, re
from ic_common import *

BASE = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous/items"
HIST = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items"
STEADY = 0.05  # within +/-5% over about 3 hours reads as steady


def usable(p):
    """A reading with a real number. Skips null values (sensor off or iced up, which would otherwise hide the last good reading),
    text qualifiers and negative sentinels such as -999999."""
    try:
        return float(p.get("value")) > -999
    except (TypeError, ValueError):
        return False


def latest(ids, code, headers):
    """Newest reading per site. Small batches, a roomy limit and pagination: with limit=100 and 25 ids, sites with several
    time series pushed some (e.g. Selway nr Lowell) off the first page and they came back 'missing'."""
    got, failed, batches = {}, 0, 0
    for i in range(0, len(ids), 10):
        batches += 1
        url = q(BASE, monitoring_location_id=",".join(ids[i:i + 10]), parameter_code=code, f="json", limit=500)
        pages = 0
        try:  # one failing batch marks only its own gauges missing; the part fails only if every batch fails
            while url and pages < 5:
                d = http_json(url, headers=headers)
                for f in d.get("features", []):
                    p = f["properties"]
                    if not usable(p):
                        continue
                    cur = got.get(p["monitoring_location_id"])
                    if cur is None or (p.get("time") or "") > (cur.get("time") or ""):
                        got[p["monitoring_location_id"]] = p
                url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
                pages += 1
        except Exception as e:
            failed += 1
            print(f"USGS {code}: batch {i // 10 + 1} failed, its gauges read missing: {type(e).__name__}: {e}"[:200])
        time.sleep(1)
    if batches and failed == batches:
        raise RuntimeError(f"every USGS batch failed for parameter {code}")
    return got


def trends(ids, headers):
    """rising / falling / steady per site from about 3 h of discharge history (OGC 'continuous' collection).
    Best effort: any failure leaves trend None (the table then shows no trend) and never fails the whole fetch."""
    out = {}
    try:
        end = now_utc()
        begin = end - dt.timedelta(hours=4)
        series = {}
        for i in range(0, len(ids), 10):
            url = q(HIST, monitoring_location_id=",".join(ids[i:i + 10]), parameter_code="00060", f="json", limit=1000,
                    time=f"{begin.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}")
            pages = 0
            while url and pages < 5:
                d = http_json(url, headers=headers)
                for f in d.get("features", []):
                    p = f["properties"]
                    if p.get("value") not in (None, "") and p.get("time"):
                        series.setdefault(p["monitoring_location_id"], {})[p["time"]] = float(p["value"])
                url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
                pages += 1
            time.sleep(1)
        for sid, pts in series.items():
            out[sid] = trend_of(pts)
    except Exception as e:
        print("trend skipped:", f"{type(e).__name__}: {e}"[:150])
    return out


def trend_of(pts):
    """pts {iso time: cfs}. Compare the newest point with the one closest to 3 h earlier; need at least 2 h of spread."""
    ts = sorted(pts, key=lambda t: dt.datetime.fromisoformat(t.replace("Z", "+00:00")))
    if len(ts) < 2:
        return None
    t1 = dt.datetime.fromisoformat(ts[-1].replace("Z", "+00:00"))
    target = t1 - dt.timedelta(hours=3)
    old = min(ts, key=lambda t: abs((dt.datetime.fromisoformat(t.replace("Z", "+00:00")) - target).total_seconds()))
    if (t1 - dt.datetime.fromisoformat(old.replace("Z", "+00:00"))).total_seconds() < 2 * 3600:
        return None
    v1, v0 = pts[ts[-1]], pts[old]
    if v0 <= 0:
        return "steady" if v1 <= 0 else "rising"
    ch = (v1 - v0) / v0
    return "rising" if ch > STEADY else "falling" if ch < -STEADY else "steady"


def rd(p, unit):
    if not p or p.get("value") in (None, ""):
        return reading(None, unit, None, "USGS", True)
    return reading(float(p["value"]), unit, p.get("time"), "USGS", p.get("approval_status") != "Approved")


def rd_temp(p):
    """Water temperature: USGS reports deg C (parameter 00010); shown in deg F. Many gauges have no temperature sensor, which reads as missing."""
    if not p or p.get("value") in (None, ""):
        return reading(None, "°F", None, "USGS", True)
    return reading(round(float(p["value"]) * 9 / 5 + 32, 1), "°F", p.get("time"), "USGS", p.get("approval_status") != "Approved")


def uses(text):
    u = []
    if re.search(r"\bP\b", text):
        u.append("paddling")
    if re.search(r"\bF\b", text):
        u.append("fishing")
    return u


def fetch():
    key = os.environ.get("USGS_API_KEY", "")
    headers = {"X-Api-Key": key} if key else {}
    rivers = load_json("data/selected_stations.json")["rivers"]
    ids = sorted({r["usgs_id"] for r in rivers})
    flow, stage = latest(ids, "00060", headers), latest(ids, "00065", headers)
    try:
        temp = latest(ids, "00010", headers)
    except Exception as e:  # water temperature is a bonus; never let it fail the flow fetch
        print("water temperature skipped:", f"{type(e).__name__}: {e}"[:150])
        temp = {}
    tr = trends(ids, headers)
    out = {}
    for r in rivers:
        entry = {"id": r["usgs_id"], "name": r["name"], "use": uses(r["use"]), "flow": rd(flow.get(r["usgs_id"]), "cfs"),
                 "stage": rd(stage.get(r["usgs_id"]), "ft"), "waterTemp": rd_temp(temp.get(r["usgs_id"])), "trend": tr.get(r["usgs_id"])}
        out.setdefault(slug(r["region"]), {}).setdefault("rivers", []).append(entry)
    return out


if __name__ == "__main__":
    run_part("usgs", fetch)
