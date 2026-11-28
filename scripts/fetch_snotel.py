#!/usr/bin/env python3
"""SNOTEL snow depth, water equivalent, 24h depth change and % of median for the stations in data/selected_stations.json -> data/parts/snotel.json.
Source: NRCS AWDB REST (no key). Daily values lag about a day, so depth, water content and the 24 h change come from the HOURLY series when it is there (provisional, a few hours old),
all three from the same hour. Daily values are the fallback. Percent of median is left empty when the median is under 1 in (early season)."""
import datetime as dt
from ic_common import *

AWDB = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"


def daily(item, code):
    for el in item.get("data", []):
        if el["stationElement"]["elementCode"] == code:
            return [v for v in el.get("values", []) if v.get("value") is not None], el
    return [], None


JUMP_IN = 6  # a one-hour step this big is a sensor jump (snow does not vanish or arrive in an hour); the 24 h change is then flagged, not trusted
PST = "-08:00"  # SNOTEL timestamps are station standard time (PST) with no zone in the text


def hourly(item, code):
    """[(naive datetime in PST, value)] oldest first, nulls dropped."""
    for el in item.get("data", []):
        if el["stationElement"]["elementCode"] == code:
            out = []
            for v in el.get("values", []):
                if v.get("value") is None:
                    continue
                try:
                    out.append((dt.datetime.strptime(v["date"], "%Y-%m-%d %H:%M"), v["value"]))
                except ValueError:
                    pass
            return sorted(out)
    return []


def snow_hourly(it):
    """Depth, water content and 24 h depth change from the latest hourly SNWD reading. None when this station has no hourly depth."""
    h = hourly(it, "SNWD")
    if not h:
        return None
    t, depth = h[-1]
    byt = dict(h)
    prev = next((byt[t - dt.timedelta(hours=k)] for k in (24, 23, 25) if t - dt.timedelta(hours=k) in byt), None)  # the hour a day earlier (or an hour either side)
    last24 = [(a, b) for a, b in zip(h, h[1:]) if b[0] - a[0] == dt.timedelta(hours=1) and b[0] > t - dt.timedelta(hours=24)]
    suspect = any(abs(b[1] - a[1]) > JUMP_IN for a, b in last24)
    w = hourly(it, "WTEQ")
    return {"t": t, "depth": depth, "change": (depth - prev) if prev is not None else None, "suspect": suspect, "swe": w[-1][1] if w else None, "swe_t": w[-1][0] if w else None}


def snow_values(hit, dit):
    """(depth, swe, change, obs, wobs, suspect, basis) for one station: the hourly series (hit) if it has depth, else the daily series (dit)."""
    hs = snow_hourly(hit)
    iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:00") + PST
    w, _ = daily(dit, "WTEQ")
    if hs:
        swe, wobs = (hs["swe"], iso(hs["swe_t"])) if hs["swe"] is not None else ((w[-1]["value"], f"{w[-1]['date']}T23:59:00{PST}") if w else (None, None))
        return hs["depth"], swe, hs["change"], iso(hs["t"]), wobs, hs["suspect"], "hourly"
    d, _ = daily(dit, "SNWD")
    obs = f"{d[-1]['date']}T23:59:00{PST}" if d else None
    wobs = f"{w[-1]['date']}T23:59:00{PST}" if w else None
    change = (d[-1]["value"] - d[-2]["value"]) if len(d) >= 2 and d[-1]["date"] > d[-2]["date"] else None
    return (d[-1]["value"] if d else None), (w[-1]["value"] if w else None), change, obs, wobs, False, "daily"


def fetch():
    find = region_finder()
    entries = [x for x in load_json("data/selected_stations.json")["snow"] if x.get("snotel")]
    peaks = load_json("data/peaks.json").get("peaks", [])  # nearby stations for each backcountry peak (not on the region Snow card)
    skis = load_json("data/ski_areas.json").get("areas", [])  # nearby stations for each ski area (not resort data)
    ids = sorted({x["snotel"]["id"] for x in entries} | {st["id"] for pk in peaks for st in pk["stations"]} | {st["id"] for a in skis for st in a["stations"]})
    end = dt.date.today()
    rows = http_json(q(AWDB + "/data", stationTriplets=",".join(ids), elements="SNWD,WTEQ", duration="DAILY",
                       beginDate=(end - dt.timedelta(days=5)).isoformat(), endDate=end.isoformat(), returnFlags="false"))
    hrows = []
    try:  # hourly depth and water content for the last 3 days; if this fails, daily values still work
        hrows = http_json(q(AWDB + "/data", stationTriplets=",".join(ids), elements="SNWD,WTEQ", duration="HOURLY",
                            beginDate=(end - dt.timedelta(days=3)).isoformat(), endDate=end.isoformat(), returnFlags="false"))
    except Exception as e:
        print("hourly lookup failed, using daily values:", e)
    hby = {it["stationTriplet"]: it for it in hrows if isinstance(it, dict)}
    med = {}
    try:
        for it in http_json(q(AWDB + "/data", stationTriplets=",".join(ids), elements="WTEQ", duration="DAILY",
                              beginDate=(end - dt.timedelta(days=5)).isoformat(), endDate=end.isoformat(),
                              centralTendencyType="MEDIAN", returnFlags="false")):
            vals, _ = daily(it, "WTEQ")
            med[it["stationTriplet"]] = vals[-1].get("median") if vals else None
    except Exception as e:  # medians are a nice-to-have
        print("median lookup failed:", e)
    elev = {}
    try:
        for s in http_json(q(AWDB + "/stations", stationTriplets=",".join(ids))):
            elev[s["stationTriplet"]] = s.get("elevation")
    except Exception as e:
        print("elevation lookup failed:", e)
    by = {it["stationTriplet"]: it for it in rows}
    out = {}
    for x in entries:
        sn = x["snotel"]
        it = by.get(sn["id"], {})
        depth, swe, change, obs, wobs, suspect, basis = snow_values(hby.get(sn["id"], {}), it)
        m = med.get(sn["id"])
        pct = round(100 * swe / m) if swe is not None and m and m >= 1.0 else None
        prov = basis == "hourly"  # hourly readings are provisional until NRCS reviews them
        entry = {"id": sn["id"], "name": sn["name"], "area": x["area"], "elevationFt": elev.get(sn["id"]), "basis": basis,
                 "depth": reading(depth, "in", obs, "NRCS SNOTEL", prov),
                 "swe": reading(swe, "in", wobs, "NRCS SNOTEL", prov),
                 "depthChange24h": {**reading(change, "in", obs, "NRCS SNOTEL", prov), **({"suspect": True} if suspect else {})},
                 "pctOfMedian": reading(pct, "%", wobs, "NRCS SNOTEL", prov)}
        rid = find(sn["lon"], sn["lat"])
        if rid:
            out.setdefault(rid, {}).setdefault("snow", []).append(entry)
    # per-peak nearby stations: out[region]["peaks"][spot id] = [station + distance/direction/feet below summit, ...]
    for pk in peaks:
        lst = []
        for st in pk["stations"]:
            it = by.get(st["id"], {})
            depth, swe, change, obs, wobs, suspect, basis = snow_values(hby.get(st["id"], {}), it)
            prov = basis == "hourly"
            lst.append({"id": st["id"], "name": st["name"], "elevationFt": elev.get(st["id"]) or st.get("elevationFt"),
                        "distanceMi": st["distanceMi"], "bearing": st["bearing"], "feetBelowSummit": st["feetBelowSummit"], "basis": basis,
                        "depth": reading(depth, "in", obs, "NRCS SNOTEL", prov),
                        "swe": reading(swe, "in", wobs, "NRCS SNOTEL", prov),
                        "depthChange24h": {**reading(change, "in", obs, "NRCS SNOTEL", prov), **({"suspect": True} if suspect else {})}})
        out.setdefault(pk["region"], {}).setdefault("peaks", {})[pk["id"]] = lst
    # per-ski-area nearby stations: out[region]["skiStations"][spot id]; distance and feet vs the mid-mountain map point travel with each one
    for a in skis:
        if not a["stations"]:
            continue
        lst = []
        for st in a["stations"]:
            it = by.get(st["id"], {})
            depth, swe, change, obs, wobs, suspect, basis = snow_values(hby.get(st["id"], {}), it)
            prov = basis == "hourly"
            lst.append({"id": st["id"], "name": st["name"], "elevationFt": elev.get(st["id"]) or st.get("elevationFt"),
                        "distanceMi": st["distanceMi"], "bearing": st["bearing"], "feetVsMid": st["feetVsMid"], "basis": basis,
                        "depth": reading(depth, "in", obs, "NRCS SNOTEL", prov),
                        "swe": reading(swe, "in", wobs, "NRCS SNOTEL", prov),
                        "depthChange24h": {**reading(change, "in", obs, "NRCS SNOTEL", prov), **({"suspect": True} if suspect else {})}})
        out.setdefault(a["region"], {}).setdefault("skiStations", {})[a["id"]] = lst
    return out


if __name__ == "__main__":
    run_part("snotel", fetch)
