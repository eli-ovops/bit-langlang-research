"""Anonymized as-of chart pack for future independent human review, not labels."""
from pathlib import Path
import hashlib,json,random
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from verify.market_2018_transition_20261102 import read
from verify.season_casebook_20261102 import draw
OUT=Path('data/verify/phase-human-review-2017nd-20261103-01')
def main():
 if OUT.exists():raise FileExistsError(OUT)
 samples=[];inputs=[]
 for year,start,end in [('2017nd','2017-11-01','2017-12-31')]:
  src=Path('data/verify/market-prior28-2017nd-20261103-01');data=Path(f'data/market/btc-{year}-usd-cross-20261102-01/bitstamp-4h.csv.gz');flags=[pd.Timestamp(x) for x in json.loads((src/'summary.json').read_text())['quality_flags_utc']];inputs += [data,src/'summary.json'];d,h=read(data)
  for f in flags:
   if f in h.index:h.loc[f,'good']=False
   if f.floor('D') in d.index:d.loc[f.floor('D'),'good']=False
  original=pd.read_csv(data);original.index=pd.to_datetime(original.ts,unit='ms',utc=True);daily=original.resample('D').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),n=('ts','size'))
  for t in pd.date_range(start,end,freq='D',tz='UTC'):
   dd=d[(d.index>=t-pd.Timedelta(days=56))&(d.index<t)];hh=h[(h.index>=t-pd.Timedelta(days=14))&(h.index<t)];ok=len(dd)==56 and dd.good.all() and len(hh)==84 and hh.good.all();samples.append({'year':year,'t':t,'ok':bool(ok),'daily':daily.loc[dd.index] if ok else None,'four':hh if ok else None})
 assert len(samples)==61;random.Random(20171101).shuffle(samples);pack=OUT/'reviewer-pack';charts=pack/'charts';charts.mkdir(parents=True);mapping=[];forms=[]
 for n,case in enumerate(samples,1):
  label=f'P{n:02}';record={'case':label,'as_of_utc':case['t'].isoformat(),'year':case['year'],'complete':case['ok']}
  if case['ok']:
   fig,axes=plt.subplots(2,1,figsize=(12,7),constrained_layout=True)
   for ax,z,title in [(axes[0],case['daily'],'Last 56 completed daily candles'),(axes[1],case['four'],'Last 84 completed 4-hour candles')]:
    z=z.copy();z[['open','high','low','close']]=z[['open','high','low','close']]/float(z.close.iloc[0])*100;draw(ax,z);ax.set_xticks([0,len(z)//2,len(z)-1]);ax.set_xticklabels(['oldest','middle','latest']);ax.set_title(title,loc='left');ax.set_ylabel('relative index')
   path=charts/(label+'.png');fig.savefig(path,dpi=110);plt.close(fig);record['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();forms.append({'case':label,'reviewer_id':'','date_independent_review_utc':'','big_background':'','small_structure':'','swing_evidence':'','boundary_evidence':'','alternatives':'','stage_hypothesis':'','confidence':'','unknown_reason':'','recognition':''})
  mapping.append(record)
 pd.DataFrame(forms,columns=['case','reviewer_id','date_independent_review_utc','big_background','small_structure','swing_evidence','boundary_evidence','alternatives','stage_hypothesis','confidence','unknown_reason','recognition']).to_csv(pack/'worksheet.csv',index=False)
 (pack/'README.md').write_text('# 独立盘面判读包\n\n只看 charts 及此表；每图均截断在判断时点，不含后续走势。填写 worksheet.csv，使用匿名编号，不查日期或其他答案。先记录长期背景、小级别事实、可指出的高低点与边界，再写竞争解释、阶段候选；不清楚留空并说明。候选包括春启动、下跌反弹、秋衰退、正常回调，也可以多选或 UNKNOWN。图是归一化 BTC 日线及4小时线，不能由价格推断真实情绪。不同人先各自独立填写，不应强行一致；人工判读不等于已验证真值。\n\n样本来自过去已公开历史，可能被识别；请注明是否认识该盘面。独立评审需要未参与规则设计且未查看模型输出、映射及未来的人。本目录不包含答案、事件、规则输出或日期映射。\n')
 (OUT/'sealed-map.json').write_text(json.dumps(mapping,indent=2)+'\n');files=inputs+[Path(__file__)];(OUT/'manifest.json').write_text(json.dumps({'status':'HUMAN_REVIEW_NOT_STARTED','fixed_sample':len(samples),'available_charts':len(forms),'unavailable':len(samples)-len(forms),'reviewer_workbook':str(pack/'worksheet.csv'),'limitations':['Single venue chart; two reviewers not yet obtained.','Familiar historic pattern and normalized price may reveal date.','No future outcomes in pack; not independent human label yet.'],'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('total',len(samples),'available',len(forms),'unknown',len(samples)-len(forms))
if __name__=='__main__':main()
