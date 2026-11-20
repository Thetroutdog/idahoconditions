#!/usr/bin/env python3
"""Probe the Idaho Conditions data sources and save trimmed sample responses.

Run locally (the cloud sandbox cannot reach these hosts). Standard library only.

Setup (Terminal):
    cd <the repo folder>
    set -a; source <your local env file>; set +a
    export IC_USER_AGENT="idahoconditions.com (your-contact@example.com)"   # NWS wants a contact
    python3 scripts/probe_sources.py            # all sources
    python3 scripts/probe_sources.py nws usgs   # just some

Keys are read from environment variables and are never printed or written to disk.
Output: docs/probes/<YYYY-MM-DD>/<source>.json and probe_summary.md
"""
import json, os, sys, time, datetime, urllib.request, urllib.parse, urllib.error

UA = os.environ.get("IC_USER_AGENT", "idahoconditions-probe/0.1")
KEYS = {k: os.environ.get(k, "") for k in ("AIRNOW_API_KEY", "USGS_API_KEY", "IDAHO511_API_KEY")}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "probes",
                   datetime.date.today().isoformat())
os.makedirs(OUT, exist_ok=True)

# Representative points per Fish and Game region (lat, lon). Candidates for discussion, not final.
POINTS = {
    "1 Panhandle: Coeur d'Alene": (47.68, -116.78),
    "2 Clearwater: Lewiston": (46.42, -117.02),
    "3 Southwest: Boise": (43.62, -116.20),
    "3 Southwest: McCall": (44.91, -116.10),
    "4 Magic Valley: Twin Falls": (42.56, -114.46),
    "4 Magic Valley: Ketchum/Sun Valley": (43.68, -114.36),
    "5 Southeast: Pocatello": (42.87, -112.45),
    "6 Upper Snake: Idaho Falls": (43.49, -112.04),
    "6 Upper Snake: Island Park": (44.42, -111.37),
    "7 Salmon: Salmon": (45.18, -113.90),
    "7 Salmon: Stanley": (44.22, -114.93),
}
ID_BBOX = (-117.25, 41.99, -111.0, 49.0)  # lon/lat envelope around Idaho

results = {}  # source -> list of call records


def redact(s):
    for v in KEYS.values():
        if v:
            s = s.replace(v, "<KEY>")
    return s


def trim(o, n=5, depth=0):
    if isinstance(o, list):
        out = [trim(x, n, depth + 1) for x in o[:n]]
        if len(o) > n:
            out.append(f"... {len(o) - n} more items")
        return out
    if isinstance(o, dict):
        return {k: trim(v, n, depth + 1) for k, v in list(o.items())[:40]}
    if isinstance(o, str) and len(o) > 300:
        return o[:300] + "..."
    return o


def call(source, label, url, headers=None, parse="json", pause=1.0):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    rec = {"label": label, "url": redact(url)}
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read()
            rec.update(status=r.status, bytes=len(body),
                       rate_headers={k: v for k, v in r.headers.items()
                                     if "ratelimit" in k.lower() or "retry" in k.lower() or k.lower() in ("cache-control", "expires", "last-modified")})
        if parse == "json":
            data = json.loads(body)
            rec["data"] = data
        else:
            rec["text"] = body.decode("utf-8", "replace")[:1500]
    except urllib.error.HTTPError as e:
        rec.update(status=e.code, error=redact(e.read().decode("utf-8", "replace")[:500]))
    except Exception as e:  # network, JSON, timeout
        rec.update(status=None, error=redact(f"{type(e).__name__}: {e}"))
    rec["ms"] = int((time.time() - t0) * 1000)
    results.setdefault(source, []).append(rec)
    flag = rec.get("status")
    print(f"[{source}] {label}: {flag} ({rec['ms']} ms)")
    time.sleep(pause)
    return rec


def q(base, **params):
    return base + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})


# ---------------- NWS ----------------
def probe_nws():
    for name, (lat, lon) in POINTS.items():
        p = call("nws", f"points {name}", f"https://api.weather.gov/points/{lat},{lon}")
        props = (p.get("data") or {}).get("properties", {})
        if props.get("forecast"):
            rec = call("nws", f"forecast {name}", props["forecast"])
            periods = ((rec.get("data") or {}).get("properties") or {}).get("periods", [])
            rec["data"] = {"zone": props.get("forecastZone"), "county": props.get("county"),
                           "office": props.get("gridId"), "periods_returned": len(periods),
                           "first_two": periods[:2],
                           "updateTime": ((rec.get("data") or {}).get("properties") or {}).get("updateTime"),
                           "generatedAt": ((rec.get("data") or {}).get("properties") or {}).get("generatedAt")}
        if p.get("data"):
            p["data"] = {"forecastZone": props.get("forecastZone"), "county": props.get("county"),
                         "fireWeatherZone": props.get("fireWeatherZone"), "gridId": props.get("gridId"),
                         "relativeLocation": (props.get("relativeLocation") or {}).get("properties")}
    a = call("nws", "alerts active, state=ID", "https://api.weather.gov/alerts/active?area=ID",
             headers={"Accept": "application/geo+json"})
    feats = (a.get("data") or {}).get("features", [])
    a["data"] = {"count": len(feats),
                 "events": [{"event": f["properties"].get("event"), "severity": f["properties"].get("severity"),
                             "areaDesc": f["properties"].get("areaDesc"), "ends": f["properties"].get("ends"),
                             "zones": f["properties"].get("affectedZones", [])[:3]} for f in feats[:10]]}


    # Idaho may have zero alerts today, so also check Montana to verify the alert shape
    m = call("nws", "alerts active, state=MT (shape check)", "https://api.weather.gov/alerts/active?area=MT",
             headers={"Accept": "application/geo+json"})
    mf = (m.get("data") or {}).get("features", [])
    m["data"] = {"count": len(mf), "first_properties_keys": sorted((mf[0]["properties"].keys())) if mf else [],
                 "sample": [{k: f["properties"].get(k) for k in ("event", "severity", "urgency", "headline", "areaDesc", "onset", "ends", "affectedZones")} for f in mf[:2]]}


# ---------------- AirNow ----------------
def probe_airnow():
    key = KEYS["AIRNOW_API_KEY"]
    if not key:
        print("[airnow] AIRNOW_API_KEY not set, skipping"); return
    base = "https://www.airnowapi.org"
    for name, (lat, lon) in list(POINTS.items()):
        # New service named in the June 2026 notice (parameters are my best guess; check docs if it errors)
        call("airnow", f"NEW ziplatlong {name}",
             q(base + "/aq/observation/current/ziplatlong/", latitude=lat, longitude=lon, format="application/json", API_KEY=key),
             pause=1)
    # Old service, retired 2026-09-30 per notice: expect an error. Included once to confirm.
    lat, lon = POINTS["3 Southwest: Boise"]
    call("airnow", "OLD latLong (retired 2026-09-30?) Boise",
         q(base + "/aq/observation/latLong/current/", latitude=lat, longitude=lon, distance=50, format="application/json", API_KEY=key))


# ---------------- NRCS SNOTEL (AWDB) ----------------
AWDB = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
WANTED = ["brundage", "secesh", "banner", "bogus", "galena", "lost wood", "chocolate", "mores creek",
          "stanley", "gold fork", "paradise", "dollarhide", "trail creek", "moose creek", "schweitzer", "lookout"]


def probe_snotel():
    st = call("snotel", "stations Idaho SNOTEL active",
              q(AWDB + "/stations", stateCodes="ID", networkCodes="SNTL", activeOnly="true"))
    stations = st.get("data") or []
    summary = {"count": len(stations)}
    picked = []
    for s in stations if isinstance(stations, list) else []:
        n = (s.get("name") or "").lower()
        if any(w in n for w in WANTED):
            picked.append({k: s.get(k) for k in ("stationTriplet", "name", "latitude", "longitude", "elevation", "countyName", "huc")})
    summary["matches_for_wanted_names"] = picked
    summary["first_raw_station"] = stations[0] if stations else None
    sntl = [x for x in stations if str(x.get("stationTriplet", "")).endswith(":ID:SNTL")] if isinstance(stations, list) else []
    summary["sntl_count"] = len(sntl)
    st["digest"] = [{k: x.get(k) for k in ("stationTriplet", "name", "countyName", "latitude", "longitude", "elevation", "dataTimeZone", "beginDate")} for x in sntl]
    st["data"] = summary
    end = datetime.date.today(); begin = end - datetime.timedelta(days=14)
    for s in picked[:6]:
        call("snotel", f"daily WTEQ,SNWD {s['name']}",
             q(AWDB + "/data", stationTriplets=s["stationTriplet"], elements="WTEQ,SNWD,PREC,TOBS",
               duration="DAILY", beginDate=begin.isoformat(), endDate=end.isoformat(), returnFlags="false"))
    if sntl:  # latest values for every Idaho SNOTEL site in one call
        triplets = ",".join(x["stationTriplet"] for x in sntl)
        r = call("snotel", "latest daily SNWD,WTEQ all Idaho SNTL (last 3 days)",
                 q(AWDB + "/data", stationTriplets=triplets, elements="SNWD,WTEQ", duration="DAILY",
                   beginDate=(end - datetime.timedelta(days=3)).isoformat(), endDate=end.isoformat(), returnFlags="false"))
        dig = []
        for item in (r.get("data") or []):
            row = {"triplet": item.get("stationTriplet")}
            for el in item.get("data", []):
                vals = [v for v in el.get("values", []) if v.get("value") is not None]
                row[el["stationElement"]["elementCode"]] = vals[-1] if vals else None
            dig.append(row)
        r["digest"] = dig
        r["data"] = {"stations_returned": len(dig)}
    if picked:
        s = picked[0]
        call("snotel", f"HOURLY SNWD {s['name']} (last 2 days)",
             q(AWDB + "/data", stationTriplets=s["stationTriplet"], elements="SNWD,WTEQ,TOBS", duration="HOURLY",
               beginDate=(end - datetime.timedelta(days=2)).isoformat(), endDate=end.isoformat(), returnFlags="false"))
        call("snotel", f"median normals (central tendency) {s['name']}",
             q(AWDB + "/data", stationTriplets=s["stationTriplet"], elements="WTEQ", duration="DAILY",
               beginDate=begin.isoformat(), endDate=end.isoformat(), centralTendencyType="MEDIAN", returnFlags="false"))


# ---------------- USGS Water Data (OGC API) ----------------
GAUGES = {  # CANDIDATE site ids, unverified. The probe reports which exist.
    "Boise R at Glenwood Br": "USGS-13206000",
    "SF Payette at Lowman": "USGS-13235000",
    "NF Payette (mockup id)": "USGS-13246000",
    "Payette R nr Emmett": "USGS-13247500",
    "Salmon R at Salmon": "USGS-13302500",
    "Salmon R at White Bird": "USGS-13317000",
    "Clearwater R at Spalding": "USGS-13342500",
    "Snake R nr Heise": "USGS-13037500",
    "Snake R nr Twin Falls": "USGS-13094000",
    "Spokane R nr Post Falls": "USGS-12419000",
}


def probe_usgs():
    hdr = {"X-Api-Key": KEYS["USGS_API_KEY"]} if KEYS["USGS_API_KEY"] else {}
    base = "https://api.waterdata.usgs.gov/ogcapi/v0"
    c = call("usgs", "collections list", base + "/collections?f=json", headers=hdr)
    cols = [x.get("id") for x in (c.get("data") or {}).get("collections", [])]
    c["data"] = {"collections": cols, "using_key": bool(hdr)}
    if not cols:  # docs mention v1 as well
        base = "https://api.waterdata.usgs.gov/ogcapi/v1"
        c2 = call("usgs", "collections list (v1)", base + "/collections?f=json", headers=hdr)
        c2["data"] = {"collections": [x.get("id") for x in (c2.get("data") or {}).get("collections", [])]}
    bb = ",".join(str(x) for x in ID_BBOX)
    a = call("usgs", "latest-continuous discharge ALL in Idaho bbox",
             q(base + "/collections/latest-continuous/items", bbox=bb, parameter_code="00060", f="json", limit=1000), headers=hdr)
    a["digest"] = [{"id": f["properties"].get("monitoring_location_id"), "time": f["properties"].get("time"),
                    "value": f["properties"].get("value"), "unit": f["properties"].get("unit_of_measure"),
                    "status": f["properties"].get("approval_status"), "lon": (f.get("geometry") or {}).get("coordinates", [None, None])[0],
                    "lat": (f.get("geometry") or {}).get("coordinates", [None, None])[1]}
                   for f in (a.get("data") or {}).get("features", [])]
    a["data"] = {"returned": len(a["digest"])}
    n = call("usgs", "monitoring-locations Idaho (state_code=16), streams (names)",
             q(base + "/collections/monitoring-locations/items", state_code="16", site_type_code="ST", f="json", limit=1000), headers=hdr)
    n["digest"] = [{"id": f["properties"].get("id"), "name": f["properties"].get("monitoring_location_name"),
                    "county": f["properties"].get("county_name"), "state": f["properties"].get("state_name"),
                    "tz": f["properties"].get("time_zone_abbreviation")}
                   for f in (n.get("data") or {}).get("features", [])]
    n["data"] = {"returned": len(n["digest"])}
    ids = ",".join(GAUGES.values())
    call("usgs", "latest-continuous discharge, candidate gauges",
         q(base + "/collections/latest-continuous/items", monitoring_location_id=ids, parameter_code="00060", f="json", limit=50),
         headers=hdr)
    end = datetime.date.today(); begin = end - datetime.timedelta(days=30)
    for name in ("SF Payette at Lowman", "Boise R at Glenwood Br"):
        call("usgs", f"daily discharge 30d {name}",
             q(base + "/collections/daily/items", monitoring_location_id=GAUGES[name], parameter_code="00060",
               time=f"{begin.isoformat()}/{end.isoformat()}", f="json", limit=40), headers=hdr)
    call("usgs", "monitoring-locations lookup (names for candidate ids)",
         q(base + "/collections/monitoring-locations/items", id=ids, f="json", limit=20), headers=hdr)


# ---------------- NIFC WFIGS ----------------
NIFC = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services"


def probe_nifc():
    env = ",".join(str(x) for x in ID_BBOX)
    common = dict(where="1=1", geometry=env, geometryType="esriGeometryEnvelope", inSR="4326",
                  spatialRel="esriSpatialRelIntersects", outFields="*", returnGeometry="false", f="json")
    for layer in ("WFIGS_Incident_Locations_Current", "WFIGS_Interagency_Perimeters_Current"):
        r = call("nifc", f"{layer} Idaho envelope", q(f"{NIFC}/{layer}/FeatureServer/0/query", **common))
        feats = (r.get("data") or {}).get("features", [])
        keep = ("IncidentName", "POOState", "POOCounty", "IncidentTypeCategory", "IncidentTypeKind", "IncidentSize",
                "PercentContained", "FireDiscoveryDateTime", "ModifiedOnDateTime", "ModifiedOnDateTime_dt", "FireOutDateTime",
                "poly_IncidentName", "poly_GISAcres", "poly_DateCurrent", "attr_POOState", "attr_IncidentTypeCategory",
                "attr_PercentContained", "attr_ModifiedOnDateTime_dt")
        r["digest"] = [{k: f.get("attributes", {}).get(k) for k in keep if k in f.get("attributes", {})} for f in feats]
        r["data"] = {"count_in_idaho_bbox": len(feats), "all_field_names": sorted({k for f in feats for k in f.get("attributes", {})}),
                     "exceededTransferLimit": (r.get("data") or {}).get("exceededTransferLimit"),
                     "fields": sorted({k for f in feats for k in f.get("attributes", {})})[:80],
                     "sample_attributes": [f.get("attributes") for f in feats[:3]]}


# ---------------- Idaho 511 ----------------
def probe_511():
    call("idaho511", "WZDx work zones (keyless per plan)", "https://511.idaho.gov/api/wzdx")
    key = KEYS["IDAHO511_API_KEY"]
    if not key:
        print("[idaho511] IDAHO511_API_KEY not set: skipping keyed endpoints (waiting on key)"); return
    for ep in ("mountainpasses", "winterroads", "event", "alerts", "cameras", "weatherstations"):
        call("idaho511", ep, q(f"https://511.idaho.gov/api/v2/get/{ep}", key=key, format="json"), pause=7)  # 10 calls / 60 s


PROBES = {"nws": probe_nws, "airnow": probe_airnow, "snotel": probe_snotel, "usgs": probe_usgs,
          "nifc": probe_nifc, "idaho511": probe_511}


def main():
    want = sys.argv[1:] or list(PROBES)
    for name in want:
        if name not in PROBES:
            print("unknown source", name, "choose from", list(PROBES)); continue
        PROBES[name]()
    lines = ["# Probe summary", f"Run: {datetime.datetime.now().isoformat(timespec='seconds')}", "",
             "| Source | Call | HTTP | ms | bytes |", "|---|---|---|---|---|"]
    for src, recs in results.items():
        with open(os.path.join(OUT, f"{src}.json"), "w") as f:
            json.dump([{k: (trim(v) if k == "data" else v) for k, v in r.items()} for r in recs], f, indent=1, default=str)
        digests = [{"label": r["label"], "digest": r["digest"]} for r in recs if r.get("digest") is not None]
        if digests:
            with open(os.path.join(OUT, f"{src}_digest.json"), "w") as f:
                json.dump(digests, f, indent=1, default=str)
        for r in recs:
            lines.append(f"| {src} | {r['label']} | {r.get('status')} | {r['ms']} | {r.get('bytes', '')} |")
    with open(os.path.join(OUT, "probe_summary.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\nWrote", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
