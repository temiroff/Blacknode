#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/.local-logs"
SERVER_OUT="$LOG_DIR/server.out.log"
SERVER_ERR="$LOG_DIR/server.err.log"
EDITOR_OUT="$LOG_DIR/editor.out.log"
EDITOR_ERR="$LOG_DIR/editor.err.log"
PYTHON_BIN="${PYTHON:-}"
VENV_DIR="${BLACKNODE_VENV:-$ROOT_DIR/.venv}"
BACKEND_PID=""
FRONTEND_PID=""
BACKEND_PORT=7777
FRONTEND_PORT=3000
EDITOR_URL="http://localhost:${FRONTEND_PORT}"

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required. Install Node.js 20.19+ or 22.12+."
  exit 1
fi

resolve_system_python() {
  if [[ -n "$PYTHON_BIN" ]]; then
    if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
      return 0
    fi

    echo "ERROR: PYTHON points to '$PYTHON_BIN', but that command was not found."
    exit 1
  fi

  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "ERROR: Python 3.11+ is required."
    exit 1
  fi
}

assert_python_version() {
  if ! "$PYTHON_BIN" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
  then
    echo "ERROR: Python 3.11+ is required. Found: $("$PYTHON_BIN" --version 2>&1)"
    exit 1
  fi
}

ensure_python_environment() {
  resolve_system_python
  assert_python_version

  if [[ -n "${PYTHON:-}" ]]; then
    return
  fi

  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "  Creating Python virtual environment (.venv)..."
    if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
      echo
      echo "  ERROR: Could not create the Python virtual environment."
      echo "  On Ubuntu/Debian, install venv support and run ./start.sh again:"
      echo
      echo "    sudo apt install python3-venv"
      exit 1
    fi
  fi

  PYTHON_BIN="$VENV_DIR/bin/python"
  assert_python_version

  if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    echo "ERROR: pip is unavailable in $VENV_DIR."
    exit 1
  fi
}

process_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

assert_process_running() {
  local pid="$1"
  local name="$2"
  local error_log="$3"

  if process_running "$pid"; then
    return 0
  fi

  echo
  echo "  ERROR: $name stopped during startup."
  if [[ -f "$error_log" ]]; then
    echo
    echo "  Last log lines:"
    tail -n 30 "$error_log" | sed 's/^/  /'
  fi
  wait "$pid" >/dev/null 2>&1 || true
  exit 1
}

cleanup() {
  if [[ -n "$FRONTEND_PID" ]]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$BACKEND_PID" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}

open_browser() {
  if [[ "${BLACKNODE_NO_BROWSER:-}" == "1" ]]; then
    echo "  Browser launch skipped (BLACKNODE_NO_BROWSER=1)."
    return
  fi

  echo "  Opening browser..."
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$EDITOR_URL" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then
    open "$EDITOR_URL" >/dev/null 2>&1 &
  elif command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "$EDITOR_URL" >/dev/null 2>&1 &
  else
    echo "Open $EDITOR_URL in your browser."
  fi
}

pip_install() {
  PYTHONPATH= "$PYTHON_BIN" -m pip install "$@"
}

ensure_blacknode_command() {
  local cli="$VENV_DIR/bin/blacknode"
  local bin_dir="$HOME/.local/bin"
  local shim="$bin_dir/blacknode"

  if [[ -n "${PYTHON:-}" || "$PYTHON_BIN" != "$VENV_DIR/bin/python" || ! -x "$cli" ]]; then
    return
  fi

  mkdir -p "$bin_dir"
  if [[ -e "$shim" && ! -L "$shim" ]]; then
    echo "  Note: $shim already exists; leaving it unchanged."
    echo "  Project CLI is available at: $cli"
    return
  fi

  ln -sfn "$cli" "$shim"
  if [[ ":$PATH:" != *":$bin_dir:"* ]]; then
    echo "  Note: $bin_dir is not on PATH; add it to your shell profile to run 'blacknode'."
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
    cyan=$'\033[38;2;83;221;226m'
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

ensure_frontend_dependencies() {
  local editor_dir="$ROOT_DIR/editor"

  if [[ ! -d "$editor_dir/node_modules" ]]; then
    echo "  Installing frontend dependencies (first run, this can take a minute)..."
    (cd "$editor_dir" && npm install)
    return
  fi

  if ! (cd "$editor_dir" && node -e "import('vite').then(() => {}).catch(() => process.exit(1))" >/dev/null 2>&1); then
    echo "  Repairing frontend dependencies for this OS..."
    (cd "$editor_dir" && npm install)
  fi
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"
mkdir -p "$LOG_DIR"

print_banner
ensure_python_environment
echo "  Checking Python dependencies..."
pip_install -r "$ROOT_DIR/editor-server/requirements.txt" -q --disable-pip-version-check

if ! "$PYTHON_BIN" -c "import importlib.metadata; importlib.metadata.version('blacknode')" >/dev/null 2>&1; then
  echo "  Installing blacknode package for the CLI..."
  pip_install -e "$ROOT_DIR" -q --disable-pip-version-check
fi
ensure_blacknode_command

# Optional: install CuPy for the GPU/CUDA nodes when an NVIDIA GPU is present.
# macOS has no NVIDIA CUDA GPUs, so nvidia-smi is absent and this is skipped.
# Non-fatal: a failure here never blocks the editor.
if command -v nvidia-smi >/dev/null 2>&1; then
  if ! "$PYTHON_BIN" -c "import cupy" >/dev/null 2>&1; then
    echo "  NVIDIA GPU detected - installing CuPy for CUDA nodes (one-time, large download)..."
    pip_install cupy-cuda12x -q --disable-pip-version-check \
      || echo "  CuPy install failed; GPU/CUDA nodes stay unavailable but the editor will run."
  fi
fi

ensure_frontend_dependencies

echo "  Done."
echo

stop_port_listener "$BACKEND_PORT"
wait_port_free "$BACKEND_PORT" || {
  print_port_busy_error "$BACKEND_PORT"
  exit 1
}

echo "  [1/2] Starting Python server  (http://127.0.0.1:$BACKEND_PORT)"
rm -f "$SERVER_OUT" "$SERVER_ERR"
(cd "$ROOT_DIR/editor-server" && "$PYTHON_BIN" server.py) >"$SERVER_OUT" 2>"$SERVER_ERR" &
BACKEND_PID=$!

sleep 3
assert_process_running "$BACKEND_PID" "Python server" "$SERVER_ERR"

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
rm -f "$EDITOR_OUT" "$EDITOR_ERR"
(cd "$ROOT_DIR/editor" && npm run dev -- --strictPort) >"$EDITOR_OUT" 2>"$EDITOR_ERR" &
FRONTEND_PID=$!

sleep 5
assert_process_running "$FRONTEND_PID" "Visual editor" "$EDITOR_ERR"
echo
open_browser
echo
echo "  Logs: .local-logs/server.out.log and .local-logs/editor.out.log"
echo "  Press Ctrl+C to stop."

while true; do
  if ! process_running "$BACKEND_PID"; then
    wait "$BACKEND_PID"
    exit $?
  fi
  if ! process_running "$FRONTEND_PID"; then
    wait "$FRONTEND_PID"
    exit $?
  fi
  sleep 1
done
