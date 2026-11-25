#!/usr/bin/env python3
"""Air quality FORECASTS for Idaho reporting areas (state/local air agencies via AirNow) -> data/parts/airnow_forecast.json, as regions.<id>.airForecast.
Source: AirNow's public reporting-area file (one pipe-delimited download, no key). Idaho DEQ posts the forecasts; AirNow republishes them.
The existing AIRNOW_API_KEY is NOT used here (it stays with the current-readings fetcher, fetch_airnow.py).
Per area: up to six forecast days (category, AQI, main pollutant, Action Day flag) plus the forecaster's discussion text when there is one.
An Action Day never changes a region's alert level; it is shown as a badge and a "what this means" line only.
Idaho DEQ mostly forecasts on weekdays, so freshness is decided at build time (build_conditions.apply_air_forecast_freshness): a forecast is
current while it still covers today and is no more than 3 days old. Failure (HTTP error, layout not recognised, no Idaho forecast rows) raises,
so run_part keeps the last data. Data is preliminary: credit the agency, show official AQI colors (docs/reviews/ic_data_terms_check.md).

File layout (AirNow reporting-area file, checked against the real file on Nov 25, 2026; one row per area, date and pollutant; no header line):
  0 IssueDate MM/DD/YY | 1 ValidDate MM/DD/YY | 2 ValidTime | 3 TimeZone | 4 RecordSequence | 5 DataType (O observed, F forecast, Y yesterday)
  6 PrimaryFlag | 7 ReportingArea | 8 StateCode | 9 Latitude | 10 Longitude | 11 Parameter | 12 AQI (empty = category only) | 13 Category (name)
  14 ActionDay (Yes / No) | 15 Discussion (often empty) | 16 Source agency
Run this script on a real machine after any change (it prints what it found); it raises a clear error if the layout ever changes."""
import re
from ic_common import *

URL = "https://files.airnowtech.org/airnow/today/reportingarea.dat"
CATS = {1: "Good", 2: "Moderate", 3: "Unhealthy for Sensitive Groups", 4: "Unhealthy", 5: "Very Unhealthy", 6: "Hazardous"}
BY_NAME = {v.lower(): k for k, v in CATS.items()}
BY_NAME.update({"usg": 3, "unhealthy for sensitive groups": 3, "unhealthy for sensitive group": 3})
EDGES = (50, 100, 150, 200, 300)  # top of Good, Moderate, USG, Unhealthy, Very Unhealthy
NO = {"", "no", "n", "false", "0", "none", "-", "n/a", "na"}
MAX_DISCUSSION = 600
SOURCE = "Idaho DEQ forecast, via AirNow"
URL_INFO = "https://www.airnow.gov/"


def cat_of(aqi, cat_text):
    """1-6 from the category field (number or name), else from the AQI number, else None."""
    t = (cat_text or "").strip().lower()
    if t.isdigit() and int(t) in CATS:
        return int(t)
    if t in BY_NAME:
        return BY_NAME[t]
    if aqi is not None:
        return 1 + sum(aqi > e for e in EDGES)
    return None


def num(s):
    try:
        v = float(s)
        return None if v < 0 else int(round(v))  # -999 means "no AQI number, category only"
    except (TypeError, ValueError):
        return None


def clip(text, n=MAX_DISCUSSION):
    t = " ".join(re.sub(r"<[^>]+>", " ", text or "").replace("&amp;", "&").replace("&nbsp;", " ").split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def parse(text):
    """-> list of Idaho forecast rows as dicts. Raises when the file does not look like the documented layout."""
    rows, shaped, other = [], 0, 0
    for line in text.splitlines():
        f = line.split("|")
        if len(f) < 15:
            continue
        if not (re.fullmatch(r"\d\d/\d\d/\d\d", f[0].strip()) and re.fullmatch(r"\d\d/\d\d/\d\d", f[1].strip())
                and f[5].strip().upper() in ("O", "F", "Y") and re.fullmatch(r"[A-Za-z]{2}", f[8].strip())):
            other += 1
            continue
        shaped += 1
        if f[8].strip().upper() != "ID" or f[5].strip().upper() != "F":
            continue
        iso = lambda mdy: "20{2}-{0}-{1}".format(*mdy.strip().split("/"))
        aqi = num(f[12])
        try:
            lat, lon = float(f[9]), float(f[10])
        except ValueError:
            lat = lon = None
        rows.append({"issued": iso(f[0]), "date": iso(f[1]), "area": f[7].strip(), "lat": lat, "lon": lon, "pollutant": f[11].strip() or None, "aqi": aqi,
                     "cat": cat_of(aqi, f[13]), "primary": f[6].strip().upper() == "Y", "action": f[14].strip().lower() not in NO,
                     "discussion": clip(f[15]) if len(f) > 15 else ""})
    if not shaped:
        raise RuntimeError(f"AirNow reporting-area file not in the expected layout ({other} unrecognised lines)")
    if not rows:
        raise RuntimeError("AirNow file has no Idaho forecast rows")
    return rows


def build_regions(rows):
    find = region_finder()
    areas = {}
    for r in rows:
        areas.setdefault(r["area"], []).append(r)
    out, unplaced = {}, []
    for name, rs in sorted(areas.items()):
        rid = find(rs[0]["lon"], rs[0]["lat"]) if rs[0]["lat"] is not None else None
        if not rid:
            unplaced.append(name)
            continue
        days = {}
        for r in rs:  # one entry per date: the worst pollutant forecast that day (the primary one wins a tie)
            if r["cat"] is None:
                continue
            d = days.setdefault(r["date"], {"date": r["date"], "aqi": None, "cat": 0, "category": None, "pollutant": None, "actionDay": False})
            if (r["cat"], r["aqi"] or 0, r["primary"]) > (d["cat"], d["aqi"] or 0, False):
                d.update(aqi=r["aqi"], cat=r["cat"], category=CATS[r["cat"]], pollutant=r["pollutant"])
            d["actionDay"] = d["actionDay"] or r["action"]
        if not days:
            continue
        ordered = [days[k] for k in sorted(days)]
        disc = next((r["discussion"] for r in sorted(rs, key=lambda r: r["date"]) if r["discussion"]), "")
        out.setdefault(rid, {"airForecast": {"areas": [], "source": SOURCE, "url": URL_INFO}})["airForecast"]["areas"].append(
            {"name": name, "issued": max(r["issued"] for r in rs), "days": ordered, "actionDay": any(d["actionDay"] for d in ordered), "discussion": disc})
    if unplaced:
        print("AirNow forecast: areas outside every region (skipped):", ", ".join(unplaced))
    return out


def fetch():
    out = build_regions(parse(http_text(URL)))
    for rid, v in out.items():
        for a in v["airForecast"]["areas"]:
            print(f"  {rid}: {a['name']}: {len(a['days'])} days from {a['days'][0]['date']}, worst {max(d['cat'] for d in a['days'])}, action day: {a['actionDay']}")
    return out


if __name__ == "__main__":
    run_part("airnow_forecast", fetch)
