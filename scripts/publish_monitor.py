#!/usr/bin/env python3
"""Publish data/conditions.json at /data/conditions.json on the deployed site, for monitoring and personal tools.
Run by the refresh workflow after the Astro build: copies the merged file into dist/data/ with a short note added.
Refuses to publish if the text contains anything that looks like a key, a password or a local path (a failed run only skips the copy; the site still deploys).
Usage: python3 scripts/publish_monitor.py [source.json] [output.json]"""
import json, os, re, sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/conditions.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else "dist/data/conditions.json"
NOTE = ("Published for monitoring and personal tools, not a supported API: the shape can change without notice and values can be late or wrong. "
        "Sources: National Weather Service, NIFC, AirNow (preliminary), USGS, NOAA, NRCS SNOTEL, and Idaho Transportation Department (ITD) / Idaho 511 (https://511.idaho.gov/). "
        "Check the official sources before you go.")
BAD = [r"/Users/", r"/home/", r"[A-Za-z]:\\", r"api[_-]?key", r"secret", r"password", r"bearer\s", r"authorization"]


def main():
    raw = open(SRC, encoding="utf-8").read()
    data = json.loads(raw)
    if not isinstance(data, dict) or "regions" not in data or "generatedAt" not in data:
        sys.exit("publish_monitor: conditions.json has no regions or generatedAt; not publishing")
    for pat in BAD:
        m = re.search(pat, raw, re.I)
        if m:
            sys.exit(f"publish_monitor: found '{m.group(0)}' in conditions.json; not publishing")
    for name in ("IDAHO511_API_KEY", "AIRNOW_API_KEY", "USGS_API_KEY", "CLOUDFLARE_API_TOKEN"):
        v = os.environ.get(name, "")
        if len(v) >= 8 and v in raw:
            sys.exit(f"publish_monitor: the value of {name} appears in conditions.json; not publishing")
    data["publishedNote"] = NOTE
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"publish_monitor: wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
