import base64, gzip, hashlib, json, re, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/verify/cycle-report-archive-20261109-01'
OUT=ROOT/'data/verify/cycle-archive-six-audit-20261109-01'


def main():
    results=[]
    for index in range(1,7):
        folder=SOURCE/f'{index:02d}'
        r=json.loads((folder/'receipt.json').read_text())
        raw=OUT/f'{index:02d}.raw'; headers=OUT/f'{index:02d}.headers'
        proc=subprocess.run(['curl','-sSL','--max-time','25','-D',str(headers),r['archive_url'],'-o',str(raw)],capture_output=True,text=True)
        item={'index':index,'report_date':r['report_date'],'returncode':proc.returncode,'status':'UNKNOWN'}
        if proc.returncode:
            item['reason']=proc.stderr.strip()[:200];results.append(item);continue
        b=raw.read_bytes();h=headers.read_text(errors='replace')
        matches=re.findall(r'^memento-datetime:\s*(.*?)\s*$',h,re.I|re.M)
        digest=base64.b32encode(hashlib.sha1(b).digest()).decode()
        decoded=gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b
        prior=(folder/'archive.html').read_bytes()
        item.update(raw_sha1_base32=digest,cdx_digest=r['cdx_digest'],raw_sha256=hashlib.sha256(b).hexdigest(),content_encoding='gzip' if b[:2]==b'\x1f\x8b' else 'other',decoded_equals_saved=decoded==prior,memento=matches[-1] if matches else None)
        if digest==r['cdx_digest'] and decoded==prior and matches and matches[-1]==r['memento_datetime']:
            item['status']='MATCH'
        else:
            item['reason']='RAW_DIGEST_DECODE_OR_MEMENTO_MISMATCH'
        results.append(item)
    (OUT/'summary.json').write_text(json.dumps(results,indent=2))
    print('MATCH',sum(x['status']=='MATCH' for x in results),'UNKNOWN',sum(x['status']=='UNKNOWN' for x in results))
    for x in results: print(x['index'],x['status'],x.get('reason',''))

if __name__=='__main__':main()
