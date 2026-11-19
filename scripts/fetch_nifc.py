#!/usr/bin/env python3
"""Wildfires and prescribed burns in Idaho (NIFC WFIGS current incident locations) -> data/parts/nifc.json.
Queries an Idaho-sized box, then keeps incidents whose location falls inside an IDFG region polygon. No key needed.
Wildfires (WF) and prescribed burns (RX) are separate lists. Old records get status 'stale' (WF 7 days, RX 14 days) and drop off later (WF 14, RX 30)."""
import datetime as dt
from ic_common import *

URL = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0/query"
BBOX = "-117.25,41.99,-111.0,49.0"
CUT = {"WF": (7, 14), "RX": (14, 30)}  # (stale after days, hide after days)


def ms(v):
    return dt.datetime.fromtimestamp(v / 1000, dt.timezone.utc) if isinstance(v, (int, float)) else None


def fetch():
    find = region_finder()
    d = http_json(q(URL, where="1=1", geometry=BBOX, geometryType="esriGeometryEnvelope", inSR="4326", spatialRel="esriSpatialRelIntersects",
                    outFields="*", returnGeometry="true", outSR="4326", f="json", resultRecordCount=2000), timeout=90)
    if not isinstance(d, dict) or "error" in d or "features" not in d:  # ArcGIS answers errors with HTTP 200; do not read that as "no fires"
        raise RuntimeError(f"NIFC returned no feature list: {str(d)[:150]}")
    now = now_utc()
    out = {}
    for f in d.get("features", []):
        a, g = f.get("attributes", {}), f.get("geometry") or {}
        kind = a.get("IncidentTypeCategory")
        if kind not in CUT or g.get("x") is None:
            continue
        rid = find(g["x"], g["y"])
        mod = ms(a.get("ModifiedOnDateTime_dt") or a.get("ModifiedOnDateTime"))
        if not rid or not mod or a.get("FireOutDateTime"):
            continue
        age = (now - mod).days
        stale_d, hide_d = CUT[kind]
        pct = a.get("PercentContained")
        if age > hide_d or (pct is not None and pct >= 100):
            continue
        item = {"name": (a.get("IncidentName") or "").title(), "acres": a.get("IncidentSize"), "containmentPct": pct,
                "county": a.get("POOCounty"), "discoveredAt": (ms(a.get("FireDiscoveryDateTime")) or now).isoformat(timespec="seconds"),
                "modifiedAt": mod.isoformat(timespec="seconds"), "status": "stale" if age > stale_d else "fresh"}
        out.setdefault(rid, {"fire": {"wildfires": [], "prescribed": []}})["fire"]["wildfires" if kind == "WF" else "prescribed"].append(item)
    return out


if __name__ == "__main__":
    run_part("nifc", fetch)
