#!/usr/bin/env python3
"""Find spots and edit their outbound links. Edits go to data/spot_links.json, so the catalog (spots.json) stays untouched.
    python3 scripts/spot_links.py find brundage
    python3 scripts/spot_links.py show southwest-brundage-mountain
    python3 scripts/spot_links.py add southwest-brundage-mountain "Brundage" https://www.brundage.com/
    python3 scripts/spot_links.py remove southwest-brundage-mountain skiidaho"""
import json, os, sys
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
D = os.path.join(ROOT, "data")
load = lambda f: json.load(open(os.path.join(D, f)))
spots = load("spots.json")["spots"]
try: spots += load("spots_extra.json")["spots"]
except Exception: pass
by_id = {s["id"]: s for s in spots}
edits = load("spot_links.json")

def show(i):
    s = by_id[i]; e = edits.get(i, {})
    print(f"{i}\n  {s['name']} ({s['activity']}, {s['region']})")
    for l in s["sources"]: print(f"  catalog: {l['label']}  {l['url']}")
    if e: print(f"  edits:   {json.dumps({k: v for k, v in e.items()})}")

def save():
    json.dump(edits, open(os.path.join(D, "spot_links.json"), "w"), indent=1); print("saved data/spot_links.json")

a = sys.argv[1:]
if len(a) >= 2 and a[0] == "find":
    q = a[1].lower()
    for s in spots:
        if q in s["name"].lower() or q in s["id"]: print(f"{s['id']:55} {s['name']} [{s['activity']}]")
elif len(a) == 2 and a[0] == "show": show(a[1])
elif len(a) == 4 and a[0] == "add" and a[1] in by_id:
    edits.setdefault(a[1], {}).setdefault("add", []).append({"label": a[2], "url": a[3]}); save(); show(a[1])
elif len(a) == 3 and a[0] == "remove" and a[1] in by_id:
    edits.setdefault(a[1], {}).setdefault("remove", []).append(a[2]); save(); show(a[1])
else: print(__doc__)
