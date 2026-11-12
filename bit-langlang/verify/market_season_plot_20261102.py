"""Static audit chart: weekly candidate labels are last observations, not truth."""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
SRC=Path('data/market/nine-futures-stage-oct31-20261031-01/BTCUSDT_5m.csv.gz');OUT=Path('data/verify/market-season-research-20261102-01')
def main():
 p=OUT/'timeline.png'
 if p.exists():raise FileExistsError(p)
 f=pd.read_csv(SRC,usecols=['ts','close']);f['time']=pd.to_datetime(f.ts,unit='ms',utc=True);d=f.set_index('time').close.resample('D').last();seg=pd.read_csv(OUT/'segments.csv');colors={'SPRING':'#80bc85','SUMMER':'#f2ba58','AUTUMN':'#c88b76','WINTER':'#829bc3','UNKNOWN':'#dfe3e6'}
 fig,ax=plt.subplots(figsize=(15,5.6));
 for row in seg.itertuples(index=False):ax.axvspan(pd.Timestamp(row.start_utc),pd.Timestamp(row.end_utc_exclusive),color=colors[row.season],alpha=.46,linewidth=0)
 ax.plot(d.loc['2025-10-01':'2026-10-30'].index,d.loc['2025-10-01':'2026-10-30'].to_numpy(),color='#26344c',linewidth=1.5)
 ax.set_title('BTC: weekly research labels, not verified market seasons',loc='left',fontsize=14);ax.set_ylabel('BTC perpetual close (USDT)');ax.grid(axis='y',alpha=.2)
 ax.legend(handles=[Patch(facecolor=colors[k],label=k.title()) for k in ('SPRING','SUMMER','AUTUMN','WINTER','UNKNOWN')],ncol=5,loc='lower center',bbox_to_anchor=(.5,-.27),frameon=False)
 fig.text(.12,.015,'UTC | Background shows last weekly decision only; 4h + daily extrema proxies; labels may be wrong.',fontsize=9);fig.subplots_adjust(bottom=.28);fig.savefig(p,dpi=140);plt.close(fig);print(p)
if __name__=='__main__':main()
