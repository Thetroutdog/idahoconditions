"""Report which data sources are down and for how long. Reads data/conditions.json (written by build_conditions.py).

  python3 scripts/source_health.py [--data FILE] [--now ISO]

For each source with ok=false it prints a GitHub Actions warning (a yellow annotation, the run stays green):
"nws has been down for 3 h 20 min". A failed fetcher keeps its previous fetchedAt, so that time is the last good fetch.
Down under 24 hours is routine; 24 hours or more is flagged LONG OUTAGE and needs a look.
Exit code 1 only if EVERY source is down or conditions.json is missing/unreadable (the site is then really stale); otherwise 0.
Also appends a short table to $GITHUB_STEP_SUMMARY when that variable is set."""
import os, sys, json, argparse, datetime as dt
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LONG_H = 24

def iso(ts): return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))

def duration(h):
    if h < 1: return f"{max(1, round(h * 60))} min"
    if h < 48: m = round(h * 60); return f"{m // 60} h {m % 60:02d} min"
    return f"{h / 24:.1f} days"

def esc(s):  # GitHub workflow-command escaping
    return str(s).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

def check(sources, now):
    """-> (list of (name, ok, hours_down or None, last_good, error), all_down)"""
    rows = []
    for name, s in sorted(sources.items()):
        if s.get("ok"): rows.append((name, True, None, s.get("fetchedAt"), None)); continue
        last = s.get("fetchedAt")
        try: hrs = (now - iso(last)).total_seconds() / 3600 if last else None
        except Exception: hrs = None
        rows.append((name, False, hrs, last, s.get("error")))
    return rows, bool(rows) and not any(r[1] for r in rows)

def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--data", default=os.path.join(ROOT, "data", "conditions.json")); ap.add_argument("--now")
    a = ap.parse_args(argv)
    now = iso(a.now) if a.now else dt.datetime.now(dt.timezone.utc)
    try: sources = json.load(open(a.data))["sources"]
    except Exception as e:
        print(f"::error title=conditions.json unreadable::{esc(type(e).__name__ + ': ' + str(e))}"); return 1
    rows, all_down = check(sources, now)
    lines = []
    for name, ok, hrs, last, err in rows:
        if ok: lines.append(f"| {name} | ok | | |"); continue
        if hrs is None: msg, flag = f"{name} is down and has no successful fetch on record", "LONG OUTAGE: "
        else: msg, flag = f"{name} has been down for {duration(hrs)} (last good fetch {last})", ("LONG OUTAGE: " if hrs >= LONG_H else "")
        print(f"::warning title={flag}Source down: {name}::{esc(flag + msg + '. Last error: ' + str(err))}")
        lines.append(f"| {name} | **DOWN** | {duration(hrs) if hrs is not None else 'unknown'} | {str(err or '')[:80]} |")
    print(f"source health: {sum(1 for r in rows if r[1])} of {len(rows)} sources ok")
    if all_down: print("::error title=Every source is down::The site has no fresh data. Check the fetch step logs.")
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ and any(not r[1] for r in rows):
        with open(summ, "a") as f: f.write("### Source health\n\n| source | status | down for | last error |\n|---|---|---|---|\n" + "\n".join(lines) + "\n\n")
    return 1 if all_down else 0

if __name__ == "__main__": sys.exit(main())
