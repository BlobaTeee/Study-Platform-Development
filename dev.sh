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

# Kill both child processes when this script exits or is interrupted.
cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "→ Starting Django backend on http://localhost:8000 ..."
( cd "$ROOT/backend" && ./venv/bin/python manage.py runserver 8000 ) &

echo "→ Starting Next.js frontend on http://localhost:3000 ..."
( cd "$ROOT" && ./node_modules/.bin/next dev ) &

wait
