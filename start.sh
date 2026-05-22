#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
BACKEND_PID=""
FRONTEND_PID=""

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "ERROR: Python 3.11+ is required."
    exit 1
  fi
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required. Install Node.js 20.19+ or 22.12+."
  exit 1
fi

cleanup() {
  if [[ -n "$FRONTEND_PID" ]]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$BACKEND_PID" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}

open_browser() {
  local url="http://localhost:3000"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 &
  else
    echo "Open $url in your browser."
  fi
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"

echo
echo "  BLACKNODE"
echo
echo "  Checking Python dependencies..."
"$PYTHON_BIN" -m pip install -r "$ROOT_DIR/editor-server/requirements.txt" -q --disable-pip-version-check

if ! "$PYTHON_BIN" -c "import importlib.metadata; importlib.metadata.version('blacknode')" >/dev/null 2>&1; then
  echo "  Installing blacknode package for the CLI..."
  "$PYTHON_BIN" -m pip install -e "$ROOT_DIR" -q --disable-pip-version-check
fi

if [[ ! -d "$ROOT_DIR/editor/node_modules" ]]; then
  echo "  Installing frontend dependencies (first run, this can take a minute)..."
  (cd "$ROOT_DIR/editor" && npm install)
fi

echo "  Done."
echo

echo "  [1/2] Starting Python server  (http://127.0.0.1:7777)"
(cd "$ROOT_DIR/editor-server" && "$PYTHON_BIN" server.py) &
BACKEND_PID=$!

sleep 3

echo "  [2/2] Starting visual editor  (http://localhost:3000)"
(cd "$ROOT_DIR/editor" && npm run dev) &
FRONTEND_PID=$!

sleep 5
echo
echo "  Opening browser..."
open_browser
echo
echo "  Both processes are running. Press Ctrl+C to stop them."

while true; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    wait "$BACKEND_PID"
    exit $?
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    wait "$FRONTEND_PID"
    exit $?
  fi
  sleep 1
done
