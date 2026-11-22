"""Weekly snapshots of data/conditions.json, for the Thursday Brief's "what changed" diff.

  python3 scripts/brief/snapshot.py save [--src FILE] [--dir DIR] [--date YYYY-MM-DD] [--keep 12]
      Writes DIR/conditions-YYYY-MM-DD.json (trimmed: forecasts dropped, they are not diffed) and prunes to the newest --keep.
  python3 scripts/brief/snapshot.py pick [--dir DIR] [--now ISO]
      Prints the path of the snapshot closest to 7 days before --now (must be 5 to 9.5 days old). Exit 1 and no output if none.

DIR defaults to $BRIEF_HOME/snapshots when BRIEF_HOME is set (see paths.py), else <repo>/snapshots. This script touches files only; it never uses git."""
import os, sys, re, json, glob, argparse, datetime as dt
import paths
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.normpath(os.path.join(HERE,'..','..'))
PAT=re.compile(r'conditions-(\d{4}-\d{2}-\d{2})\.json$')

def iso(ts): return dt.datetime.fromisoformat(ts.replace('Z','+00:00'))

def trim(d):
    d=dict(d); d.pop('spotForecast',None)
    d['regions']={k:{kk:vv for kk,vv in r.items() if kk!='forecast'} for k,r in d['regions'].items()}
    return d

def listing(dirpath):
    out=[]
    for f in glob.glob(os.path.join(dirpath,'conditions-*.json')):
        m=PAT.search(f)
        if m: out.append((m.group(1),f))
    return sorted(out)

def save(src,dirpath,date,keep):
    os.makedirs(dirpath,exist_ok=True)
    d=json.load(open(src))
    date=date or iso(d['generatedAt']).astimezone(dt.timezone(dt.timedelta(hours=-7))).date().isoformat()
    path=os.path.join(dirpath,f'conditions-{date}.json')
    tmp=path+'.tmp'
    with open(tmp,'w') as f: json.dump(trim(d),f,separators=(',',':'))
    os.replace(tmp,path)
    for _,f in listing(dirpath)[:-keep]: os.remove(f)
    return path

def pick(dirpath,now):
    best=None
    for date,f in listing(dirpath):
        days=(now-dt.datetime.fromisoformat(date+'T12:00:00+00:00')).total_seconds()/86400
        if 5<=days<=9.5 and (best is None or abs(days-7)<best[0]): best=(abs(days-7),f)
    return best[1] if best else None

def main(argv=None):
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('save'); s.add_argument('--src',default=os.path.join(ROOT,'data','conditions.json'))
    s.add_argument('--dir',default=paths.snapshots_dir()); s.add_argument('--date'); s.add_argument('--keep',type=int,default=12)
    p=sub.add_parser('pick'); p.add_argument('--dir',default=paths.snapshots_dir()); p.add_argument('--now')
    a=ap.parse_args(argv)
    if a.cmd=='save': print(save(a.src,a.dir,a.date,a.keep)); return 0
    now=iso(a.now) if a.now else dt.datetime.now(dt.timezone.utc)
    r=pick(a.dir,now)
    if r: print(r); return 0
    print('no snapshot 5 to 9.5 days old in '+a.dir,file=sys.stderr); return 1

if __name__=='__main__': sys.exit(main())
