"""Read the official ZIP central directory only, with exact-range checks."""
from pathlib import Path
import hashlib,json,struct,requests

ROOT=Path('data/verify/kraken-ohlc-directory-20261104-01');BASE='https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_Full.zip.part04'
def main():
    m=json.loads((ROOT/'summary.json').read_text());assert m['status']=='TAIL_RECORDED';parts=[int(v['content_range'].split('/')[1]) for v in m['parts']];z=m['zip64_eocd'];offset=z['directory_offset'];size=z['directory_size'];assert 0<size<=1000000 and offset>=sum(parts[:4]) and offset+size<=sum(parts);local=offset-sum(parts[:4]);end=local+size-1
    r=requests.get(BASE,headers={'Range':f'bytes={local}-{end}'},stream=True,timeout=60);cr=r.headers.get('Content-Range','');expected=f'bytes {local}-{end}/{parts[4]}';assert r.status_code==206 and cr==expected;data=r.content;assert len(data)==size;p=ROOT/'central-directory.bin';p.write_bytes(data)
    entries=[];i=0
    while i<len(data):
        if data[i:i+4]!=b'PK\x01\x02':raise ValueError(f'bad central record {i}')
        x=struct.unpack_from('<4s6H3I5H2I',data,i);nl,el,cl=x[10:13];name=data[i+46:i+46+nl].decode('utf-8');extra=data[i+46+nl:i+46+nl+el];usize,csize,off=x[9],x[8],x[16]
        if any(v==0xffffffff for v in (usize,csize,off)):
            k=0
            while k<len(extra):
                tag,n=struct.unpack_from('<HH',extra,k);payload=extra[k+4:k+4+n];k+=4+n
                if tag==1:
                    a=0
                    if usize==0xffffffff:usize=struct.unpack_from('<Q',payload,a)[0];a+=8
                    if csize==0xffffffff:csize=struct.unpack_from('<Q',payload,a)[0];a+=8
                    if off==0xffffffff:off=struct.unpack_from('<Q',payload,a)[0];a+=8
                    break
        if ('XBTUSD' in name.upper() or 'BTCUSD' in name.upper()) and ('240' in name or '60' in name):entries.append({'name':name,'compression':x[4],'crc32':f'{x[7]:08x}','compressed_size':csize,'uncompressed_size':usize,'local_header_offset':off})
        i+=46+nl+el+cl
    info={'status':'DIRECTORY_INDEXED','range':cr,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'matching_entries':entries,'limits':['No archive part or whole archive checksum verified.','No candles or trades retrieved.']};(ROOT/'directory-index.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(info,indent=2))
if __name__=='__main__':main()
