#!/usr/bin/env python3
"""小工具：不依赖 tabulate 的 markdown 表格输出。"""
from __future__ import annotations

import pandas as pd


def to_md(df: pd.DataFrame, floatfmt: str = ".3f") -> str:
    if df is None or len(df) == 0:
        return "_(empty)_"
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        cells = []
        for c in df.columns:
            v = row[c]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                cells.append("")
            elif isinstance(v, float):
                cells.append(format(v, floatfmt))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
