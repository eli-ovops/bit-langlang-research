import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
MARKET = os.path.join(DATA, "market")
VERIFY = os.path.join(DATA, "verify")
os.makedirs(VERIFY, exist_ok=True)

TRADE_FIELDS = ["date","symbol","side","plan_id","setup","entry","stop","t1","exit","qty",
                "notional","margin","fee","slippage","risk_pct","hold_min","five_q_pass",
                "stop_placed","added","reversed","plan_deviation","review_class","note"]

ACCOUNT = 2000.0
RISK_PCT = 0.01

def num(x, default=0.0):
    try:
        v = float(x)
        return v if v == v else default
    except Exception:
        return default

def yn(x):
    return str(x).strip().lower() in ("1","true","yes","y","是","t")
