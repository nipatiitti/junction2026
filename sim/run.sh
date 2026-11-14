#!/bin/bash
# sim/run.sh <out dir> <prober args...>: runs the prober against a fresh local simulator (never the Spread server)
cd "$(dirname "$0")/.." || exit 1
OUT=$1; shift; PORT=${PORT:-8787}
node sim/server.ts --port $PORT > /dev/null 2>&1 & SRV=$!
for i in $(seq 50); do curl -s -o /dev/null localhost:$PORT/v1/map && break; sleep 0.1; done
SPREAD_URL=http://localhost:$PORT SPREAD_KEY1=sim SPREAD_KEY2= node sim/prober.ts --out "$OUT" "$@"
kill $SRV
