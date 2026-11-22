"""Where Brief files live. One optional environment variable, BRIEF_HOME, names a folder outside the repo.

  BRIEF_HOME set:    drafts go to $BRIEF_HOME/drafts/<send date>/  and weekly snapshots to $BRIEF_HOME/snapshots/
  BRIEF_HOME unset:  drafts go to <repo>/brief-out/  and snapshots to <repo>/snapshots/  (both git-ignored)

The send date is the next Thursday on or after today (Boise time), so a draft built Wednesday or Thursday lands in that Thursday's folder.
Command-line flags (--out, --dir, --snapshots) and BRIEF_OUT still override all of this."""
import os, datetime as dt
from zoneinfo import ZoneInfo
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.normpath(os.path.join(HERE,'..','..'))

def home():
    h=(os.environ.get('BRIEF_HOME') or '').strip()
    return os.path.abspath(os.path.expanduser(h)) if h else None

def snapshots_dir():
    h=home()
    return os.path.join(h,'snapshots') if h else os.path.join(ROOT,'snapshots')

def next_thursday(now=None):
    today=(now or dt.datetime.now(ZoneInfo('America/Boise'))).date()
    return today+dt.timedelta(days=(3-today.weekday())%7)

def out_dir(now=None):
    h=home()
    return os.path.join(h,'drafts',next_thursday(now).isoformat()) if h else os.path.join(ROOT,'brief-out')
