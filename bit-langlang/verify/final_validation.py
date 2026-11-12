#!/usr/bin/env python3
"""TPH v2 最终验证：选择器（Top-K 币）+ 季节过滤 + 组合层，全样本与冻结样本外。
注意：策略形态参数（0.4% 止损/趋势出场）在早期研究中已固定，本脚本不改；
选择器规则使用"当日事前可得"的 rs7 排名（前一交易日数据），不引入未来。
"""
import json, os
import numpy as np
import pandas as pd
from .common import VERIFY
from .portfolio_sim import build_trades, simulate

def select(df, mode):
    d = df.copy()
    if mode in ("S1_top3", "S3_top3_on", "S4_top5"):
        k = 3 if mode != "S4_top5" else 5
        coins = d[["day", "symbol", "rs7"]].drop_duplicates(["day", "symbol"]).copy()
        coins["rank"] = coins.groupby("day")["rs7"].rank(ascending=False, method="first")
        d = d.merge(coins[["day", "symbol", "rank"]], on=["day", "symbol"], how="left")
        d = d[d["rank"] <= k]
    if mode in ("S2_on", "S3_top3_on"):
        d = d[d.btc_on]
    return d

def sim(df, risk, conc, initial=2000.0):
    if not len(df): return None
    r = simulate(df.sort_values("entry_ts"), risk=risk, max_conc=conc, initial=initial)
    return dict(final=r["final"], cagr=r["cagr_pct"], mdd=r["mdd_pct"],
                sharpe=r["sharpe"], taken=r["trades_taken"])

def main():
    tr=build_trades()
    btc=pd.read_csv(os.path.join("data","market","BTCUSDT_1d.csv.gz"))
    btc["ts"]=pd.to_datetime(btc.ts,unit="ms",utc=True); btc=btc.sort_values("ts").set_index("ts").close
    out={}
    for split,lo in (("full","2022-05-01"),("oos","2024-07-01")):
        d0=tr[pd.to_datetime(tr.entry_ts,utc=True)>=pd.Timestamp(lo,tz="UTC")] if split=="oos" else tr
        out[split]={}
        for mode in ("S0_all","S1_top3","S2_on","S3_top3_on","S4_top5"):
            d=select(d0,mode)
            for conc in (1,3):
                r=sim(d,0.001,conc)
                out[split][f"{mode}|conc{conc}"]=r
                if r: print(f"{split:4s} {mode:12s} conc{conc} n_sig={len(d):5d} taken={r['taken']:5d} final={r['final']:>10,.0f} cagr={r['cagr']:>6.1f}% mdd={r['mdd']:>6.1f}% sharpe={r['sharpe']}")
    # 基准：BTC 买入持有
    for split,lo,hi in (("full","2022-05-01","2026-10-25"),("oos","2024-07-01","2026-10-25")):
        s=btc[lo:hi]; out.setdefault("benchmark",{})[split]=round(float((s.iloc[-1]/s.iloc[0]-1)*100),1)
    out["benchmark_cagr"]={k:round(((1+v/100)**(1/((pd.Timestamp("2026-10-25")-pd.Timestamp("2022-05-01" if k=="full" else "2024-07-01")).days/365.25))-1)*100,1) for k,v in out["benchmark"].items()}
    json.dump(out,open(os.path.join(VERIFY,"final_validation.json"),"w"),ensure_ascii=False,indent=2)
    print("benchmark:",out["benchmark"],"cagr:",out["benchmark_cagr"])

if __name__=="__main__":
    main()
