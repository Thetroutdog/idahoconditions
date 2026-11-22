"""Self-test for the Brief tools. Run: python3 scripts/brief/selftest.py  (uses data/conditions.sample.json, no network)."""
import os, sys, json, tempfile, subprocess, datetime as dt
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.normpath(os.path.join(HERE,'..','..'))
sys.path.insert(0,HERE)
import snapshot
SAMPLE=os.path.join(ROOT,'data','conditions.sample.json')
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
r=subprocess.run([sys.executable,os.path.join(HERE,'run_brief.py'),'--snapshots',os.path.join(tmp,'none'),'--out',out,'--data',SAMPLE],capture_output=True,text=True)
st=json.load(open(os.path.join(out,'status.json')))
check('no baseline: BLOCKED with a clear reason, exit 0', r.returncode==0 and st['status']=='BLOCKED' and 'no last-week snapshot' in ' '.join(st['reasons']))
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
r=subprocess.run([sys.executable,os.path.join(HERE,'run_brief.py'),'--snapshots',os.path.join(tmp,'none'),'--data',SAMPLE,'--now','2026-12-02T12:00:00+00:00'],capture_output=True,text=True,env=dict(os.environ))
check('BRIEF_HOME: run_brief writes into <home>/drafts/<date> and nothing in the repo', os.path.exists(os.path.join(home,'drafts','2026-12-03','status.json')))
del os.environ['BRIEF_HOME']
check('BRIEF_HOME unset: falls back to git-ignored folders in the repo', paths.out_dir(wed).endswith('brief-out') and paths.snapshots_dir().endswith('snapshots') and paths.ROOT in paths.out_dir(wed))

print('\nALL PASS' if all(ok) else '\nSOME FAILED'); sys.exit(0 if all(ok) else 1)
