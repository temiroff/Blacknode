#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
BACKEND_PID=""
FRONTEND_PID=""
BACKEND_PORT=7777
FRONTEND_PORT=3000
EDITOR_URL="http://localhost:${FRONTEND_PORT}"

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
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$EDITOR_URL" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then
    open "$EDITOR_URL" >/dev/null 2>&1 &
  else
    echo "Open $EDITOR_URL in your browser."
  fi
}

port_pids() {
  local port="$1"

  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
    return
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :$port" 2>/dev/null |
      sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' |
      sort -u
    return
  fi

  if command -v netstat >/dev/null 2>&1; then
    netstat -ltnp 2>/dev/null |
      awk -v port=":$port" '$4 ~ port "$" && $7 ~ /^[0-9]+/ { split($7, parts, "/"); print parts[1] }' |
      sort -u
  fi
}

port_in_use() {
  [[ -n "$(port_pids "$1")" ]]
}

blacknode_editor_ready() {
  command -v curl >/dev/null 2>&1 &&
    curl -fsS --max-time 2 "$EDITOR_URL" 2>/dev/null |
      grep -q "<title>Blacknode</title>"
}

wait_blacknode_editor_ready() {
  local timeout="${1:-5}"
  local end=$((SECONDS + timeout))

  while (( SECONDS < end )); do
    if blacknode_editor_ready; then
      return 0
    fi
    sleep 0.5
  done

  return 1
}

wait_port_free() {
  local port="$1"
  local timeout="${2:-5}"
  local end=$((SECONDS + timeout))

  while (( SECONDS < end )); do
    if ! port_in_use "$port"; then
      return 0
    fi
    sleep 0.5
  done

  ! port_in_use "$port"
}

stop_port_listener() {
  local port="$1"
  local pids
  pids="$(port_pids "$port")"

  if [[ -z "$pids" ]]; then
    return 0
  fi

  while IFS= read -r pid; do
    if [[ -n "$pid" && "$pid" != "$$" ]]; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done <<< "$pids"
}

print_port_busy_error() {
  local port="$1"
  local pids
  pids="$(port_pids "$port" | paste -sd, -)"

  echo
  echo "  ERROR: Port $port is already in use by another app."
  if [[ -n "$pids" ]]; then
    echo
    echo "  Listening process id(s): $pids"
  fi
  echo "  Close that app or free port $port, then run ./start.sh again."
}

print_banner() {
  local cyan=""
  local reset=""

  if [[ -t 1 ]]; then
    cyan=$'\033[36m'
    reset=$'\033[0m'
  fi

  printf '\n'
  printf '%s  ██████╗ ██╗      █████╗  ██████╗██╗  ██╗███╗   ██╗ ██████╗ ██████╗ ███████╗%s\n' "$cyan" "$reset"
  printf '%s  ██╔══██╗██║     ██╔══██╗██╔════╝██║ ██╔╝████╗  ██║██╔═══██╗██╔══██╗██╔════╝%s\n' "$cyan" "$reset"
  printf '%s  ██████╔╝██║     ███████║██║     █████╔╝ ██╔██╗ ██║██║   ██║██║  ██║█████╗  %s\n' "$cyan" "$reset"
  printf '%s  ██╔══██╗██║     ██╔══██║██║     ██╔═██╗ ██║╚██╗██║██║   ██║██║  ██║██╔══╝  %s\n' "$cyan" "$reset"
  printf '%s  ██████╔╝███████╗██║  ██║╚██████╗██║  ██╗██║ ╚████║╚██████╔╝██████╔╝███████╗%s\n' "$cyan" "$reset"
  printf '%s  ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═════╝ ╚══════╝%s\n' "$cyan" "$reset"
  printf '\n'
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"

print_banner
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

stop_port_listener "$BACKEND_PORT"
wait_port_free "$BACKEND_PORT" || {
  print_port_busy_error "$BACKEND_PORT"
  exit 1
}

echo "  [1/2] Starting Python server  (http://127.0.0.1:$BACKEND_PORT)"
(cd "$ROOT_DIR/editor-server" && "$PYTHON_BIN" server.py) &
BACKEND_PID=$!

sleep 3

if port_in_use "$FRONTEND_PORT"; then
  if ! wait_blacknode_editor_ready; then
    print_port_busy_error "$FRONTEND_PORT"
    exit 1
  fi

  echo "  Stopping existing visual editor on port $FRONTEND_PORT..."
  stop_port_listener "$FRONTEND_PORT"
  if ! wait_port_free "$FRONTEND_PORT"; then
    print_port_busy_error "$FRONTEND_PORT"
    exit 1
  fi
fi

echo "  [2/2] Starting visual editor  ($EDITOR_URL)"
(cd "$ROOT_DIR/editor" && npm run dev -- --strictPort) &
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
