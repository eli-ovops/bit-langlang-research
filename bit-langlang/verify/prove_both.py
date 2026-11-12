#!/usr/bin/env python3
"""双侧：多头=强势回踩；空头=顶部假突破（近20日高+5m冲高收回）。
两者都是 0.4% 止损 + 持有 72h + 不加仓。"""
import json, os
import numpy as np
import pandas as pd
from .prove_method import load5, SYMS, sim_exit, stats
from .common import VERIFY

def btc_close():
    b=load5("BTCUSDT"); d=b.set_index(b.ts.dt.floor("D")).close.resample("D").last(); d.index=pd.to_datetime(d.index).tz_localize(None); return d

def run(start,end):
    bc=btc_close(); rows=[]
    for sym in SYMS:
        d=load5(sym); d=d[(d.ts>=start)&(d.ts<=end)].reset_index(drop=True)
        if len(d)<1000: continue
        day=d.ts.dt.floor("D")
        dly=pd.DataFrame({"day":day.values,"close":d.close.values,"high":d.high.values,"low":d.low.values}).groupby("day").agg({"close":"last","high":"max","low":"min"}).reset_index()
        dly["hi20"]=dly.high.rolling(20).max(); dly["lo20"]=dly.low.rolling(20).min()
        dly["ret7"]=dly.close.pct_change(7); dly["dist_hi"]=(dly.hi20-dly.close)/dly.close
        rs7=dly.ret7-bc.pct_change(7).reindex(dly.day).values
        dly["rs7"]=rs7.values
        feats=dly.set_index("day").shift(1)[["dist_hi","rs7"]].reindex(day.values).values
        dh,rs=feats[:,0],feats[:,1]
        hi20=d.high.rolling(20).max(); lo20=d.low.rolling(20).min(); prev=d.close.shift(1)
        long_c=(rs>0)&(dh<0.03)&(d.low<=lo20*1.001)&(d.close>prev)
        short_c=(dh<0.03)&(d.high>=hi20*0.999)&(d.close<prev)
        for i in np.where(long_c.fillna(False).values)[0]:
            if i+2<len(d): rows.append(dict(side=1,ts=d.ts.values[i],R=sim_exit(d.open.values,d.high.values,d.low.values,d.close.values,int(i),1,trail_trigger=None,max_bars=864)))
        for i in np.where(short_c.fillna(False).values)[0]:
            if i+2<len(d): rows.append(dict(side=-1,ts=d.ts.values[i],R=sim_exit(d.open.values,d.high.values,d.low.values,d.close.values,int(i),-1,trail_trigger=None,max_bars=864)))
    df=pd.DataFrame(rows); df["year"]=pd.to_datetime(df.ts).dt.year; return df

def main():
    df=run("2022-05-01","2026-10-25")
    out={"all":{f"{bps}bp":stats(df.R.values,bps) for bps in (5.7,10,20)},
         "long":{f"{bps}bp":stats(df[df.side==1].R.values,bps) for bps in (5.7,10,20)},
         "short":{f"{bps}bp":stats(df[df.side==-1].R.values,bps) for bps in (5.7,10,20)},
         "by_year":{int(y):{f"{bps}bp":stats(g.R.values,bps) for bps in (10,)} for y,g in df.groupby("year")}}
    json.dump(out,open(os.path.join(VERIFY,"prove_both.json"),"w"),ensure_ascii=False,indent=2)
    for k in ("all","long","short"):
        m=out[k]["10bp"]; print(f"{k:6s} n={m['n']:6d} gross={m['gross_R']:+.3f} net@10={m['net_R']:+.3f} win={m['win']:.1f}% PF={m['pf']} P300={m.get('P_profit_300')} P1000={m.get('P_profit_1000')}")
    print("by year @10bp:")
    for y,v in out["by_year"].items():
        m=v["10bp"]; print(f"  {y}: n={m['n']:6d} net={m['net_R']:+.3f} gross={m['gross_R']:+.3f} PF={m['pf']}")

if __name__=="__main__": main()
