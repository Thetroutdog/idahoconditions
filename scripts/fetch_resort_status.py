#!/usr/bin/env python3
"""Best-effort crawl for each ski, Nordic and snowmobile area's current status (open / closed / opening soon) and opening day
-> data/resort_status.json, plus a review table on screen. Run locally, about weekly until the season is rolling, then weekly toward the end:
    python3 scripts/fetch_resort_status.py
Two sources: (1) the Ski Idaho home page, one request that lists all 19 ski areas with an "Opening Day" or open label; (2) each area's own conditions
or landing page (from data/resort_pages.json, made by crawl_resort_pages.py, else data/resort_sites.json). Plain text pattern matching, so it is a
helper, not gospel: every result keeps the sentence it came from (evidence) and a confidence, and 'unknown' is a normal answer.
The site does not read this file yet: look at a few runs first, then we decide what to show (chip, verdict, or both). Polite crawling rules: web_crawl.py."""
import json, os, re, sys
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import web_crawl as wc

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
D = lambda *a: os.path.join(ROOT, "data", *a)
KINDS = {"ski", "nordic", "snowmobile"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
TRIG = r"(?:opening day|season opens?|opens?|opening|re-?opens?|reopening|target(?:ed|ing)?|aiming|kick(?:ing)? off|start(?:s|ing)?|first day|season on)"
DATE = r"(?:(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)[a-z]*\.?,?\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
CLOSED = r"closed for the (?:\w+ )?(?:off-?)?season|currently closed|is closed|are closed|we(?:'re| are) closed|closed for (?:the )?(?:summer|fall|spring|winter)|off-?season|for summer operations|season has ended|closed until"
OPEN = r"now open|we(?:'re| are) open|is open (?:today|now|for)|open (?:today|daily|now)|open for (?:the )?(?:winter |ski |skiing |snow )?(?:season|skiing|operations)|lifts? (?:are )?(?:open|spinning|running)|opening day (?:is )?(?:today|here)|season is underway"


def thanksgiving(year):
    d = date(year, 11, 1)
    return d + timedelta(days=(3 - d.weekday()) % 7 + 21)


def to_iso(mon, day, today):
    try:
        d = date(today.year, MONTHS[mon[:3].lower()], int(day))
    except ValueError:
        return None
    if (today - d).days > 60:  # "March 14" read in November means next March
        d = date(today.year + 1, d.month, d.day)
    return d.isoformat()


def find_opening(text, today=None):
    """-> (display text, iso or None, evidence sentence) or None."""
    today = today or date.today()
    for m in re.finditer(TRIG, text, re.I):
        win = text[m.start(): m.start() + 130]
        d = re.search(DATE, win, re.I)
        if d:
            return f"{d.group(1).title()} {d.group(2)}", to_iso(d.group(1), d.group(2), today), " ".join(win.split())
    m = re.search(r"opening day[^.\n]{0,10}\b(tbd|to be determined|tba)\b", text, re.I)
    if m:
        return "TBD", None, " ".join(text[max(0, m.start() - 20): m.end() + 20].split())
    m = re.search(r"(?:open|opening|kick off)[^.\n]{0,60}thanksgiving", text, re.I)
    if m:
        t = thanksgiving(today.year)
        return "Thanksgiving", t.isoformat(), " ".join(text[m.start(): m.end() + 20].split())
    return None


def find_status(text, opening, today=None):
    """-> (status, confidence, evidence). status: open | closed | opening-soon | unknown."""
    today = today or date.today()
    op, cl = re.search(OPEN, text, re.I), re.search(CLOSED, text, re.I)
    ev = lambda m: " ".join(text[max(0, m.start() - 40): m.end() + 60].split())
    if cl and re.search(r"summer operations", cl.group(0), re.I):
        return "closed", "high", ev(cl)
    if op and not cl:
        return "open", "high", ev(op)
    if cl and not op:
        iso = opening[1] if opening else None
        soon = iso and 0 <= (date.fromisoformat(iso) - today).days <= 21
        return ("opening-soon" if soon else "closed"), "high", ev(cl)
    if op and cl:  # pages often mention both ("closed Mon-Wed", "open daily"); too ambiguous to call
        return "unknown", "low", ev(op)
    if opening:  # an announced or "TBD" opening day means it is not open yet
        return "closed", "low", opening[2]
    return "unknown", "low", ""


def analyze(text, today=None):
    text = text[:40000]
    o = find_opening(text, today)
    st, conf, ev = find_status(text, o, today)
    return {"status": st, "confidence": conf, "opening": o[0] if o else None, "openingISO": o[1] if o else None, "evidence": (ev or (o[2] if o else ""))[:200]}


def skiidaho(spots, today):
    """One page lists every ski area with its opening day or open label."""
    out = {}
    final, html = wc.fetch("https://www.skiidaho.us/")
    if not final:
        print("skiidaho.us unavailable:", html)
        return out
    text, _ = wc.parse(html, final)
    flat = " ".join(text.split())
    for sp in spots:
        if sp["activity"] != "ski":
            continue
        name = re.sub(r"\s*\(.*?\)", "", sp["name"]).strip()
        for m in re.finditer(re.escape(name), flat, re.I):
            ctx = flat[max(0, m.start() - 90): m.end() + 40]
            if re.search(r"opening day|open now|closed|open", ctx, re.I):
                a = analyze(ctx, today)
                if a["status"] != "unknown" or a["opening"]:
                    out[sp["id"]] = {**a, "source": "skiidaho.us", "url": final, "confidence": "low"}  # layout guesswork: never better than low
                    break
    return out


def main():
    today = date.today()
    spots = []
    for f in ("spots.json", "spots_extra.json"):
        spots += json.load(open(D(f)))["spots"]
    spots = [s for s in spots if s["activity"] in KINDS]
    pages = json.load(open(D("resort_pages.json"))) if os.path.exists(D("resort_pages.json")) else {}
    sites = json.load(open(D("resort_sites.json")))["sites"]
    res = skiidaho(spots, today)
    print(f"Ski Idaho listing gave something for {len(res)} ski areas")
    seen = {}
    for i, sp in enumerate(spots, 1):
        pg = pages.get(sp["id"], {})
        url = pg.get("conditions") or pg.get("landing") or sites.get(sp["id"], {}).get("site")
        if not url:
            continue
        if url not in seen:  # several spots can share a page (e.g. the McCall nordic areas): fetch it once
            final, html = wc.fetch(url)
            seen[url] = analyze(wc.parse(html, final)[0], today) if final else None
            if not final:
                print(f"  {sp['id']}: {url} did not load ({html})")
        a = seen[url]
        if a and (a["status"] != "unknown" or a["opening"]):
            res[sp["id"]] = {**a, "source": "resort page", "url": url}  # the operator's own page beats the Ski Idaho listing
        print(f"[{i}/{len(spots)}] {sp['id']}: {res.get(sp['id'], {}).get('status', '-')} {res.get(sp['id'], {}).get('opening') or ''}", flush=True)
    for sp in spots:
        res.setdefault(sp["id"], {"status": "unknown", "confidence": "low", "opening": None, "openingISO": None, "evidence": "", "source": None, "url": None})
        res[sp["id"]]["checkedAt"] = today.isoformat()
    json.dump({"fetchedAt": datetime.now().isoformat(timespec="seconds"), "spots": res}, open(D("resort_status.json"), "w"), indent=1)
    c = {}
    for v in res.values():
        c[v["status"]] = c.get(v["status"], 0) + 1
    print("\nResult:", c, "-> data/resort_status.json")
    print("Check a few against the real pages before trusting this; 'evidence' shows the sentence each call came from.")


if __name__ == "__main__":
    main()
