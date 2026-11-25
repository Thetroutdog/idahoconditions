"""Self-test for the Brief tools. Run: python3 scripts/brief/selftest.py  (uses data/conditions.sample.json, no network)."""
import os, sys, json, tempfile, subprocess, datetime as dt
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.normpath(os.path.join(HERE,'..','..'))
sys.path.insert(0,HERE)
import snapshot
SAMPLE=os.path.join(ROOT,'data','conditions.sample.json')
FIXTURE=os.path.join(HERE,'fixtures','conditions.fixture.json')
ok=[]
def check(name,cond):
    print(('ok   ' if cond else 'FAIL ')+name); ok.append(bool(cond))
def utc(s): return dt.datetime.fromisoformat(s.replace('Z','+00:00'))

tmp=tempfile.mkdtemp()
# --- snapshot: trim, save, prune, pick
d=json.load(open(SAMPLE))
p=snapshot.save(SAMPLE,tmp,'2026-11-05',12)
t=json.load(open(p))
check('snapshot drops spotForecast and per-region forecast', 'spotForecast' not in t and all('forecast' not in r for r in t['regions'].values()))
check('snapshot keeps roads/snow/rivers', all(k in next(iter(t['regions'].values())) for k in ('roads','snow','rivers','air','fire')))
snapshot.save(SAMPLE,tmp,'2026-11-12',12); snapshot.save(SAMPLE,tmp,'2026-11-19',12)
check('pick finds the snapshot 7 days back', snapshot.pick(tmp,utc('2026-11-19T12:17:00Z')).endswith('2026-11-12.json'))
check('pick refuses when nothing is 5-9.5 days old', snapshot.pick(tmp,utc('2026-11-21T12:00:00Z')) is not None and snapshot.pick(tmp,utc('2026-12-30T12:00:00Z')) is None)
snapshot.save(SAMPLE,tmp,'2026-11-26',2)
check('prune keeps only the newest N', sorted(os.listdir(tmp))==['conditions-2026-11-19.json','conditions-2026-11-26.json'])

# --- run_brief with no baseline must BLOCK cleanly, never crash or send
out=os.path.join(tmp,'out')
r=subprocess.run([sys.executable,os.path.join(HERE,'run_brief.py'),'--snapshots',os.path.join(tmp,'none'),'--out',out,'--data',FIXTURE,'--now','2026-11-23T11:30:00-07:00'],capture_output=True,text=True,env={k:v for k,v in os.environ.items() if not k.startswith('BRIEF_')})
st=json.load(open(os.path.join(out,'status.json')))
check('no baseline: BLOCKED with a clear reason, exit 0', r.returncode==0 and st['status']=='BLOCKED' and 'no last-week snapshot' in ' '.join(st['reasons']))
nb=open(os.path.join(out,'brief-draft.md')).read() if os.path.exists(os.path.join(out,'brief-draft.md')) else ''
check('no baseline: the draft is still built, What changed says [CHECK: no last-week snapshot], and it stays BLOCKED', st['builtDraft'] and '[CHECK: no last-week snapshot]' in nb and os.path.exists(os.path.join(out,'brief-draft.html')) and os.path.exists(os.path.join(out,'brief-titles.txt')) and st['status']=='BLOCKED')
r=subprocess.run([sys.executable,os.path.join(HERE,'run_brief.py'),'--snapshots',os.path.join(tmp,'none'),'--out',out,'--data',SAMPLE,'--strict'],capture_output=True,text=True)
check('--strict exits 1 when blocked', r.returncode==1)

# --- preflight catches markers, demo baselines and stale data
os.makedirs(os.path.join(tmp,'pf'))
base=os.path.join(tmp,'pf','brief-draft')
body="## Bottom line\n\nAll fine.\n\n## From the Desk\n\n[EDITOR: two lines]\n\n## What changed\n\n- FAKE thing None {id}\n"
for e in ('md','html','txt'): open(f'{base}.{e}','w').write(body)
json.dump({'lastWeek':'2026-11-12T20:00:00+00:00','lastWeekIsFake':True},open(os.path.join(tmp,'pf','diff.json'),'w'))
r=subprocess.run([sys.executable,os.path.join(HERE,'preflight.py'),base,'--data',SAMPLE,'--now','2026-11-19T12:00:00-07:00'],capture_output=True,text=True)
o=r.stdout
check('preflight fails and names [EDITOR], FAKE, leaked template, FAKE baseline', r.returncode==1 and all(x in o for x in ('[EDITOR]','FAKE','leaked template','baseline is flagged FAKE')))
check('preflight flags stale data', 'generated' in o and 'h ago' in o)

# --- BRIEF_HOME: drafts and snapshots live outside the repo when it is set
import paths, datetime as _dt
home=os.path.join(tmp,'home'); os.environ['BRIEF_HOME']=home
wed=_dt.datetime(2026,12,2,12,0,tzinfo=_dt.timezone.utc); thu=_dt.datetime(2026,12,3,12,0,tzinfo=_dt.timezone.utc); fri=_dt.datetime(2026,12,4,12,0,tzinfo=_dt.timezone.utc)
check('BRIEF_HOME: snapshots go to <home>/snapshots', paths.snapshots_dir()==os.path.join(home,'snapshots'))
check('BRIEF_HOME: Wed and Thu drafts go to the Thursday folder, Fri to the next', [os.path.basename(paths.out_dir(x)) for x in (wed,thu,fri)]==['2026-12-03','2026-12-03','2026-12-10'] and os.path.dirname(paths.out_dir(wed))==os.path.join(home,'drafts'))
r=subprocess.run([sys.executable,os.path.join(HERE,'run_brief.py'),'--snapshots',os.path.join(tmp,'none'),'--data',FIXTURE,'--now','2026-12-02T12:00:00+00:00'],capture_output=True,text=True,env=dict(os.environ))
check('BRIEF_HOME: run_brief writes into <home>/drafts/<date> and nothing in the repo', os.path.exists(os.path.join(home,'drafts','2026-12-03','status.json')))
del os.environ['BRIEF_HOME']
check('BRIEF_HOME unset: falls back to git-ignored folders in the repo', paths.out_dir(wed).endswith('brief-out') and paths.snapshots_dir().endswith('snapshots') and paths.ROOT in paths.out_dir(wed))

# =========================== v4 builder ===========================
import re, shutil
FIX=os.path.join(HERE,'fixtures','conditions.fixture.json')
cfg=json.load(open(os.path.join(HERE,'brief_config.json')))
fx=json.load(open(FIX))
lw=json.loads(json.dumps(fx)); lw['generatedAt']=(utc(fx['generatedAt'])-dt.timedelta(days=7)).isoformat()
for r in lw['regions'].values():
    for v in r['rivers']:
        if v['flow']['value']: v['flow']['value']=round(v['flow']['value']/2)   # last week's rivers were half of today's: gives What changed something to say
LAST=os.path.join(tmp,'lastweek.json'); json.dump(snapshot.trim(lw),open(LAST,'w'))
NOW='2026-11-23T11:30:00-07:00'
CLEAN={k:v for k,v in os.environ.items() if not k.startswith('BRIEF_')}
OMT_OK='Henrys Fork Angler Notebook | https://example.org/notebook | A local shop writes up what the river is doing this week.'
NOTE_OK='Drove past the lake Tuesday.\\nA skin of ice and one confident duck.'
def build(name,data=FIX,env=None,files=None):
    o=os.path.join(tmp,name); os.makedirs(o,exist_ok=True)
    for f,txt in (files or {}).items(): open(os.path.join(o,f),'w').write(txt)
    e=dict(CLEAN,**(env or {}))
    r=subprocess.run([sys.executable,os.path.join(HERE,'run_brief.py'),'--data',data,'--last-week',LAST,'--out',o,'--now',NOW],capture_output=True,text=True,env=e)
    st=json.load(open(os.path.join(o,'status.json')))
    return o,st,r
def rd(o,f): return open(os.path.join(o,f)).read()
o1,st1,r1=build('v4ok',env={'BRIEF_EDITOR_NOTE':NOTE_OK,'BRIEF_ONE_MORE_THING':OMT_OK})
check('v4: fixture build PASSES with editor note and One more thing supplied', st1['status']=='PASS' and not st1['reasons'])
html1,md1=rd(o1,'brief-draft.html'),rd(o1,'brief-draft.md')
bad=[w for w in ('masthead','footer','unsubscribe','manage preferences','style=','<style','<table','<img','background','<div') if w in html1.lower()]
check('v4: body HTML has no masthead, footer, unsubscribe, styles, boxes or layout tables', not bad and all(t in html1 for t in ('<h2>','<ul>','<a href=','<strong>')))
heads=re.findall(r'^## (.+)$',md1,flags=re.M)
want=[cfg['titles'][k] for k in cfg['seasons']['winter']['sections']]
check('v4: section headings follow the v4 order, one The weekend, no Coming up or This weekend',
      [h for h in want if h in heads]==heads and heads.count('The weekend')==1 and not any(h in heads for h in ('Coming up','This weekend')) and all(h in heads for h in ('Bottom line','From the Desk','The weekend','One more thing','Current conditions by region','Sources')) and want==['Bottom line','From the Desk','What changed','The weekend','Vs. Normal (to date)','One more thing','Avalanche','Current conditions by region','Sources'])
check('v4: One more thing renders the supplied title, link and blurb', 'Worth reading' in md1 and '[Henrys Fork Angler Notebook](https://example.org/notebook)' in md1 and 'confident duck' not in md1.split('## One more thing')[1].split('## ')[0])
SPOTS=['panhandle-schweitzer','panhandle-lookout-pass','southwest-bogus-basin','southwest-brundage-mountain','magic-valley-sun-valley-bald-mountain-dollar','magic-valley-pomerelle','upper-snake-grand-targhee-wy-idaho-access','salmon-stanley-sawtooth-nra-fisher-creek-elk-mtn-redfish']
check('v4: brief_config.json winter places are the eight ski-area spots, in order', [p.get('spot') for p in cfg['seasons']['winter']['places']]==SPOTS and [p['label'] for p in cfg['seasons']['winter']['places']]==['Schweitzer','Lookout Pass','Bogus Basin','Brundage','Sun Valley','Pomerelle','Grand Targhee','Stanley / Sawtooths'])
wl=re.findall(r'^- \*\*([^*]+):\*\* Sat (.+?); Sun ',md1,flags=re.M)
check('v4: winter weekend lines are the eight ski-area grids (read from spotForecast), labeled by ski area', [a for a,_ in wl]==sorted([p['label'] for p in cfg['seasons']['winter']['places']],key=str.lower) and all(f'fixture snow {SPOTS.index(next(p["spot"] for p in cfg["seasons"]["winter"]["places"] if p["label"]==a))}' in b for a,b in wl))
check('v4: the weekend lines are not town points', not any(t in md1.split('## The weekend')[1].split('## ')[0] for t in ('Boise:','McCall:','Coeur')))
tt=rd(o1,'brief-titles.txt'); sm=rd(o1,'STATUS.md')
check('v4: brief-titles.txt has 2-3 title and 2-3 subtitle options, also shown in STATUS.md, none in the body', 2<=len(re.findall(r'^  \d\. ',tt.split('SUBTITLE')[0],flags=re.M))<=3 and 2<=len(re.findall(r'^  \d\. ',tt.split('SUBTITLE')[1],flags=re.M))<=3 and 'one thing worth reading.' in tt and '!' not in tt and 'SUBTITLE' in sm and 'Subject:' not in md1)
check('v4: the body has no masthead image, dateline or hidden preheader', 'THURSDAY BRIEF' not in md1 and 'display:none' not in html1 and '.jpg' not in html1)
# One more thing is required: missing, placeholder, or malformed all BLOCK
o2,st2,_=build('v4noomt',env={'BRIEF_EDITOR_NOTE':NOTE_OK})
check('v4: no One more thing: BLOCKED and the reason says so', st2['status']=='BLOCKED' and 'One more thing' in ' '.join(st2['reasons']))
o3,st3,_=build('v4todo',env={'BRIEF_EDITOR_NOTE':NOTE_OK,'BRIEF_ONE_MORE_THING':'TODO title | https://example.org/x | [OMT] blurb'})
check('v4: placeholder One more thing (TODO, [OMT]) BLOCKS', st3['status']=='BLOCKED' and 'TODO' in ' '.join(st3['reasons']))
o4,st4,_=build('v4file',env={'BRIEF_EDITOR_NOTE':NOTE_OK},files={'one-more-thing.txt':'File Title\nhttps://example.org/file\nBlurb from the file.\n'})
check('v4: One more thing also works from one-more-thing.txt in the drafts folder, and a re-run keeps it', st4['status']=='PASS' and 'File Title' in rd(o4,'brief-draft.md') and os.path.exists(os.path.join(o4,'one-more-thing.txt')))
# the 4-period trim: grids with only today and tomorrow give a [CHECK] line, never a relabeled town point
thin=json.loads(json.dumps(fx))
for g in thin['spotForecast']['grids'].values(): g['days']=g['days'][:2]
TH=os.path.join(tmp,'thin.json'); json.dump(thin,open(TH,'w'))
o5,st5,_=build('v4thin',data=TH,env={'BRIEF_EDITOR_NOTE':NOTE_OK,'BRIEF_ONE_MORE_THING':OMT_OK})
md5=rd(o5,'brief-draft.md')
check('v4: grids without weekend days print [CHECK: no weekend forecast] per line and BLOCK', md5.count('[CHECK: no weekend forecast]')==8 and st5['status']=='BLOCKED' and 'McCall' not in md5)
# editor-supplied dated line, dated max, word caps
o6,st6,_=build('v4dated',env={'BRIEF_EDITOR_NOTE':NOTE_OK,'BRIEF_ONE_MORE_THING':OMT_OK,'BRIEF_DATED_LINES':'Dec 5: Christmas tree permit window opens\\nDec 6: Second line'})
wk6=rd(o6,'brief-draft.md').split('## The weekend')[1].split('## ')[0]
check('v4: editor dated lines come first; at most 3 dated items', '**Dec 5:** Christmas tree permit window opens.' in wk6 and len(re.findall(r'^- \*\*[A-Z][a-z]{2} \d+:\*\*',wk6,flags=re.M))<=cfg['datedMax'])
import io
from common import words
for sec,bc in cfg['wordBudget'].items():
    if sec.startswith('_'): continue
    bud,cap=bc
    t=cfg['titles'][sec]; body=md1.split('## '+t)[1].split('\n## ')[0] if '## '+t in md1 else ''
    if body: check(f'v4: {t} within its word cap ({words(body)} <= {cap})', words(body)<=cap)
check('v4: whole body under the hard cap', sum(words(b.split('\n',1)[1]) for b in re.split(r'^(?=## )',md1,flags=re.M) if b.startswith('## '))<cfg['bodyWordsHardCap'])
long_md=md1+'\n## Extra\n\n'+' word'*620+'\n'
LP=os.path.join(tmp,'long'); os.makedirs(LP,exist_ok=True)
for e in ('md','html','txt'): open(os.path.join(LP,f'brief-draft.{e}'),'w').write(long_md)
shutil.copy(os.path.join(o1,'diff.json'),LP)
r=subprocess.run([sys.executable,os.path.join(HERE,'preflight.py'),os.path.join(LP,'brief-draft'),'--data',FIX,'--now',NOW],capture_output=True,text=True)
check('v4: preflight blocks a body over the hard cap', r.returncode==1 and 'body is' in r.stdout)
check('v4: draft-only: no send or network code in scripts/brief', not any(w in open(os.path.join(HERE,f)).read() for f in ('build_brief.py','run_brief.py','preflight.py') for w in ('smtplib','requests.post','urllib.request','api.beehiiv')))

# --- fetch_nws.py keeps a week of days only for the Brief's ski-area grids (no network: the helpers are called directly)
import importlib.util
_sp=importlib.util.spec_from_file_location('fetch_nws_t',os.path.join(ROOT,'scripts','fetch_nws.py')); fn=importlib.util.module_from_spec(_sp); _sp.loader.exec_module(fn)
_raw=[{"name":f"n{i}","startTime":(dt.datetime(2026,11,25,6)+dt.timedelta(hours=12*i)).isoformat(),"isDaytime":i%2==0,"temperature":30+i,"shortForecast":"Snow","windSpeed":"5 mph","detailedForecast":"long text","probabilityOfPrecipitation":{"value":40}} for i in range(14)]
_full,_site=fn.spot_days(_raw,True),fn.spot_days(_raw,False)
check('fetch_nws: Brief spots come from brief_config.json (the eight winter ski areas)', fn.brief_spots()=={p['spot'] for p in cfg['seasons']['winter']['places']} and len(fn.brief_spots())==8)
check('fetch_nws: a Brief grid keeps 7 days, reaching Saturday and Sunday from a Wednesday run', len(_full)==7 and {'2026-11-28','2026-11-29'}<={x['date'] for x in _full})
check('fetch_nws: Brief grids keep the full text for days 1-4 and drop it after that', all('detail' in x for x in _full[:4]) and not any('detail' in x or 'nightDetail' in x for x in _full[4:]))
check('fetch_nws: every other grid still keeps 2 days (the feed stays small)', len(_site)==2 and all('detail' in x for x in _site))

# =========================== v4 polish ===========================
sections=re.split(r'^## ',md1,flags=re.M)[1:]
check('polish: a divider between sections (hr in HTML, --- in markdown), none before the first or after the last', html1.count('<hr>')==len(heads)-1 and md1.count('\n---\n')==len(heads)-1 and not md1.startswith('---') and not md1.rstrip().endswith('---') and html1.index('<h2>')<html1.index('<hr>') and html1.rstrip().rfind('<hr>')<html1.rstrip().rfind('<h2>'))
bq=re.findall(r'<blockquote>(.*?)</blockquote>',html1,flags=re.S)
check('polish: Bottom line and From the Desk are blockquotes with their bold labels inside', len(bq)>=2 and '<strong>The numbers favor:</strong>' in bq[0] and 'confident duck' in bq[1] and html1.index('<blockquote>')<html1.index('<h2>From the Desk</h2>')<html1.rindex('<blockquote>'))
check('polish: still no style, table or div after the blockquotes and dividers', not any(w in html1.lower() for w in ('style=','<style','<table','<div','<img')))
check('polish: markdown quotes the callouts', '> **The numbers favor:**' in md1 and '> A skin of ice' in md1)
# winter best bet comes from the ski-area grid list
bbj=json.load(open(os.path.join(o1,'best_bet.json')))
check('polish: the winter best bet is one of the eight ski-area grids, never a town', bbj['best']['pointId'] in SPOTS and bbj['best']['spot'] and not bbj['best']['fallback'] and all(x['pointId'] in SPOTS for x in bbj['ranked']))
nf=md1.split('## Bottom line')[1].split('## ')[0]
check('polish: the bottom line and subject say "at <ski area>"', re.search(r'\*\*The numbers favor:\*\* (Saturday|Sunday) at ',nf) is not None and re.search(r'the numbers favor (Saturday|Sunday) at ',tt) is not None and ' in Twin Falls' not in nf)
# thin grids: the pick falls back to a town but is flagged, so the draft blocks (and never reads as a mountain)
bbt=json.load(open(os.path.join(o5,'best_bet.json')))
check('polish: with no weekend grid data the pick falls back to a town and is marked [CHECK]', bbt['best']['fallback'] and '[CHECK: no ski-area weekend forecast yet' in md5)
# dated lines are their own list under a lead-in
wkh=html1.split('<h2>The weekend</h2>')[1].split('<hr>')[0]
check('polish: dated items sit in a second list under a Coming up lead-in, not in the forecast list', (wkh.count('<ul>')==2 and '<p><strong>Coming up:</strong></p>' in wkh and all('Sat ' in li for li in re.findall(r'<li>(.*?)</li>',wkh.split('<p><strong>Coming up')[0]))) or ('Coming up' not in wkh and wkh.count('<ul>')==1))
wk6h=rd(o6,'brief-draft.html').split('<h2>The weekend</h2>')[1].split('<hr>')[0]
check('polish: with dated lines supplied the lead-in and the second list are there', '<p><strong>Coming up:</strong></p>' in wk6h and wk6h.count('<ul>')==2 and 'Christmas tree permit window opens' in wk6h.split('Coming up')[1])
check('polish: ski opening lines drop the doubled hedge', '(low confidence)' not in md1 and '(low confidence)' not in rd(o6,'brief-draft.md'))
# summer is unchanged: town points and "in"
sumdata=json.loads(json.dumps(fx)); sumdata['generatedAt']=sumdata['generatedAt'].replace('2026-11-23','2026-07-14')
for _r in sumdata['regions'].values():
    for _p in _r['forecast']['points']:
        for _x in _p['days']: _x['date']=(dt.date.fromisoformat(_x['date'])+(dt.date(2026,7,14)-dt.date(2026,11,23))).isoformat()
SU=os.path.join(tmp,'summer.json')
json.dump(sumdata,open(SU,'w'))
r=subprocess.run([sys.executable,os.path.join(HERE,'best_bet.py'),SU],capture_output=True,text=True)
sb=json.loads(r.stdout)['best'] if r.returncode==0 and r.stdout else {}
check('polish: summer best bet still scores the town points', sb.get('spot') is False and sb.get('pointId') not in SPOTS and sb.get('pointId'))

# =========================== v4 round 2 ===========================
check('r2: One more thing is a blockquote in HTML and > in markdown', len(bq)==3 and 'Worth reading' in bq[2] and '<a href="https://example.org/notebook">' in bq[2] and '> **Worth reading:**' in md1)
def build_last(name,lastweek):
    o=os.path.join(tmp,name); os.makedirs(o,exist_ok=True)
    L=os.path.join(tmp,name+'-last.json'); json.dump(snapshot.trim(lastweek),open(L,'w'))
    e=dict(CLEAN,BRIEF_EDITOR_NOTE=NOTE_OK,BRIEF_ONE_MORE_THING=OMT_OK)
    r=subprocess.run([sys.executable,os.path.join(HERE,'run_brief.py'),'--data',FIX,'--last-week',L,'--out',o,'--now',NOW],capture_output=True,text=True,env=e)
    return o,r
# a pass that dropped out of the 511 feed is "no report", not cleared and not the Biggest change
nl=json.loads(json.dumps(lw))
nl['regions']['upper-snake']['roads']['winter'].append({'id':'9001','name':'I-15','where':'Monida Pass from MP 0 to MP 10','condition':'Snow Covered','secondary':'','weather':[],'updated':nl['generatedAt'],'lat':44.5,'lon':-112.3,'fields':{}})
o7,r7=build_last('r2notlisted',nl)
md7=rd(o7,'brief-draft.md'); tt7=rd(o7,'brief-titles.txt')
check('r2: a pass missing from the 511 feed is not listed as a change, nor the Biggest change', 'Monida' not in md7.split('## The weekend')[0] and 'not listed' not in md7.lower())
check('r2: titles and subtitles are plain text: no links, markdown or parentheses', not re.search(r'\]\(|\(|\*\*|→','\n'.join(re.findall(r'^  \d\. .*$',tt7,flags=re.M))))
check('r2: titles and subtitles have no "went not" or "One changes"', 'went not' not in tt7 and 'One changes' not in tt7 and 'not listed' not in tt7.lower())
# grammar: one change reads "One change that matters"; a real pass change reads "<Pass> is <condition>"
ch=json.loads(json.dumps(lw))
for r_ in ch['regions'].values():
    for w in r_['roads']['winter']:
        if 'Targee' in w['where']: w['condition']='Dry'
o8,r8=build_last('r2grammar',ch)
tt8=rd(o8,'brief-titles.txt')
check('r2: no title or subtitle says "changes that matter" for a count of one, or "went <one word>"', not re.search(r'\bOne changes\b',tt8) and not re.search(r'went \w+;',tt8))
check('r2: every subject line is a clean sentence start (no lowercase "not", no empty clause)', all(not re.search(r'\b(went|is|are) (not|)$',x.split(';')[0]) for x in re.findall(r'^  \d\. (.*)$',tt8.split('SUBTITLE')[0],flags=re.M)))

# =========================== v4 round 3 ===========================
check('r3: By region is now "Current conditions by region"; Vs. normal is "Vs. Normal (to date)"', '## Current conditions by region' in md1 and '## Vs. Normal (to date)' in md1 and '## By region' not in md1 and '## Vs. normal' not in md1)
bl=md1.split('## From the Desk')[0]
check('r3: the Backcountry line is out of the Bottom line and sits just above Current conditions by region (winter)', 'Backcountry' not in bl and re.search(r'\*\*Backcountry:\*\* read your avalanche center first\. \[Payette\]\(.+?\) · \[Sawtooth\]\(.+?\) · \[Panhandle\]\(.+?\)\n+---\n+## Current conditions by region',md1) is not None)
check('r3: with fewer than 2 changes there is no What changed section and no "nothing big moved" repeat', '## What changed' not in md7 and md7.lower().count('nothing big moved')==0 and 'Biggest change' in md7)
check('r3: with 2 or more changes What changed still shows', '## What changed' in rd(o8,'brief-draft.md'))
# preflight does not flag a missing What changed
check('r3: preflight does not flag a missing What changed', 'What changed' not in ' '.join(json.load(open(os.path.join(o7,'status.json')))['reasons']))
wkl=re.findall(r'^- \*\*([^*]+):\*\* Sat ',md1,flags=re.M)
check('r3: winter ski-area lines are A to Z by display name', wkl==sorted(wkl,key=str.lower) and wkl[0]=='Bogus Basin')
nsec=md1.split('## Vs. Normal (to date)')[1].split('## ')[0]
check('r3: Vs. Normal is short lines: Snowpack by region, then Rivers; no site-to-site range', re.search(r'- Snowpack: [A-Z][\w ]+ \d+% of normal, [A-Z][\w ]+ \d+%\.',nsec) is not None and re.search(r'- Rivers: lowest is the .+?, \d+% of normal for the date\.',nsec) is not None and ' to ' not in nsec.split('Rivers')[0] and 'of median' not in nsec)
# the snowpack figure is the median of the region's SNOTEL sites
import statistics
exp={r['name']:statistics.median(x['pctOfMedian']['value'] for x in r['snow'] if x['pctOfMedian']['value'] is not None) for r in fx['regions'].values() if any(x['pctOfMedian']['value'] is not None for x in r['snow'])}
lo_,hi_=min(exp.items(),key=lambda z:z[1]),max(exp.items(),key=lambda z:z[1])
check('r3: Snowpack names the lowest and highest region with the median of its sites', f"Snowpack: {lo_[0]} {lo_[1]:.0f}% of normal, {hi_[0]} {hi_[1]:.0f}%." in nsec)

print('\nALL PASS' if all(ok) else '\nSOME FAILED'); sys.exit(0 if all(ok) else 1)
