#!/usr/bin/env python3
"""Suggest USGS gauge matches for river-type spots (whitewater, fishing, paddle) by name overlap within a region.
Writes data/spot_sources.json with confirmed:false. The site ignores entries until you set confirmed:true.
    python3 scripts/suggest_spot_sources.py"""
import json, os, re
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
spots = json.load(open(os.path.join(ROOT, "data", "spots.json")))["spots"]
st = json.load(open(os.path.join(ROOT, "data", "selected_stations.json")))
STOP = {"river", "fork", "near", "the", "at", "and", "creek", "lake", "of", "to", "from", "south", "north", "main", "middle", "id"}
tok = lambda s: {t for t in re.findall(r"[a-z]+", s.lower()) if t not in STOP and len(t) > 2}
slug = lambda r: r.lower().replace(" ", "-")
out, lines = {}, []
for sp in spots:
    if sp["activity"] not in ("whitewater", "fishing", "paddle"): continue
    best = None
    for g in st["rivers"]:
        if slug(g["region"]) != sp["region"]: continue
        n = len(tok(sp["name"] + " " + sp["desc"]) & tok(g["name"]))
        if n and (best is None or n > best[0]): best = (n, g)
    if best:
        gid = best[1]["usgs_id"].replace("USGS-", "")
        out[sp["id"]] = {"usgs": gid, "gauge": best[1]["name"], "confirmed": False}
        lines.append(f"{sp['region']:13} {sp['name'][:44]:44} -> {best[1]['name']} ({gid})")
json.dump(out, open(os.path.join(ROOT, "data", "spot_sources.json"), "w"), indent=1)
print("\n".join(lines)); print(f"\n{len(out)} suggestions written to data/spot_sources.json (all confirmed:false)")
