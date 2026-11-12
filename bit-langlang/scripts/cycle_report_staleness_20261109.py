import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cycle_causal_pullback_20261105 import daily
from cycle_pullback_supplement_20261105 import SOURCES

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/verify/cycle-report-staleness-20261109-01'
DAY=timedelta(days=1)


def measure(data,start,end):
    n=(end-start).days
    if n<0 or start+DAY*n!=end:return None
    before=data.get(start-DAY)
    days=[data.get(start+i*DAY) for i in range(n)]
    if before is None or any(d is None for d in days):return None
    start_close=before['close'];end_close=days[-1]['close'] if days else start_close
    return {'start_close':start_close,'end_close':end_close,'change_pct':100*(end_close/start_close-1),
            'high':max((d['high'] for d in days),default=start_close),'low':min((d['low'] for d in days),default=start_close),'days':n}


def main():
    sample={datetime(2025,1,1,tzinfo=timezone.utc):{'close':10,'high':11,'low':9},datetime(2025,1,2,tzinfo=timezone.utc):{'close':12,'high':13,'low':10}}
    assert abs(measure(sample,datetime(2025,1,2,tzinfo=timezone.utc),datetime(2025,1,3,tzinfo=timezone.utc))['change_pct']-20)<1e-9
    assert measure(sample,datetime(2025,1,2,tzinfo=timezone.utc),datetime(2025,1,4,tzinfo=timezone.utc)) is None
    refs=list(csv.DictReader((ROOT/'docs/浪浪周期-同期周报全观察参考清单-20261109.csv').open()))
    prior=json.loads((ROOT/'data/verify/cycle-report-archive-20261109-01/summary.json').read_text())['results']
    metadata={x['as_of_utc']:x for x in prior}
    datasets={q:daily(ROOT/path) for q,path in SOURCES.items()}
    original=json.loads((ROOT/'data/verify/cycle-report-archive-20261109-01/summary.json').read_text())['results']
    recovery=json.loads((ROOT/'data/verify/cycle-report-archive-recovery-20261109-01/audit_verified.json').read_text())
    remaining=json.loads((ROOT/'data/verify/cycle-report-archive-remaining-20261109-01/progress.json').read_text())
    archive={x['index']:x['status'] for x in original if x['status'].startswith('ARCHIVE_')}
    for x in recovery:
        if x['selected_matches_memento']:archive[x['index']]='ARCHIVE_MATCH' if x.get('body_status')=='MATCH' or x.get('body_equal') is True else 'ARCHIVE_DIFF'
    for x in remaining:
        if x['status'].startswith('ARCHIVE_'):archive[x['index']]=x['status']
    output=[]
    for ref in refs:
        t=datetime.fromisoformat(ref['as_of_utc'].replace('Z','+00:00'));q=f'{t.year}Q{(t.month-1)//3+1}'
        row={'as_of_utc':ref['as_of_utc'],'report_date':ref['report_date'],'report_url':ref['report_url'],
             'published_time':'UNKNOWN','start_utc':'UNKNOWN','days':'UNKNOWN','start_close':'UNKNOWN',
             'end_close':'UNKNOWN','change_pct':'UNKNOWN','high':'UNKNOWN','low':'UNKNOWN',
             'archive_status':'NO_REPORT','phase':'UNKNOWN','sentiment':'UNKNOWN'}
        m=metadata.get(ref['as_of_utc'])
        if m:
            row['archive_status']=archive.get(m['index'],'UNKNOWN')
            if m.get('published_time'):
                pub=datetime.fromisoformat(m['published_time'].replace('Z','+00:00'))
                start=(pub+DAY).replace(hour=0,minute=0,second=0,microsecond=0)
                assert pub<start<=t and pub.date().isoformat()==ref['report_date']
                row.update(published_time=pub.isoformat(),start_utc=start.isoformat())
                values=measure(datasets[q],start,t)
                if values is not None:row.update(values)
        output.append(row)
    assert len(output)==26 and len({x['as_of_utc'] for x in output})==26
    OUT.mkdir(parents=True,exist_ok=False)
    with (OUT/'timegaps.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(output[0]));w.writeheader();w.writerows(output)
    print('rows',len(output),'valid',sum(r['change_pct']!='UNKNOWN' for r in output))
    for r in output:
        if r['change_pct']!='UNKNOWN':print(r['as_of_utc'][:10],r['report_date'],r['days'],f"{r['change_pct']:.2f}%",r['archive_status'])


if __name__=='__main__':main()
