import base64
import csv
import gzip
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/verify/cycle-market-archive-20261109-01'
SOURCE = ROOT/'data/verify/cycle-pullback-supplement-20261105-01/segments.csv'
A01 = ROOT/'data/verify/cycle-a01-market-archive-20261109-01'


def unpack(path):
    b = path.read_bytes()
    return gzip.decompress(b) if b[:2] == b'\x1f\x8b' else b


def get(url, body, headers, params=(), raw_response=False):
    command = ['curl','--silent','--show-error','--location','--max-time','25','--dump-header',str(headers),'--output',str(body),'--write-out','%{http_code}\n%{url_effective}']
    if not raw_response: command.append('--compressed')
    if params:
        command += ['--get',url]
        for x in params: command += ['--data-urlencode',x]
    else: command.append(url)
    p = subprocess.run(command,capture_output=True,text=True)
    if p.returncode or not p.stdout.startswith('200\n'):
        raise ConnectionError(f'curl={p.returncode} http={p.stdout[:3]} stderr={p.stderr.strip()[:200]}')
    time.sleep(.4)


def parse_page(raw):
    soup = BeautifulSoup(raw, 'html.parser')
    for table in soup.select('table'):
        heads = [x.get_text(' ',strip=True) for x in table.select('thead th')]
        if not all(x in heads for x in ('#','Coin','7d')): continue
        idx={x:heads.index(x) for x in ('#','Coin','7d')};trs=table.select('tbody tr');items=[]
        if len(trs)<30: raise ValueError('LESS_THAN_30_ROWS')
        for n,tr in enumerate(trs[:30],1):
            cells=tr.select('td')
            if len(cells)<=max(idx.values()) or cells[idx['#']].get_text(strip=True)!=str(n): raise ValueError('RANK_MISMATCH')
            name=cells[idx['Coin']].get_text(' ',strip=True);v=cells[idx['7d']].get_text(' ',strip=True)
            if not name or not re.fullmatch(r'[+\-]?\d+(?:\.\d+)?%',v): raise ValueError('INVALID_DISPLAY')
            num=float(v[:-1]);span=cells[idx['7d']].select_one('span');classes=set(span.get('class',[])) if span else set()
            up=bool(classes & {'gecko-up','text-green'});down=bool(classes & {'gecko-down','text-danger'})
            if up==down: raise ValueError('AMBIGUOUS_DIRECTION_STYLE')
            if num < 0 and not down: raise ValueError('DIRECTION_STYLE_CONFLICT')
            direction='ZERO_DISPLAYED' if num==0 else 'DOWN' if down else 'UP'
            signed_display=('-' if down and num>0 else '')+v
            items.append({'rank':n,'name':name,'change7_display':signed_display,'direction':direction})
        return items
    raise ValueError('EXPECTED_TABLE_ABSENT')


def main():
    assert re.fullmatch(r'[+\-]?\d+(?:\.\d+)?%', '-7.4%')
    with SOURCE.open(newline='') as f: obs=list(csv.DictReader(f))
    assert len(obs)==26 and {x['quarter'] for x in obs}=={'2023Q1','2025Q2'}
    OUT.mkdir(parents=True,exist_ok=False);results=[];items=[];network_failed=False
    for i,row in enumerate(obs,1):
        n=f'{i:02d}';t=datetime.fromisoformat(row['as_of_utc']);day=(t-timedelta(days=1)).strftime('%Y%m%d')
        r={'index':i,'quarter':row['quarter'],'as_of_utc':t.isoformat(),'status':'UNKNOWN','phase':'UNKNOWN','sentiment':'UNKNOWN'}
        cdx=OUT/f'{n}.cdx';ch=OUT/f'{n}.cdx.headers';body=OUT/f'{n}.html';head=OUT/f'{n}.headers'
        try:
            if day=='20230211': cdx=A01/'cdx.json';body=A01/'archive.html';head=A01/'archive.headers'
            else:
                if network_failed: raise ValueError('NOT_ATTEMPTED_AFTER_NETWORK_FAILURE')
                get('https://web.archive.org/cdx/search/cdx',cdx,ch,['url=https://www.coingecko.com/','output=json','fl=timestamp,original,statuscode,digest','filter=statuscode:200','from='+day,'to='+day])
            records=json.loads(unpack(cdx));r['cdx_sha256']=hashlib.sha256(cdx.read_bytes()).hexdigest()
            if not records: raise ValueError('NO_ARCHIVE_INDEX')
            if records[0]!=['timestamp','original','statuscode','digest']: raise ValueError('BAD_CDX_SCHEMA')
            candidates=[x for x in records[1:] if x[2]=='200' and x[0].startswith(day)]
            if not candidates: raise ValueError('NO_ARCHIVE_INDEX')
            chosen=min(candidates,key=lambda x:x[0]);cap=datetime.strptime(chosen[0],'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
            if cap>=t: raise ValueError('ARCHIVE_AFTER_CUTOFF')
            r.update(capture_utc=cap.isoformat(),capture_digest=chosen[3],archive_url=f'https://web.archive.org/web/{chosen[0]}id_/{chosen[1]}')
            if day!='20230211': get(r['archive_url'],body,head,raw_response=True)
            matches=re.findall(r'(?im)^memento-datetime:\s*(.+?)\s*$',head.read_text())
            if len(matches)!=1 or parsedate_to_datetime(matches[0])!=cap: raise ValueError('MEMENTO_MISMATCH')
            raw=body.read_bytes(); decoded=unpack(body)
            digest=base64.b32encode(hashlib.sha1(raw).digest()).decode()
            if digest != chosen[3]: raise ValueError('CDX_DIGEST_MISMATCH')
            arr=parse_page(decoded);r.update(status='DATA_READY',archive_sha256=hashlib.sha256(raw).hexdigest(),archive_storage=str(body.relative_to(ROOT)),count_up=sum(x['direction']=='UP' for x in arr),count_down=sum(x['direction']=='DOWN' for x in arr),count_zero=sum(x['direction']=='ZERO_DISPLAYED' for x in arr),source_data_cutoff='UNKNOWN')
            items.extend({'index':i,**x} for x in arr)
        except ConnectionError as e:
            r['error']=str(e);network_failed=True
        except (ValueError,KeyError,TypeError,IndexError,OSError,json.JSONDecodeError) as e:
            r['error']=str(e)
        results.append(r);(OUT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
        print(n,r['status'],r.get('error',''),flush=True)
    with (OUT/'first-30-private.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['index','rank','name','change7_display','direction']);w.writeheader();w.writerows(items)
    assert len(results)==26

if __name__=='__main__':main()
