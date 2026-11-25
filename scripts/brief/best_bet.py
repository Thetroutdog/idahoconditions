"""Rules-based 'best bet this weekend'. Scores every NWS forecast point for Saturday and Sunday.
Usage: python3 best_bet.py [conditions.json] > out/best_bet.json   (the editor then agrees or overrides.)"""
import json, sys, re, os, datetime as dt
from zoneinfo import ZoneInfo
BOISE=ZoneInfo('America/Boise')
# ---- rules (all transparent; edit here) ----------------------------------------
SKY = [("mostly sunny",3),("sunny",3),("partly sunny",2),("partly cloudy",2),("mostly cloudy",1)]  # first match on the day's short forecast; else 0
PRECIP = [(20,2),(35,1)]          # precipChance <= 20 -> +2, <= 35 -> +1
PRECIP_WET, PRECIP_WET_PTS = 60,-2 # precipChance >= 60 -> -2
SNOW_PER_PT_IN, SNOW_CAP = 2, 3    # forecast new snow before the weekend (low end, Wed night-Fri night): +1 per 2 in., max +3
SNOTEL_24H_MIN, SNOTEL_24H_PTS = 3, 1  # SNOTEL 24h depth gain >= 3 in. at the point's station -> +1
AIR_NOT_GOOD = -2                  # AirNow category other than Good at the same point (falls back to the region)
ADVISORY_ACTIVE = -3               # an NWS alert in the region overlaps that day
SNOW_COVERED_ROAD = -1             # any 'Snow Covered' highway segment in the region
COLD_HI_F, COLD_PTS = 30, -1       # daytime high below 30F
POINT_SNOTEL = {"ketchum":"537:ID:SNTL","mccall":"370:ID:SNTL","boise":"978:ID:SNTL","salmon":"639:ID:SNTL",
                "coeur-d-alene":"594:ID:SNTL","lewiston":"1142:ID:SNTL","pocatello":"1299:ID:SNTL",
                # winter: the same stations for the ski areas that sit beside them
                "southwest-bogus-basin":"978:ID:SNTL","southwest-brundage-mountain":"370:ID:SNTL","magic-valley-sun-valley-bald-mountain-dollar":"537:ID:SNTL"}
# --------------------------------------------------------------------------------
if len(sys.argv)<2: sys.exit('usage: best_bet.py conditions.json > best_bet.json')
d=json.load(open(sys.argv[1]))
gen=dt.datetime.fromisoformat(d['generatedAt']).astimezone(BOISE).date()
sat=gen+dt.timedelta(days=(5-gen.weekday())%7); sun=sat+dt.timedelta(days=1)
# Winter candidates are the Brief's ski-area grids (scripts/brief/brief_config.json, seasons.winter.places), not the town points; summer keeps the towns.
HERE=os.path.dirname(os.path.abspath(__file__))
cfg=json.load(open(os.path.join(HERE,'brief_config.json')))
season=cfg['season']['override'] or cfg['season']['byMonth'][str(gen.month)]
PLACES=[pl for pl in cfg['seasons'][season].get('places',[]) if pl.get('spot')]
SPOTS=d.get('spotForecast') or {}
SPOT_MODE=bool(PLACES)
def spot_region(sid):
    return max((k for k in d['regions'] if sid.startswith(k+'-')),key=len,default=None)
def spot_days(sid):
    gk=(SPOTS.get('bySpot') or {}).get(sid); g=(SPOTS.get('grids') or {}).get(gk) if gk else None
    return (g or {}).get('days') or []
def points_for(rid,r):
    if not SPOT_MODE: return r['forecast']['points']
    return [{'id':pl['spot'],'name':pl['label'],'days':spot_days(pl['spot']),'spot':True} for pl in PLACES if spot_region(pl['spot'])==rid]
def new_snow_low(text):
    m=re.search(r'New snow accumulation of (?:around )?(\d+) to (\d+) inch',text)
    if m: return float(m.group(1))
    if re.search(r'New snow accumulation of around one inch',text): return 1.0
    return 0.0  # 'less than ...' or none
def sky_pts(short):
    s=(short or '').lower().split(' then ')[0]
    for k,v in SKY:
        if s.startswith(k): return v,k
    return 0,None
def score_all():
    res=[]
    for rid,r in d['regions'].items():
        snow={s['id']:s for s in r['snow']}
        snow_cov=[w for w in r['roads']['winter'] if w['condition'].lower()=='snow covered']
        for p in points_for(rid,r):
            days={x['date']:x for x in p['days']}
            lead=0.0
            for x in p['days']:
                dd=dt.date.fromisoformat(x['date'])
                if dd>=sat: break
                if dd==gen: lead+=new_snow_low(x.get('nightDetail') or '')
                else: lead+=new_snow_low(x.get('detail') or '')+new_snow_low(x.get('nightDetail') or '')
            same=[a for a in r['air']['points'] if a['id']==p['id']] or r['air']['points']
            air_bad=[a for a in same if a['category']!='Good']
            st=snow.get(POINT_SNOTEL.get(p['id'],''))
            g24=st['depthChange24h']['value'] if st else None
            for day in (sat,sun):
                x=days.get(day.isoformat())
                if not x: continue
                parts=[]; score=0
                sp,sk=sky_pts(x.get('short')); score+=sp; parts.append(("sky",sp,x.get('short') or ''))
                pc=x.get('precipChance'); pp=0 if pc is None else next((v for lim,v in PRECIP if pc<=lim),0)  # no chance published: no points either way
                if pc is not None and pc>=PRECIP_WET: pp=PRECIP_WET_PTS
                score+=pp; parts.append(("precip",pp,f"{pc}%"))
                spts=min(SNOW_CAP,int(lead//SNOW_PER_PT_IN)); score+=spts; parts.append(("new snow",spts,f"{lead:g} in. forecast before the weekend"))
                if g24 is not None and g24>=SNOTEL_24H_MIN: score+=SNOTEL_24H_PTS; parts.append(("snotel",SNOTEL_24H_PTS,f"{st['name']} +{g24} in. 24h"))
                if air_bad: score+=AIR_NOT_GOOD; parts.append(("air",AIR_NOT_GOOD,", ".join(f"{a['name']} {a['category']}" for a in air_bad)))
                act=[a for a in r['alerts'] if (dt.datetime.fromisoformat(a['onset']).date() if a.get('onset') else dt.date.min)<=day<=(dt.datetime.fromisoformat(a['ends']).date() if a.get('ends') else dt.date.max)]  # no end time = until further notice
                if act: score+=ADVISORY_ACTIVE; parts.append(("advisory",ADVISORY_ACTIVE,act[0]['event']))
                if snow_cov: score+=SNOW_COVERED_ROAD; parts.append(("roads",SNOW_COVERED_ROAD,", ".join(w['name'] for w in snow_cov)))
                if x.get('hi') is not None and x['hi']<COLD_HI_F: score+=COLD_PTS; parts.append(("cold",COLD_PTS,f"high {x['hi']}F"))
                res.append({"region":r['name'],"regionId":rid,"point":p['name'],"pointId":p['id'],"spot":bool(p.get('spot')),"fallback":FALLBACK,"day":day.strftime('%A'),"date":day.isoformat(),
                            "score":score,"hi":x['hi'],"lo":x['lo'],"short":x['short'],"precip":pc,"aqi":same[0]['aqi']['value'] if same else None,
                            "leadSnowIn":lead,"parts":parts})
    return res
FALLBACK=False
res=score_all()
if SPOT_MODE and not res:   # no ski-area grid reaches the weekend yet: score the towns, and say so downstream (the Brief blocks on it)
    SPOT_MODE=False; FALLBACK=True; res=score_all()
res.sort(key=lambda z:(-z['score'], z['date'], z['point']))
best=res[0]
why=[]
for k,v,t in best['parts']:
    if v>0: why.append({"sky":f"{t.lower()}","precip":f"{t} precip","new snow":t,"snotel":t}.get(k,t))
best['why']=f"{best['day']} in {best['point']} scores {best['score']}: "+"; ".join(why)+f"; high {best['hi']}°F."
json.dump({"weekend":[sat.isoformat(),sun.isoformat()],"best":best,"ranked":res},sys.stdout,indent=1)
