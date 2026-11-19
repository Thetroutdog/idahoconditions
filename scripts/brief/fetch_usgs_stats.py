"""Fetch USGS daily-statistics median discharge (p50) for each gauge's day-of-year.
Cache: data/usgs_daily_median.json (run on Eric's Mac: python3 scripts/brief/fetch_usgs_stats.py)  {site: {"MM-DD": p50_cfs, ...}, "_meta": {...}}
Run yearly or on gauge-list change; stats only change as new approved data lands."""
import json, os, urllib.request, sys, datetime
ROOT=os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),"..",".."))
d=json.load(open(os.path.join(ROOT,"data","conditions.json")))
sites=sorted({v['id'].split('-',1)[1] for r in d['regions'].values() for v in r['rivers'] if v['id'].startswith('USGS-')})
out={"_meta":{"source":"https://waterservices.usgs.gov/nwis/stat/ (statReportType=daily, statTypeCd=median, 00060)","fetched":datetime.datetime.now().astimezone().isoformat(timespec='minutes')}}
for s in sites:
    url=f"https://waterservices.usgs.gov/nwis/stat/?format=rdb&sites={s}&statReportType=daily&statTypeCd=median&parameterCd=00060"
    try:
        txt=urllib.request.urlopen(url,timeout=30).read().decode()
    except Exception as e:
        print(s,'ERR',e); continue
    rows=[l.split('\t') for l in txt.splitlines() if l and not l.startswith('#')]
    if len(rows)<3: print(s,'no stats'); continue
    hdr=rows[0]; ix={h:i for i,h in enumerate(hdr)}
    m={}
    for r in rows[2:]:
        if r[ix['parameter_cd']]!='00060': continue
        try: m[f"{int(r[ix['month_nu']]):02d}-{int(r[ix['day_nu']]):02d}"]={"p50":float(r[ix['p50_va']]),"years":f"{r[ix['begin_yr']]}-{r[ix['end_yr']]}","n":int(r[ix['count_nu']])}
        except: pass
    out[s]=m; print(s,len(m),m.get('11-18'))
json.dump(out,open(os.path.join(ROOT,'data','usgs_daily_median.json'),'w'),indent=0)
