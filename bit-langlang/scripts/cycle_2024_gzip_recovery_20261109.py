import base64,gzip,hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/verify/cycle-2024-gzip-recovery-20261109-01'
TARGETS=[('cycle-2024q2-reports-20261109-01',2),('cycle-2024q2-reports-20261109-01',6),('cycle-2024q2-near-market-20261109-01',8),('cycle-2024q2-near-market-20261109-01',10),('cycle-2024q2-market-archive-20261109-01',6)]

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    results=[]
    for n,(folder,index) in enumerate(TARGETS,1):
        source=ROOT/'data/verify'/folder
        r=next(x for x in json.loads((source/'summary.json').read_text()) if x['index']==index)
        old=(source/f'{index:02d}.html').read_bytes()
        raw=OUT/f'{n:02d}.raw';head=OUT/f'{n:02d}.headers'
        p=subprocess.run(['curl','-sSL','--max-time','25','-D',str(head),r['archive_url'],'-o',str(raw)],capture_output=True,text=True)
        v={'source':folder,'index':index,'url':r['archive_url'],'status':'UNKNOWN','returncode':p.returncode}
        if p.returncode:
            v['error']=p.stderr[:300];results.append(v);continue
        b=raw.read_bytes(); h=head.read_text(errors='replace')
        digest=base64.b32encode(hashlib.sha1(b).digest()).decode()
        m=re.findall(r'^memento-datetime:\s*(.*?)\s*$',h,re.I|re.M)
        oldh=(source/f'{index:02d}.headers').read_text(errors='replace')
        previous=re.findall(r'^memento-datetime:\s*(.*?)\s*$',oldh,re.I|re.M)
        same=gzip.decompress(b)==old if b[:2]==b'\x1f\x8b' else b==old
        v.update(cdx_digest=r['cdx_digest'],raw_sha1_base32=digest,raw_sha256=hashlib.sha256(b).hexdigest(),gzip=b[:2]==b'\x1f\x8b',decoded_equals_saved=same,memento=m[-1] if m else None)
        if digest==r['cdx_digest'] and same and m and previous and m[-1]==previous[-1]:v['status']='MATCH'
        else:v['error']='DIGEST_DECODE_OR_MEMENTO_MISMATCH'
        results.append(v)
    (OUT/'summary.json').write_text(json.dumps(results,indent=2))
    for x in results:print(x['source'],x['index'],x['status'],x.get('error',''))

if __name__=='__main__':main()
