#!/bin/sh
# Records every message of the public final leaderboard (GET /v1/leaderboard, no key, free)
# to leaderboard.jsonl.gz, one JSON message per line, until the feed says "ended".
cd "$(dirname "$0")"
while :; do
  curl -sS -N --max-time 3600 "${SPREAD_URL:-https://spread.bahnexpress.com}/v1/leaderboard" \
    | sed -u -n 's/^data: //p' | while IFS= read -r line; do
        printf '%s\n' "$line" | gzip >> leaderboard.jsonl.gz
        printf '%s\n' "$line" > leaderboard.json
        case "$line" in '{"status":"ended"'*) exit 9;; esac
      done
  [ $? -eq 9 ] && break
  sleep 1
done
