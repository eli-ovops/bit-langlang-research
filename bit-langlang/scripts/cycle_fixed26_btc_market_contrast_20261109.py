import csv,gzip,hashlib,json
from pathlib import Path
from cycle_market_archive_20261109 import parse_page
R=Path(__file__).resolve().parents[1]
BASE=R/'data/verify/cycle-market-archive-corrected-20261109-01/summary.json'
REC=R/'data/verify/cycle-2023-2025-gzip-recovery-20261109-01/summary.json'
DIR=R/'data/verify/cycle-market-archive-20261109-01'
OUT=R/'data/verify/cycle-fixed26-btc-market-contrast-20261109-01'

def main():
 base=json.loads(BASE.read_text()); rec={x['index']:x for x in json.loads(REC.read_text()) if x['status']=='READY'}
 assert len(base)==26 and len(rec)==3
 OUT.mkdir(parents=True,exist_ok=False); rows=[]
 for r in base:
  n=r['index'];v=rec.get(n);out={'index':n,'asof':r['as_of_utc'],'quarter':r['quarter'],'status':'UNKNOWN','reason':r.get('error',''),'capture':r.get('capture_utc',''),'btc_direction':'UNKNOWN','btc_7d_display':'UNKNOWN','up':'UNKNOWN','down':'UNKNOWN','zero':'UNKNOWN','comparison':'UNKNOWN','source_sha256':''}
  if r['status']=='DATA_READY' or v:
   file=R/r['archive_storage'] if r.get('archive_storage') else DIR/f'{n:02}.html'
   raw=file.read_bytes();body=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw;arr=parse_page(body)
   assert len(arr)==30 and arr[0]['name']=='Bitcoin BTC'
   up=sum(z['direction']=='UP' for z in arr);down=sum(z['direction']=='DOWN' for z in arr);zero=30-up-down
   expected=(v['up'],v['down'],v['zero']) if v else (r['count_up'],r['count_down'],r['count_zero'])
   assert (up,down,zero)==expected,(n,(up,down,zero),expected)
   direction=arr[0]['direction'];compare='MIXED' if up==down else 'BTC_UP_OTHERS_MOST_DOWN' if direction=='UP' and down>up else 'BTC_DOWN_OTHERS_MOST_UP' if direction=='DOWN' and up>down else 'DIRECTIONS_ALIGNED_OR_ZERO'
   out.update(status='READY',reason='',btc_direction=direction,btc_7d_display=arr[0]['change7_display'],up=up,down=down,zero=zero,comparison=compare,source_sha256=hashlib.sha256(raw).hexdigest())
  rows.append(out)
 assert len(rows)==26 and sum(z['status']=='READY' for z in rows)==17
 with (OUT/'all-26.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 (OUT/'summary.json').write_text(json.dumps({'input_sha256':{str(x.relative_to(R)):hashlib.sha256(x.read_bytes()).hexdigest() for x in (BASE,REC)},'count':26,'ready':17,'unknown':9,'divergences':[x for x in rows if x['comparison'] in ('BTC_UP_OTHERS_MOST_DOWN','BTC_DOWN_OTHERS_MOST_UP')]},indent=2))
 print(json.dumps({'ready':17,'unknown':9,'divergences':[x for x in rows if x['comparison'] in ('BTC_UP_OTHERS_MOST_DOWN','BTC_DOWN_OTHERS_MOST_UP')]}))

if __name__=='__main__':main()
