"""Shared helpers for the data fetchers. Standard library only.
Every fetcher writes data/parts/<source>.json; build_conditions.py merges the parts. On failure a fetcher keeps its previous
part and marks it ok=false, so the site shows last-known data as stale instead of blank."""
import json, os, sys, time, urllib.request, urllib.parse, datetime as dt

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PARTS = os.path.join(ROOT, "data", "parts")
# NWS requires a contact (email or site) in the User-Agent. Set the real value in IC_USER_AGENT (your local env file, see secrets/.env.example; GitHub secret in Actions); this is only the fallback.
UA = os.environ.get("IC_USER_AGENT") or "idahoconditions.com (contact@idahoconditions.com)"  # "or": an unset Actions secret arrives as an empty string
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def slug(name):
    return name.lower().replace(" region", "").replace(" ", "-")


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def http_json(url, headers=None, timeout=60):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return json.loads(r.read())


def http_text(url, timeout=60):
    """A plain-text download (pipe-delimited files and the like), decoded leniently: a stray odd byte must not fail the run."""
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def q(base, **params):
    return base + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})


def load_json(rel):
    return json.load(open(os.path.join(ROOT, *rel.split("/"))))


def region_finder():
    """Returns f(lon, lat) -> region slug or None, using the official IDFG polygons."""
    from region_tools import find_region
    feats = load_json("data/idfg_regions.geojson")["features"]
    return lambda lon, lat: (lambda n: slug(n) if n else None)(find_region(feats, lon, lat))


def reading(value, unit, observed, source, provisional=False):
    """A Reading per docs/conditions-schema.md. status is re-evaluated by build_conditions.py at build time."""
    return {"value": value, "unit": unit, "observedAt": observed, "status": "fresh" if value is not None else "missing",
            "provisional": provisional, "source": source}


def run_part(name, fn):
    """fn() -> {region_slug: {section: value}}. Writes data/parts/<name>.json; keeps the previous data on failure."""
    path = os.path.join(PARTS, f"{name}.json")
    os.makedirs(PARTS, exist_ok=True)
    try:
        regions = fn()
        part = {"source": name, "fetchedAt": now_utc().isoformat(timespec="seconds"), "ok": True, "error": None, "regions": regions}
    except Exception as e:
        try:
            part = json.load(open(path)) if os.path.exists(path) else {"source": name, "fetchedAt": None, "regions": {}}
        except Exception:  # previous part is unreadable (half-written): start empty rather than crash
            part = {"source": name, "fetchedAt": None, "regions": {}}
        part.update({"ok": False, "error": f"{type(e).__name__}: {e}"[:200]})
        print("FAILED, keeping previous data:", part["error"])
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:  # write beside, then swap in, so a crash never leaves a half-written part
        json.dump(part, fh, indent=1)
    os.replace(tmp, path)
    print("wrote", path, "| ok:", part["ok"], "| regions:", {k: list(v) for k, v in part["regions"].items()})
    return part
