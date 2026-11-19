#!/usr/bin/env python3
"""River flow from the NOAA National Water Prediction Service for gauges in data/noaa_gauges.json -> data/parts/noaa.json.
Used where USGS no longer publishes a gauge (Hells Canyon Dam is run by Idaho Power). Flow arrives in kcfs; stored as cfs.
Entries match the USGS river shape (id NOAA-<LID>) so build_conditions.py merges them into each region's rivers list."""
from ic_common import *

BASE = "https://api.water.noaa.gov/nwps/v1/gauges/{lid}/stageflow"
TO_CFS = {"cfs": 1.0, "kcfs": 1000.0}


def newest(obs):
    """Latest observed point that has a flow value. Points come oldest first, but do not rely on it."""
    pts = [p for p in obs.get("data", []) if isinstance(p.get("secondary"), (int, float)) and p["secondary"] > -999 and p.get("validTime")]
    return max(pts, key=lambda p: p["validTime"]) if pts else None


def one(g):
    d = http_json(BASE.format(lid=g["lid"]))
    obs = d.get("observed", {})
    p = newest(obs)
    k = TO_CFS.get((obs.get("secondaryUnits") or "").lower())
    flow = reading(round(float(p["secondary"]) * k) if p and k else None, "cfs", p["validTime"] if p else None, "NOAA NWPS", True)
    stage = reading(float(p["primary"]) if p and p.get("primary") is not None and (obs.get("primaryUnits") or "").lower() == "ft" else None, "ft",
                    p["validTime"] if p else None, "NOAA NWPS", True)
    return {"id": f"NOAA-{g['lid'].upper()}", "name": g["name"], "use": ["paddling"] if "P" in g["use"].split() or g["use"].startswith("P") else [],
            "flow": flow, "stage": stage, "trend": None}


def fetch():
    out, failed, total = {}, 0, 0
    for g in load_json("data/noaa_gauges.json")["gauges"]:
        total += 1
        try:  # one bad gauge must not fail the others
            out.setdefault(slug(g["region"]), {}).setdefault("rivers", []).append(one(g))
        except Exception as e:
            failed += 1
            print(f"NOAA {g.get('lid')}: skipped: {type(e).__name__}: {e}"[:200])
        time.sleep(1)
    if total and failed == total:
        raise RuntimeError("every NOAA gauge failed")
    return out


if __name__ == "__main__":
    run_part("noaa", fetch)
