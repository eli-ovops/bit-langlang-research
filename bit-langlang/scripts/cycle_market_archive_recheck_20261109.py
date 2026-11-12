import base64
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from bs4 import BeautifulSoup
from cycle_market_archive_20261109 import parse_page

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'data/verify/cycle-market-archive-20261109-01'
OUT=ROOT/'data/verify/cycle-market-archive-corrected-20261109-01'


def check_parser():
    def table(cls,value):
        row=lambda n:f'<tr><td>{n}</td><td>Asset</td><td><span class="{cls}">{value}%</span></td></tr>'
        return ('<table><thead><tr><th>#</th><th>Coin</th><th>7d</th></tr></thead><tbody>'+''.join(row(i) for i in range(1,31))+'</tbody></table>').encode()
    assert parse_page(table('gecko-down','5.2'))[0]['direction']=='DOWN'
    assert parse_page(table('text-danger','-5.2'))[0]['direction']=='DOWN'
    assert parse_page(table('gecko-up','5.2'))[0]['direction']=='UP'
    assert parse_page(table('gecko-down','0.0'))[0]['direction']=='ZERO_DISPLAYED'


def main():
    check_parser();records=json.loads((OLD/'summary.json').read_text());assert len(records)==26
    OUT.mkdir(parents=True,exist_ok=False);items=[];out=[]
    for r in records:
        x={k:v for k,v in r.items() if k not in ('count_up','count_down','count_zero')}
        if r['status']=='DATA_READY':
            try:
                raw=(ROOT/r['archive_storage']).read_bytes();assert hashlib.sha256(raw).hexdigest()==r['archive_sha256'];d=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
                assert base64.b32encode(hashlib.sha1(d).digest()).decode()==r['capture_digest']
                a=parse_page(d);t=BeautifulSoup(d,'html.parser').select_one('table');heads=[h.get_text(' ',strip=True) for h in t.select('thead th')];j=heads.index('7d')
                for v,tr in zip(a,t.select('tbody tr')[:30]):
                    cell=tr.select('td')[j];sort=float(cell['data-sort']);display=float(v['change7_display'][:-1]);assert abs(sort-display)<0.051
                    if v['direction']!='ZERO_DISPLAYED':assert (sort<0)==(v['direction']=='DOWN')
                c=Counter(v['direction'] for v in a);x.update(count_up=c['UP'],count_down=c['DOWN'],count_zero=c['ZERO_DISPLAYED'],display_sign_corrected=True);items.extend({'index':r['index'],**v} for v in a)
            except (ValueError,KeyError,IndexError,AssertionError) as e:x.update(status='UNKNOWN',error='SIGN_CHECK_FAILED '+str(e))
        out.append(x)
    (OUT/'summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    with (OUT/'first-30-private.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['index','rank','name','change7_display','direction']);w.writeheader();w.writerows(items)
    print('Corrected:',len(items)//30,'samples; status:',dict(Counter(x.get('error','READY') for x in out)))
    for x in out:
        if x['status']=='DATA_READY':print(x['index'],x['as_of_utc'][:10],x['count_up'],x['count_down'],x['count_zero'])

if __name__=='__main__':main()
