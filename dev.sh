#!/usr/bin/env bash
# Run the Next.js frontend and the Django backend together.
#
# Why: the frontend can start fine on its own, but with the backend down the
# app loads with an empty notebook list — which looks like data loss even
# though everything is safe in Postgres. Starting both together avoids that.
#
# Usage:  ./dev.sh   (or:  pnpm dev:all)

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Stop both servers when this script exits or is interrupted. Only our own
# children: `kill 0` would signal this script too, and the shell then
# reports the whole run as "Terminated" even after a clean Ctrl+C.
cleanup() {
  trap - EXIT INT TERM
  local pids
  pids="$(jobs -p)"
  [ -n "$pids" ] && kill $pids 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# A second copy (an old terminal, a forgotten background run) holds the
# ports; the new servers then fail to bind and the run ends at once. Say
# which process it is instead.
for port in 8000 3000; do
  if holder="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1)" && [ -n "$holder" ]; then
    echo "✗ Port $port is already in use by PID $holder: $(ps -o command= -p "$holder" | cut -c1-80)"
    echo "  Stop it first (kill $holder), or close the other dev:all window."
    exit 1
  fi
done

echo "→ Starting Django backend on http://localhost:8000 ..."
# uvicorn, not runserver: the group chat needs a server that speaks
# websockets, and Socket.IO is mounted on the same ASGI app.
( cd "$ROOT/backend" && ./venv/bin/uvicorn studyplatform.asgi:application --port 8000 --reload ) &

echo "→ Starting Next.js frontend on http://localhost:3000 ..."
( cd "$ROOT" && ./node_modules/.bin/next dev ) &

wait
