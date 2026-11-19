#!/usr/bin/env python3
"""Check every outbound link on the built site.

Usage (from the repo root):
    npm run build                      # makes dist/ (the pages the check reads)
    python3 scripts/check_links.py     # about 5-10 minutes; writes docs/probes/link-report.md

It reads dist/*.html, collects every external link with the page it appears on
and its link text, then:
  1. Offline checks: the same URL used for different places, and link text that
     disagrees with the URL (e.g. "ski" pointing at a nordic page).
  2. Live checks: fetches each unique URL slowly (one request per host at a time)
     and flags dead links, redirects to a home page, and redirects to another site.
Standard library only; changes nothing in the site.
"""
import collections, concurrent.futures as cf, html, re, sys, time, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
OUT = ROOT / "docs" / "probes" / "link-report.md"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15 idahoconditions-linkcheck"
SKIP_HOSTS = {"idahoconditions.com", "fonts.googleapis.com", "fonts.gstatic.com", "x.com", "www.instagram.com"}
HOST_GAP = 1.0  # seconds between requests to the same site

LINK_RE = re.compile(r'<a\b[^>]*?href="(https?://[^"#]+)[^"]*"[^>]*>(.*?)</a>', re.S | re.I)


def collect():
    uses = collections.defaultdict(list)  # url -> [(page, text)]
    for f in sorted(DIST.rglob("*.html")):
        page = "/" + str(f.relative_to(DIST)).replace("index.html", "").rstrip("/")
        text = f.read_text(errors="ignore")
        for url, label in LINK_RE.findall(text):
            url = html.unescape(url)
            if urlparse(url).netloc in SKIP_HOSTS:
                continue
            label = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", label))).strip()
            uses[url].append((page, label))
    return uses


def offline_flags(uses):
    """Cheap sanity checks that need no network."""
    flags = []
    for url, where in uses.items():
        low = url.lower()
        pages = {p.rstrip("/").split("/")[-1] for p, _ in where}
        if "ski" in pages and "nordic" in low:
            flags.append((url, "appears on a Ski (downhill) page but the URL looks like a Nordic page"))
        if "nordic" in pages and re.search(r"alpine|downhill|lift-ticket|snow-report", low):
            flags.append((url, "appears on a Nordic page but the URL looks like downhill/alpine"))
        labels = {l.lower() for _, l in where if l}
        if len(labels) > 3:
            flags.append((url, f"same URL used under {len(labels)} different link texts: {sorted(labels)[:4]}"))
    return flags


def fetch(url):
    def go(method):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.geturl()
    for method in ("HEAD", "GET"):
        try:
            return go(method)
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (400, 403, 404, 405, 501):
                continue  # some servers refuse HEAD; retry with GET
            return e.code, url
        except Exception as e:  # timeouts, DNS, TLS
            if method == "HEAD":
                continue
            return f"ERR {type(e).__name__}", url
    return "ERR", url


def judge(url, status, final):
    a, b = urlparse(url), urlparse(final)
    ha, hb = a.netloc.removeprefix("www."), b.netloc.removeprefix("www.")
    if isinstance(status, str):
        return "error", status
    if status in (404, 410):
        return "dead", f"HTTP {status}"
    if status in (401, 403, 429, 999):
        return "blocked", f"HTTP {status} (site may block automated checks; open by hand)"
    if status >= 400:
        return "error", f"HTTP {status}"
    if ha != hb:
        return "moved-site", f"redirects to {final}"
    deep = len(a.path.strip("/")) > 0
    if deep and b.path.strip("/") == "":
        return "to-homepage", f"deep link redirects to the home page: {final}"
    if final.rstrip("/") != url.rstrip("/"):
        return "redirect", f"redirects to {final}"
    return "ok", ""


def main():
    if not DIST.exists():
        sys.exit("dist/ not found. Run 'npm run build' first.")
    uses = collect()
    urls = sorted(uses)
    print(f"{len(urls)} unique outbound links; checking (one request per site at a time)...")
    flags = offline_flags(uses)

    by_host = collections.defaultdict(list)
    for u in urls:
        by_host[urlparse(u).netloc].append(u)
    results = {}

    def run_host(host):
        for u in by_host[host]:
            st, fin = fetch(u)
            results[u] = judge(u, st, fin)
            time.sleep(HOST_GAP)

    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(run_host, by_host))

    groups = collections.defaultdict(list)
    for u, (kind, note) in results.items():
        groups[kind].append((u, note))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Link check - {time.strftime('%Y-%m-%d %H:%M')}", "",
             f"{len(urls)} unique outbound links. " + ", ".join(f"{k}: {len(v)}" for k, v in sorted(groups.items())), ""]

    def section(title, items, note_first=True):
        if not items:
            return
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        for u, note in items:
            pages = sorted({p for p, _ in uses[u]})
            labels = sorted({l for _, l in uses[u] if l})[:2]
            lines.append(f"- {u}")
            if note:
                lines.append(f"  - {note}")
            lines.append(f"  - link text: {labels}; on: {', '.join(pages[:4])}{' ...' if len(pages) > 4 else ''}")
        lines.append("")

    section("Dead (404/410) - fix these first", groups["dead"])
    section("Redirect to a home page - probably moved", groups["to-homepage"])
    section("Redirect to a different site", groups["moved-site"])
    section("Errors (timeouts, DNS, TLS)", groups["error"])
    section("Offline: link text and URL disagree", [(u, n) for u, n in flags])
    section("Blocked - open these by hand", groups["blocked"])
    section("Redirects (harmless, could update)", groups["redirect"])
    OUT.write_text("\n".join(lines))
    print(f"Done. Report: {OUT}")
    for k in ("dead", "to-homepage", "moved-site", "error", "blocked", "redirect", "ok"):
        print(f"  {k}: {len(groups.get(k, []))}")
    print(f"  text/URL disagreements: {len(flags)}")


if __name__ == "__main__":
    main()
