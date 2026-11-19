"""Small polite-crawler helpers shared by crawl_resort_pages.py and fetch_resort_status.py. Standard library only.
Rules: identify ourselves (IC_USER_AGENT), obey robots.txt, at most one request per host every 2 seconds, plain GETs of public pages only,
no logins, no forms, a hard cap on page size. A site that disallows us is skipped, never worked around."""
import os, re, time, urllib.parse, urllib.request, urllib.robotparser
from html.parser import HTMLParser

UA = os.environ.get("IC_USER_AGENT") or "idahoconditions.com (contact@idahoconditions.com)"
MAX_BYTES = 1_500_000
_last, _robots = {}, {}


def allowed(url):
    host = urllib.parse.urlsplit(url)
    base = f"{host.scheme}://{host.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                rp.parse(r.read(200_000).decode("utf-8", "replace").splitlines())
        except Exception:
            rp = None  # no readable robots.txt: allowed
        _robots[base] = rp
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(UA, url)


def fetch(url, timeout=25):
    """-> (final_url, html) or (None, reason). Never raises."""
    if not allowed(url):
        return None, "robots.txt disallows"
    host = urllib.parse.urlsplit(url).netloc
    wait = 2.0 - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "")
            if "html" not in ctype and "text" not in ctype:
                return None, f"not a web page ({ctype})"
            return r.geturl(), r.read(MAX_BYTES).decode(r.headers.get_content_charset() or "utf-8", "replace")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"[:120]
    finally:
        _last[host] = time.time()


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links, self._skip, self._href, self._atext = [], [], 0, None, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        if tag == "a":
            self._href, self._atext = dict(attrs).get("href"), []
        if tag in ("br", "p", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._atext).split())))
            self._href = None

    def handle_data(self, d):
        if self._skip:
            return
        self.text.append(d)
        if self._href is not None:
            self._atext.append(d)


def parse(html, base_url):
    """-> (text, [(absolute_url, link_text)]). Text keeps line breaks between blocks."""
    p = _Page()
    try:
        p.feed(html)
    except Exception:
        pass
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.text))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    links, seen = [], set()
    for href, t in p.links:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        u = urllib.parse.urljoin(base_url, href).split("#")[0]
        if u not in seen:
            seen.add(u)
            links.append((u, t))
    return text, links
