#!/usr/bin/env python3
"""SNOTEL snow depth, water equivalent, 24h depth change and % of median for the stations in data/selected_stations.json -> data/parts/snotel.json.
Source: NRCS AWDB REST (no key). Daily values lag about a day. Percent of median is left empty when the median is under 1 in (early season)."""
import datetime as dt
from ic_common import *

AWDB = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"


def daily(item, code):
    for el in item.get("data", []):
        if el["stationElement"]["elementCode"] == code:
            return [v for v in el.get("values", []) if v.get("value") is not None], el
    return [], None


def fetch():
    find = region_finder()
    entries = [x for x in load_json("data/selected_stations.json")["snow"] if x.get("snotel")]
    peaks = load_json("data/peaks.json").get("peaks", [])  # nearby stations for each backcountry peak (not on the region Snow card)
    ids = sorted({x["snotel"]["id"] for x in entries} | {st["id"] for pk in peaks for st in pk["stations"]})
    end = dt.date.today()
    rows = http_json(q(AWDB + "/data", stationTriplets=",".join(ids), elements="SNWD,WTEQ", duration="DAILY",
                       beginDate=(end - dt.timedelta(days=5)).isoformat(), endDate=end.isoformat(), returnFlags="false"))
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
        d, _ = daily(it, "SNWD")
        w, _ = daily(it, "WTEQ")
        # daily values are stamped for station standard time (PST, UTC-8); use the end of that day as the observation time
        obs = (lambda v: f"{v['date']}T23:59:00-08:00")(d[-1]) if d else None
        wobs = (lambda v: f"{v['date']}T23:59:00-08:00")(w[-1]) if w else None
        change = (d[-1]["value"] - d[-2]["value"]) if len(d) >= 2 and d[-1]["date"] > d[-2]["date"] else None
        m = med.get(sn["id"])
        pct = round(100 * w[-1]["value"] / m) if w and m and m >= 1.0 else None
        entry = {"id": sn["id"], "name": sn["name"], "area": x["area"], "elevationFt": elev.get(sn["id"]),
                 "depth": reading(d[-1]["value"] if d else None, "in", obs, "NRCS SNOTEL"),
                 "swe": reading(w[-1]["value"] if w else None, "in", wobs, "NRCS SNOTEL"),
                 "depthChange24h": reading(change, "in", obs, "NRCS SNOTEL"),
                 "pctOfMedian": reading(pct, "%", wobs, "NRCS SNOTEL")}
        rid = find(sn["lon"], sn["lat"])
        if rid:
            out.setdefault(rid, {}).setdefault("snow", []).append(entry)
    # per-peak nearby stations: out[region]["peaks"][spot id] = [station + distance/direction/feet below summit, ...]
    for pk in peaks:
        lst = []
        for st in pk["stations"]:
            it = by.get(st["id"], {})
            d, _ = daily(it, "SNWD")
            w, _ = daily(it, "WTEQ")
            obs = (lambda v: f"{v['date']}T23:59:00-08:00")(d[-1]) if d else None
            wobs = (lambda v: f"{v['date']}T23:59:00-08:00")(w[-1]) if w else None
            change = (d[-1]["value"] - d[-2]["value"]) if len(d) >= 2 and d[-1]["date"] > d[-2]["date"] else None
            lst.append({"id": st["id"], "name": st["name"], "elevationFt": elev.get(st["id"]) or st.get("elevationFt"),
                        "distanceMi": st["distanceMi"], "bearing": st["bearing"], "feetBelowSummit": st["feetBelowSummit"],
                        "depth": reading(d[-1]["value"] if d else None, "in", obs, "NRCS SNOTEL"),
                        "swe": reading(w[-1]["value"] if w else None, "in", wobs, "NRCS SNOTEL"),
                        "depthChange24h": reading(change, "in", obs, "NRCS SNOTEL")})
        out.setdefault(pk["region"], {}).setdefault("peaks", {})[pk["id"]] = lst
    return out


if __name__ == "__main__":
    run_part("snotel", fetch)
