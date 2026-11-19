"""Thursday Brief draft: phone-first, no tables in the content, ~250 words. DRAFT ONLY: this writes files and never sends anything.
Inputs: conditions.json, diff.json (diff_week.py), best_bet.json (best_bet.py), data/usgs_daily_median.json (optional),
brief_config.json. Human inputs, as environment variables: BRIEF_ERIC_NOTE ("line one\\nline two"), BRIEF_BEST_BET_OVERRIDE.
Other environment: BRIEF_OUT (output folder, default <repo>/brief-out), BRIEF_CONDITIONS (default <repo>/data/conditions.json).
Writes brief-draft.{html,md,txt} into the output folder. Run through run_brief.py."""
import sys, os, json, re, shutil, datetime as dt, html
from zoneinfo import ZoneInfo
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.normpath(os.path.join(HERE,'..','..'))
sys.path.insert(0,HERE)
from common import PINE,GOLD,CREAM,MOSS,INK,SERIF,SANS,MONO,FONTS,md2html
B=ZoneInfo('America/Boise')
OUTDIR=os.environ.get('BRIEF_OUT') or os.path.join(ROOT,'brief-out'); os.makedirs(OUTDIR,exist_ok=True)
cfg=json.load(open(os.path.join(HERE,'brief_config.json')))
d=json.load(open(os.environ.get('BRIEF_CONDITIONS') or os.path.join(ROOT,'data','conditions.json')))
diff=json.load(open(os.path.join(OUTDIR,'diff.json'))); bb=json.load(open(os.path.join(OUTDIR,'best_bet.json')))
RSF=os.path.join(ROOT,'data','resort_status.json')
rs=json.load(open(RSF)) if os.path.exists(RSF) else {'spots':{}}
MEDF=os.path.join(ROOT,'data','usgs_daily_median.json')
med=json.load(open(MEDF)) if os.path.exists(MEDF) else {}   # run scripts/brief/fetch_usgs_stats.py on the Mac to create it
ERIC_NOTE=(os.environ.get('BRIEF_ERIC_NOTE') or '').replace('\\n','\n').strip() or None   # two lines from Eric
BEST_BET_OVERRIDE=(os.environ.get('BRIEF_BEST_BET_OVERRIDE') or '').strip() or None   # replaces the rules pick in the bottom line
OUT=os.path.join(OUTDIR,'brief-draft')
gen=dt.datetime.fromisoformat(d['generatedAt']).astimezone(B)
send=gen.date()+dt.timedelta(days=(3-gen.weekday())%7)
season=cfg['season']['override'] or cfg['season']['byMonth'][str(gen.month)]
S=cfg['seasons'][season]
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
# ---------- Weekend (popular places) ----------
wk=[]; watch=None
for pl in S['places']:
    p,r=points[pl['point']]; days={x['date']:x for x in p['days']}
    a,b=days.get(sat),days.get(sun)
    if not a or not b: wk.append(f"**{pl['label']}:** [CHECK: no forecast for the weekend]"); continue
    wk.append(f"**{pl['label']}:** Sat {short(a['short'])}, {a['hi']}°; Sun {short(b['short'])}, {b['hi']}°")
    for nm,x in (("Saturday",a),("Sunday",b)):
        if x['precipChance']>=60 and (watch is None or x['precipChance']>watch[2]): watch=(pl['label'],nm,x['precipChance'],x['short'])
# ---------- Bottom line ----------
best=bb['best']
bw=[]
for k,v,t in best['parts']:
    if v>0 and k=='sky': bw.append(t.lower())
    if v>0 and k=='new snow': bw.append(f"after ~{best['leadSnowIn']:g} in. of forecast new snow")
pick=BEST_BET_OVERRIDE or f"{best['day']} in {best['point']}, {bw[0] if bw else 'the best score'} and {best['hi']}°" + (f" {bw[1]}" if len(bw)>1 else "")
bottom=[f"**The numbers favor:** {pick}.", f"**Biggest change:** {biggest}.",
        (f"**Watch:** {watch[0]}, {short(watch[3])} {watch[1]} ({watch[2]}%)." if watch else "**Watch:** nothing in particular. Enjoy it.")]
# ---------- Notable vs normal (one line) ----------
mmdd=gen.strftime('%m-%d'); rows=[]
for r in d['regions'].values():
    for v in r['rivers']:
        m=med.get(v['id'].split('-',1)[1],{}).get(mmdd)
        if m and v['flow']['value'] is not None: rows.append((v['flow']['value']/m['p50'],v))
if rows: q,lowv=min(rows,key=lambda z:z[0])
else: q,lowv=None,None   # no medians file yet: skip the river comparison
snows=sorted([s for r in d['regions'].values() for s in r['snow'] if s['pctOfMedian']['value'] is not None],key=lambda s:s['pctOfMedian']['value'])
snow_bit=f"snowpack runs {snows[0]['pctOfMedian']['value']}% of median at {snows[0]['name']} to {snows[-1]['pctOfMedian']['value']}% at {snows[-1]['name']}" if snows else None
river_bit=f"lowest river vs. its {gen.strftime('%b %-d')} median is {rv(lowv['id'],lowv['name'])} at {q*100:.0f}%" if rows else None
bits=[b for b in ([snow_bit,river_bit] if S['normalOrder'][0]=='snow' else [river_bit,snow_bit]) if b]
normal=(bits[0][0].upper()+bits[0][1:]+("; "+bits[1] if len(bits)>1 else "")+".") if bits else "[CHECK: no snow or river comparison data]"
# ---------- Coming up (3) ----------
up=[]
if 'ski' in S['comingUpTypes']:
    names={"southwest-bogus-basin":"Bogus Basin","upper-snake-grand-targhee-wy-idaho-access":"Grand Targhee"}
    for k,s in rs['spots'].items():
        if k in names and s.get('openingISO') and s['status']!='open':
            o=dt.date.fromisoformat(s['openingISO'])
            if gen.date()<o<=gen.date()+dt.timedelta(days=14):
                up.append((o,f"{names[k]} opening day, unconfirmed{' (low confidence)' if s['confidence']!='high' else ''}"))
if 'closure' in S['comingUpTypes']:
    ex=cfg['comingUpExclude']
    for r in d['regions'].values():
        for c in r['roads']['closures']:
            if not c['highway'] or not c['end'] or c['subType'] in ex['subTypes'] or any(w in c['description'] for w in ex['descriptionContains']): continue
            e=dt.datetime.fromisoformat(c['end']).astimezone(B)
            if gen+dt.timedelta(hours=20)<e<gen+dt.timedelta(days=45):
                up.append((e.date(),f"{c['name']} closure {loc(c['description'])} ({r['name']}) scheduled to end"))
up=sorted(up,key=lambda z:z[0])[:cfg['comingUpMax']]
coming=[f"**{o.strftime('%b %-d')}:** {t}." for o,t in up]
# ---------- Avalanche ----------
A=cfg['avalanche']; aval=None
touch=[]
if any(k=='new snow' and v>0 for k,v,_ in best['parts']): touch+=A['pointCenters'].get(best['pointId'],[])
for g in groups:
    if g[0]['type']=='snow':
        rid=next(k for k,v in d['regions'].items() if v['name']==g[0]['region']); touch+=A['regionCenters'].get(rid,[])
touch=[c for i,c in enumerate(touch) if c not in touch[:i] and c!='avalanche_org']
if 'avalanche' in S['sections'] and touch:
    aval="Avalanche forecasts: "+", ".join(f"[{A['centers'][c]['name']}]({A['centers'][c]['url']})" for c in touch)+f"; everywhere else, [avalanche.org]({A['centers']['avalanche_org']['url']}). We don't restate danger. Read theirs."
# ---------- links + footer ----------
rl=" · ".join(f"[{r['name']}]({cfg['regionUrl'].format(id=rid)})" for rid,r in d['regions'].items())+("" if cfg['regionUrlConfirmed'] else " [CHECK: URL pattern]")
src=d['sources']
fc=[bt(r['forecast']['updated'],'%-I:%M %p') for r in d['regions'].values()]
lastfake=bool(diff.get('lastWeekIsFake'))
footer=(f"Times MST. Data {gen.strftime('%a %b %-d, %-I:%M %p')}: NWS forecasts {min(fc)}–{max(fc)}; Idaho 511 {bt(src['idaho511']['fetchedAt'],'%-I:%M %p')}; "
        f"USGS/NOAA gauges ~11:30 AM–1:15 PM, provisional (medians: USGS daily stats); SNOTEL daily; AirNow {bt(src['airnow']['fetchedAt'],'%-I %p').replace('1 PM','1 PM')}, preliminary; NIFC {bt(src['nifc']['fetchedAt'],'%-I:%M %p')}. "
        f"Last week: {bt(diff['lastWeek'],'%b %-d')} snapshot{' (FAKE, demo)' if lastfake else ''}. A conditions check, not a to-do list.")
EN=ERIC_NOTE or "[ERIC: two lines. What you saw, drove or skied this week.]"
best_short=best['point'].split(' /')[0]
subj_change="A quiet week" if QUIET else ((" and ".join(a['place'].split('/')[-1].replace(' Pass','') for a in top)+" went "+top[0]['to'].lower().split()[0]) if top[0]['type']=='pass' else biggest)
SUBJECT=f"{subj_change[0].upper()+subj_change[1:]}; the numbers favor {best['day']} in {best_short}"
NUM={1:"One",2:"Two",3:"Three",4:"Four",5:"Five",6:"Six"}
PRE=("A quiet week" if QUIET else f"{NUM.get(len(changed),len(changed))} changes that matter")+f", the weekend in {NUM.get(len(wk),len(wk)).lower()} lines, and what's coming up."
DATELINE=f"THURSDAY BRIEF · {send.strftime('%b %-d, %Y').upper()} · DATA AS OF {gen.strftime('%a %-I:%M %p').upper()} MST"
FAKE="DEMO: \"last week\" is a FAKE snapshot made up to show the weekly diff." if lastfake else None
TITLES={"bottom":"Bottom line","eric":"From Eric","changed":"What changed","weekend":"The weekend","normal":"Vs. normal","coming":"Coming up","avalanche":"Avalanche","links":"By region","sources":"Sources"}
CONTENT={"bottom":bottom,"eric":[EN],"changed":changed,"weekend":wk,"normal":[normal],"coming":coming,"avalanche":[aval] if aval else [],"links":[rl],"sources":[footer]}
LISTY={"changed","coming"}
# ---------- HTML (fluid, single column) ----------
def BOLD(t): return t.replace('<strong>','<strong style="color:'+PINE+';">')
def P(s,size=16,color=INK,extra='',lc=MOSS):
    inner=md2html(s,lc)
    if color==INK: inner=inner.replace("<strong>",'<strong style="color:'+PINE+';">')
    return f'<p style="margin:0 0 10px;font-family:{SANS};font-size:{size}px;line-height:1.5;color:{color};{extra}">'+inner+'</p>'
def H(t): return f'<p style="margin:22px 0 8px;font-family:{MONO};font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:{MOSS};border-top:1px solid #d3cdbd;padding-top:12px;">{html.escape(t)}</p>'
h=[]
h.append(f'<img src="ic-masthead-1200x400.jpg" alt="Idaho Conditions: rivers, roads, snow, smoke, fire" width="600" style="display:block;width:100%;height:auto;border:0;">')
h.append(f'<div style="background:{MOSS};padding:8px 20px;font-family:{MONO};font-size:11px;letter-spacing:0.03em;color:{CREAM};">{DATELINE}</div>')
if FAKE: h.append(f'<div style="background:#b5452f;padding:9px 20px;font-family:{MONO};font-size:12px;line-height:1.45;color:#fff;font-weight:500;">&#9888; {html.escape(FAKE)}</div>')
h.append('<div style="padding:18px 20px 6px;">')
for sec in S['sections']:
    items=CONTENT[sec]
    if not items: continue
    if sec=='bottom':
        h.append(f'<div style="background:{PINE};border-left:5px solid {GOLD};border-radius:6px;padding:16px 18px 8px;margin:0 0 4px;"><p style="margin:0 0 8px;font-family:{MONO};font-size:11px;letter-spacing:0.1em;color:{GOLD};">BOTTOM LINE</p>'
                 + ''.join(P(x,16,CREAM,lc=GOLD).replace('<strong>',f'<strong style="color:{GOLD};">') for x in items)+'</div>')
    elif sec=='eric':
        h.append(f'<div style="margin:14px 0 0;padding:12px 14px;border:2px dashed {GOLD};border-radius:6px;"><p style="margin:0 0 4px;font-family:{MONO};font-size:11px;letter-spacing:0.1em;color:{MOSS};">FROM ERIC</p>{P(items[0],15,extra="margin:0;font-style:italic;")}</div>')
    elif sec=='sources':
        h.append(H(TITLES[sec])+f'<p style="margin:0 0 6px;font-family:{MONO};font-size:11px;line-height:1.55;color:#4a5a52;">{md2html(items[0])}</p>')
    elif sec in LISTY:
        h.append(H(TITLES[sec])+''.join(f'<p style="margin:0 0 9px;padding-left:14px;text-indent:-14px;font-family:{SANS};font-size:15px;line-height:1.5;color:{INK};"><span style="color:{GOLD};font-weight:700;">&#9656;</span>&nbsp;{BOLD(md2html(x))}</p>' for x in items))
    else:
        h.append(H(TITLES[sec])+''.join(P(x,15) for x in items))
h.append('</div>')
h.append(f'''<div style="background:{PINE};padding:18px 20px;font-family:{MONO};font-size:12px;line-height:1.7;color:{CREAM};">
<img src="ic-logo-112.png" width="44" height="44" alt="Idaho Conditions logo" style="display:block;border:0;border-radius:7px;margin:0 0 8px;">
<a href="https://idahoconditions.com" style="color:{GOLD};text-decoration:none;">idahoconditions.com</a> · <a href="https://x.com/idahoconditions" style="color:{GOLD};text-decoration:none;">X</a> · <a href="https://www.instagram.com/idahoconditions/" style="color:{GOLD};text-decoration:none;">Instagram</a> · <a href="mailto:contact@idahoconditions.com" style="color:{GOLD};text-decoration:none;">contact@idahoconditions.com</a><br>
<span style="color:#9fb3a8;">Reply and it reaches Eric. <a href="#" style="color:#9fb3a8;">Unsubscribe</a></span></div>''')
doc=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(SUBJECT)}</title>{FONTS}</head>
<body style="margin:0;padding:0;background:{PINE};"><div style="display:none;max-height:0;overflow:hidden;opacity:0;">{html.escape(PRE)}</div>
<div style="padding:16px 8px;"><div style="max-width:600px;margin:0 auto;background:{CREAM};border-radius:6px;overflow:hidden;">
{''.join(h)}
</div></div></body></html>'''
open(OUT+'.html','w').write(doc)
# ---------- Markdown ----------
m=[f"**Subject:** {SUBJECT}  ",f"**Preview text:** {PRE}","","---","","![Idaho Conditions masthead](ic-masthead-1200x400.jpg)","",f"`{DATELINE}`",""]+([f"> ⚠ **{FAKE}**",""] if FAKE else [])
for sec in S['sections']:
    items=CONTENT[sec]
    if not items: continue   # optional section with nothing to say this week (the HTML skips it too)
    m.append(f"## {TITLES[sec]}"); m.append("")
    if sec in LISTY: m+= [f"- {x}" for x in items]
    else:
        for x in items: m+= [x+"  " if sec=='bottom' else x, "" if sec!='bottom' and sec!='weekend' else ""]
    m.append("")
m+=["---","","[idahoconditions.com](https://idahoconditions.com) · [X](https://x.com/idahoconditions) · [Instagram](https://www.instagram.com/idahoconditions/) · contact@idahoconditions.com"]
md='\n'.join(m); md=re.sub(r'\n{3,}','\n\n',md)+'\n'
# weekend lines need hard breaks in markdown
md=re.sub(r'(\*\*[^*\n]+:\*\* Sat [^\n]+)\n',r'\1  \n',md)
open(OUT+'.md','w').write(md)
# ---------- Plain text ----------
t=md
t=re.sub(r'!\[[^\]]*\]\([^)]*\)\n','',t)
t=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1 <\2>',t)
t=t.replace('**','').replace('`','').replace('  \n','\n')
t=re.sub(r'^## (.+)$',lambda m_:m_.group(1).upper()+"\n"+"="*len(m_.group(1)),t,flags=re.M)
t=re.sub(r'^> ','',t,flags=re.M); t=re.sub(r'^---\n','',t,flags=re.M); t=re.sub(r'\n{3,}','\n\n',t)
open(OUT+'.txt','w').write(t)
# ---------- word count: body excluding footer (sources, links, masthead) ----------
body=' '.join(bottom+[EN]+changed+wk+[normal]+coming+([aval] if aval else []))
body=re.sub(r'\]\([^)]+\)',']',body).replace('**','')
print("SEASON:",season); print("SUBJECT:",SUBJECT); print("PREVIEW:",PRE); print("BODY WORDS:",len(body.split()))
print("BOTTOM LINE:"); [print("  ",re.sub(r'\*\*','',x)) for x in bottom]
