#!/usr/bin/env python3
"""证明"他的做法"是否赚钱（行为层，而非信号层）。

实验 A：用他的真实入场点，套用"他的行为"（0.4% 快止损 + 5m 结构跟踪 + 最长 72h + 不加仓），
        看他这套"截断亏损/让利润奔跑"的行为本身是否正期望。
实验 B：在独立时段 2024-07~2026-10，用通用"强势币回踩"入场 + 同一行为，检验可迁移性。
成本：按他的 5.7bp（往返）/ 零售 10bp / 压力 20bp 三档。
输出：data/verify/prove_method.json + 终端摘要。
"""
import json, os
import numpy as np
import pandas as pd
from .common import MARKET, VERIFY

SYMS = ["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","PEOPLEUSDT","TRBUSDT","WLDUSDT","APTUSDT","ORDIUSDT","1000PEPEUSDT"]
MAP = {"BTC-USDT-SWAP":"BTCUSDT","ETH-USDT-SWAP":"ETHUSDT","SOL-USDT-SWAP":"SOLUSDT","DOGE-USDT-SWAP":"DOGEUSDT",
       "PEOPLE-USDT-SWAP":"PEOPLEUSDT","TRB-USDT-SWAP":"TRBUSDT","WLD-USDT-SWAP":"WLDUSDT","APT-USDT-SWAP":"APTUSDT",
       "ORDI-USDT-SWAP":"ORDIUSDT","PEPE-USDT-SWAP":"1000PEPEUSDT"}

def load5(sym):
    p = os.path.join(MARKET, f"{sym}_5m.csv.gz")
    if not os.path.exists(p): return None
    d = pd.read_csv(p, usecols=["ts","open","high","low","close"])
    d["ts"] = pd.to_datetime(d.ts, unit="ms", utc=True)
    return d.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)

def sim_exit(o,h,l,c,i,dirn,stop_pct=0.004,max_bars=864,trail_trigger=None):
    """下一根开盘入场；0.4% 止损；可选：盈利达到 trail_trigger 后按前 20 根摆动跟踪；最长 max_bars。"""
    n=len(c); entry=o[i+1]; stop=entry*(1-dirn*stop_pct); R=abs(entry-stop)
    for j in range(i+1, min(i+max_bars, n)):
        if dirn==1 and l[j] <= stop: return -1.0
        if dirn==-1 and h[j] >= stop: return -1.0
        if trail_trigger is not None and j > i+3:
            if dirn==1 and (h[j]-entry)/R >= trail_trigger:
                trail = l[max(0,j-20):j].min()
                if c[j] < trail: return (c[j]-entry)/R
            if dirn==-1 and (entry-l[j])/R >= trail_trigger:
                trail = h[max(0,j-20):j].max()
                if c[j] > trail: return (entry-c[j])/R
    j=min(i+max_bars,n-1)
    return dirn*(c[j]-entry)/R

def part_a():
    pos=pd.read_csv("data/processed/v2/trades_positions.csv",parse_dates=["entry_time","exit_time"])
    pos["sym"]=pos.symbol.map(MAP); pos=pos.dropna(subset=["sym"]).copy()
    pos["dir"]=np.where(pos.side=="多",1,-1)
    rows=[]
    for sym,g in pos.groupby("sym"):
        d=load5(sym)
        if d is None: continue
        idx=np.clip(np.searchsorted(d.ts,(g.entry_time-pd.Timedelta(hours=8)).dt.tz_localize("UTC")),0,len(d)-2)
        for (_,r),i in zip(g.iterrows(),idx):
            if i+2>=len(d): continue
            gr=sim_exit(d.open.values,d.high.values,d.low.values,d.close.values,int(i),int(r["dir"]))
            # 他的实际（用风险单位：名义*0.4%）
            actual_R = r.pnl/(r.notional*0.004) if r.notional>0 else np.nan
            rows.append(dict(sym=sym,entry_time=r.entry_time,dir=int(r["dir"]),gross_R=gr,actual_R=actual_R,hold_min=r.hold_min))
    A=pd.DataFrame(rows)
    return A

def part_b(start="2024-07-01",end="2026-10-25"):
    """通用强势币回踩入场；返回各行为变体的 gross R 列表。"""
    btc=load5("BTCUSDT"); btc_d=btc.set_index(btc.ts.dt.floor("D")).close.resample("D").last()
    btc_d.index = pd.to_datetime(btc_d.index).tz_localize(None)
    variants={"trail1":dict(trail_trigger=1.0,max_bars=864),
              "hold24h":dict(trail_trigger=None,max_bars=288),
              "hold72h":dict(trail_trigger=None,max_bars=864)}
    out={k:[] for k in variants}
    for sym in SYMS:
        if sym=="BTCUSDT": continue
        d=load5(sym); d=d[(d.ts>=start)&(d.ts<=end)].reset_index(drop=True)
        if len(d)<1000: continue
        day=d.ts.dt.floor("D")
        dly=pd.DataFrame({"day":day.values,"close":d.close.values}).groupby("day").close.last().reset_index()
        dly["hi20"]=dly.close.rolling(20).max()
        rs7=dly.close.pct_change(7)-btc_d.pct_change(7).reindex(dly.day).values
        dly["rs7"]=rs7.values; dly["dist_hi"]=(dly.hi20-dly.close)/dly.close
        ok=dly.set_index("day")[["rs7","dist_hi"]].shift(1)
        feats=ok.reindex(day.values).values
        rs=feats[:,0]; dh=feats[:,1]
        lo20=d.low.rolling(20).min(); prev=d.close.shift(1)
        cond=(rs>0)&(dh<0.03)&(d.low<=lo20*1.001)&(d.close>prev)
        idx=np.where(cond.fillna(False).values)[0]
        for i in idx:
            if i+2>=len(d): continue
            for k,kw in variants.items():
                out[k].append(sim_exit(d.open.values,d.high.values,d.low.values,d.close.values,int(i),1,**kw))
    return out

def stats(R, cost_bps, stop_pct=0.004):
    R=np.asarray(R,dtype=float); R=R[np.isfinite(R)]
    cost_R=(cost_bps/10000)/stop_pct
    net=R-cost_R
    out=dict(n=len(net),gross_R=round(float(R.mean()),3),cost_R=round(float(cost_R),3),
             net_R=round(float(net.mean()),3),win=round(float((net>0).mean()*100),1),
             pf=round(float(net[net>0].sum()/abs(net[net<0].sum())),2) if (net<0).any() else None)
    rng=np.random.default_rng(42)
    for N in (50,100,300,1000,3000):
        if len(net)<N: continue
        sums=np.array([rng.choice(net,size=N,replace=True).sum() for _ in range(2000)])
        out[f"P_profit_{N}"]=round(float((sums>0).mean()*100),1)
    return out

def main():
    A=part_a(); B=part_b()
    res={"part_a_his_entries":{}, "part_b_independent":{}}
    for bps in (5.7,10,20):
        res["part_a_his_entries"][f"{bps}bp"]=stats(A.gross_R,bps)
    for k,v in B.items():
        res["part_b_independent"][k]={f"{bps}bp":stats(v,bps) for bps in (5.7,10,20)}
    json.dump(res,open(os.path.join(VERIFY,"prove_method.json"),"w"),ensure_ascii=False,indent=2)
    print(json.dumps(res,ensure_ascii=False,indent=1))

if __name__=="__main__":
    main()
