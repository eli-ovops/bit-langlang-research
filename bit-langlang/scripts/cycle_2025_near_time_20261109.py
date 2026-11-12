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
from cycle_article_near_time_20261109 import asof_next_midnight
from cycle_pullback_blindpack_20261105 import chart

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'data/verify/cycle-report-archive-20261109-01'
RECOVERY=ROOT/'data/verify/cycle-report-archive-recovery-20261109-01'
REMAIN=ROOT/'data/verify/cycle-report-archive-remaining-20261109-01'
OUT=ROOT/'data/verify/cycle-2025-near-time-20261109-01'
PRICE=ROOT/'data/market/btc-2025q2-usd-cross-20261104-01/bitstamp-4h.csv.gz'
DAY=timedelta(days=1)


def readbytes(p):
    b=p.read_bytes()
    return gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b


def main():
    assert readbytes(PRICE)[:2]!=b'\x1f\x8b'
    source=json.loads((OLD/'summary.json').read_text())['results']
    completed={x['index']:x for x in json.loads((REMAIN/'progress.json').read_text())}
    data=daily(PRICE);OUT.mkdir(parents=True,exist_ok=False)
    records=[];no_network=False
    for index in range(12,25):
        old=source[index-1];n=f'{index:02d}';weekly=datetime.fromisoformat(old['as_of_utc'].replace('Z','+00:00'))
        cdxfile=(RECOVERY/f'{n}.cdx.json') if index in (14,15) else (REMAIN/f'{n}.cdx.body')
        r={'index':index,'weekly_asof':old['as_of_utc'],'article_url':old['url'],'status':'UNKNOWN','phase':'UNKNOWN','sentiment':'UNKNOWN'}
        try:
            rows=json.loads(readbytes(cdxfile))
            if not isinstance(rows,list) or (rows and rows[0]!=['timestamp','original','statuscode','digest']):raise ValueError('BAD_CDX')
            choices=[(datetime.strptime(x[0],'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc),x) for x in rows[1:] if x[2]=='200']
            choices=[(t,x) for t,x in choices if t<weekly]
            if not choices:raise ValueError('NO_CAPTURE_IN_BOUNDED_INDEX')
            cap,selected=min(choices,key=lambda x:x[0]);at=asof_next_midnight(cap);r.update(capture_utc=cap.isoformat(),review_asof_utc=at.isoformat(),cdx_sha256=hashlib.sha256(cdxfile.read_bytes()).hexdigest())
            if not cap<=at<weekly:raise ValueError('NO_EARLIER_DAILY_OBSERVATION')
            u=f'https://web.archive.org/web/{selected[0]}id_/{selected[1]}'
            if index in (14,15):
                prevbody=RECOVERY/f'{n}.html';prevhead=RECOVERY/f'{n}.headers'
                headers=prevhead.read_text();ms=re.findall(r'(?im)^memento-datetime:\s*(.+?)\s*$',headers)
                local=(len(ms)==1 and parsedate_to_datetime(ms[0])==cap)
            else:
                p=completed.get(index,{})
                local=p.get('memento_utc')==cap.isoformat() and p.get('status','').startswith('ARCHIVE_')
                prevbody=REMAIN/f'{n}.archive.body';prevhead=REMAIN/f'{n}.archive.headers'
            if local:
                raw=prevbody.read_bytes();headers=prevhead.read_text();r['archive_storage']=str(prevbody.relative_to(ROOT))
            else:
                if no_network:raise ValueError('NOT_ATTEMPTED_AFTER_CONNECTION_FAILURE')
                hdr=OUT/f'{n}.headers';body=OUT/f'{n}.html'
                proc=subprocess.run(['curl','--silent','--show-error','--location','--compressed','--max-time','25','--dump-header',str(hdr),'--output',str(body),'--write-out','%{http_code}\n%{url_effective}',u],capture_output=True,text=True)
                r.update(curl_exit=proc.returncode,curl_output=proc.stdout.strip(),curl_error=proc.stderr.strip())
                if proc.returncode or not proc.stdout.startswith('200\n'):
                    no_network=True;raise ValueError('ARCHIVE_REQUEST_FAILED')
                raw=body.read_bytes();headers=hdr.read_text();r['archive_storage']=str(body.relative_to(ROOT))
            m=re.findall(r'(?im)^memento-datetime:\s*(.+?)\s*$',headers)
            if len(m)!=1 or parsedate_to_datetime(m[0])!=cap:raise ValueError('MEMENTO_MISMATCH')
            html=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
            title,text,_=content(html)
            bars=[data.get(at-DAY*i) for i in range(56,0,-1)]
            if any(x is None for x in bars):raise ValueError('INCOMPLETE_56_DAYS')
            r.update(status='DATA_READY',archive_url=u,article_title=title,archive_raw_sha256=hashlib.sha256(raw).hexdigest(),body_sha256=hashlib.sha256(text.encode()).hexdigest(),
                     last_close=bars[-1]['close'],high56=max(x['high'] for x in bars),low56=min(x['low'] for x in bars),high14=max(x['high'] for x in bars[-14:]),low14=min(x['low'] for x in bars[-14:]))
            with (OUT/f'{n}.daily.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['date_start_utc','open','high','low','close']);w.writeheader()
                for i,b in enumerate(bars):w.writerow({'date_start_utc':(at-DAY*(56-i)).isoformat(),**b})
            factor=100/bars[-1]['close'];candles=[[b[k]*factor for k in ('open','high','low','close')] for b in bars]
            fig,axes=plt.subplots(1,2,figsize=(13,4.4),constrained_layout=True,gridspec_kw={'width_ratios':[2,1]})
            chart(axes[0],candles,-56);chart(axes[1],candles[-14:],-14)
            axes[0].set_title('56 completed daily candles');axes[1].set_title('Last 14 days');fig.suptitle(f'Observation {n}')
            fig.savefig(OUT/f'{n}.png',dpi=130,metadata={'Software':'Matplotlib'});plt.close(fig)
        except (ValueError,KeyError,IndexError,TypeError,OSError) as e:r['error']=str(e)
        records.append(r);(OUT/'summary.json').write_text(json.dumps(records,indent=2,ensure_ascii=False)+'\n')
        print(index,r['status'],r.get('capture_utc',''),r.get('review_asof_utc',''),r.get('error',''),flush=True)
    assert len(records)==13


if __name__=='__main__':main()
