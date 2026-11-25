"""Build the Thursday Brief DRAFT. Draft-only by design: this writes files and never sends, posts or emails anything.

  python3 scripts/brief/run_brief.py [--snapshots DIR] [--out DIR] [--last-week FILE] [--now ISO] [--strict]

Steps: pick last week's snapshot -> diff_week -> best_bet -> build_brief -> pre-send check (preflight). With no last-week snapshot the draft is still built and the run is BLOCKED.
Human inputs (environment): BRIEF_EDITOR_NOTE, BRIEF_ONE_MORE_THING (or one-more-thing.txt in the output folder), BRIEF_BEST_BET_OVERRIDE, optional BRIEF_DATED_LINES (or dated-lines.txt).
Without the editor's note or the One more thing the check BLOCKS on purpose.
Output folder (default: see paths.py; $BRIEF_HOME/drafts/<send date>/ if BRIEF_HOME is set, else <repo>/brief-out): brief-draft.{html,md,txt} (body only, paste-safe),
brief-titles.txt (title and subtitle options), diff.json, best_bet.json, STATUS.md, status.json. Inputs the editor drops in that folder (one-more-thing.txt, dated-lines.txt) are kept between runs.
Exit code is 0 even when BLOCKED (the draft is still worth reading); --strict makes BLOCKED exit 1.
Read STATUS.md. PASS means the automatic checks found nothing, not that the Brief is right: read it before pasting."""
import os, sys, json, shutil, argparse, subprocess, datetime as dt
import paths
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.normpath(os.path.join(HERE,'..','..'))
PY=sys.executable

def run(cmd,env,stdout=None):
    return subprocess.run([PY]+cmd,env=env,stdout=stdout,stderr=subprocess.PIPE,text=True)

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--snapshots',default=paths.snapshots_dir()); ap.add_argument('--out')
    ap.add_argument('--last-week'); ap.add_argument('--now'); ap.add_argument('--strict',action='store_true')
    ap.add_argument('--data',default=os.path.join(ROOT,'data','conditions.json'))
    a=ap.parse_args(argv)
    if not a.out: a.out=paths.out_dir(dt.datetime.fromisoformat(a.now.replace('Z','+00:00')) if a.now else None)
    os.makedirs(a.out,exist_ok=True)
    KEEP={'one-more-thing.txt','dated-lines.txt'}   # editor inputs live in the drafts folder; a re-run must not wipe them
    for f in os.listdir(a.out):
        p=os.path.join(a.out,f)
        if os.path.isfile(p) and f not in KEEP: os.remove(p)
    env=dict(os.environ,BRIEF_OUT=a.out,BRIEF_CONDITIONS=a.data)
    problems=[]; log=[]
    last=a.last_week
    if not last:
        r=run([os.path.join(HERE,'snapshot.py'),'pick','--dir',a.snapshots]+(['--now',a.now] if a.now else []),env,subprocess.PIPE)
        last=r.stdout.strip() if r.returncode==0 else None
        if not last: problems.append("no last-week snapshot yet (the first Brief has nothing to compare with): "+r.stderr.strip())
    built=False
    # No last-week snapshot (the first Brief): still build, with What changed marked [CHECK: no last-week snapshot]; the run stays BLOCKED.
    steps=[('best_bet',[os.path.join(HERE,'best_bet.py'),a.data],'best_bet.json')]
    if last: steps.insert(0,('diff_week',[os.path.join(HERE,'diff_week.py'),a.data,last],'diff.json'))
    else: json.dump({'ranked':[],'lastWeek':None,'lastWeekIsFake':False,'noBaseline':True},open(os.path.join(a.out,'diff.json'),'w'))
    ok=True
    for name,cmd,outn in steps:
        with open(os.path.join(a.out,outn),'w') as fh: r=run(cmd,env,fh)
        if r.returncode: problems.append(f"{name} failed: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.returncode}"); ok=False; break
    if ok:
        r=run([os.path.join(HERE,'build_brief.py')],env,subprocess.PIPE)
        log.append(r.stdout)
        if r.returncode: problems.append("build_brief failed: "+(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else str(r.returncode)))
        else: built=True
    reasons=[]
    if built:
        r=run([os.path.join(HERE,'preflight.py'),os.path.join(a.out,'brief-draft'),'--data',a.data]+(['--now',a.now] if a.now else []),env,subprocess.PIPE)
        pf=r.stdout.strip(); log.append(pf)
        if r.returncode: reasons=[l.strip()[2:] for l in pf.splitlines() if l.strip().startswith('- ')] or [pf or r.stderr.strip()]
    status='PASS' if built and not reasons and not problems else 'BLOCKED'
    reasons=problems+reasons
    ts=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    data_ok=not any(x.startswith(('source ','conditions.json generated')) for x in reasons)   # a snapshot of stale or failed data would poison next week's diff
    json.dump({'status':status,'dataOk':data_ok,'reasons':reasons,'builtDraft':built,'generated':ts,'lastWeek':os.path.basename(last) if last else None},open(os.path.join(a.out,'status.json'),'w'),indent=1)
    md=[f"# Brief draft: {status}","",f"Built {ts}. DRAFT ONLY: nothing was sent. You paste it into beehiiv yourself.",""]
    if status=='PASS': md+=["Automatic checks found nothing. Still read it before you paste: PASS is not proof it is right.",""]
    else: md+=["Fix these before pasting:",""]+[f"- {x}" for x in reasons]+[""]
    if built:
        md+=["Files: `brief-draft.html` (body only; open it in a browser, copy, paste into the beehiiv body), `brief-draft.md`, `brief-draft.txt`, `brief-titles.txt` (title and subtitle options).",""]
        tf=os.path.join(a.out,'brief-titles.txt')
        if os.path.exists(tf): md+=["Pick one title and one subtitle and paste them into beehiiv's title and subtitle fields (not the body):","","```",open(tf).read().rstrip(),"```",""]
    md+=["```",*[l for l in '\n'.join(log).splitlines()],"```",""]
    open(os.path.join(a.out,'STATUS.md'),'w').write('\n'.join(md))
    print(f"output: {a.out}")
    print(f"{status}: "+('; '.join(reasons) if reasons else 'no problems'))
    return 1 if (a.strict and status!='PASS') else 0

if __name__=='__main__': sys.exit(main())
