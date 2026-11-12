#!/usr/bin/env python3
"""最后一轮预注册测试：
A. 只做 BTC/ETH（TPH v2 多头，趋势出场 vs 7d/14d 固定持有）
B. 熊市空头：BTC 20日收益<-8% 且 <EMA200 时，顶部假突破做空（72h/14d）
"""
import json, os
import numpy as np
import pandas as pd
from .common import MARKET, VERIFY
from .prove_method import load5, stats

def ema(s,n): return s.ewm(span=n,adjust=False).mean()

def daily(sym):
    b=load5(sym)
    d=b.set_index(b.ts.dt.floor("D"))
    dly=pd.DataFrame({"close":d.close.resample("D").last(),"high":d.high.resample("D").max(),"low":d.low.resample("D").min()}).reset_index().rename(columns={"ts":"day"})
    dly["day"]=pd.to_datetime(dly["day"]).dt.tz_localize(None)
    dly["ema20"]=ema(dly.close,20); dly["ema50"]=ema(dly.close,50)
    dly["hi20"]=dly.high.rolling(20).max(); dly["lo20"]=dly.low.rolling(20).min()
    return dly

def btc_ctx():
    dly=daily("BTCUSDT")
    dly["ema200"]=ema(dly.close,200)
    dly["ret20"]=dly.close.pct_change(20)
    dly["risk_on"]=((dly.close>dly.ema50)&(dly.ema50>dly.ema50.shift(5))&(dly.close>dly.ema200)).shift(1).fillna(False)
    dly["bear"]=((dly.ret20<-0.08)&(dly.close<dly.ema200)).shift(1).fillna(False)
    return dly.set_index("day")

def sim(d,day,ema20,regime,idx,dirn,stop=0.004,max_days=30,mode="trend"):
    o,h,l,c=d.open.values,d.high.values,d.low.values,d.close.values
    entry=o[idx+1]; st=entry*(1-dirn*stop); R=abs(entry-st)
    days=day.values; j=idx+1
    while j<len(d) and (pd.Timestamp(days[j])-pd.Timestamp(days[idx])).days<=max_days:
        if dirn==1 and l[j]<=st: return -1.0
        if dirn==-1 and h[j]>=st: return -1.0
        if mode=="trend" and (j==len(d)-1 or days[j+1]!=days[j]):
            e=ema20.get(pd.Timestamp(days[j]))
            if e is not None and not np.isnan(e) and ((dirn==1 and c[j]<e) or (dirn==-1 and c[j]>e)):
                return dirn*(c[j]-entry)/R
        j+=1
    j=min(j,len(d)-1); return dirn*(c[j]-entry)/R

def buildup(start="2022-05-01",end="2026-10-25"):
    ctx=btc_ctx(); ctx.index=pd.to_datetime(ctx.index).tz_localize(None); rows=[]
    for sym in ("BTCUSDT","ETHUSDT"):
        d=load5(sym); d=d[(d.ts>=start)&(d.ts<=end)].reset_index(drop=True)
        day=d.ts.dt.floor("D"); dly=daily(sym)
        dly["rs7"]=dly.close.pct_change(7)-ctx.close.pct_change(7).reindex(dly.day).values
        dly["dist_hi"]=(dly.hi20-dly.close)/dly.close
        dly["risk_on"]=ctx.risk_on.reindex(dly.day).fillna(False).values
        dly["bear"]=ctx.bear.reindex(dly.day).fillna(False).values
        ema20=dly.set_index("day").ema20
        f=dly.set_index("day").shift(1).reindex(day.values)
        rs,dh,on,bear=f["rs7"].values,f["dist_hi"].values,f["risk_on"].values,f["bear"].values
        hi20=d.high.rolling(20).max(); lo20=d.low.rolling(20).min(); prev=d.close.shift(1)
        long_c=(rs>0)&(dh<0.03)&(on==True)&(d.low<=lo20*1.001)&(d.close>prev)
        short_c=(dh<0.03)&(bear==True)&(d.high>=hi20*0.999)&(d.close<prev)
        for label,c_,dirn in (("long",long_c,1),("short",short_c,-1)):
            for i in np.where(c_.fillna(False).values)[0]:
                if i+2>=len(d): continue
                for mode,md in (("trend",30),("hold7",7),("hold14",14)):
                    rows.append(dict(side=label,mode=mode,sym=sym,ts=d.ts.values[i],R=sim(d,day,ema20,None,int(i),dirn,max_days=md,mode="trend" if mode=="trend" else "hold")))
    return pd.DataFrame(rows)

def main():
    df=buildup(); out={}
    df["year"]=pd.to_datetime(df.ts).dt.year
    for (side,mode),g in df.groupby(["side","mode"]):
        s=stats(g.R.values,10)
        out[f"{side}|{mode}"]={"n":s["n"],"gross":s["gross_R"],"net10":s["net_R"],"win":s["win"],"pf":s["pf"],"P300":s.get("P_profit_300"),
                                "by_year":{int(y):round(stats(gg.R.values,10)["net_R"],2) for y,gg in g.groupby("year")}}
        print(f"{side:5s} {mode:6s} n={s['n']:5d} net={s['net_R']:+.3f} PF={s['pf']} P300={s.get('P_profit_300')} by_year={out[f'{side}|{mode}']['by_year']}")
    # OOS
    oos=df[df.ts>=pd.Timestamp("2024-07-01")]
    print("\nOOS 2024-07~2026-10:")
    for (side,mode),g in oos.groupby(["side","mode"]):
        if len(g)<20: continue
        s=stats(g.R.values,10); print(f"  {side:5s} {mode:6s} n={s['n']:4d} net={s['net_R']:+.3f} PF={s['pf']}")
        out[f"{side}|{mode}|oos"]={"n":s["n"],"net10":s["net_R"],"pf":s["pf"]}
    json.dump(out,open(os.path.join(VERIFY,"last_tests.json"),"w"),ensure_ascii=False,indent=2)

if __name__=="__main__":
    main()
