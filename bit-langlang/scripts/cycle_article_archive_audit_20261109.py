import csv
import difflib
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT/'docs/浪浪周期-同期周报全观察参考清单-20261109.csv'
OUT = ROOT/'data/verify/cycle-report-archive-20261109-01'
CDX = 'https://web.archive.org/cdx/search/cdx'


def content(data):
    soup = BeautifulSoup(data,'html.parser')
    sections = soup.select('section.gh-content')
    if len(sections) != 1:
        raise ValueError(f'expected one main article body, got {len(sections)}')
    for item in sections[0].select('script,style,noscript'):
        item.decompose()
    title = soup.find('title')
    text = ' '.join(sections[0].get_text(' ',strip=True).split())
    if not title or len(text)<500:
        raise ValueError('missing title or body')
    return title.get_text(' ',strip=True),text,soup


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fetch(i,row):
    folder=OUT/f'{i:02d}'
    folder.mkdir()
    result={'index':i,'as_of_utc':row['as_of_utc'],'report_date':row['report_date'],
            'url':row['report_url'],'status':'UNKNOWN'}
    asof=datetime.fromisoformat(row['as_of_utc'].replace('Z','+00:00'))
    try:
        current=requests.get(row['report_url'],timeout=25)
        result['current_http']=current.status_code
        current.raise_for_status()
        (folder/'current.html').write_bytes(current.content)
        title,now,soup=content(current.content)
        result.update(title=title,current_html_sha256=digest(current.content),current_body_sha256=digest(now.encode()),current_body_chars=len(now))
        for k in ('published_time','modified_time'):
            meta=soup.find('meta',attrs={'property':'article:'+k})
            result[k]=meta.get('content') if meta else None
        oldurl=row['report_url'].replace('https://research.glassnode.com/','https://insights.glassnode.com/')
        params={'url':oldurl,'output':'json','filter':'statuscode:200','fl':'timestamp,original,statuscode,digest',
                'from':row['report_date'].replace('-',''),'to':asof.strftime('%Y%m%d')}
        response=requests.get(CDX,params=params,timeout=25)
        result['cdx_http']=response.status_code
        response.raise_for_status()
        (folder/'cdx.json').write_bytes(response.content)
        index=response.json()
        if not isinstance(index,list) or (index and index[0]!=['timestamp','original','statuscode','digest']):
            raise ValueError('unexpected CDX schema')
        captures=[]
        for x in index[1:]:
            capture=datetime.strptime(x[0],'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
            if capture < asof and x[2]=='200': captures.append((capture,x))
        result['pre_asof_capture_count']=len(captures)
        if not captures:
            result['status']='NO_CAPTURE_BEFORE_ASOF'
            return result
        captured,selected=max(captures,key=lambda x:x[0]); stamp=selected[0]
        result.update(capture_utc=captured.isoformat(),cdx_digest=selected[3],archive_url=f'https://web.archive.org/web/{stamp}id_/{selected[1]}')
        archived=requests.get(result['archive_url'],timeout=25)
        result['archive_http']=archived.status_code
        archived.raise_for_status()
        result['memento_datetime']=archived.headers.get('Memento-Datetime')
        if not result['memento_datetime'] or parsedate_to_datetime(result['memento_datetime']) != captured:
            raise ValueError('missing or inconsistent Memento-Datetime')
        if 'text/html' not in archived.headers.get('Content-Type',''):
            raise ValueError('archive not HTML')
        (folder/'archive.html').write_bytes(archived.content)
        archived_title,then,_=content(archived.content)
        if title != archived_title:
            raise ValueError('article title mismatch')
        score=difflib.SequenceMatcher(None,then.split(),now.split(),autojunk=False)
        edits=[{'operation':tag,'before_words':i2-i1,'after_words':j2-j1} for tag,i1,i2,j1,j2 in score.get_opcodes() if tag!='equal']
        result.update(archive_html_sha256=digest(archived.content),archive_body_sha256=digest(then.encode()),
                      archive_body_chars=len(then),body_similarity=score.ratio(),edits=edits,
                      status='ARCHIVE_MATCH' if then==now else 'ARCHIVE_DIFF')
    except (requests.RequestException,ValueError,KeyError,TypeError,IndexError) as e:
        result['error']=f'{type(e).__name__}: {e}'
    (folder/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def main():
    assert content(b'<title>x</title><section class="gh-content">'+b'a '*300+b'</section>')[1] == ' '.join(['a']*300)
    rows=[r for r in csv.DictReader(INPUT.open()) if r['report_url']]
    assert len(rows)==24
    OUT.mkdir(parents=True,exist_ok=False)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(lambda ir:fetch(*ir),enumerate(rows,1)))
    summary={'input_sha256':digest(INPUT.read_bytes()),'results':results}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    for r in results:
        print(r['as_of_utc'],r['status'],r.get('capture_utc',''),r.get('body_similarity',''),r.get('error',''),flush=True)


if __name__=='__main__':main()
