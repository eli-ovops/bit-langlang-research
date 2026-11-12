"""Generate as-of only charts; selection is stratified and retrospective."""
import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from .market_season_research_20261102 import SOURCE,sha
BASE=Path('data/verify/market-season-research-20261102-01');OUT=Path('data/verify/season-asof-casebook-20261102-01');DEF=Path('docs/市场阶段-同期盘面案例审查定义-20261102.md')

def draw(ax,g):
 for i,r in enumerate(g.itertuples()):
  color='#187952' if r.close>=r.open else '#b63838';ax.vlines(i,r.low,r.high,color=color,linewidth=.7);bottom=min(r.open,r.close);height=max(abs(r.close-r.open),.00001);ax.add_patch(Rectangle((i-.30,bottom),.6,height,facecolor=color,edgecolor=color,linewidth=.5))
 ax.set_xlim(-1,len(g));ax.grid(axis='y',alpha=.2);ticks=np.linspace(0,len(g)-1,6,dtype=int);ax.set_xticks(ticks);ax.set_xticklabels([g.index[i].strftime('%m-%d') for i in ticks],fontsize=8);ax.tick_params(axis='y',labelsize=8)

def main():
 if OUT.exists():raise FileExistsError(OUT)
 paths=[SOURCE,BASE/'weekly.csv',DEF,Path(__file__)];inputs={str(p):sha(p) for p in paths};weekly=pd.read_csv(BASE/'weekly.csv');chosen=weekly.groupby('season',sort=True).head(1).sort_values('as_of_utc')
 if set(chosen.season)!={'SPRING','SUMMER','AUTUMN','WINTER','UNKNOWN'}:raise ValueError('missing category')
 f=pd.read_csv(SOURCE);f['time']=pd.to_datetime(f.ts,unit='ms',utc=True);f=f.set_index('time');v=f[['open','high','low','close']];f['bad']=(~np.isfinite(v).all(axis=1))|(v<=0).any(axis=1)|(f.low>v.min(axis=1))|(f.high<v.max(axis=1))
 def agg(freq,expected):
  x=f.resample(freq).agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),n=('ts','size'),bad=('bad','sum'));x['good']=x.n.eq(expected)&x.bad.eq(0);return x
 daily=agg('D',288);four=agg('4h',48);OUT.mkdir(parents=True);key=[]
 for i,r in enumerate(chosen.itertuples(index=False),1):
  t=pd.Timestamp(r.as_of_utc);d=daily.loc[(daily.index>=t-pd.Timedelta(days=45))&(daily.index<t)];h=four.loc[(four.index>=t-pd.Timedelta(days=14))&(four.index<t)]
  if len(d)!=45 or len(h)!=84 or not d.good.all() or not h.good.all() or d.index[-1]+pd.Timedelta(days=1)>t or h.index[-1]+pd.Timedelta(hours=4)>t:raise ValueError('history invalid')
  case=f'C{i:02}';fig,axes=plt.subplots(2,1,figsize=(13,7.4),constrained_layout=True);draw(axes[0],d);draw(axes[1],h);axes[0].set_title(f'{case} | BTC daily | decision {t:%Y-%m-%d %H:%M} UTC',loc='left');axes[1].set_title('BTC 4h | last 14 days | all candles closed by decision time',loc='left');axes[0].set_ylabel('USDT');axes[1].set_ylabel('USDT');fig.savefig(OUT/(case+'.png'),dpi=140);plt.close(fig)
  key.append({'case':case,'as_of_utc':t.isoformat(),'model_candidate':r.season,'daily_relation':r.daily_relation,'h4_relation':r.four_hour_relation,'midpoint_condition':bool(r.close_above_daily14_mid),'daily_last_close_end_utc':(d.index[-1]+pd.Timedelta(days=1)).isoformat(),'h4_last_close_end_utc':(h.index[-1]+pd.Timedelta(hours=4)).isoformat(),'independent_reviewer_status':'UNKNOWN','independent_label':'UNKNOWN','chart_sha256':sha(OUT/(case+'.png'))})
 if any(sha(p)!=v for p,v in inputs.items()):raise ValueError('input modified')
 pd.DataFrame(key).to_csv(OUT/'case-key.csv',index=False);(OUT/'manifest.json').write_text(json.dumps({'status':'RESEARCH_CASEBOOK_NOT_INDEPENDENT_VALIDATION','inputs_sha256':inputs,'case_count':len(key),'cases':key,'limits':['Charts exclude future bars, but dates and historical outcomes known in project.','Stratified first-per-category sample not representative.','Independent reviewer and ground truth absent.']},ensure_ascii=False,indent=2)+'\n');print(json.dumps(key,indent=2))
if __name__=='__main__':main()
