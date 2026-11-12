import difflib
import gzip
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from cycle_article_archive_audit_20261109 import content

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'data/verify/cycle-report-archive-20261109-01'
OUT=ROOT/'data/verify/cycle-report-archive-remaining-20261109-01'
TARGETS=[11,12,13,16,17,18,19,20,21,22,23,24]


def sha(data):return hashlib.sha256(data).hexdigest()


def decode(raw):return gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw


def get(url, filename, params=None):
    hdr=OUT/(filename+'.headers');body=OUT/(filename+'.body')
    args=['curl','--silent','--show-error','--location','--compressed','--max-time','25',
          '--dump-header',str(hdr),'--output',str(body),'--write-out','%{http_code}\n%{url_effective}']
    if params:
        args.append('--get')
        for k,v in params.items():args.extend(['--data-urlencode',f'{k}={v}'])
    p=subprocess.run(args+[url],capture_output=True,text=True)
    parts=p.stdout.splitlines();receipt={'exit':p.returncode,'http':parts[0] if parts else None,
        'final_url':parts[1] if len(parts)>1 else None,'stderr':p.stderr.strip()}
    if hdr.exists():receipt['headers_sha256']=sha(hdr.read_bytes())
    if body.exists():receipt['raw_sha256']=sha(body.read_bytes())
    if p.returncode or receipt['http']!='200':raise RuntimeError(json.dumps(receipt))
    return decode(body.read_bytes()),hdr.read_text(),receipt


def main():
    assert decode(gzip.compress(b'hello'))==b'hello'
    OUT.mkdir(parents=True,exist_ok=False)
    old=json.loads((OLD/'summary.json').read_text())['results'];results=[]
    for index in TARGETS:
        r=old[index-1];n=f'{index:02d}';asof=datetime.fromisoformat(r['as_of_utc'].replace('Z','+00:00'))
        rec={'index':index,'as_of_utc':r['as_of_utc'],'status':'UNKNOWN'}
        try:
            u=r['url'].replace('https://research.glassnode.com/','https://insights.glassnode.com/')
            params={'url':u,'output':'json','filter':'statuscode:200','fl':'timestamp,original,statuscode,digest',
                    'from':r['report_date'].replace('-',''),'to':asof.strftime('%Y%m%d')}
            raw,_,rec['cdx_receipt']=get('https://web.archive.org/cdx/search/cdx',n+'.cdx',params)
            rows=json.loads(raw)
            if not isinstance(rows,list) or (rows and rows[0]!=['timestamp','original','statuscode','digest']):
                raise ValueError('unexpected CDX response')
            avail=[(datetime.strptime(x[0],'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc),x) for x in rows[1:] if x[2]=='200']
            avail=[(t,x) for t,x in avail if t<asof]
            if not avail:rec['status']='NO_CAPTURE_BEFORE_ASOF'
            else:
                expected,selected=max(avail,key=lambda x:x[0]);rec['selected_utc']=expected.isoformat()
                url=f'https://web.archive.org/web/{selected[0]}id_/{selected[1]}'
                archived,head,rec['archive_receipt']=get(url,n+'.archive')
                matches=re.findall(r'(?im)^memento-datetime:\s*(.+?)\s*$',head)
                if len(matches)!=1:raise ValueError('missing/ambiguous Memento-Datetime')
                actual=parsedate_to_datetime(matches[0]);rec['memento_utc']=actual.isoformat()
                if actual>=asof:raise ValueError('capture not pre-asof')
                if actual!=expected:raise ValueError('redirected to a different capture')
                title,then,_=content(archived);current_title,now,_=content((OLD/n/'current.html').read_bytes())
                rec.update(archive_title=title,current_title=current_title,archive_body_sha256=sha(then.encode()),current_body_sha256=sha(now.encode()))
                match=difflib.SequenceMatcher(None,then.split(),now.split(),autojunk=False)
                rec['edits']=[{'op':tag,'archive':then.split()[i:j], 'current':now.split()[k:l]} for tag,i,j,k,l in match.get_opcodes() if tag!='equal']
                rec['status']='ARCHIVE_MATCH' if then==now else 'ARCHIVE_DIFF'
        except (RuntimeError,ValueError,KeyError,IndexError,TypeError) as e:
            rec['error']=str(e)
        results.append(rec)
        (OUT/'progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
        print(index,rec['as_of_utc'],rec['status'],rec.get('selected_utc',''),rec.get('error','')[:160],flush=True)
        if rec.get('error'):break
    print('completed',len(results),'of',len(TARGETS),flush=True)


if __name__=='__main__':main()
