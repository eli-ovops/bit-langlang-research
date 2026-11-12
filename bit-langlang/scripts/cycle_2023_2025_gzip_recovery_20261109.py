import base64,gzip,hashlib,json,re,subprocess
from collections import Counter
from pathlib import Path
from bs4 import BeautifulSoup
from cycle_market_archive_20261109 import parse_page
R=Path(__file__).resolve().parents[1]
SRC=R/'data/verify/cycle-market-archive-20261109-01'
PREV=R/'data/verify/cycle-market-archive-corrected-20261109-01/summary.json'
OUT=R/'data/verify/cycle-2023-2025-gzip-recovery-20261109-01'

def main():
    items=[x for x in json.loads(PREV.read_text()) if x.get('error')=='CDX_DIGEST_MISMATCH'];assert len(items)==6
    OUT.mkdir(parents=True,exist_ok=False);results=[]
    for r in items:
        n=r['index'];p=OUT/f'{n:02}';rawfile=p.with_suffix('.raw');head=p.with_suffix('.headers')
        cmd=['curl','-sSL','--max-time','25','-D',str(head),r['archive_url'],'-o',str(rawfile),'--write-out','%{http_code}']
        proc=subprocess.run(cmd,capture_output=True,text=True);x={'index':n,'asof':r['as_of_utc'],'quarter':r['quarter'],'status':'UNKNOWN','http':proc.stdout,'returncode':proc.returncode}
        if proc.returncode or proc.stdout!='200':x['error']='FETCH_FAILED';results.append(x);continue
        try:
            raw=rawfile.read_bytes();m=re.findall(r'(?im)^memento-datetime:\s*(.+?)\s*$',head.read_text(errors='replace'));oldh=(SRC/f'{n:02}.headers').read_text(errors='replace');om=re.findall(r'(?im)^memento-datetime:\s*(.+?)\s*$',oldh)
            assert len(m)==1 and len(om)==1 and m[0]==om[0]
            assert base64.b32encode(hashlib.sha1(raw).digest()).decode()==r['capture_digest']
            body=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
            assert body==(SRC/f'{n:02}.html').read_bytes()
            x.update(archive_status='MATCH',capture=r['capture_utc'],raw_sha256=hashlib.sha256(raw).hexdigest())
            arr=parse_page(body);table=BeautifulSoup(body,'html.parser').select_one('table');heads=[z.get_text(' ',strip=True) for z in table.select('thead th')];j=heads.index('7d')
            for v,tr in zip(arr,table.select('tbody tr')[:30]):
                numeric=float(tr.select('td')[j]['data-sort']);display=float(v['change7_display'][:-1]);assert abs(numeric-display)<.051
                if v['direction']!='ZERO_DISPLAYED':assert (numeric<0)==(v['direction']=='DOWN')
            counts=Counter(v['direction'] for v in arr);x.update(status='READY',up=counts['UP'],down=counts['DOWN'],zero=counts['ZERO_DISPLAYED'],quote_time='UNKNOWN')
        except (AssertionError,ValueError,KeyError,IndexError,OSError) as e:x['error']=str(e) or type(e).__name__
        results.append(x)
    (OUT/'summary.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results))

if __name__=='__main__':main()
