"""Week-over-week diff of two conditions.json snapshots.
Usage: python3 diff_week.py [this_week.json] [last_week.json] > out/diff.json
Output groups changes by TYPE; each item names its region. Thresholds are below."""
import json, sys, re, os
ROOT=os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..'))
# ---- thresholds ------------------------------------------------------------
RIVER_PCT_MIN   = 15     # % change in flow...
RIVER_CFS_MIN   = 50     # ...AND absolute cfs change (both must be met)
SNOW_DEPTH_MIN  = 2      # inches of SNOTEL depth change
AQI_CATEGORY    = True   # report any AQI category change
HIGHWAY_ONLY    = True   # only report closures flagged highway=True
ROAD_RANK = {"dry":0,"bare":0,"wet":1,"slush":2,"icy patches":3,"snow covered":4,"ice":5,"closed":6}
PASS_WORDS = ("pass","summit","hill")
# significance score (base, before the season's typeWeight from brief_config.json)
SIG = {"advisory_new":100,"advisory_ended":60,"closure":90,"pass_worse":85,"pass_better":70,"road_worse":50,"road_better":40,
       "river_base":40,"river_pct_cap":60,"snow_base":30,"snow_per_in":4,"air":30,"air_to_bad":10,"fire":45,"rx":15,"gauge":20}
SEVERITY_STEP = 5   # extra points per road-condition rank step
# ---------------------------------------------------------------------------
if len(sys.argv)<3: sys.exit('usage: diff_week.py this_week.json last_week.json > diff.json')
now=json.load(open(sys.argv[1]))
old=json.load(open(sys.argv[2]))
RN={k:v['name'] for k,v in now['regions'].items()}
out={"thisWeek":now['generatedAt'],"lastWeek":old['generatedAt'],"lastWeekIsFake":bool(old.get('meta',{}).get('FAKE')),
     "thresholds":{"riverPct":RIVER_PCT_MIN,"riverCfs":RIVER_CFS_MIN,"snowIn":SNOW_DEPTH_MIN},
     "advisories":[],"closures":[],"roads":[],"rivers":[],"snow":[],"air":[],"fire":[],"gauges":[]}
def place(w):
    where=w.get('where') or ''
    m=re.search(r'\(([^)]*(?:Pass|Summit)[^)]*)\)',where)
    return m.group(1) if m else where.split(' from ')[0]
def is_pass(w): return any(p in (w.get('where') or '').lower() for p in PASS_WORDS)
for rid in now['regions']:
    a,b=now['regions'][rid],old['regions'].get(rid)
    if not b: continue
    reg=RN[rid]
    # advisories (dedupe by id across regions later)
    na={x['id']:x for x in a['alerts']}; oa={x['id']:x for x in b['alerts']}
    for i in na.keys()-oa.keys(): out['advisories'].append({"kind":"new","region":reg,"event":na[i]['event'],"ends":na[i]['ends'],"url":na[i]['url'],"id":i,"headline":na[i]['headline']})
    for i in oa.keys()-na.keys(): out['advisories'].append({"kind":"ended","region":reg,"event":oa[i]['event'],"ends":oa[i]['ends'],"url":oa[i]['url'],"id":i})
    # closures
    nc={x['id']:x for x in a['roads']['closures'] if x['highway'] or not HIGHWAY_ONLY}
    oc={x['id']:x for x in b['roads']['closures'] if x['highway'] or not HIGHWAY_ONLY}
    for i in nc.keys()-oc.keys(): out['closures'].append({"kind":"new","region":reg,"road":nc[i]['name'],"desc":(nc[i].get('description') or '').strip(),"end":nc[i]['end']})
    for i in oc.keys()-nc.keys(): out['closures'].append({"kind":"cleared","region":reg,"road":oc[i]['name'],"desc":(oc[i].get('description') or '').strip()})
    # winter road segments
    key=lambda w:(w['name'],w['where'])
    nw={key(w):w for w in a['roads']['winter']}; ow={key(w):w for w in b['roads']['winter']}
    for k in nw.keys()|ow.keys():
        w1,w0=nw.get(k),ow.get(k); w=w1 or w0
        c1=(w1['condition'] if w1 else 'Dry'); c0=(w0['condition'] if w0 else 'Dry')
        r1,r0=ROAD_RANK.get(c1.lower(),3),ROAD_RANK.get(c0.lower(),3)
        if r1==r0: continue
        out['roads'].append({"kind":"worse" if r1>r0 else "better","region":reg,"road":w['name'],"place":place(w),"pass":is_pass(w),
                             "from":c0 if w0 else "not listed","to":c1 if w1 else "not listed (clear)"})
    # rivers
    orv={v['id']:v for v in b['rivers']}
    for v in a['rivers']:
        o=orv.get(v['id']); f1=v['flow']['value']; f0=o['flow']['value'] if o else None
        if f1 is None and f0 is not None: out['gauges'].append({"region":reg,"name":v['name'],"id":v['id'],"note":"stopped reporting"}); continue
        if f1 is None or f0 is None or f0==0: continue
        d=f1-f0; pct=100*d/f0
        if abs(pct)>=RIVER_PCT_MIN and abs(d)>=RIVER_CFS_MIN:
            out['rivers'].append({"region":reg,"name":v['name'],"id":v['id'],"from":f0,"to":f1,"pct":round(pct),"source":v['flow']['source']})
    # snow
    osn={s['id']:s for s in b['snow']}
    for s in a['snow']:
        o=osn.get(s['id'])
        if not o or s['depth']['value'] is None or o['depth']['value'] is None: continue
        d=s['depth']['value']-o['depth']['value']
        if abs(d)>=SNOW_DEPTH_MIN: out['snow'].append({"region":reg,"name":s['name'],"id":s['id'],"from":o['depth']['value'],"to":s['depth']['value'],"delta":d,"pct":s['pctOfMedian']['value']})
    # air
    oair={x['id']:x for x in b['air']['points']}
    for x in a['air']['points']:
        o=oair.get(x['id'])
        if o and AQI_CATEGORY and o['category']!=x['category']:
            out['air'].append({"region":reg,"place":x['name'],"from":f"{o['category']} ({o['aqi']['value']})","to":f"{x['category']} ({x['aqi']['value']})","pollutant":x['pollutant']})
    # fire
    nf={x['name'] for x in a['fire']['wildfires']}; of={x['name']:x for x in b['fire']['wildfires']}
    for n in of.keys()-nf: out['fire'].append({"kind":"dropped","region":reg,"name":n,"acres":of[n]['acres'],"containment":of[n]['containmentPct']})
    for x in a['fire']['wildfires']:
        if x['name'] not in of: out['fire'].append({"kind":"new","region":reg,"name":x['name'],"acres":x['acres'],"containment":x['containmentPct']})
    drx=len(a['fire']['prescribed'])-len(b['fire']['prescribed'])
    if drx: out['fire'].append({"kind":"rx","region":reg,"delta":drx,"now":len(a['fire']['prescribed'])})
# dedupe advisories that appear in several regions
seen={}
for x in out['advisories']:
    k=(x['kind'],x['id'])
    if k in seen: seen[k]['region']+=", "+x['region']
    else: seen[k]=x
out['advisories']=list(seen.values())
out['rivers'].sort(key=lambda x:-abs(x['pct'])); out['snow'].sort(key=lambda x:-x['delta'])
# ---- significance ranking ----
import datetime as _dt, os
cfg=json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'brief_config.json')))
month=str(_dt.datetime.fromisoformat(now['generatedAt']).month)
season=cfg['season']['override'] or cfg['season']['byMonth'][month]
W=cfg['seasons'][season]['typeWeight']
ranked=[]
def add(typ,base,item): item['type']=typ; item['sig']=round(base*W.get(typ,1.0),1); ranked.append(item)
for a in out['advisories']: add('advisory',SIG['advisory_new'] if a['kind']=='new' else SIG['advisory_ended'],a)
for c in out['closures']: add('closure',SIG['closure'],c)
for r in out['roads']:
    step=abs(ROAD_RANK.get(r['to'].split(' (')[0].lower().replace('not listed','dry'),3)-ROAD_RANK.get(r['from'].lower().replace('not listed','dry'),3))
    if r['pass']: add('pass',(SIG['pass_worse'] if r['kind']=='worse' else SIG['pass_better'])+SEVERITY_STEP*step,r)
    else: add('road',(SIG['road_worse'] if r['kind']=='worse' else SIG['road_better'])+SEVERITY_STEP*step,r)
for r in out['rivers']: add('river',SIG['river_base']+min(abs(r['pct']),SIG['river_pct_cap']),r)
for s_ in out['snow']: add('snow',SIG['snow_base']+SIG['snow_per_in']*abs(s_['delta']),s_)
for a in out['air']: add('air',SIG['air']+(SIG['air_to_bad'] if not a['to'].startswith('Good') else 0),a)
for f in out['fire']: add('fire',SIG['rx'] if f['kind']=='rx' else SIG['fire'],f)
for g in out['gauges']: add('gauge',SIG['gauge'],g)
ranked.sort(key=lambda x:(-x['sig'], x.get('ends') or '', x['region'], json.dumps(x,sort_keys=True)))  # deterministic
out['season']=season; out['ranked']=ranked
json.dump(out,sys.stdout,indent=1)
