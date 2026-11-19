#!/usr/bin/env python3
"""One-time (rerun any time) crawl: for every ski area, Nordic area and snowmobile area, find the page where the operator posts
snow / trail / mountain conditions -> data/resort_pages.json, plus a review list at data/resort_pages_review.txt.
Run on your Mac:  python3 scripts/crawl_resort_pages.py           (about 10-15 minutes, polite: 1 request per host per 2 s, robots.txt obeyed)
Then look at the review list, fix anything wrong in data/resort_pages_manual.json ({spot_id: {"conditions": url}}), and apply:
                  python3 scripts/crawl_resort_pages.py --apply   (adds the links to data/spot_links.json; never removes or edits existing ones)
Where no conditions page is found the area's main landing page is added instead, as asked. Standard library only."""
import json, os, re, sys, urllib.parse
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import web_crawl as wc

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
D = lambda *a: os.path.join(ROOT, "data", *a)
KINDS = {"ski", "nordic", "snowmobile"}
SKIP_HOSTS = ("skiidaho.us", "wikipedia.org", "facebook.com", "instagram.com", "youtube.com")
GENERIC = ("/park-activity/",)  # IDPR "all parks that do X" pages are not one area's own page

# (regex on link text or url path, points). Best score wins; ties go to the shorter URL.
SCORES = [
    (r"snow ?report|mountain ?report|conditions ?report|trail ?report|grooming ?report|groom(ing)? (report|status|update)", 10),
    (r"mountain (status|conditions)|lift (and trail )?status|trail (status|conditions)|snow (conditions|update)|current conditions|conditions", 8),
    (r"grooming|trail updates?|weather|snow", 4),
    (r"status", 3),
]
NEGATIVE = r"blog|news|career|job|privacy|terms|shop|store|donat|gift|rental|lesson|season ?pass|ticket|lodging|dining|menu|contact|about|history|facebook|instagram|twitter|youtube|cams?\b|webcam"
NAV = r"the mountain|winter|trails?|conditions|mountain info|snow|nordic|plan your"  # one-hop navigation links worth opening


def score(url, text):
    t = f"{text} {urllib.parse.urlsplit(url).path}".lower()
    if re.search(NEGATIVE, text.lower()) and not re.search(r"report|status|conditions", text.lower()):
        return 0
    return max((pts for pat, pts in SCORES if re.search(pat, t)), default=0)


def best_link(links, host):
    cand = [(score(u, t), -len(u), u, t) for u, t in links if urllib.parse.urlsplit(u).netloc.replace("www.", "") == host.replace("www.", "")]
    cand = [c for c in cand if c[0] > 0]
    return max(cand) if cand else None


def targets():
    spots = []
    for f in ("spots.json", "spots_extra.json"):
        spots += json.load(open(D(f)))["spots"]
    sites = json.load(open(D("resort_sites.json")))["sites"]
    manual = json.load(open(D("resort_pages_manual.json"))) if os.path.exists(D("resort_pages_manual.json")) else {}
    out = []
    for sp in spots:
        if sp["activity"] not in KINDS:
            continue
        seeds = []
        if sp["id"] in sites:
            seeds.append(sites[sp["id"]]["site"])
        seeds += [s["url"] for s in sp.get("sources", []) if not any(h in s["url"] for h in SKIP_HOSTS) and not any(g in s["url"] for g in GENERIC)]
        out.append((sp, list(dict.fromkeys(seeds)), sites.get(sp["id"], {}).get("conditions"), manual.get(sp["id"], {}).get("conditions")))
    return out


def crawl(sp, seeds, known, manual):
    """-> dict with landing, conditions (or None), how it was found."""
    if manual:
        return {"landing": seeds[0] if seeds else None, "conditions": manual, "via": "manual"}
    res = {"landing": None, "conditions": None, "via": None, "note": ""}
    for seed in seeds:
        final, html = wc.fetch(seed)
        if not final:
            res["note"] += f"{seed}: {html}. "
            continue
        res["landing"] = res["landing"] or final
        host = urllib.parse.urlsplit(final).netloc
        text, links = wc.parse(html, final)
        hit = best_link(links, host)
        if hit and hit[0] >= 8:
            res.update(conditions=hit[2], via=f"link '{hit[3][:40]}' on landing page", score=hit[0])
            break
        # one hop: open up to 3 navigation links ("The Mountain", "Winter", "Trails") and look again
        navs = [u for u, t in links if urllib.parse.urlsplit(u).netloc == host and re.search(NAV, t.lower()) and not re.search(NEGATIVE, t.lower())][:3]
        best2 = hit
        for n in navs:
            f2, h2 = wc.fetch(n)
            if not f2:
                continue
            _, l2 = wc.parse(h2, f2)
            h = best_link(l2, host)
            if h and (not best2 or h[0] > best2[0]):
                best2 = h
        if best2 and best2[0] >= 4:
            res.update(conditions=best2[2], via=f"link '{best2[3][:40]}' one click in", score=best2[0])
            break
    if known and not res["conditions"]:  # a conditions page I found by search; used when the crawl could not confirm one
        res.update(conditions=known, via="known page (from research)")
    return res


def verify(res):
    if res.get("conditions") and res["via"] not in ("manual",):
        f, h = wc.fetch(res["conditions"])
        res["conditionsOk"] = bool(f)
        if not f:
            res["note"] = (res.get("note", "") + f"conditions link did not load: {h}").strip()
    return res


def main():
    out = json.load(open(D("resort_pages.json"))) if os.path.exists(D("resort_pages.json")) else {}
    rows = targets()
    print(f"{len(rows)} areas to look at")
    for i, (sp, seeds, known, manual) in enumerate(rows, 1):
        if not seeds and not manual and not known:
            out[sp["id"]] = {"landing": None, "conditions": None, "note": "no website on file"}
            print(f"[{i}/{len(rows)}] {sp['id']}: no website on file")
            continue
        r = verify(crawl(sp, seeds, known, manual))
        r["checkedAt"] = date.today().isoformat()
        out[sp["id"]] = r
        print(f"[{i}/{len(rows)}] {sp['id']}: {'conditions ' + r['conditions'] if r.get('conditions') else 'landing only ' + str(r.get('landing'))}", flush=True)
        json.dump(out, open(D("resort_pages.json"), "w"), indent=1)
    byid = {sp["id"]: sp for sp, *_ in rows}
    with open(D("resort_pages_review.txt"), "w") as f:
        for k, r in sorted(out.items(), key=lambda kv: (byid.get(kv[0], {}).get("activity", ""), kv[0])):
            tag = "OK " if r.get("conditions") and r.get("conditionsOk", True) else ("LANDING " if r.get("landing") else "NOTHING ")
            f.write(f"{tag}{k}\t{r.get('conditions') or r.get('landing')}\t{r.get('via') or ''}\t{r.get('note', '')}\n")
    n_c = sum(1 for r in out.values() if r.get("conditions"))
    print(f"\nconditions page found: {n_c}; landing page only: {sum(1 for r in out.values() if not r.get('conditions') and r.get('landing'))}; nothing: {sum(1 for r in out.values() if not r.get('landing') and not r.get('conditions'))}")
    print("review list: data/resort_pages_review.txt  (fix wrong ones in data/resort_pages_manual.json, rerun, then --apply)")


def apply():
    out = json.load(open(D("resort_pages.json")))
    path = D("spot_links.json")
    links = json.load(open(path)) if os.path.exists(path) else {}
    added = 0
    for sid, r in out.items():
        url, label = (r["conditions"], "Conditions / status") if r.get("conditions") and r.get("conditionsOk", True) else (r.get("landing"), "Official site")
        if not url:
            continue
        e = links.setdefault(sid, {})
        have = {x["url"] for x in e.get("add", [])}
        if url not in have:
            e.setdefault("add", []).append({"label": label, "url": url})
            added += 1
    json.dump(links, open(path, "w"), indent=1)
    print(f"added {added} links to data/spot_links.json")


if __name__ == "__main__":
    apply() if "--apply" in sys.argv else main()
