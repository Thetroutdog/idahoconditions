"""Hard pre-send check for the Thursday brief. Exit 0 = clear to paste; exit 1 = lists every reason.
Usage: python3 scripts/brief/preflight.py [--max-age-hours N] [--now ISO] [--data FILE] [--diff FILE] [base]
  base default: <output folder from paths.py>/brief-draft ; data default: <repo>/data/conditions.json ; diff default: <base folder>/diff.json
Checks: placeholder/demo markers in .md/.html/.txt, empty or leaked-template text, empty sections, stale or failed sources,
and that last week's baseline is a real snapshot 5-9 days old. This tool only reports; nothing in this repo sends email."""
import os, sys, re, json, argparse, datetime as dt
import paths
from zoneinfo import ZoneInfo
B=ZoneInfo('America/Boise'); HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.normpath(os.path.join(HERE,'..','..'))
cfg=json.load(open(os.path.join(HERE,'brief_config.json')))
def iso(ts): return dt.datetime.fromisoformat(ts.replace('Z','+00:00'))
ap=argparse.ArgumentParser(); ap.add_argument('base',nargs='?',default=os.path.join(paths.out_dir(),'brief-draft'))
ap.add_argument('--max-age-hours',type=float,default=cfg.get('maxDataAgeHours',18)); ap.add_argument('--now')
ap.add_argument('--data',default=os.path.join(ROOT,'data','conditions.json')); ap.add_argument('--diff'); a=ap.parse_args()
MARKERS={'[CHECK]':r'\[CHECK','[EDITOR]':r'\[EDITOR','FAKE':r'\bFAKE\b','[DEMO]':r'\[DEMO',
         'leaked template':r'\{id\}|\{[a-z_]+\}|\bNone\b|\bnan\b|\bundefined\b|Traceback'}
now=iso(a.now) if a.now else dt.datetime.now(B)
fails=[]
for ext in ('md','html','txt'):
    try: txt=open(f"{a.base}.{ext}").read()
    except FileNotFoundError: fails.append(f"missing output: {a.base}.{ext}"); continue
    import html as _h
    plain=_h.unescape(re.sub(r'<[^>]+>',' ',txt)) if ext=='html' else txt
    plain=re.sub(r'[ \t]+',' ',plain)
    for name,mk in MARKERS.items():
        ms=list(re.finditer(mk,plain))
        if ms:
            i=ms[0].start(); ctx=plain[max(0,i-25):i+55].replace('\n',' ').strip()
            fails.append(f"{ext}: {name} x{len(ms)} … \"{ctx}\"")
# empty sections (markdown is the canonical text)
md=open(f"{a.base}.md").read()
secs=re.split(r'^## ',md,flags=re.M)[1:]
for sct in secs:
    title,_,body=sct.partition('\n')
    if not re.sub(r'[\s\-–—·]','',body.split('\n---')[0]): fails.append(f"empty section: {title.strip()}")
# data age
d=json.load(open(a.data))
def age(ts): return (now-iso(ts)).total_seconds()/3600
g=age(d['generatedAt'])
if g>a.max_age_hours: fails.append(f"conditions.json generated {g:.1f} h ago (limit {a.max_age_hours:g} h)")
for k,s in d['sources'].items():
    if not s.get('ok'): fails.append(f"source {k} not ok: {s.get('error')}")
    elif age(s['fetchedAt'])>a.max_age_hours: fails.append(f"source {k} fetched {age(s['fetchedAt']):.1f} h ago (limit {a.max_age_hours:g} h)")
# last week's baseline must be a real snapshot, about a week old
dfile=a.diff or os.path.join(os.path.dirname(a.base) or '.','diff.json')
try:
    df=json.load(open(dfile))
    if df.get('lastWeekIsFake'): fails.append("last-week baseline is flagged FAKE")
    lw=df.get('lastWeek')
    if not lw: fails.append("diff has no lastWeek date")
    else:
        days=(now-iso(lw)).total_seconds()/86400
        if not 5<=days<=9.5: fails.append(f"last-week snapshot is {days:.1f} days old (want 5 to 9)")
except FileNotFoundError: fails.append(f"missing diff file: {dfile}")
print(f"preflight {a.base} @ {now.astimezone(B):%a %b %-d %-I:%M %p} MST · data age {g:.1f} h · limit {a.max_age_hours:g} h")
if fails:
    print(f"FAIL ({len(fails)}):"); [print("  -",f) for f in fails]; sys.exit(1)
print("PASS"); sys.exit(0)
