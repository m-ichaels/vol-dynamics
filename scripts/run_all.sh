#!/usr/bin/env bash
# Full pipeline: (data ->) build -> forecast -> premia -> events -> vix -> strategies -> tests -> figures -> summary -> report
# Usage: scripts/run_all.sh [--download] [--quick]
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
Q=""; [[ " $* " == *" --quick "* ]] && Q="--quick"
if [[ " $* " == *" --download "* ]]; then
  python tools/download.py cboe vx rates prices dvol candles
  python tools/download.py deribit
  python tools/download.py volhist earnings chains
fi
python -u -m voldyn build $Q | tee results/build.log
python -u -m voldyn forecast $Q | tee results/forecast.log
python -u -m voldyn premia $Q | tee results/premia.log
python -u -m voldyn events $Q | tee results/events.log
python -u -m voldyn vix | tee results/vix.log
python -u -m voldyn strategies $Q | tee results/strategies.log
python -m pytest -q | tee results/tests.txt
python scripts/plots.py
python scripts/summarize.py
python scripts/report.py
echo done
