#!/usr/bin/env python3
"""逐笔交易日志：add / list / import / export / validate。"""
import argparse, csv, os, sys
from datetime import datetime
from .common import TRADE_FIELDS, VERIFY

DEFAULT = os.path.join(VERIFY, "trades.csv")

def load(path=DEFAULT):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def save(rows, path=DEFAULT):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in TRADE_FIELDS})

def validate(rows):
    errs = []
    for i, r in enumerate(rows, 1):
        for k in ("date", "symbol", "side", "entry", "stop", "exit", "risk_pct"):
            if not str(r.get(k, "")).strip():
                errs.append(f"row{i}: 缺少 {k}")
        try:
            e, s, x = float(r["entry"]), float(r["stop"]), float(r["exit"])
            if r["side"].lower().startswith("l") and not (s < e and x > 0):
                errs.append(f"row{i}: 多单止损应低于入场")
            if r["side"].lower().startswith("s") and not (s > e and x > 0):
                errs.append(f"row{i}: 空单止损应高于入场")
        except Exception:
            errs.append(f"row{i}: 价格不是数字")
        if float(r.get("risk_pct") or 0) > 2.0:
            errs.append(f"row{i}: risk_pct>2% 超限")
    return errs

def cmd_add(a):
    rows = load(a.file)
    rows.append({k: getattr(a, k) for k in TRADE_FIELDS})
    save(rows, a.file)
    print(f"added; total={len(rows)}")

def cmd_list(a):
    rows = load(a.file)
    if a.last:
        rows = rows[-a.last:]
    for r in rows:
        print(" | ".join(f"{k}={r.get(k,'')}" for k in ("date","symbol","side","entry","stop","exit","risk_pct","review_class")))

def cmd_import(a):
    src = load(a.src)
    dst = load(a.dst)
    dst.extend(src)
    save(dst, a.dst)
    print(f"imported {len(src)}; total={len(dst)}")

def cmd_export(a):
    save(load(a.file), a.out)
    print("exported", a.out)

def cmd_validate(a):
    errs = validate(load(a.file))
    print("\n".join(errs) if errs else "OK: 无错误")
    sys.exit(1 if errs else 0)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    for k in TRADE_FIELDS: a.add_argument(f"--{k}", default="")
    a.set_defaults(func=cmd_add)
    l = sub.add_parser("list"); l.add_argument("--last", type=int, default=20); l.set_defaults(func=cmd_list)
    im = sub.add_parser("import"); im.add_argument("src"); im.add_argument("--dst", default=DEFAULT); im.set_defaults(func=cmd_import)
    ex = sub.add_parser("export"); ex.add_argument("out"); ex.set_defaults(func=cmd_export)
    va = sub.add_parser("validate"); va.set_defaults(func=cmd_validate)
    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
