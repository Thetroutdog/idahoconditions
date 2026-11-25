"""Thursday Brief v4 draft: body-only, paste-safe for beehiiv's Free editor (headings, paragraphs, bold, links, simple lists; no inline styles, boxes or layout tables).
The beehiiv template already has the masthead and the footer, and the subject/preview come from brief-titles.txt, so none of those are in the body.
DRAFT ONLY: this writes files and never sends anything.
Inputs: conditions.json, diff.json (diff_week.py), best_bet.json (best_bet.py), data/usgs_daily_median.json (optional), brief_config.json.
Human inputs. Environment variables: BRIEF_EDITOR_NOTE ("line one\\nline two"), BRIEF_BEST_BET_OVERRIDE,
  BRIEF_ONE_MORE_THING ("Title | https://link | one-line blurb", or the three on separate lines joined with \\n), BRIEF_DATED_LINES (optional, "Dec 5: text" per line, \\n between).
  Files in the output folder work too (the env var wins): one-more-thing.txt (title, URL, blurb on three lines or in the pipe form) and dated-lines.txt.
Other environment: BRIEF_OUT (output folder; default see paths.py: $BRIEF_HOME/drafts/<send date> or <repo>/brief-out), BRIEF_CONDITIONS (default <repo>/data/conditions.json).
Writes brief-draft.{html,md,txt} and brief-titles.txt into the output folder. Run through run_brief.py."""
import sys, os, json, re, datetime as dt, html
from zoneinfo import ZoneInfo
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.normpath(os.path.join(HERE,'..','..'))
sys.path.insert(0,HERE)
from common import md2html_plain, words
B=ZoneInfo('America/Boise')
import paths
OUTDIR=os.environ.get('BRIEF_OUT') or paths.out_dir(); os.makedirs(OUTDIR,exist_ok=True)
cfg=json.load(open(os.path.join(HERE,'brief_config.json')))
d=json.load(open(os.environ.get('BRIEF_CONDITIONS') or os.path.join(ROOT,'data','conditions.json')))
diff=json.load(open(os.path.join(OUTDIR,'diff.json')));NOBASE=bool(diff.get('noBaseline')); bb=json.load(open(os.path.join(OUTDIR,'best_bet.json')))
RSF=os.path.join(ROOT,'data','resort_status.json')
rs=json.load(open(RSF)) if os.path.exists(RSF) else {'spots':{}}
MEDF=os.path.join(ROOT,'data','usgs_daily_median.json')
med=json.load(open(MEDF)) if os.path.exists(MEDF) else {}   # run scripts/brief/fetch_usgs_stats.py locally to create it
def env_text(name): return (os.environ.get(name) or '').replace('\\n','\n').strip()
def file_text(name):
    p=os.path.join(OUTDIR,name)
    return open(p).read().strip() if os.path.exists(p) else ''
EDITOR_NOTE=env_text('BRIEF_EDITOR_NOTE') or None   # two lines from the editor
BEST_BET_OVERRIDE=(os.environ.get('BRIEF_BEST_BET_OVERRIDE') or '').strip() or None   # replaces the rules pick in the bottom line
OMT_RAW=env_text('BRIEF_ONE_MORE_THING') or file_text('one-more-thing.txt')
DATED_RAW=env_text('BRIEF_DATED_LINES') or file_text('dated-lines.txt')
OUT=os.path.join(OUTDIR,'brief-draft')
gen=dt.datetime.fromisoformat(d['generatedAt']).astimezone(B)
send=gen.date()+dt.timedelta(days=(3-gen.weekday())%7)
season=cfg['season']['override'] or cfg['season']['byMonth'][str(gen.month)]
S=cfg['seasons'][season]
TITLES=cfg['titles']; BUDGET=cfg['wordBudget']
DISPLAY_NAME={}  # the fetcher's river names are complete now (v0.12.7); kept as a hook for one-off fixes
USGS_URL="https://waterdata.usgs.gov/monitoring-location/USGS-{n}/"
SNOTEL_URL="https://wcc.sc.egov.usda.gov/nwcc/site?sitenum={n}"
def bt(s,f='%a %-I %p'): return dt.datetime.fromisoformat(s).astimezone(B).strftime(f)
def rv(id_,name): return f"[{DISPLAY_NAME.get(id_,name)}]({USGS_URL.format(n=id_.split('-',1)[1])})"
def sn(id_,name): return f"[{name}]({SNOTEL_URL.format(n=id_.split(':')[0])})"
def short(s):
    s=s.lower()
    s=re.sub(r'\blight ','',s)
    for a,b in [("rain and snow showers","rain/snow"),("rain and snow","rain/snow"),("snow showers","snow"),("areas of fog","fog"),("widespread fog","fog")]: s=s.replace(a,b)
    return re.sub(r'\bchance (?!of)','chance of ',s)
def loc(desc):
    m=re.search(r'from (.+?) to (.+?)\.',desc)
    if m: return re.sub(r'\s*\(MP \d+\)','',f"{m.group(1)} to {m.group(2)}")
    m=re.search(r'Near .*?\((MP \d+)\)',desc); return f"near {m.group(1)}" if m else ''
points={p['id']:(p,r) for r in d['regions'].values() for p in r['forecast']['points']}
sat,sun=bb['weekend']
# ---------- What changed (ranked by diff_week.py significance) ----------
caps=dict(cfg['changedMaxPerType']); taken={}; picked=[]
for x in diff['ranked']:
    if x['type']=='closure' and x.get('end') and dt.datetime.fromisoformat(x['end'])<gen+dt.timedelta(hours=20): continue
    if x['type'] in ('pass','road') and any('not listed' in str(x.get(k,'')).lower() for k in ('from','to')): continue   # missing from the 511 feed is "no report", not a change
    if taken.get(x['type'],0)>=caps.get(x['type'],1): continue
    taken[x['type']]=taken.get(x['type'],0)+1; picked.append(x)
groups=[]  # merge same-type items into one bullet where the wording allows
for x in picked:
    g=next((g for g in groups if g[0]['type']==x['type'] and x['type'] in('advisory','pass') and g[0].get('kind')==x.get('kind') and g[0].get('from')==x.get('from') and g[0].get('to')==x.get('to')),None)
    (g.append(x) if g else groups.append([x]))
groups=groups[:cfg['changedMax']]
def bullet(g):
    x=g[0]; t=x['type']
    if t=='advisory':
        if x['kind']=='new':
            off=lambda a: re.sub(r' [A-Z]{2}$','',a.get('headline','').split(' by ')[-1]) or a['event']
            if len({a['event'] for a in g})==1:
                return "New "+(g[0]['event'][:-1]+"ies" if len(g)>1 and g[0]['event'].endswith('y') else g[0]['event'])+": "+"; ".join(f"[{off(a)}]({a['url']}), {a['region']}, to {bt(a['ends'])}" for a in g)+"."
            return "New: "+"; ".join(f"[{a['event']}]({a['url']}), {a['region']}, to {bt(a['ends'])}" for a in g)+"."
        return f"{x['event']} ({x['region']}) ended."
    if t=='pass':
        names=" and ".join(f"{a['place'].split('/')[-1]} ({a['road']}, {a['region']})" for a in g)
        return f"{names}: {x['from'].lower().replace('not listed','clear')} → {x['to'].lower()}."
    if t=='road': return f"{x['road']} {x['place']} ({x['region']}): {x['from'].lower().replace('not listed','clear')} → {x['to'].lower().replace('not listed (clear)','clear')}."
    if t=='closure':
        where=loc(x['desc'].replace(' (FAKE)',''))
        return f"{x['road']} {where} ({x['region']}) " + ("reopened." if x['kind']=='cleared' else f"closed{', through '+bt(x['end'],'%b %-d') if x.get('end') else ''}.")
    if t=='snow': return f"{sn(x['id'],x['name'])} SNOTEL ({x['region']}): {x['from']:g} → {x['to']:g} in., now {x['pct']}% of median."
    if t=='river': return f"{rv(x['id'],x['name'])} ({x['region']}): {x['from']:,.0f} → {x['to']:,.0f} cfs ({x['pct']:+d}%)."
    if t=='air': return f"{x['place']} ({x['region']}) air: {x['from']} → {x['to']}, preliminary."
    if t=='fire': return (f"{x['name']} ({x['region']}) fire dropped off the NIFC list." if x['kind']=='dropped' else f"Prescribed burns listed, {x['region']}: {x['now']} ({x['delta']:+d}).")
    if t=='gauge': return f"{x['name']} gauge ({x['region']}) stopped reporting [CHECK]."
changed=[bullet(g) for g in groups]
QUIET=not groups   # nothing crossed the significance bar this week
top=groups[0] if groups else None
if QUIET:
    changed=["Nothing big moved since last Thursday."]; biggest="nothing big moved since last Thursday"
else: biggest=bullet(top).rstrip('.')
if top and top[0]['type']=='pass':
    biggest=" and ".join(a['place'].split('/')[-1].replace(' Pass','') for a in top)+(" passes" if len(top)>1 else "")+f" went from {top[0]['from'].lower()} to {top[0]['to'].lower()}"
# No last-week snapshot (the first Brief): still build the draft, mark What changed, and stay blocked (run_brief and preflight both flag it)
if NOBASE:
    changed=["[CHECK: no last-week snapshot]"]; biggest="[CHECK: no last-week snapshot]"
# What changed: one labeled line per item (Passes, Roads, Snow, Rivers, Alerts, Air, Fire), trimmed to the section's hard cap
LABEL={'advisory':'Alerts','pass':'Passes','road':'Roads','closure':'Roads','snow':'Snow','river':'Rivers','gauge':'Rivers','air':'Air','fire':'Fire'}
if not QUIET and not NOBASE:
    changed=[f"**{LABEL.get(g[0]['type'],'Other')}:** {bullet(g)}" for g in groups]
    while len(changed)>1 and words(' '.join(changed))>BUDGET['changed'][1]: changed.pop()
NCH=len(groups)   # items that crossed the bar this week (for the subtitle)
if not NOBASE and len(changed)<2: changed=[]   # What changed only when it adds something; Biggest change already says the one thing
# ---------- The weekend: forecast lines, then up to 3 dated items ----------
SPOTS=d.get('spotForecast') or {}
def grid_days(spot):
    gk=(SPOTS.get('bySpot') or {}).get(spot); g=(SPOTS.get('grids') or {}).get(gk) if gk else None
    return (g or {}).get('days') or []
def degs(x): return f"{x['hi']}°" if x.get('hi') is not None else ''
wk=[]; watch=None
PLACES=sorted(S['places'],key=lambda p:p['label'].lower()) if all('spot' in p for p in S['places']) else S['places']   # winter ski areas A to Z; summer keeps the configured order
for pl in PLACES:
    if 'spot' in pl: daylist=grid_days(pl['spot'])                      # winter: the ski area's own NWS grid (mid-mountain to summit)
    else: daylist=(points.get(pl['point']) or ({'days':[]},None))[0]['days']   # summer: the town point
    days={x['date']:x for x in daylist}
    a,b=days.get(sat),days.get(sun)
    if not a or not b: wk.append(f"**{pl['label']}:** [CHECK: no weekend forecast]"); continue
    wk.append(f"**{pl['label']}:** Sat {short(a['short'])}, {degs(a)}; Sun {short(b['short'])}, {degs(b)}")
    for nm,x in (("Saturday",a),("Sunday",b)):
        if (x.get('precipChance') or 0)>=60 and (watch is None or x['precipChance']>watch[2]): watch=(pl['label'],nm,x['precipChance'],x['short'])
# ---------- Dated items (folds in the old Coming up): editor lines first, then ski/nordic openings and closures ----------
MON={m:i for i,m in enumerate(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],1)}
def editor_dated(raw):
    out=[]
    for ln in [x.strip() for x in raw.splitlines() if x.strip()]:
        m=re.match(r'^([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2})\s*[:\-–]\s*(.+)$',ln)
        if m and m.group(1) in MON:
            dd=dt.date(gen.year,MON[m.group(1)],int(m.group(2)))
            if dd<gen.date()-dt.timedelta(days=30): dd=dd.replace(year=gen.year+1)
            out.append((dd,m.group(3).strip()))
        else: out.append((dt.date.max,ln))
    return out
def endp(t): return t if t[-1:] in '.!?' else t+'.'
dated_ed=[(o,t) for o,t in editor_dated(DATED_RAW)]
auto=[]
if 'ski' in S['datedTypes']:
    seen=set()
    for r in d['regions'].values():
        for s in r.get('ski',[]):
            oi=s.get('openingISO') or (rs['spots'].get(s['id']) or {}).get('openingISO')
            if not oi or s['id'] in seen or s.get('status')=='open': continue
            seen.add(s['id']); o=dt.date.fromisoformat(oi)
            if gen.date()<o<=gen.date()+dt.timedelta(days=14):
                auto.append((o,f"{s['name']} opening day, unconfirmed"))
if 'closure' in S['datedTypes']:
    ex=cfg['datedExclude']
    for r in d['regions'].values():
        for c in r['roads']['closures']:
            if not c['highway'] or not c['end'] or c['subType'] in ex['subTypes'] or any(w in c['description'] for w in ex['descriptionContains']): continue
            e=dt.datetime.fromisoformat(c['end']).astimezone(B)
            if gen+dt.timedelta(hours=20)<e<gen+dt.timedelta(days=45):
                kind='parade closure' if c['subType']=='parade' else 'closure'
                auto.append((e.date(),f"{c['name']} {kind} {loc(c['description'])} ({r['name']}) scheduled to end"))
dated=(dated_ed+sorted(auto,key=lambda z:z[0]))[:cfg['datedMax']]
dated_lines=[f"**{o.strftime('%b %-d')}:** {endp(t)}" if o!=dt.date.max else endp(t) for o,t in dated]
# keep the section under its hard cap: drop the last dated items first
while dated_lines and words(' '.join(wk+dated_lines))>BUDGET['weekend'][1]: dated_lines.pop()
# ---------- Bottom line ----------
best=bb['best']
bw=[]
for k,v,t in best['parts']:
    if v>0 and k=='sky': bw.append(t.lower())
    if v>0 and k=='new snow': bw.append(f"after ~{best['leadSnowIn']:g} in. of forecast new snow")
PREP='at' if best.get('spot') else 'in'   # winter picks are ski areas
pick=BEST_BET_OVERRIDE or ('[CHECK: no ski-area weekend forecast yet, so the pick fell back to a town: '+f"{best['day']} in {best['point']}]" if best.get('fallback') else None) or f"{best['day']} {PREP} {best['point']}, {bw[0] if bw else 'the best score'} and {best['hi']}°" + (f" {bw[1]}" if len(bw)>1 else "")
bottom=[f"**The numbers favor:** {pick}.", f"**Biggest change:** {biggest}.",
        (f"**Watch:** {watch[0]}, {short(watch[3])} {watch[1]} ({watch[2]}%)." if watch else "**Watch:** nothing in particular. Enjoy it.")]
# ---------- Vs. normal (one short paragraph; skipped when there is nothing to compare) ----------
mmdd=gen.strftime('%m-%d'); rows=[]
for r in d['regions'].values():
    for v in r['rivers']:
        m=med.get(v['id'].split('-',1)[1],{}).get(mmdd)
        if m and v['flow']['value'] is not None: rows.append((v['flow']['value']/m['p50'],v))
if rows: q,lowv=min(rows,key=lambda z:z[0])
else: q,lowv=None,None   # no medians file yet: skip the river comparison and say so
import statistics
byreg=[(r['name'],statistics.median(x['pctOfMedian']['value'] for x in r['snow'] if x['pctOfMedian']['value'] is not None)) for r in d['regions'].values() if any(x['pctOfMedian']['value'] is not None for x in r['snow'])]
byreg.sort(key=lambda z:z[1])
if len(byreg)>=2: snow_line=f"Snowpack: {byreg[0][0]} {byreg[0][1]:.0f}% of normal, {byreg[-1][0]} {byreg[-1][1]:.0f}%."
elif byreg: snow_line=f"Snowpack: {byreg[0][0]} {byreg[0][1]:.0f}% of normal."
else: snow_line=None
river_line=f"Rivers: lowest is the {rv(lowv['id'],lowv['name'])}, {q*100:.0f}% of normal for the date." if rows else "Rivers: no medians loaded yet, so no comparison."
normal=[x for x in ([snow_line,river_line] if S['normalOrder'][0]=='snow' else [river_line,snow_line]) if x]
if not rows and not snow_line: normal=[]
# ---------- One more thing (editor-supplied; never generated from site data) ----------
def parse_omt(raw):
    if not raw: return None
    parts=[x.strip() for x in (raw.split(' | ') if '\n' not in raw.strip() else raw.strip().splitlines()) if x.strip()]
    if len(parts)>=3 and re.match(r'https?://',parts[1]): return parts[0],parts[1],' '.join(parts[2:])
    return 'BAD'
omt=parse_omt(OMT_RAW)
if omt is None: OMT=["[EDITOR: One more thing is required. Supply BRIEF_ONE_MORE_THING or one-more-thing.txt: title, URL, one-line blurb.]"]
elif omt=='BAD': OMT=["[EDITOR: One more thing needs three parts: a title, an https:// link, and a one-line blurb.]"]
else: OMT=[f"**Worth reading:** [{omt[0]}]({omt[1]}). {endp(omt[2])}"]
# ---------- Avalanche ----------
A=cfg['avalanche']; aval=None
touch=[]
if any(k=='new snow' and v>0 for k,v,_ in best['parts']): touch+=A['pointCenters'].get(best['pointId']) or A['regionCenters'].get(best['regionId'],[])
for g in groups:
    if g[0]['type']=='snow':
        rid=next(k for k,v in d['regions'].items() if v['name']==g[0]['region']); touch+=A['regionCenters'].get(rid,[])
touch=[c for i,c in enumerate(touch) if c not in touch[:i] and c!='avalanche_org']
if 'avalanche' in S['sections'] and touch:
    aval="Avalanche forecasts: "+", ".join(f"[{A['centers'][c]['name']}]({A['centers'][c]['url']})" for c in touch)+f"; everywhere else, [avalanche.org]({A['centers']['avalanche_org']['url']}). We don't restate danger. Read theirs."
# ---------- Backcountry line under the Bottom line (winter only; links, never a danger rating) ----------
A=cfg['avalanche']; BACK=None
if 'avalanche' in S['sections']:
    BACK="**Backcountry:** read your avalanche center first. "+" · ".join(f"[{A['centers'][c]['short']}]({A['centers'][c]['url']})" for c in A['bottomLine'])
# ---------- By region + Sources ----------
rl=" · ".join(f"[{r['name']}]({cfg['regionUrl'].format(id=rid)})" for rid,r in d['regions'].items())+("" if cfg['regionUrlConfirmed'] else " [CHECK: URL pattern]")
lastfake=bool(diff.get('lastWeekIsFake'))
footer=(f"Times MST. Pulled {gen.strftime('%a %b %-d, %-I:%M %p')}. Sources: NWS, [Idaho Transportation Department (ITD) / Idaho 511](https://511.idaho.gov/), USGS, NOAA, SNOTEL, AirNow (preliminary), NIFC. "
        f"Last week: {(bt(diff['lastWeek'],'%b %-d')+' snapshot') if diff.get('lastWeek') else 'no snapshot yet'}{' (FAKE, demo)' if lastfake else ''}. Independent and informational only; check NWS, Idaho 511 and your avalanche center before you go. "
        f"A conditions check, not a to-do list. [idahoconditions.com](https://idahoconditions.com) · contact@idahoconditions.com")
EN=EDITOR_NOTE or "[EDITOR: two lines. What you saw, drove or skied this week.]"
best_short=best['point'].split(' /')[0]
def pass_phrase(top):
    names=[a['place'].split('/')[-1].replace(' Pass','') for a in top]
    who=" and ".join(names)+(" passes" if len(top)>1 else "")
    to=re.sub(r'\s*\(.*?\)','',top[0]['to']).strip().lower()
    return f"{who} {'are' if len(top)>1 else 'is'} {to}" if to else f"{who} changed"
def plain_change(top):
    x=top[0]
    if x['type']=='pass': return pass_phrase(top)
    if x['type']=='river': return f"{DISPLAY_NAME.get(x['id'],x['name'])} {'rose' if x['to']>x['from'] else 'fell'} {abs(x['pct'])}%"
    t=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',bullet(top)); t=re.sub(r'\s*\([^)]*\)','',t)
    return t.rstrip('.').strip()   # titles are plain text: no links, no region parentheses
subj_change="No last-week snapshot yet" if NOBASE else "A quiet week" if QUIET else plain_change(top)
cap1=lambda s: s[0].upper()+s[1:]
NUM={1:"One",2:"Two",3:"Three",4:"Four",5:"Five",6:"Six",7:"Seven",8:"Eight"}
nm=lambda n: NUM.get(n,str(n))
# Title (subject) and subtitle (preview) options go to brief-titles.txt; the editor pastes one of each into beehiiv's title and subtitle fields, not the body.
SUBJECTS=[f"{cap1(subj_change)}; the numbers favor {best['day']} {PREP} {best_short}",
          f"The numbers favor {best['day']} {PREP} {best_short}",
          cap1(subj_change)]
PREVIEWS=[("This week's draft" if NOBASE else "A quiet week" if QUIET else f"{nm(NCH)} {'change that matters' if NCH==1 else 'changes that matter'}")+f", the weekend in {nm(len(wk)).lower()} lines, and one thing worth reading.",
          f"The weekend in {nm(len(wk)).lower()} lines, and one thing worth reading.",
          f"{cap1(subj_change)}. Plus the weekend, and one thing worth reading."]
def uniq(xs): return [x for i,x in enumerate(xs) if x not in xs[:i]]
SUBJECTS,PREVIEWS=uniq(SUBJECTS),uniq(PREVIEWS)
SUBJECT,PRE=SUBJECTS[0],PREVIEWS[0]
FAKE="DEMO: \"last week\" is a FAKE snapshot made up to show the weekly diff." if lastfake else None
open(os.path.join(OUTDIR,'brief-titles.txt'),'w').write("TITLE (subject) options. Paste one into beehiiv's title field:\n"+''.join(f"  {i}. {s}\n" for i,s in enumerate(SUBJECTS,1))+
    "\nSUBTITLE (preview) options. Paste one into beehiiv's subtitle field:\n"+''.join(f"  {i}. {s}\n" for i,s in enumerate(PREVIEWS,1)))
CONTENT={"bottom":bottom,"editor":[x.strip() for x in EN.splitlines() if x.strip()],"changed":changed,"weekend":wk+(["**Coming up:**"]+dated_lines if dated_lines else []),"normal":normal,"onemore":OMT,"avalanche":[aval] if aval else [],"links":[rl],"sources":[footer]}
BULLETS={"changed","weekend","normal"}
QUOTED={"bottom","editor","onemore"}   # beehiiv renders a <blockquote> in its quote style: the stand-in for the mock's dark and dashed boxes
# ---------- Markdown (body only: no masthead, dateline or footer; beehiiv's template has those) ----------
m=([f"**{FAKE}**",""] if FAKE else [])
shown=[sec for sec in S['sections'] if CONTENT[sec]]
for i,sec in enumerate(shown):
    items=CONTENT[sec]
    if sec=='links' and BACK: m+=[BACK,""]
    if i: m+=["---",""]   # a divider between sections, not before the first or after the last
    m+=[f"## {TITLES[sec]}",""]
    if sec=='weekend': m+=[f"- {x}" for x in wk]+[""]+(["**Coming up:**","",*[f"- {x}" for x in dated_lines],""] if dated_lines else [])
    elif sec in ('changed','normal') and not NOBASE: m+=[f"- {x}" for x in items]+[""]
    elif sec in QUOTED: m+=[y for x in items for y in (f"> {x}",">")][:-1]+[""]
    else: m+=[y for x in items for y in (x,"")]
md=re.sub(r'\n{3,}','\n\n','\n'.join(m)).strip()+'\n'
open(OUT+'.md','w').write(md)
# ---------- HTML: headings, paragraphs, bold, links, simple lists only ----------
def ul(xs): return '<ul>\n'+''.join(f'<li>{md2html_plain(x)}</li>\n' for x in xs)+'</ul>'
h=[f'<p><strong>{html.escape(FAKE)}</strong></p>'] if FAKE else []
for i,sec in enumerate(shown):
    items=CONTENT[sec]
    if sec=='links' and BACK: h.append(f'<p>{md2html_plain(BACK)}</p>')
    if i: h.append('<hr>')
    h.append(f'<h2>{html.escape(TITLES[sec])}</h2>')
    if sec=='weekend': h.append(ul(wk)+(('\n<p><strong>Coming up:</strong></p>\n'+ul(dated_lines)) if dated_lines else ''))
    elif sec in ('changed','normal') and not NOBASE: h.append(ul(items))
    elif sec in QUOTED: h.append('<blockquote>\n'+'\n'.join(f'<p>{md2html_plain(x)}</p>' for x in items)+'\n</blockquote>')
    else: h+= [f'<p>{md2html_plain(x)}</p>' for x in items]
doc='<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>Thursday Brief draft</title></head>\n<body>\n'+'\n'.join(h)+'\n</body></html>\n'
open(OUT+'.html','w').write(doc)
# ---------- Plain text ----------
t=md
t=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1 <\2>',t)
t=t.replace('**','').replace('`','')
t=re.sub(r'^## (.+)$',lambda m_:m_.group(1).upper()+"\n"+"="*len(m_.group(1)),t,flags=re.M)
t=re.sub(r'^---\n','',t,flags=re.M); t=re.sub(r'^> ?','',t,flags=re.M)
t=re.sub(r'\n{3,}','\n\n',t)
open(OUT+'.txt','w').write(t)
# ---------- word budget ----------
sw={sec:words(' '.join(CONTENT[sec])) for sec in S['sections'] if CONTENT[sec]}
total=sum(sw.values()); lo,hi=cfg['bodyWordsTarget']
print("SEASON:",season); print("SUBJECT:",SUBJECT); print("PREVIEW:",PRE)
print(f"BODY WORDS: {total} (target {lo}-{hi}, hard cap under {cfg['bodyWordsHardCap']})"+("" if lo<=total<=hi else "  [outside the target range]"))
print("SECTION WORDS: "+", ".join(f"{TITLES[k]} {v}/{BUDGET[k][0]}(cap {BUDGET[k][1]})"+(" OVER CAP" if v>BUDGET[k][1] else "") for k,v in sw.items()))
print("WEEKEND LINES:",len(wk),"forecast,",len(dated_lines),"dated")
print("BOTTOM LINE:"); [print("  ",re.sub(r'\*\*','',x)) for x in bottom]
