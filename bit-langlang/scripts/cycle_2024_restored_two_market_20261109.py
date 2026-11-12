import base64,gzip,hashlib,json,re
from collections import Counter
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from bs4 import BeautifulSoup
from cycle_market_archive_20261109 import get,parse_page
R=Path(__file__).resolve().parents[1]
INPUT=R/'data/verify/cycle-2024q2-restored-two-20261109-01/summary.json'
OUT=R/'data/verify/cycle-2024q2-restored-two-market-20261109-01'

def main():
    source=json.loads(INPUT.read_text())['records'];assert len(source)==2
    OUT.mkdir(parents=True,exist_ok=False);results=[]
    for item in source:
        n=item['index'];t=datetime.fromisoformat(item['asof']);day=(t-timedelta(days=1)).strftime('%Y%m%d');p=OUT/f'{n:02}'
        result={'index':n,'asof':t.isoformat(),'status':'UNKNOWN'}
        try:
            c=p.with_suffix('.cdx');get('https://web.archive.org/cdx/search/cdx',c,p.with_suffix('.cdxheaders'),['url=https://www.coingecko.com/','output=json','fl=timestamp,original,statuscode,digest','filter=statuscode:200','from='+day,'to='+day])
            raw=c.read_bytes();rows=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
            assert rows and rows[0]==['timestamp','original','statuscode','digest']
            choices=[x for x in rows[1:] if x[2]=='200' and x[0].startswith(day)]
            if not choices:raise ValueError('NO_ARCHIVE_INDEX')
            row=min(choices,key=lambda z:z[0]);cap=datetime.strptime(row[0],'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc);assert cap<t
            url=f'https://web.archive.org/web/{row[0]}id_/{row[1]}';body=p.with_suffix('.raw');headers=p.with_suffix('.headers');get(url,body,headers,raw_response=True)
            raw=body.read_bytes();m=re.findall(r'(?im)^memento-datetime:\s*(.+?)\s*$',headers.read_text())
            assert len(m)==1 and parsedate_to_datetime(m[0])==cap
            assert base64.b32encode(hashlib.sha1(raw).digest()).decode()==row[3]
            html=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
            arr=parse_page(html);table=BeautifulSoup(html,'html.parser').select_one('table');heads=[z.get_text(' ',strip=True) for z in table.select('thead th')];j=heads.index('7d')
            for x,tr in zip(arr,table.select('tbody tr')[:30]):
                v=float(tr.select('td')[j]['data-sort']);shown=float(x['change7_display'][:-1]);assert abs(v-shown)<.051
                if x['direction']!='ZERO_DISPLAYED':assert (v<0)==(x['direction']=='DOWN')
            counts=Counter(x['direction'] for x in arr);result.update(status='READY',capture=cap.isoformat(),up=counts['UP'],down=counts['DOWN'],zero=counts['ZERO_DISPLAYED'],raw_sha256=hashlib.sha256(raw).hexdigest(),quote_time='UNKNOWN')
        except (ValueError,KeyError,IndexError,AssertionError,ConnectionError,OSError) as e:result['error']=str(e) or type(e).__name__
        results.append(result)
    (OUT/'summary.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results))

if __name__=='__main__':main()
