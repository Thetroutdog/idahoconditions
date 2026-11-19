#!/usr/bin/env python3
"""Parse docs/Idaho_Outdoor_Activities_by_Region.pdf (from Grok) into data/activities.json:
region -> activity -> [{spot, facts, town, sources:[{label,url}]}]. Spots are placed by county per Idaho Code 36-102 (as the guide says).
Needs pdfplumber (pip install pdfplumber). Run: python3 scripts/parse_activities.py"""
import json, os, re, sys
import pdfplumber

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PDF = os.path.join(ROOT, "docs", "Idaho_Outdoor_Activities_by_Region.pdf")
REGIONS = ["Panhandle", "Clearwater", "Southwest", "Magic Valley", "Southeast", "Upper Snake", "Salmon"]
ACTIVITIES = ["Downhill Skiing", "Cross-Country / Nordic Skiing", "Backcountry Skiing", "Snowmobiling", "Whitewater Rafting / Kayaking", "Fishing",
              "Hiking", "Backpacking / Wilderness", "Mountain Biking", "Motorcycle / Adventure Riding (Idaho BDR & OHV)", "Hot Springs",
              "Rock Climbing", "Paddleboarding / Flatwater"]
clean = lambda s: re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def overlaps(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def main():
    out, meta = {}, {}
    region = None
    last_act = None
    with pdfplumber.open(PDF) as pdf:
        for pn, page in enumerate(pdf.pages, 1):
            lines = [(w["top"], w["text"]) for w in page.extract_text_lines()] if hasattr(page, "extract_text_lines") else []
            text_lines = [(l["top"], l["text"]) for l in page.extract_text_lines()]
            for _, t in text_lines:
                m = re.match(r"^(\w[\w ]*?) Region$", t.strip())
                if m and m.group(1) in REGIONS:
                    region = m.group(1)
            links = [(h["x0"], h["top"], h["x1"], h["bottom"], h["uri"]) for h in page.hyperlinks]
            for tb in page.find_tables():
                rows = tb.rows
                if not rows or not region:
                    continue
                head = [clean(c) for c in tb.extract()[0]]
                if not head or head[0] != "Spot":
                    continue
                above = [t for top, t in text_lines if top < tb.bbox[1] and tb.bbox[1] - top < 40]
                act = next((a for a in reversed(above) if a.strip() in ACTIVITIES), None)
                if not act:  # table continues from the previous page: reuse the last activity heading
                    act = last_act
                    if not act:
                        print(f"page {pn}: table with no activity heading, region {region}")
                        continue
                last_act = act
                for row, cells in zip(rows[1:], tb.extract()[1:]):
                    spot, facts, town, src = (clean(c) for c in cells[:4])
                    if not spot:
                        continue
                    srcbox = row.cells[3] if len(row.cells) > 3 else None
                    urls = [l[4] for l in links if srcbox and overlaps(l[:4], srcbox)]
                    labels = [s.strip() for s in (cells[3] or "").split("\n")]
                    out.setdefault(region, {}).setdefault(act.strip(), []).append(
                        {"spot": spot, "facts": facts, "town": town, "source": src, "urls": list(dict.fromkeys(urls))})
    total = sum(len(v) for r in out.values() for v in r.values())
    nolink = sum(1 for r in out.values() for v in r.values() for s in v if not s["urls"])
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "activities.json"), "w"), indent=1)
    print("spots:", total, "(guide says 268) | spots with no link found:", nolink)
    for r in REGIONS:
        print(r, sum(len(v) for v in out.get(r, {}).values()), {a: len(v) for a, v in out.get(r, {}).items()})


if __name__ == "__main__":
    main()
