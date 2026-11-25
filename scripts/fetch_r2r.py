#!/usr/bin/env python3
"""Boise foothills trail conditions (Ridge to Rivers, City of Boise) -> data/parts/r2r.json, as regions.southwest.local.r2r.
One small ArcGIS query (about 270 staff-set trail rows, no geometry, no key). Staff set mud/dry/frozen/closed, usually early in the day.
Trail conditions: Ridge to Rivers (City of Boise). R2R staff confirmed scraping is fine with City of Boise credit (docs/reviews/ic_data_terms_check.md in the notes).
Failure (HTTP/JSON error, an ArcGIS error body, zero rows) raises, so run_part keeps the last data. A stale report (newest row over 72 h old) is not a failure.
The written daily report and its photo are a separate, later step (not in this file)."""
import datetime as dt, re
from ic_common import *

URL = "https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Ridge_to_Rivers_Trails_Assessment_Map_WFL1/FeatureServer/2/query"
FIELDS = "TrailName,Name,TrailSubSystem,Condition,ConditionNotes,ConditionDate,AllWeather,R2R_Use"  # no editor/user fields
PAGE = 2000
STALE_H = 72
REGION = "southwest"
PAGE_URL = "https://www.ridgetorivers.org/condition-reports/"
MAP_URL = "https://www.ridgetorivers.org/trails/interactive-map/"
CREDIT = "Trail conditions, text and photos: City of Boise / Ridge to Rivers"
CODES = ("muddy", "mixed", "dry", "frozen", "frozen-am", "closed", "unknown")


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
    subs, closed, allw, unk, original, newest = {}, {}, [], set(), {}, 0
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
        newest = max(newest, a.get("ConditionDate") or 0)
        if c == "closed":
            g = closed.setdefault(plain(a.get("ConditionNotes")), {"note": plain(a.get("ConditionNotes")), "trails": [], "areas": []})
            g["trails"].append(name)
            if sub not in g["areas"]:
                g["areas"].append(sub)
        if (a.get("AllWeather") or "").lower() == "yes" and c in ("dry", "frozen", "frozen-am", "mixed"):
            allw.append(name)
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
    parts = [f"{counts[k]} {k.replace('frozen-am', 'frozen early')}" for k in ("muddy", "mixed", "dry", "frozen", "frozen-am", "closed") if counts[k]]
    ranked = []
    for s in subs.values():
        ok = s["dry"] + s["frozen"] + s["frozen-am"]
        opn = ok + s["muddy"] + s["mixed"]
        if opn >= 3 and ok / opn >= 0.75:
            ranked.append((-ok / opn, -opn, s["name"]))
    best = [x[2] for x in sorted(ranked)[:3]]
    as_of = iso(newest)
    stale = (not as_of) or (now - dt.datetime.fromisoformat(as_of)).total_seconds() > STALE_H * 3600
    return {"title": "Boise foothills trails", "verdict": verdict, "tone": tone, "summary": ", ".join(parts) + ".", "asOf": as_of, "stale": stale,
            "counts": counts, "total": sum(counts.values()), "subsystems": sorted(subs.values(), key=lambda s: s["name"]),
            "bestBets": best, "allWeather": {"count": len(allw), "names": sorted(set(allw))[:12]},
            "closed": sorted(closed.values(), key=lambda g: -len(g["trails"])), "originalText": original,
            "url": PAGE_URL, "mapUrl": MAP_URL, "credit": CREDIT}


def fetch():
    return {REGION: {"local": {"r2r": summarize(rows())}}}


if __name__ == "__main__":
    run_part("r2r", fetch)
