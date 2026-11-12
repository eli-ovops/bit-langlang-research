import base64,csv,gzip,hashlib,json,re
from collections import Counter
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from bs4 import BeautifulSoup
from cycle_market_archive_20261109 import get,parse_page

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/verify/cycle-2024q2-market-archive-20261109-01'


def main():
    OUT.mkdir(parents=True,exist_ok=False);records=[];items=[];stop=False
    start=datetime(2024,4,1,tzinfo=timezone.utc)
    for n in range(1,14):
        t=start+timedelta(days=7*(n-1));day=(t-timedelta(days=1)).strftime('%Y%m%d');f=f'{n:02d}'
        c=OUT/f'{f}.cdx';ch=OUT/f'{f}.cdx.headers';b=OUT/f'{f}.html';h=OUT/f'{f}.headers';r={'index':n,'as_of_utc':t.isoformat(),'status':'UNKNOWN','phase':'UNKNOWN','sentiment':'UNKNOWN'}
        try:
            if stop:raise ValueError('NOT_ATTEMPTED_AFTER_NETWORK_FAILURE')
            get('https://web.archive.org/cdx/search/cdx',c,ch,['url=https://www.coingecko.com/','output=json','fl=timestamp,original,statuscode,digest','filter=statuscode:200','from='+day,'to='+day]);raw=c.read_bytes();raw=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw;rec=json.loads(raw);r['cdx_sha256']=hashlib.sha256(c.read_bytes()).hexdigest()
            if not rec:raise ValueError('NO_ARCHIVE_INDEX')
            if rec[0]!=['timestamp','original','statuscode','digest']:raise ValueError('BAD_CDX_SCHEMA')
            choices=[x for x in rec[1:] if x[2]=='200' and x[0].startswith(day)]
            if not choices:raise ValueError('NO_ARCHIVE_INDEX')
            chosen=min(choices,key=lambda x:x[0]);cap=datetime.strptime(chosen[0],'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
            if cap>=t:raise ValueError('CAPTURE_AFTER_ASOF')
            url=f'https://web.archive.org/web/{chosen[0]}id_/{chosen[1]}';r.update(capture_utc=cap.isoformat(),archive_url=url,cdx_digest=chosen[3]);get(url,b,h,raw_response=True)
            m=re.findall(r'(?im)^memento-datetime:\s*(.+?)\s*$',h.read_text())
            if len(m)!=1 or parsedate_to_datetime(m[0])!=cap:raise ValueError('MEMENTO_MISMATCH')
            raw=b.read_bytes();body=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
            if base64.b32encode(hashlib.sha1(raw).digest()).decode()!=chosen[3]:raise ValueError('CDX_DIGEST_MISMATCH')
            arr=parse_page(body);table=BeautifulSoup(body,'html.parser').select_one('table');heads=[x.get_text(' ',strip=True) for x in table.select('thead th')];j=heads.index('7d')
            for item,tr in zip(arr,table.select('tbody tr')[:30]):
                num=float(tr.select('td')[j]['data-sort']);val=float(item['change7_display'][:-1]);assert abs(num-val)<.051
                if item['direction']!='ZERO_DISPLAYED':assert (num<0)==(item['direction']=='DOWN')
            cnt=Counter(x['direction'] for x in arr);r.update(status='DATA_READY',sha256=hashlib.sha256(raw).hexdigest(),up=cnt['UP'],down=cnt['DOWN'],zero=cnt['ZERO_DISPLAYED'],source_data_cutoff='UNKNOWN');items.extend({'index':n,**x} for x in arr)
        except ConnectionError as e:r['error']=str(e);stop=True
        except (AssertionError,ValueError,KeyError,IndexError,TypeError,OSError) as e:r['error']=str(e) or 'DATA_CHECK_FAILURE'
        records.append(r);(OUT/'summary.json').write_text(json.dumps(records,indent=2)+'\n');print(f,r['status'],r.get('error',''),flush=True)
    with (OUT/'first-30-private.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=['index','rank','name','change7_display','direction']);w.writeheader();w.writerows(items)
    assert len(records)==13

if __name__=='__main__':main()
