#!/bin/sh
# 一键复现：cd scripts/attribution && sh run_all.sh
set -e
cd "$(dirname "$0")"
for s in 01_pnl_bridge.py 02_dimension_attribution.py 03_tail_structure.py 04_scale_turnover.py \
         05_counterfactuals.py 06_robustness.py 07_charts.py 08_export_tables.py 09_market_context.py; do
  echo "== $s =="
  python3 "$s"
done
echo "done -> ../../data/attribution/"
