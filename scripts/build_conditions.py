#!/usr/bin/env python3
"""Merge fetcher parts (data/parts/*.json) into data/conditions.json per docs/conditions-schema.md.
Computes each region's level/summary and the statewide alert bar. Sections with no fetcher yet stay empty/missing.
    python3 scripts/build_conditions.py [--parts DIR] [--out FILE]      python3 scripts/build_conditions.py selftest"""
import json, os, re, sys, glob, datetime as dt
from zoneinfo import ZoneInfo

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REGIONS = [("panhandle", "Panhandle", "America/Los_Angeles"), ("clearwater", "Clearwater", "America/Los_Angeles"),
           ("southwest", "Southwest", "America/Boise"), ("magic-valley", "Magic Valley", "America/Boise"),
           ("southeast", "Southeast", "America/Boise"), ("upper-snake", "Upper Snake", "America/Boise"), ("salmon", "Salmon", "America/Boise")]
NWS_STALE_MIN = 60   # was 30 (rules-proposal.md). Runs are every 30 min; 60 leaves room for GitHub cron starting 10-30 min late and still catches a run that really failed
ROADS_STALE_MIN = 120
CLOSURE_FRESH_MIN = 48 * 60    # an unplanned closure not updated for 2 days is probably a forgotten record
WINTER_FRESH_MIN = 36 * 60
ICY = ("ice", "icy", "slick")                 # any icy highway segment makes the region amber
SNOWY = ("snow", "packed", "covered")         # snow-covered counts toward the share rule; slush alone never colors a region
SNOW_SHARE = 0.5                              # amber when at least half the reporting highway segments are snow-covered...
SNOW_MIN_SEGMENTS = 3                         # ...and at least this many are  # rules-proposal.md: Idaho 511 data older than 2 h is stale
# Idaho 511 data is fetched and kept under roads["preview"], but it does not change the site (road card, region color,
# "Roads clear") until this is True. Flip it after checking the first real fetch: field names and the closure/winter rules
# below were written before any real response was seen.
ROADS_LIVE = True
HAZARD = ("snow", "ice", "icy", "slick", "slippery", "packed", "slush", "chain", "traction", "hazard", "poor", "difficult", "drifting")
RANK = {None: 0, "amber": 1, "red": 2}
SEVERITY = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}   # sort order inside one color: worst first, then soonest end


RESORT_STALE_DAYS = 8   # resort_status.json is crawled weekly by hand; older than this is shown as stale, not as current


def ski_by_region(now):
    """Weekly open/closed/opening-day results (data/resort_status.json from fetch_resort_status.py) grouped by region id, newest facts only.
    'unknown' results are left out: they say nothing. Re-evaluated at build time so a missed weekly crawl shows as stale."""
    try:
        status = json.load(open(os.path.join(ROOT, "data", "resort_status.json")))
        catalog = json.load(open(os.path.join(ROOT, "data", "spots.json")))["spots"]
        try:
            catalog += json.load(open(os.path.join(ROOT, "data", "spots_extra.json")))["spots"]
        except Exception:
            pass
    except Exception:
        return {}
    names = {c["id"]: c["name"] for c in catalog}
    rids = sorted((r[0] for r in REGIONS), key=len, reverse=True)  # longest first: "upper-snake" before any shorter prefix
    out = {}
    for sid, v in status.get("spots", {}).items():
        if v.get("status") in (None, "unknown"):
            continue
        rid = next((r for r in rids if sid.startswith(r + "-")), None)
        if not rid:
            continue
        try:
            age = (now.date() - dt.date.fromisoformat(v["checkedAt"])).days
        except Exception:
            age = None
        out.setdefault(rid, []).append({"id": sid, "name": names.get(sid, sid), "status": v["status"], "confidence": v.get("confidence"),
                                        "opening": v.get("opening"), "openingISO": v.get("openingISO"), "url": v.get("url"), "checkedAt": v.get("checkedAt"),
                                        "freshness": "stale" if age is None or age > RESORT_STALE_DAYS else "fresh", "source": v.get("source")})
    for lst in out.values():
        lst.sort(key=lambda x: x["name"])
    return out


def avalanche_links():
    """data/avalanche_centers.json -> ({region id: [center, ...]}, {forecast point id: [center ids]}). Static links, not fetched data.
    A center is {id, name, url, area}. Missing or unreadable file gives nothing, and the build carries on."""
    try:
        d = json.load(open(os.path.join(ROOT, "data", "avalanche_centers.json")))
    except Exception:
        return {}, {}
    cs = d.get("centers", {})
    regs = {rid: [{"id": c, **cs[c]} for c in ids if c in cs] for rid, ids in d.get("regions", {}).items()}
    pts = {pid: [c for c in ids if c in cs] for pid, ids in d.get("points", {}).items()}
    return regs, pts


def skeleton(name, tz):
    return {"name": name, "tz": tz, "level": "gray", "levelReasons": [], "summary": "", "alerts": [],
            "forecast": {"points": [], "updated": None}, "roads": {"status": "missing", "passes": [], "closures": [], "restrictions": []},
            "snow": [], "peaks": {}, "rivers": [], "air": {"points": [], "note": None}, "fire": {"wildfires": [], "prescribed": []}, "ski": [], "avalanche": [], "local": {}, "airForecast": None}


def fmt_end(iso, tz):
    if not iso:
        return "further notice"
    t = dt.datetime.fromisoformat(iso).astimezone(ZoneInfo(tz))
    return t.strftime("%a ") + t.strftime("%I %p").lstrip("0") if t.minute == 0 else t.strftime("%a ") + t.strftime("%I:%M %p").lstrip("0")


def age_min(iso, now):
    return (now - dt.datetime.fromisoformat(iso)).total_seconds() / 60 if iso else None


# Hours after which a reading is stale / hidden (docs/rules-proposal.md). Re-evaluated at build time from observedAt.
CUT = {"snow": (48, 96), "rivers": (3, 24), "air": (3, 6)}


def restatus(r, stale_h, hide_h, now):
    if not isinstance(r, dict) or "observedAt" not in r:
        return
    if r.get("value") is None or not r.get("observedAt"):
        r["status"] = "missing"
        return
    h = (now - dt.datetime.fromisoformat(r["observedAt"])).total_seconds() / 3600
    if h > hide_h:
        r["value"], r["status"] = None, "missing"
    else:
        r["status"] = "stale" if h > stale_h else "fresh"


FIRE_CUT_DAYS = {"wildfires": (7, 14), "prescribed": (14, 30)}  # same as fetch_nifc.py: (stale after, hide after)


def apply_fire_freshness(region, now):
    """NIFC's own status is set when it is fetched. If the fetch stops, old fires must not keep a region amber, so re-check modifiedAt here."""
    for kind, (stale_d, hide_d) in FIRE_CUT_DAYS.items():
        keep = []
        for f in region.get("fire", {}).get(kind, []):
            try:
                age = (now - dt.datetime.fromisoformat(f["modifiedAt"])).days
            except Exception:
                keep.append(f)
                continue
            if age > hide_d:
                continue
            f["status"] = "stale" if age > stale_d else "fresh"
            keep.append(f)
        if kind in region.get("fire", {}):
            region["fire"][kind] = keep


LOCAL_STALE_H = {"r2r": 72}  # per local source: hours after its own "as of" before it dims. Local sources never change the region level.


def apply_local_freshness(region, parts, now):
    """Re-check each local source's stale flag at build time, so a stopped fetcher cannot leave an old report looking current."""
    for key, item in (region.get("local") or {}).items():
        if not isinstance(item, dict):
            continue
        h = LOCAL_STALE_H.get(key)
        a = age_min(item.get("asOf"), now) if item.get("asOf") else None
        if h is not None:
            item["stale"] = a is None or a > h * 60
        part = parts.get(key)
        if part is not None and not part.get("ok"):  # fetch failing: keep the last data, flagged so the UI says it may be old
            item["fetchFailing"] = True


AIR_FORECAST_MAX_DAYS = 3  # about 72 h. Idaho DEQ mostly forecasts on weekdays, so a Friday forecast must still be current on Saturday and Sunday.


def apply_air_forecast_freshness(region, now):
    """A forecast area stays while it still covers today (in the region's time zone) and was issued no more than 3 days ago; days already past
    are dropped. Never changes the region level: an Action Day is information, not a status."""
    af = region.get("airForecast")
    if not af:
        return
    today = now.astimezone(ZoneInfo(region["tz"])).date()
    keep = []
    for a in af.get("areas", []):
        try:
            issued = dt.date.fromisoformat(a["issued"])
            days = [d for d in a.get("days", []) if dt.date.fromisoformat(d["date"]) >= today]
        except (KeyError, ValueError, TypeError):
            continue
        if not days or (today - issued).days > AIR_FORECAST_MAX_DAYS:
            continue
        keep.append({**a, "days": days, "actionDay": any(d.get("actionDay") for d in days)})
    region["airForecast"] = {**af, "areas": keep} if keep else None


def drop_dead_closures(rd, now):
    """Hide closures whose planned end has passed, and unplanned ones not updated for CLOSURE_FRESH_MIN (a forgotten record).
    Planned closures keep showing without a recent update: a seasonal closure is legitimately quiet."""
    if not isinstance(rd.get("closures"), list):
        return
    def alive(c):
        try:
            if c.get("end") and dt.datetime.fromisoformat(c["end"]) < now:
                return False
        except Exception:
            pass
        a = age_min(c.get("updated"), now)
        return not (c.get("unplanned") and a is not None and a > CLOSURE_FRESH_MIN)
    rd["closures"] = [c for c in rd["closures"] if alive(c)]


def _hwy(s):
    return re.sub(r"[\s-]+", "", s or "").upper()


def _plain(s):
    return re.sub(r"\s+", " ", re.sub(r"\bcr\.", "creek", (s or "").lower().replace("\u2019", "'"))).strip()


def _pass_phrase(name):
    """'Beaver Creek' -> 'beaver creek'; 'Targee Pass' -> 'targee'. A trailing Pass, Summit or Hill is dropped: segment descriptions often say 'Beaver Creek Summit'."""
    return re.sub(r"\s+(pass|summit|hill)$", "", _plain(name))


def _cond_severity(c):
    c = (c or "").lower()
    return 0 if re.search(r"closed|impass", c) else 1 if any(w in c for w in ICY) else 2 if any(w in c for w in SNOWY) else 3


def attach_pass_conditions(rd, now):
    """Idaho 511's mountain-pass feed has no condition field (only name, highway, elevation, grade, location). A pass gets the condition of
    the winter-road segment that is on the same highway AND whose description names the pass ("Banner Creek Summit/Stanley from MP 105...").
    Nearest-segment guessing is not used: it can borrow a stretch of road tens of miles away. No match, or a stale segment, gives None
    (the page then says "see Idaho 511"). The worst condition wins when several segments name the pass."""
    winter = rd.get("winter") or []
    for p in rd.get("passes") or []:
        f = p.get("fields") or {}
        p["highway"] = f.get("Roadway") or None
        try:
            p["elevationFt"] = int(float(f.get("MaxElevation")))
        except (TypeError, ValueError):
            p["elevationFt"] = None
        key, hits = _pass_phrase(p.get("name")), []
        if key and p["highway"]:
            for w in winter:
                a = age_min(w.get("updated"), now)
                if _hwy(w.get("name")) == _hwy(p["highway"]) and key in _plain(w.get("where")) and w.get("condition") and a is not None and a <= WINTER_FRESH_MIN:
                    hits.append(w)
        if hits:
            w = min(hits, key=lambda x: _cond_severity(x["condition"]))
            p["roadCondition"] = {"condition": w["condition"], "where": " ".join((w.get("where") or "").split()), "updated": w.get("updated"), "segments": len(hits)}
        else:
            p["roadCondition"] = None


def apply_freshness(region, now):
    for sec, key_list in (("snow", ("depth", "swe", "depthChange24h", "pctOfMedian")), ("rivers", ("flow", "stage", "waterTemp"))):
        for item in region.get(sec, []):
            for k in key_list:
                restatus(item.get(k), *CUT[sec], now)
    for stations in region.get("peaks", {}).values():  # nearby stations for backcountry peaks
        for item in stations:
            for k in ("depth", "swe", "depthChange24h"):
                restatus(item.get(k), *CUT["snow"], now)
    for pt in region.get("air", {}).get("points", []):
        restatus(pt.get("aqi"), *CUT["air"], now)


def build(parts, now, ski_status=None):
    regions = {rid: skeleton(n, tz) for rid, n, tz in REGIONS}
    sources = {k: {"fetchedAt": None, "ok": False, "error": "no fetcher yet"} for k in ("nws", "airnow", "snotel", "usgs", "noaa", "nifc", "idaho511")}
    nws_fresh = False
    unplaced = {"weather": [], "roads": [], "air": [], "fire": []}  # items no region claims; shown in the matching statewide card
    nws = parts.get("nws")
    spot_forecast = (nws or {}).get("spotForecast") or {"bySpot": {}, "grids": {}}  # mountain-elevation forecasts for winter spots
    if nws:
        a = age_min(nws.get("fetchedAt"), now)
        nws_fresh = bool(nws.get("ok")) and a is not None and a <= NWS_STALE_MIN
        sources["nws"] = {"fetchedAt": nws.get("fetchedAt"), "ok": bool(nws.get("ok")), "error": nws.get("error")}
        for rid, fc in nws.get("forecast", {}).items():
            if rid in regions:
                regions[rid]["forecast"] = fc
        if nws_fresh:
            unplaced["weather"] = [{"event": a["event"], "ends": a.get("ends"), "level": a.get("level"), "url": a.get("url"), "headline": a.get("headline")}
                                   for a in nws.get("alerts", {}).get("_unplaced", [])]
        for rid, al in nws.get("alerts", {}).items():
            if rid in regions:
                live = [x for x in al if not x.get("ends") or dt.datetime.fromisoformat(x["ends"]) > now]  # an alert past its end time is over
                regions[rid]["alerts"] = sorted(live, key=lambda x: (-RANK[x["level"]], SEVERITY.get(x.get("severity"), 4), x.get("ends") or "9999"))
    for name, part in parts.items():
        if name == "nws":
            continue
        sources[name] = {"fetchedAt": part.get("fetchedAt"), "ok": bool(part.get("ok")), "error": part.get("error")}
        for rid, secs in part.get("regions", {}).items():
            if rid in regions:
                for k, v in secs.items():  # rivers from several parts (usgs, noaa) are combined, not replaced; local sources are merged by source key
                    if k == "local" and isinstance(v, dict):
                        regions[rid].setdefault("local", {}).update(v)
                    else:
                        regions[rid][k] = regions[rid].get(k, []) + v if k == "rivers" and isinstance(v, list) else v
    av_regions, av_points = avalanche_links()
    for rid, lst in av_regions.items():
        if rid in regions:
            regions[rid]["avalanche"] = lst
    if ski_status is not None:
        for rid, lst in ski_status.items():
            if rid in regions:
                regions[rid]["ski"] = lst
    p511 = parts.get("idaho511")
    for rid, r in regions.items():
        rd = r["roads"]
        drop_dead_closures(rd, now)
        attach_pass_conditions(rd, now)
        if p511 and rd.get("winter") is not None and "counts" in rd:
            a = age_min(p511.get("fetchedAt"), now)
            status = "fresh" if p511.get("ok") and a is not None and a <= ROADS_STALE_MIN else "stale"
            if ROADS_LIVE:
                rd["status"] = status
            else:  # keep the data for review, leave the site as it was
                r["roads"] = {"status": "missing", "passes": [], "closures": [], "restrictions": [], "preview": {**rd, "status": status}}
    bar_items = []
    for rid, r in regions.items():
        apply_freshness(r, now)
        apply_fire_freshness(r, now)
        apply_local_freshness(r, parts, now)
        apply_air_forecast_freshness(r, now)
        cand = []  # (rank, priority, reason, summary)
        for x in [x for x in r["alerts"] if x.get("level") and x.get("countsTowardLevel", True)] if nws_fresh else []:
            text = f"{x['event']} until {fmt_end(x['ends'], r['tz'])}"
            cand.append((RANK[x["level"]], 3 if x["level"] == "red" else 1, ("nws-alert", text), text + "."))
        aqis = [(p["aqi"]["value"], p) for p in r["air"]["points"] if p["aqi"]["status"] == "fresh" and p["aqi"]["value"] is not None]
        if aqis:
            v, p = max(aqis, key=lambda t: t[0])
            if v >= 101:
                lv = 2 if v >= 151 else 1
                cand.append((lv, 2 if lv == 2 else 0, ("air", f"AQI {v} ({p['category']}) at {p['name']}"), f"AQI {v} ({p['category']})."))
        for f in [f for f in r["fire"]["wildfires"] if f.get("status") == "fresh" and (f.get("containmentPct") or 0) < 100]:
            cand.append((1, 0, ("wildfire", f"{f['name']} fire, {f.get('acres') or '?'} acres"), f"{f['name']} fire, {f.get('acres') or '?'} acres."))
        roads_ok = r["roads"]["status"] == "fresh"
        if roads_ok:  # only reachable once ROADS_LIVE is on
            for c in r["roads"].get("closures", []):
                a = age_min(c.get("updated"), now)
                if c.get("fullClosure") and c.get("highway") and c.get("unplanned") and c.get("name") and a is not None and a <= CLOSURE_FRESH_MIN:
                    first = re.split(r"\.\s", " ".join((c.get("description") or "").split()), maxsplit=1)[0].rstrip(".")  # first sentence, whole
                    t = f"{c['name']} closed" + (f": {first}" if first and len(first) <= 110 else "")
                    cand.append((2, 2, ("road-closure", t), t + "."))
            groups = {}  # one reason per road and condition, not one per 10-mile segment
            for w in r["roads"].get("winter", []):
                a = age_min(w.get("updated"), now)
                if a is None or a > WINTER_FRESH_MIN:
                    continue
                groups.setdefault((w.get("name") or w.get("where") or "Road", str(w.get("condition", ""))), []).append(w)
            snowy = 0
            for (nm, cond_raw), ws in groups.items():
                cond = cond_raw.lower()
                t = f"{nm}: {cond_raw}" + (f" ({len(ws)} segments)" if len(ws) > 1 else "")
                if "closed" in cond or "impassable" in cond:
                    cand.append((2, 2, ("road-closure", f"{nm} closed"), f"{nm} closed."))
                elif any(w in cond for w in ICY):
                    cand.append((1, 0, ("road-winter", t), t + "."))
                elif any(w in cond for w in SNOWY):
                    snowy += len(ws)
            rep = (r["roads"].get("counts") or {}).get("winterReporting")
            if rep and snowy >= SNOW_MIN_SEGMENTS and snowy / rep >= SNOW_SHARE:
                t = f"Snow-covered roads on {snowy} of {rep} reporting highway segments"
                cand.append((1, 0, ("road-winter", t), t + "."))
        if cand:
            top = max(c[0] for c in cand)
            r["level"] = "red" if top == 2 else "amber"
            r["levelReasons"] = [{"kind": c[2][0], "text": c[2][1]} for c in sorted(cand, key=lambda c: (-c[0], -c[1]))]
            seen, picked = set(), []
            for c in sorted(cand, key=lambda c: (-c[0], -c[1])):  # one line per source so roads can't crowd out alerts, air and fire
                if c[2][0] not in seen:
                    seen.add(c[2][0]); picked.append(c[3])
            r["summary"] = " ".join(picked[:3])
            alert_cands = [c for c in cand if c[2][0] == "nws-alert"]
            if alert_cands:
                bar_items.append((max(c[0] for c in alert_cands), alert_cands[0][2][1].split(" until")[0], rid))
        elif nws_fresh and roads_ok:
            r["level"], r["levelReasons"], r["summary"] = "green", [], "No alerts. Roads clear."
        else:
            r["level"] = "gray"
            why = "Weather alerts are out of date" if not nws_fresh else "Road data not connected yet, so we can't confirm clear"
            r["levelReasons"] = [{"kind": "roads-pending" if nws_fresh else "no-data", "text": why}]
            r["summary"] = "No alerts right now. Road conditions not checked yet." if nws_fresh else "Alert data is out of date."
    bar = None
    if bar_items:
        bar_items.sort(reverse=True)
        top_rank, top_event = bar_items[0][0], bar_items[0][1]
        same = [rid for rk, ev, rid in bar_items if ev == top_event]
        bar = {"level": "red" if top_rank == 2 else "amber", "text": f"{top_event}: " + (", ".join(regions[r]["name"] for r in same) if len(same) <= 3 else f"{len(same)} regions"),
               "moreCount": len(bar_items) - len(same), "regionIds": same}
    return {"schemaVersion": "0.1", "meta": {"sample": False, "nwsFresh": nws_fresh}, "generatedAt": now.isoformat(timespec="seconds"),
            "sources": sources, "alertBar": bar, "unplaced": unplaced, "regions": regions, "avalanchePoints": av_points, "spotForecast": spot_forecast}


def load_parts(d):
    return {os.path.basename(f)[:-5]: json.load(open(f)) for f in glob.glob(os.path.join(d, "*.json"))}


def selftest():
    global ROADS_LIVE
    orig_live, ROADS_LIVE = ROADS_LIVE, False
    now = dt.datetime(2026, 11, 15, 20, 0, tzinfo=dt.timezone.utc)
    al = lambda ev, lv, share_ok=True: {"id": ev, "event": ev, "level": lv, "ends": "2026-11-17T06:00:00+00:00", "countsTowardLevel": share_ok}
    part = {"source": "nws", "ok": True, "fetchedAt": "2026-11-15T19:50:00+00:00", "error": None, "forecast": {},
            "alerts": {"clearwater": [al("Winter Weather Advisory", "amber")], "salmon": [al("Winter Weather Advisory", "amber")],
                       "southwest": [al("Winter Storm Warning", "red")], "panhandle": [al("Wind Advisory", "amber", False)]}}
    c = build({"nws": part}, now)
    assert c["regions"]["southwest"]["level"] == "red" and c["regions"]["clearwater"]["level"] == "amber"
    assert c["regions"]["panhandle"]["level"] == "gray", "alert on <30% of region must not color it"
    assert c["alertBar"]["level"] == "red" and "Southwest" in c["alertBar"]["text"] and c["alertBar"]["moreCount"] == 2, c["alertBar"]
    part["alerts"]["_unplaced"] = [al("Special Weather Statement", "amber", False)]
    cu = build({"nws": part}, now)
    assert [a["event"] for a in cu["unplaced"]["weather"]] == ["Special Weather Statement"] and "_unplaced" not in cu["regions"], cu["unplaced"]
    del part["alerts"]["_unplaced"]
    part["fetchedAt"] = "2026-11-15T18:00:00+00:00"   # 2 h old -> stale -> everything gray
    c2 = build({"nws": part}, now)
    assert all(r["level"] == "gray" for r in c2["regions"].values()) and c2["alertBar"] is None
    # Idaho 511: data is kept for review but does not change the site while ROADS_LIVE is False
    p511 = {"source": "idaho511", "ok": True, "fetchedAt": "2026-11-15T19:50:00+00:00", "error": None, "regions": {
        "salmon": {"roads": {"winter": [{"name": "US-93", "condition": "Snow packed", "where": "Salmon", "updated": "2026-11-15T19:00:00+00:00"}], "closures": [{"name": "SH-75", "fullClosure": True, "highway": True, "unplanned": True, "updated": "2026-11-15T19:30:00+00:00", "description": "Slide"}, {"name": "Elm Rd", "fullClosure": True, "highway": False, "unplanned": True, "updated": "2026-11-15T19:30:00+00:00"}],
                             "passes": [], "restrictions": [], "alerts": [], "counts": {"winter": 1, "closures": 2, "passes": 0, "alerts": 0}}},
        "southwest": {"roads": {"winter": [], "closures": [], "passes": [], "restrictions": [], "alerts": [], "counts": {"winter": 0, "closures": 0, "passes": 0, "alerts": 0}}}}}
    c3 = build({"nws": {**part, "fetchedAt": "2026-11-15T19:50:00+00:00"}, "idaho511": p511}, now)
    assert c3["regions"]["salmon"]["roads"]["status"] == "missing" and c3["regions"]["salmon"]["roads"]["preview"]["counts"]["closures"] == 2
    assert c3["regions"]["southwest"]["level"] == "red" and c3["regions"]["salmon"]["level"] == "amber", "off: roads must not change levels"
    ROADS_LIVE = True
    c4 = build({"nws": {**part, "fetchedAt": "2026-11-15T19:50:00+00:00"}, "idaho511": p511}, now)
    assert c4["regions"]["salmon"]["roads"]["status"] == "fresh" and c4["regions"]["salmon"]["level"] == "red", c4["regions"]["salmon"]["summary"]
    assert "SH-75 closed" in c4["regions"]["salmon"]["summary"]
    c5 = build({"nws": {**part, "fetchedAt": "2026-11-15T19:50:00+00:00", "alerts": {}}, "idaho511": p511}, now)
    assert c5["regions"]["southwest"]["level"] == "green" and c5["regions"]["southwest"]["summary"] == "No alerts. Roads clear."
    p511["fetchedAt"] = "2026-11-15T16:00:00+00:00"   # 4 h old -> stale -> not green
    c6 = build({"nws": {**part, "fetchedAt": "2026-11-15T19:50:00+00:00", "alerts": {}}, "idaho511": p511}, now)
    assert c6["regions"]["southwest"]["level"] == "gray"
    # amber threshold: ice always; snow only when it covers at least half of the reporting segments
    fresh = "2026-11-15T19:50:00+00:00"
    seg = lambda n, c: [{"name": "SH-21", "condition": c, "updated": fresh} for _ in range(n)]
    mk = lambda w, rep: {**p511, "fetchedAt": fresh, "regions": {"southwest": {"roads": {"winter": w, "closures": [], "passes": [], "restrictions": [], "alerts": [],
         "counts": {"winter": len(w), "closures": 0, "passes": 0, "alerts": 0, "winterReporting": rep}}}}}
    nws_ok = {**part, "fetchedAt": fresh, "alerts": {}}
    ca = build({"nws": nws_ok, "idaho511": mk(seg(4, "Snow Covered"), 6)}, now)
    assert ca["regions"]["southwest"]["level"] == "amber" and "4 of 6" in ca["regions"]["southwest"]["summary"], ca["regions"]["southwest"]["summary"]
    cb = build({"nws": nws_ok, "idaho511": mk(seg(4, "Snow Covered"), 10)}, now)
    assert cb["regions"]["southwest"]["level"] == "green", "40% snow-covered must stay green"
    cc = build({"nws": nws_ok, "idaho511": mk(seg(1, "Icy Patches"), 10)}, now)
    assert cc["regions"]["southwest"]["level"] == "amber"
    cd = build({"nws": nws_ok, "idaho511": mk(seg(6, "Slush"), 6)}, now)
    assert cd["regions"]["southwest"]["level"] == "green", "slush alone must not color a region"
    # an alert past its end time is dropped; one with no end time reads "until further notice", never "until ."
    ex = {**part, "fetchedAt": fresh, "alerts": {"southwest": [{**al("Wind Advisory", "amber"), "ends": "2026-11-15T10:00:00+00:00"}, {**al("Winter Storm Warning", "red"), "ends": None}]}}
    ce = build({"nws": ex}, now)
    assert [a["event"] for a in ce["regions"]["southwest"]["alerts"]] == ["Winter Storm Warning"], ce["regions"]["southwest"]["alerts"]
    assert "until further notice" in ce["regions"]["southwest"]["summary"], ce["regions"]["southwest"]["summary"]
    # fire freshness is re-checked at build time: 14 days old is stale, older than that is hidden
    old_fire = lambda d: {"name": "X", "acres": 1, "containmentPct": 0, "modifiedAt": d, "status": "fresh"}
    pf = {"source": "nifc", "ok": True, "fetchedAt": fresh, "error": None, "regions": {"salmon": {"fire": {"wildfires": [old_fire("2026-11-01T20:00:00+00:00"), old_fire("2026-10-20T00:00:00+00:00")], "prescribed": []}}}}
    cf = build({"nws": nws_ok, "nifc": pf}, now)
    assert [f["status"] for f in cf["regions"]["salmon"]["fire"]["wildfires"]] == ["stale"], cf["regions"]["salmon"]["fire"]
    # passes: a pass takes the condition of the same-highway segment that names it; no name match means None (never the nearest segment)
    pp = {**p511, "fetchedAt": fresh, "regions": {"salmon": {"roads": {"winter": [
        {"name": "SH-21", "condition": "Slush", "where": "Idaho City/Beaver Creek Summit from MP 39", "updated": fresh},
        {"name": "SH-21", "condition": "Snow Covered", "where": "Banner Creek Summit/Stanley from MP 105 to MP 131", "updated": fresh},
        {"name": "SH-21", "condition": "Icy Patches", "where": "Pine Cr. Pass area", "updated": "2026-11-10T00:00:00+00:00"}],
        "closures": [], "restrictions": [], "alerts": [], "counts": {"winter": 3, "closures": 0, "passes": 4, "alerts": 0, "winterReporting": 3},
        "passes": [{"id": "1", "name": "Banner Creek", "condition": "", "fields": {"Roadway": "SH 21", "MaxElevation": "7037"}},
                   {"id": "2", "name": "Mores Creek", "condition": "", "fields": {"Roadway": "SH 21"}},
                   {"id": "3", "name": "Beaver Creek", "condition": "", "fields": {"Roadway": "US 95"}},
                   {"id": "4", "name": "Pine Creek Pass", "condition": "", "fields": {"Roadway": "SH 21"}}]}}}}
    cp = build({"nws": nws_ok, "idaho511": pp}, now)
    ps = {x["name"]: x for x in cp["regions"]["salmon"]["roads"]["passes"]}
    assert ps["Banner Creek"]["roadCondition"]["condition"] == "Snow Covered" and ps["Banner Creek"]["elevationFt"] == 7037 and ps["Banner Creek"]["highway"] == "SH 21", ps["Banner Creek"]
    assert ps["Mores Creek"]["roadCondition"] is None and ps["Mores Creek"]["elevationFt"] is None, "no segment names Mores Creek"
    assert ps["Beaver Creek"]["roadCondition"] is None, "a segment on a different highway must not match"
    assert ps["Pine Creek Pass"]["roadCondition"] is None, "a segment older than 36 h must not give a condition"
    # avalanche links come from data/avalanche_centers.json
    cv = build({"nws": nws_ok}, now)
    assert [c["id"] for c in cv["regions"]["upper-snake"]["avalanche"]] == ["gnfac", "btac"], cv["regions"]["upper-snake"]["avalanche"]
    assert cv["regions"]["southeast"]["avalanche"][0]["id"] == "uac_logan" and cv["regions"]["panhandle"]["avalanche"][0]["url"].startswith("https://")
    assert cv["avalanchePoints"]["island-park"] == ["gnfac"]
    # air forecast: shown while it covers today and is at most 3 days old (Friday's forecast still serves the weekend); never moves the region level
    day = lambda d, c, a=False: {"date": d, "aqi": 40 + 30 * c, "cat": c, "category": "x", "pollutant": "PM2.5", "actionDay": a}
    fc = lambda issued, days: {"source": "airnow_forecast", "ok": True, "fetchedAt": fresh, "error": None, "regions": {"southwest": {"airForecast": {
        "areas": [{"name": "Boise", "issued": issued, "days": days, "actionDay": False, "discussion": ""}], "source": "x", "url": "https://www.airnow.gov/"}}}}
    now_sat = dt.datetime(2026, 11, 28, 19, 0, tzinfo=dt.timezone.utc)  # Saturday noon in Boise
    cg = build({"nws": {**nws_ok, "fetchedAt": "2026-11-28T18:50:00+00:00"}, "airnow_forecast": fc("2026-11-27", [day("2026-11-27", 2), day("2026-11-28", 3, True), day("2026-11-29", 2)])}, now_sat)
    af = cg["regions"]["southwest"]["airForecast"]
    assert [d["date"] for d in af["areas"][0]["days"]] == ["2026-11-28", "2026-11-29"] and af["areas"][0]["actionDay"] is True, af
    assert cg["regions"]["southwest"]["level"] != "amber" and "Action" not in cg["regions"]["southwest"]["summary"], "an Action Day must not change the region level"
    ch = build({"nws": {**nws_ok, "fetchedAt": "2026-11-28T18:50:00+00:00"}, "airnow_forecast": fc("2026-11-24", [day("2026-11-24", 2), day("2026-11-29", 2)])}, now_sat)
    assert ch["regions"]["southwest"]["airForecast"] is None, "issued more than 3 days ago: hidden"
    ci = build({"nws": {**nws_ok, "fetchedAt": "2026-11-28T18:50:00+00:00"}, "airnow_forecast": fc("2026-11-27", [day("2026-11-27", 2)])}, now_sat)
    assert ci["regions"]["southwest"]["airForecast"] is None, "no day covers today: hidden"
    ROADS_LIVE = orig_live
    print("selftest ok")


def main():
    args = sys.argv[1:]
    d = args[args.index("--parts") + 1] if "--parts" in args else os.path.join(ROOT, "data", "parts")
    out = args[args.index("--out") + 1] if "--out" in args else os.path.join(ROOT, "data", "conditions.json")
    now = dt.datetime.now(dt.timezone.utc)
    c = build(load_parts(d), now, ski_by_region(now))
    json.dump(c, open(out, "w"), indent=1)
    print("wrote", out, "| levels:", {k: v["level"] for k, v in c["regions"].items()})


if __name__ == "__main__":
    selftest() if sys.argv[1:2] == ["selftest"] else main()
