"""Limited public range access to official multipart archive ZIP metadata."""
from pathlib import Path
import hashlib,json,struct,requests

OUT=Path('data/verify/kraken-ohlc-directory-20261104-01')
BASE='https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_Full.zip.part'
def main():
    OUT.mkdir(exist_ok=False);parts=[]
    for i in range(5):
        r=requests.get(BASE+f'{i:02}',headers={'Range':'bytes=0-0'},stream=True,timeout=30);h={'part':i,'url':r.url,'status':r.status_code,'content_range':r.headers.get('Content-Range'),'content_length':r.headers.get('Content-Length')};parts.append(h)
        if r.status_code!=206 or not h['content_range'] or not h['content_range'].startswith('bytes 0-0/'):
            r.close();(OUT/'summary.json').write_text(json.dumps({'status':'UNKNOWN_RANGE_UNAVAILABLE','parts':parts},indent=2)+'\n');print('UNKNOWN range',h);return
        r.close()
    r=requests.get(BASE+'04',headers={'Range':'bytes=-65536'},timeout=45);h=r.headers.get('Content-Range','');assert r.status_code==206 and h.endswith('/'+parts[4]['content_range'].split('/')[1]) and len(r.content)==65536
    p=OUT/'part04-tail-65536.bin';p.write_bytes(r.content);e=r.content.rfind(b'PK\x05\x06');z=r.content.rfind(b'PK\x06\x06');loc=r.content.rfind(b'PK\x06\x07');info={'status':'TAIL_RECORDED','parts':parts,'tail_sha256':hashlib.sha256(r.content).hexdigest(),'tail_content_range':h,'eocd_in_tail_offset':e,'zip64_eocd_in_tail_offset':z,'zip64_locator_in_tail_offset':loc}
    if e>=0 and e+22<=len(r.content):
        v=struct.unpack_from('<4s4H2LH',r.content,e);info['eocd']={'disk':v[1],'directory_disk':v[2],'entries_disk':v[3],'entries_total':v[4],'directory_size':v[5],'directory_offset':v[6],'comment_length':v[7]}
    if z>=0 and z+56<=len(r.content):
        v=struct.unpack_from('<4sQHHLLQQQQ',r.content,z);info['zip64_eocd']={'disk':v[4],'directory_disk':v[5],'entries_disk':v[6],'entries_total':v[7],'directory_size':v[8],'directory_offset':v[9]}
    (OUT/'summary.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(info,indent=2))
if __name__=='__main__':main()
