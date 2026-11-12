import csv
import gzip
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from cycle_causal_pullback_20261105 import daily
from cycle_article_archive_audit_20261109 import content
from cycle_pullback_blindpack_20261105 import chart

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'data/verify/cycle-report-archive-20261109-01'
OUT=ROOT/'data/verify/cycle-article-near-time-20261109-01'
PRICE=ROOT/'data/verify/cycle-2023q1-phase-20261104-01/bitstamp-4h.csv'
DAY=timedelta(days=1)


def sha(v):return hashlib.sha256(v).hexdigest()


def asof_next_midnight(t):
    start=t.replace(hour=0,minute=0,second=0,microsecond=0)
    return start if t==start else start+DAY


def main():
    t=datetime(2023,1,1,0,0,tzinfo=timezone.utc)
    assert asof_next_midnight(t)==t and asof_next_midnight(t+timedelta(seconds=1))==t+DAY
    source=json.loads((OLD/'summary.json').read_text())['results'];data=daily(PRICE)
    OUT.mkdir(parents=True,exist_ok=False);records=[]
    for n in range(1,5):
        original=source[n-1];cdx=json.loads((OLD/f'{n:02d}'/'cdx.json').read_text());old_asof=datetime.fromisoformat(original['as_of_utc'].replace('Z','+00:00'))
        choices=[(datetime.strptime(x[0],'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc),x) for x in cdx[1:] if x[2]=='200']
        choices=[(t,x) for t,x in choices if t<old_asof]
        r={'index':n,'weekly_asof':original['as_of_utc'],'article_url':original['url'],'status':'UNKNOWN','phase':'UNKNOWN','sentiment':'UNKNOWN'}
        try:
            if not choices:raise ValueError('NO_CAPTURE_BEFORE_WEEKLY')
            cap,selected=min(choices,key=lambda x:x[0]);at=asof_next_midnight(cap);r.update(capture_utc=cap.isoformat(),review_asof_utc=at.isoformat())
            if at>=old_asof:raise ValueError('NO_EARLIER_DAILY_OBSERVATION')
            u=f'https://web.archive.org/web/{selected[0]}id_/{selected[1]}'
            hdr=OUT/f'{n:02d}.headers';body=OUT/f'{n:02d}.html'
            p=subprocess.run(['curl','--silent','--show-error','--location','--compressed','--max-time','25','--dump-header',str(hdr),'--output',str(body),'--write-out','%{http_code}\n%{url_effective}',u],capture_output=True,text=True)
            r.update(curl_exit=p.returncode,curl_output=p.stdout.strip(),curl_error=p.stderr.strip())
            if p.returncode or not p.stdout.startswith('200\n'):raise ValueError('ARCHIVE_REQUEST_FAILED')
            raw=body.read_bytes();headers=hdr.read_text();m=re.findall(r'(?im)^memento-datetime:\s*(.+?)\s*$',headers)
            if len(m)!=1 or parsedate_to_datetime(m[0])!=cap:raise ValueError('MEMENTO_MISMATCH')
            html=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
            title,text,_=content(html)
            bars=[data.get(at-DAY*i) for i in range(56,0,-1)]
            if any(x is None for x in bars):raise ValueError('INCOMPLETE_56_DAYS')
            assert len(bars)==56 and at-DAY+DAY==at
            r.update(status='DATA_READY',archive_url=u,article_title=title,archive_raw_sha256=sha(raw),body_sha256=sha(text.encode()),
                     price_start_utc=(at-56*DAY).isoformat(),last_close=bars[-1]['close'],high56=max(x['high'] for x in bars),low56=min(x['low'] for x in bars),
                     high14=max(x['high'] for x in bars[-14:]),low14=min(x['low'] for x in bars[-14:]))
            with (OUT/f'{n:02d}.daily.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['date_start_utc','open','high','low','close']);w.writeheader()
                for i,b in enumerate(bars):w.writerow({'date_start_utc':(at-DAY*(56-i)).isoformat(),**b})
            factor=100/bars[-1]['close'];candles=[[b[k]*factor for k in ('open','high','low','close')] for b in bars]
            fig,axes=plt.subplots(1,2,figsize=(13,4.4),constrained_layout=True,gridspec_kw={'width_ratios':[2,1]})
            chart(axes[0],candles,-56);chart(axes[1],candles[-14:],-14)
            axes[0].set_title('56 completed daily candles');axes[1].set_title('Last 14 days');fig.suptitle(f'Observation {n:02d}')
            fig.savefig(OUT/f'{n:02d}.png',dpi=130,metadata={'Software':'Matplotlib'});plt.close(fig)
        except (ValueError,KeyError,IndexError) as e:r['error']=str(e)
        records.append(r)
        (OUT/'summary.json').write_text(json.dumps(records,indent=2,ensure_ascii=False)+'\n')
        print(n,r['status'],r.get('capture_utc'),r.get('review_asof_utc'),r.get('error',''),flush=True)
        if r.get('error') in ('ARCHIVE_REQUEST_FAILED','MEMENTO_MISMATCH'):break
    print('processed',len(records),'of 4',flush=True)


if __name__=='__main__':main()
