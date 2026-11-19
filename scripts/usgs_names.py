#!/usr/bin/env python3
"""Fetch ALL Idaho stream-site names from USGS (follows pagination), join them with the latest-continuous readings and
the region assignment, and write docs/probes/<latest>/gauges_by_region.md (fresh gauges only, grouped by region).
Run on Eric's Mac after probe_sources.py and region_tools.py assign. Standard library only."""
import json, os, glob, sys, urllib.request, datetime as dt

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
UA = os.environ.get("IC_USER_AGENT", "idahoconditions-probe/0.1")
KEY = os.environ.get("USGS_API_KEY", "")
START = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items?f=json&state_code=16&site_type_code=ST&limit=1000"


def get(url):
    h = {"User-Agent": UA, "Accept": "application/json"}
    if KEY:
        h["X-Api-Key"] = KEY
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=90) as r:
        return json.loads(r.read())


def all_names():
    names, url, pages = {}, START, 0
    while url and pages < 20:
        d = get(url)
        for f in d.get("features", []):
            p = f.get("properties", {})
            names[f.get("id") or p.get("id")] = p.get("monitoring_location_name")
        url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
        pages += 1
        print("page", pages, "names so far", len(names))
    return names


def main():
    d = sorted(glob.glob(os.path.join(ROOT, "docs", "probes", "2*")))[-1]
    names = all_names()
    json.dump(names, open(os.path.join(d, "usgs_all_names.json"), "w"), indent=0)
    vals = {v["id"]: v for v in json.load(open(os.path.join(d, "usgs_digest.json")))[0]["digest"]}
    A = json.load(open(os.path.join(d, "region_assignment.json")))
    now = dt.datetime.now(dt.timezone.utc)
    out = ["# Fresh USGS gauges by region (reading under 3 days old)\n"]
    for reg, blocks in A["regions"].items():
        if reg.startswith("outside"):
            continue
        rows = []
        for k, v in blocks.items():
            if not k.startswith("latest"):
                continue
            for x in v:
                r = vals.get(x["id"])
                if not r:
                    continue
                age = (now - dt.datetime.fromisoformat(r["time"])).total_seconds() / 86400
                if age < 3:
                    rows.append((names.get(x["id"]) or "?", x["id"], r["value"], r.get("status")))
        out.append(f"\n## {reg} ({len(rows)})\n")
        out += [f"- {n} | {i} | {val} cfs | {st}" for n, i, val, st in sorted(rows)]
    p = os.path.join(d, "gauges_by_region.md")
    open(p, "w").write("\n".join(out) + "\n")
    print("wrote", p)


if __name__ == "__main__":
    main()
