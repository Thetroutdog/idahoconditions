#!/usr/bin/env python3
"""Boise foothills trail conditions (Ridge to Rivers, City of Boise) -> data/parts/r2r.json, as regions.southwest.local.r2r.
One small ArcGIS query (about 270 staff-set trail rows, no geometry, no key). Staff set mud/dry/frozen/closed, usually early in the day.
Trail conditions: Ridge to Rivers (City of Boise). R2R staff confirmed scraping is fine with City of Boise credit (docs/reviews/ic_data_terms_check.md in the notes).
Failure (HTTP/JSON error, an ArcGIS error body, zero rows) raises, so run_part keeps the last data. A stale report (newest row over 72 h old) is not a failure.
The written daily report and its photo are a separate, later step (not in this file)."""
import datetime as dt, re
from ic_common import *

URL = "https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Ridge_to_Rivers_Trails_Assessment_Map_WFL1/FeatureServer/2/query"
FIELDS = "TrailName,Name,TrailSubSystem,Condition,ConditionNotes,ConditionDate,last_edited_date,AllWeather,R2R_Use"  # no editor/user fields
# ConditionDate is the staff-entered time stored as if it were UTC (wall clock; it reads 6-7 h early, and once flipped by 7 h between two runs),
# so "as of" uses last_edited_date, which ArcGIS stamps in real UTC. ConditionDate is only the fallback.
PAGE = 2000
STALE_H = 72
REGION = "southwest"
PAGE_URL = "https://www.ridgetorivers.org/condition-reports/"
MAP_URL = "https://www.ridgetorivers.org/trails/interactive-map/"
CREDIT = "Trail conditions, text and photos: City of Boise / Ridge to Rivers"
CODES = ("muddy", "mixed", "dry", "frozen", "frozen-am", "closed", "unknown")
AREA_MIN_OPEN = 5      # an area needs this many open (dry/frozen/mixed/muddy) trails to be named as driest or frozen
AREA_SHARE = 0.9       # ...and at least this share of them dry (or, for the frozen list, frozen)
AREA_MAX_CLOSED = 0.25  # ...and less than this share of all its trails closed (a mostly closed area is not a place to go)
MUDDY_VERDICTS = ("Mostly muddy", "Muddy in spots")


def code_of(text):
    """Match on keywords, not the exact string (en dashes, curly quotes and spacing vary). Unknown wording maps to 'unknown'."""
    t = " ".join((text or "").lower().replace("’", "'").split())
    if t.startswith("closed"):
        return "closed"
    if "frozen early" in t or "before it thaws" in t:
        return "frozen-am"
    if t.startswith("muddy") or "do not use" in t:
        return "muddy"
    if t.startswith("dry at start") or "could be muddy" in t:
        return "mixed"
    if t.startswith("frozen") or "snow covered" in t:
        return "frozen"
    if t.startswith("dry") or "tacky" in t:
        return "dry"
    return "unknown"


def plain(s, n=200):
    t = re.sub(r"<[^>]+>", " ", s or "")
    t = " ".join(t.replace("&amp;", "&").replace("&nbsp;", " ").split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat(timespec="seconds") if isinstance(ms, (int, float)) and ms > 0 else None


def rows():
    out, off = [], 0
    while True:
        d = http_json(q(URL, where="1=1", outFields=FIELDS, returnGeometry="false", f="json", resultRecordCount=PAGE, resultOffset=off), timeout=60)
        if not isinstance(d, dict) or "error" in d or "features" not in d:  # ArcGIS answers errors with HTTP 200
            raise RuntimeError(f"R2R returned no feature list: {str(d)[:150]}")
        out += [f.get("attributes") or {} for f in d["features"]]
        if not d.get("exceededTransferLimit") or not d["features"]:
            return out
        off += len(d["features"])


def summarize(rs, now=None):
    now = now or now_utc()
    if not rs:
        raise RuntimeError("R2R returned zero trail rows")
    counts = {c: 0 for c in CODES}
    subs, closed, allw, unk, original, newest = {}, {}, [], set(), {}, 0  # allw: (trail, area) of all-weather trails still usable
    for a in rs:
        sub = (a.get("TrailSubSystem") or "").strip()
        if not sub or sub == "N/A":  # access roads and unassigned rows
            continue
        text = (a.get("Condition") or "").strip()
        c = code_of(text)
        if c == "unknown" and text and text.lower() != "not evaluated":
            unk.add(text[:80])
        original.setdefault(c, text)
        name = (a.get("TrailName") or a.get("Name") or "").strip()
        counts[c] += 1
        s = subs.setdefault(sub, {"name": sub, **{k: 0 for k in CODES}, "n": 0})
        s[c] += 1
        s["n"] += 1
        newest = max(newest, a.get("last_edited_date") or a.get("ConditionDate") or 0)
        if c == "closed":
            g = closed.setdefault(plain(a.get("ConditionNotes")), {"note": plain(a.get("ConditionNotes")), "trails": [], "areas": []})
            g["trails"].append(name)
            if sub not in g["areas"]:
                g["areas"].append(sub)
        if (a.get("AllWeather") or "").lower() == "yes" and c in ("dry", "frozen", "frozen-am", "mixed"):
            allw.append((name, sub))
    if unk:
        print("R2R: unrecognized condition wording mapped to unknown:", sorted(unk))
    evald = {k: counts[k] for k in CODES if k not in ("unknown", "closed")}
    n = sum(evald.values())
    frozen = evald["frozen"] + evald["frozen-am"]
    if not n:
        verdict, tone = "No trail reports", "neutral"
    elif evald["muddy"] / n >= 0.5:
        verdict, tone = "Mostly muddy", "amber"
    elif (evald["muddy"] + evald["mixed"]) / n >= 0.5:
        verdict, tone = "Muddy in spots", "amber"
    elif frozen / n >= 0.5:
        verdict, tone = "Mostly frozen", "neutral"
    elif evald["dry"] / n >= 0.5:
        verdict, tone = "Mostly dry", "green"
    else:
        verdict, tone = "Mixed conditions", "neutral"
    parts = [f"{counts[k]} {k.replace('frozen-am', 'frozen early').replace('unknown', 'not evaluated')}" for k in ("muddy", "mixed", "dry", "frozen", "frozen-am", "closed", "unknown") if counts[k]]
    def opn(a):
        return a["dry"] + a["frozen"] + a["frozen-am"] + a["mixed"] + a["muddy"]
    def fit(a, code):  # an area worth naming: enough open trails, nearly all in `code`, and not mostly closed for the winter
        o = opn(a)
        return o >= AREA_MIN_OPEN and a[code] / o >= AREA_SHARE and a["closed"] / a["n"] < AREA_MAX_CLOSED
    areas = sorted(subs.values(), key=lambda a: a["name"])
    driest = sorted((a for a in areas if fit(a, "dry")), key=lambda a: (-a["dry"], a["name"]))[:3]
    frozen_areas = sorted((a for a in areas if fit(a, "frozen")), key=lambda a: (-a["frozen"], a["name"]))[:3]
    muddiest = sorted((a for a in areas if a["muddy"] >= AREA_MIN_OPEN), key=lambda a: (-a["muddy"], a["name"]))[:3]
    closed_areas = sorted((a for a in areas if a["closed"] and a["closed"] / a["n"] >= AREA_MAX_CLOSED), key=lambda a: (-a["closed"], a["name"]))
    aw_areas = {}
    for _, sub in allw:
        aw_areas[sub] = aw_areas.get(sub, 0) + 1
    as_of = iso(newest)
    stale = (not as_of) or (now - dt.datetime.fromisoformat(as_of)).total_seconds() > STALE_H * 3600
    return {"title": "Boise foothills trails", "verdict": verdict, "tone": tone, "summary": ", ".join(parts) + ".", "asOf": as_of, "stale": stale,
            "counts": counts, "total": sum(counts.values()), "subsystems": sorted(subs.values(), key=lambda s: s["name"]),
            "driest": driest, "frozenAreas": frozen_areas, "muddiest": muddiest, "closedAreas": closed_areas,
            "suggestAllWeather": verdict in MUDDY_VERDICTS,
            "allWeather": {"count": len(allw), "areas": [{"name": k, "count": v} for k, v in sorted(aw_areas.items(), key=lambda kv: (-kv[1], kv[0]))]},
            "closed": sorted(closed.values(), key=lambda g: -len(g["trails"])), "originalText": original,
            "url": PAGE_URL, "mapUrl": MAP_URL, "credit": CREDIT}


def fetch():
    return {REGION: {"local": {"r2r": summarize(rows())}}}


if __name__ == "__main__":
    run_part("r2r", fetch)
