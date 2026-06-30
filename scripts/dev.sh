#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"

if [[ ! -f ".env" && -f ".env.example" ]]; then
  cp ".env.example" ".env"
  echo "Created .env from .env.example"
fi

if [[ ! -d ".venv" ]]; then
  python -m venv .venv
  echo "Created Python virtual environment at .venv"
fi

# shellcheck disable=SC1091
source ".venv/bin/activate"
pip install -r requirements.txt

uvicorn app.main:app --reload --host 127.0.0.1 --port ${BACKEND_PORT:-8000} &
BACKEND_PID=$!

cd "$ROOT_DIR/frontend"
npm install
npm run dev -- --host 127.0.0.1 --port ${FRONTEND_PORT:-5173} &
FRONTEND_PID=$!

cat <<MSG

DeepAlpha development stack is starting:
- API: http://127.0.0.1:${BACKEND_PORT}
- Web: http://127.0.0.1:${FRONTEND_PORT}

Press Ctrl+C to stop both processes.
MSG

wait "$BACKEND_PID" "$FRONTEND_PID"
