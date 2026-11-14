#!/bin/bash
# sim/cal.sh <out dir>: the same fee probes as data/scrape/probe2, against the simulator, one seed per port
cd "$(dirname "$0")/.." || exit 1
OUT=$1; rm -rf "$OUT"
PORT=8791 sim/run.sh "$OUT" --mode fee --share ${SHARE:-0.2} --qLo 1.0 --qHi 1.7 --seeds pr-1 > /dev/null 2>&1 &
PORT=8792 sim/run.sh "$OUT" --mode fee --share ${SHARE:-0.2} --qLo 1.0 --qHi 1.7 --seeds pr-3 > /dev/null 2>&1 &
PORT=8793 sim/run.sh "$OUT" --mode fee --share ${SHARE:-0.2} --qLo 1.25 --qHi 1.9 --seeds pr-5 > /dev/null 2>&1 &
PORT=8794 sim/run.sh "$OUT" --mode fee --share ${SHARE:-0.2} --qLo 1.25 --qHi 1.9 --seeds pr-8 > /dev/null 2>&1 &
wait
