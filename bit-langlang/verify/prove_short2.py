#!/usr/bin/env python3
"""空头再审视：不镜像多头，而是测"顶部假突破/超买反转"等更贴近他空单的入场。"""
import json, os
import numpy as np
import pandas as pd
from .prove_method import load5, SYMS, sim_exit, stats
from .common import VERIFY

def btc_regime():
    b = load5("BTCUSDT"); d = b.set_index(b.ts.dt.floor("D")).close.resample("D").last().reset_index()
    d.columns = ["day","close"]; d["day"]=pd.to_datetime(d["day"]).dt.tz_localize(None)
    e50=d.close.ewm(span=50).mean(); e200=d.close.ewm(span=200).mean()
    d["on"]=((d.close>e50)&(e50>e50.shift(5))&(d.close>e200)).shift(1).fillna(False).values
    d["off"]=((d.close<e50)&(e50<e50.shift(5))&(d.close<e200)).shift(1).fillna(False).values
    return d.set_index("day")[["on","off"]]

def run(start,end,r):
    rows=[]
    for sym in SYMS:
        d=load5(sym); d=d[(d.ts>=start)&(d.ts<=end)].reset_index(drop=True)
        if len(d)<1000: continue
        day=d.ts.dt.floor("D"); rr=r.reindex(day.values).values
        dly=pd.DataFrame({"day":day.values,"close":d.close.values,"high":d.high.values,"low":d.low.values}).groupby("day").agg({"close":"last","high":"max","low":"min"}).reset_index()
        dly["hi20"]=dly.high.rolling(20).max(); dly["lo20"]=dly.low.rolling(20).min()
        dly["ret5"]=dly.close.pct_change(5); dly["ret7"]=dly.close.pct_change(7)
        dly["dist_hi"]=(dly.hi20-dly.close)/dly.close
        feats=dly.set_index("day").shift(1)[["dist_hi","ret5","ret7"]].reindex(day.values).values
        dh,ret5,ret7=feats[:,0],feats[:,1],feats[:,2]
        hi20=d.high.rolling(20).max(); prev=d.close.shift(1)
        trig=(d.high>=hi20*0.999)&(d.close<prev)
        conds={
 "H2_顶部假突破":(dh<0.03)&trig,
 "H3_超买反转":(ret5>0.15)&(dh<0.06)&trig,
 "H4_弱势+顶部失败":(rr[:,1]==True)&(dh<0.06)&trig,
 "H5_任意5m反转":trig,
        }
        for name,c in conds.items():
            for i in np.where(c.fillna(False).values)[0]:
                if i+2>=len(d): continue
                for stop in (0.004,0.01,0.02):
                    for hold in (48,288,864):
                        rows.append((name,stop,hold,d.ts.values[i],sim_exit(d.open.values,d.high.values,d.low.values,d.close.values,int(i),-1,stop_pct=stop,trail_trigger=None,max_bars=hold)))
    return pd.DataFrame(rows,columns=["name","stop","hold","ts","R"])

def main():
    r=btc_regime(); out={}
    periods={"2022_bear":("2022-05-01","2022-12-31"),"2023_2024H1_bull":("2023-01-01","2024-06-30"),"2024H2_2026":("2024-07-01","2026-10-25")}
    for p,(a,b) in periods.items():
        df=run(a,b,r); out[p]={}
        for (name,stop,hold),g in df.groupby(["name","stop","hold"]):
            if len(g)<200: continue
            s=stats(g.R.values,10)
            out[p][f"{name}|stop{stop*100:.1f}%|hold{hold*5/60:.0f}h"]={"n":s["n"],"gross_R":s["gross_R"],"net_R":s["net_R"],"win":s["win"],"pf":s["pf"],"P300":s.get("P_profit_300")}
    json.dump(out,open(os.path.join(VERIFY,"prove_short2.json"),"w"),ensure_ascii=False,indent=2)
    # 打印每个时段 best by net_R
    for p,d in out.items():
        top=sorted(d.items(),key=lambda kv:kv[1]["net_R"],reverse=True)[:6]
        print("==",p)
        for k,v in top: print(f"  {k:45s} n={v['n']:5d} net={v['net_R']:+.3f} PF={v['pf']} P300={v['P300']}")

if __name__=="__main__":
    main()
