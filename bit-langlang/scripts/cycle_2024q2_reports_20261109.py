import base64,gzip,hashlib,json,re
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from cycle_market_archive_20261109 import get
from cycle_article_archive_audit_20261109 import content

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/verify/cycle-2024q2-reports-20261109-01'


def main():
    OUT.mkdir(parents=True,exist_ok=False);results=[];stop=False;start=datetime(2024,4,1,tzinfo=timezone.utc)
    for n in range(1,14):
        t=start+timedelta(days=7*(n-1));week=n+12;f=f'{n:02d}';u=f'https://insights.glassnode.com/the-week-onchain-week-{week}-2024/';c=OUT/f'{f}.cdx';ch=OUT/f'{f}.cdx.headers';b=OUT/f'{f}.html';h=OUT/f'{f}.headers'
        r={'index':n,'as_of_utc':t.isoformat(),'week':week,'original_url':u,'status':'UNKNOWN','independent_phase':'UNKNOWN','sentiment':'UNKNOWN'}
        try:
            if stop:raise ValueError('NOT_ATTEMPTED_AFTER_NETWORK_FAILURE')
            get('https://web.archive.org/cdx/search/cdx',c,ch,['url='+u,'output=json','fl=timestamp,original,statuscode,digest','filter=statuscode:200','from='+(t-timedelta(days=14)).strftime('%Y%m%d'),'to='+t.strftime('%Y%m%d')]);raw=c.read_bytes();raw=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw;rec=json.loads(raw);r['cdx_sha256']=hashlib.sha256(c.read_bytes()).hexdigest()
            if not rec:raise ValueError('NO_ARCHIVE_INDEX')
            if rec[0]!=['timestamp','original','statuscode','digest']:raise ValueError('BAD_CDX_SCHEMA')
            choices=[]
            for x in rec[1:]:
                cap=datetime.strptime(x[0],'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
                if x[2]=='200' and t-timedelta(days=14)<=cap<t:choices.append((cap,x))
            if not choices:raise ValueError('NO_ARCHIVE_INDEX')
            cap,x=max(choices,key=lambda z:z[0]);url=f'https://web.archive.org/web/{x[0]}id_/{x[1]}';r.update(capture_utc=cap.isoformat(),cdx_digest=x[3],archive_url=url);get(url,b,h,raw_response=True)
            m=re.findall(r'(?im)^memento-datetime:\s*(.+?)\s*$',h.read_text())
            if len(m)!=1 or parsedate_to_datetime(m[0])!=cap:raise ValueError('MEMENTO_MISMATCH')
            raw=b.read_bytes();body=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
            if base64.b32encode(hashlib.sha1(raw).digest()).decode()!=x[3]:raise ValueError('CDX_DIGEST_MISMATCH')
            title,text,soup=content(body);meta=soup.find('meta',attrs={'property':'article:published_time'})
            if meta is None or not meta.get('content'):raise ValueError('PUBLISHED_TIME_UNKNOWN')
            pub=datetime.fromisoformat(meta['content'].replace('Z','+00:00'))
            if not(t-timedelta(days=14)<=pub<=cap<t):raise ValueError('PUBLISHED_TIME_INVALID')
            (OUT/f'{f}.text').write_text(text+'\n');r.update(status='ARCHIVE_READY',title=title,published_utc=pub.isoformat(),archive_sha256=hashlib.sha256(raw).hexdigest(),body_sha256=hashlib.sha256(text.encode()).hexdigest(),body_chars=len(text))
        except ConnectionError as e:r['error']=str(e);stop=True
        except (ValueError,KeyError,IndexError,TypeError,OSError) as e:r['error']=str(e)
        results.append(r);(OUT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n');print(f,r['status'],r.get('error',''),flush=True)
    assert len(results)==13

if __name__=='__main__':main()
