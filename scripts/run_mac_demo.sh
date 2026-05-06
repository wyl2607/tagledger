#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"

open_demo_url() {
  if [ "$OPEN_BROWSER" = "1" ] && command -v open >/dev/null 2>&1; then
    open "http://127.0.0.1:${PORT}" >/dev/null 2>&1 || true
  fi
}

wait_and_open_demo_url() {
  if [ "$OPEN_BROWSER" != "1" ]; then
    return 0
  fi
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if "$VENV_PYTHON" - "$PORT" <<'PY'
import json
import sys
import urllib.request

port = int(sys.argv[1])
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
        sys.exit(0 if json.load(response).get("status") == "ok" else 1)
except Exception:
    sys.exit(1)
PY
    then
      open_demo_url
      return 0
    fi
    sleep 0.5
  done
  open_demo_url
}

port_has_this_app() {
  "$PYTHON_BIN" - "$PORT" <<'PY'
import json
import sys
import urllib.request

port = int(sys.argv[1])
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
        sys.exit(0 if json.load(response).get("status") == "ok" else 1)
except Exception:
    sys.exit(1)
PY
}

port_is_busy() {
  "$PYTHON_BIN" - "$PORT" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.2)
    sys.exit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
PY
}

if [ ! -x "$VENV_PYTHON" ]; then
  "$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
fi

"$VENV_PYTHON" -m pip install -e ".[dev]"

echo "Starting TagLedger macOS demo"
echo "Local demo: http://127.0.0.1:${PORT}"
echo "API docs:   http://127.0.0.1:${PORT}/docs"
echo "LAN demo:   HOST=0.0.0.0 PORT=${PORT} ./scripts/run_mac_demo.sh"
echo "Warning: HOST=0.0.0.0 exposes this demo to the local network."

if port_is_busy; then
  if port_has_this_app; then
    echo "Port ${PORT} is already running this demo. Opening it now."
    open_demo_url
  else
    echo "Port ${PORT} is already in use by another local service."
    echo "Start on another port: PORT=8010 ./scripts/run_mac_demo.sh"
  fi
  exit 0
fi

if [ "$OPEN_BROWSER" = "1" ]; then
  wait_and_open_demo_url >/dev/null 2>&1 &
fi

exec "$VENV_PYTHON" -m uvicorn backend.app.main:app --host "$HOST" --port "$PORT" --reload
