"""Fetch the documented BTC/USD ZIP member from official public ranges only."""
from pathlib import Path
import hashlib,json,struct,zlib,requests

DIR=Path('data/verify/kraken-ohlc-directory-20261104-01');OUT=Path('data/market/kraken-xbtusd-native4h-20261104-01')
def get(url,start,end,total):
    r=requests.get(url,headers={'Range':f'bytes={start}-{end}'},stream=True,timeout=60);expected=f'bytes {start}-{end}/{total}';assert r.status_code==206 and r.headers.get('Content-Range')==expected
    b=r.content;assert len(b)==end-start+1;return b,{'url':url,'range':expected,'sha256':hashlib.sha256(b).hexdigest()}
def main():
    index=json.loads((DIR/'directory-index.json').read_text());info=json.loads((DIR/'summary.json').read_text());xs=[x for x in index['matching_entries'] if x['name']=='XBTUSD_240.csv'];assert len(xs)==1;x=xs[0];assert x['compressed_size']==733527 and x['uncompressed_size']==1773450 and x['compression']==8
    sizes=[int(z['content_range'].split('/')[1]) for z in info['parts']];off=x['local_header_offset'];part=next(i for i in range(len(sizes)) if off<sum(sizes[:i+1]));local=off-sum(sizes[:part]);assert local+512+x['compressed_size']<sizes[part];url=info['parts'][part]['url'];OUT.mkdir(exist_ok=False)
    head,hr=get(url,local,local+511,sizes[part]);(OUT/'local-header-512.bin').write_bytes(head);v=struct.unpack_from('<4s5H3I2H',head);assert v[0]==b'PK\x03\x04' and v[3]==8;name=head[30:30+v[9]].decode();assert name==x['name'];start=local+30+v[9]+v[10];compressed,cr=get(url,start,start+x['compressed_size']-1,sizes[part]);(OUT/'member.deflate').write_bytes(compressed)
    d=zlib.decompressobj(-15);raw=d.decompress(compressed)+d.flush();assert d.eof and not d.unused_data and len(raw)==x['uncompressed_size'] and f'{zlib.crc32(raw)&0xffffffff:08x}'==x['crc32'];p=OUT/x['name'];p.write_bytes(raw);result={'source':'Kraken official multipart ZIP, one member only','member':x,'part':part,'header_request':hr,'member_request':cr,'raw_sha256':hashlib.sha256(raw).hexdigest(),'crc32_verified':True,'deflate_eof':d.eof,'raw_bytes':len(raw),'limitations':['No whole archive or part SHA validation.','CRC only checks member consistency with received central directory.','No proof of trade authenticity.']};(OUT/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
