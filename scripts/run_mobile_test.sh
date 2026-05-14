#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"
RELOAD="${RELOAD:-0}"
TAGLEDGER_PAIRING_ENABLED="${TAGLEDGER_PAIRING_ENABLED:-0}"
export TAGLEDGER_PAIRING_ENABLED

find_lan_ip() {
  if command -v ifconfig >/dev/null 2>&1; then
    for interface in en0 en1; do
      local ip
      ip="$(ifconfig "$interface" 2>/dev/null | awk '/inet / && $2 !~ /^127\./ && $2 !~ /^169\.254\./ { print $2; exit }')"
      if [ -n "$ip" ]; then
        printf '%s\n' "$ip"
        return 0
      fi
    done
  fi

  if command -v ipconfig >/dev/null 2>&1; then
    for interface in en0 en1; do
      local ip
      ip="$(ipconfig getifaddr "$interface" 2>/dev/null || true)"
      if [ -n "$ip" ]; then
        printf '%s\n' "$ip"
        return 0
      fi
    done
  fi

  if command -v ifconfig >/dev/null 2>&1; then
    ifconfig | awk '
      /^[a-z0-9]+:/ {
        interface = $1
        sub(":", "", interface)
        skip = interface ~ /^(lo|utun|bridge|awdl|llw|gif|stf|anpi|ap)[0-9]*/
      }
      !skip && /inet / && $2 !~ /^127\./ && $2 !~ /^169\.254\./ && $2 !~ /^100\./ { print $2; exit }
    '
    return 0
  fi

  printf '127.0.0.1\n'
}

healthcheck() {
  "$VENV_PYTHON" - "$PORT" <<'PY'
import json
import sys
import urllib.error
import urllib.request

port = int(sys.argv[1])
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
        if json.load(response).get("status") != "ok":
            sys.exit(1)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/outbound/summary", timeout=0.5):
            sys.exit(0)
    except urllib.error.HTTPError as exc:
        sys.exit(1 if exc.code == 404 else 0)
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

print_urls() {
  local lan_ip="$1"
  cat <<EOF
TagLedger factory LAN server

Center entry:
  http://${lan_ip}:${PORT}/

Phone picking:
  http://${lan_ip}:${PORT}/mobile

History:
  http://${lan_ip}:${PORT}/history

Runtime status:
  http://${lan_ip}:${PORT}/runtime/status

Local fallback:
  http://127.0.0.1:${PORT}/
  http://127.0.0.1:${PORT}/mobile

Pairing guard:
  TAGLEDGER_PAIRING_ENABLED=${TAGLEDGER_PAIRING_ENABLED}
  Set TAGLEDGER_PAIRING_ENABLED=1 to require phone pairing cookies.

If iPhone cannot open it, confirm both devices are on the same Wi-Fi and allow incoming connections for Python/uvicorn in macOS firewall.
EOF
}

if [ ! -x "$VENV_PYTHON" ]; then
  "$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
fi

if ! "$VENV_PYTHON" -c "import importlib.metadata as m; m.version('tagledger')" >/dev/null 2>&1; then
  echo "Installing local package: pip install -e .[dev]"
  "$VENV_PYTHON" -m pip install -e ".[dev]"
fi

LAN_IP="$(find_lan_ip)"

if port_is_busy; then
  if healthcheck; then
    print_urls "$LAN_IP"
    echo
    echo "Port ${PORT} is already running this app."
    exit 0
  fi
  echo "Port ${PORT} is already in use by another service."
  echo "It may be an older TagLedger process if /api/outbound/summary returns 404."
  echo "Try: PORT=8010 ./scripts/run_mobile_test.sh"
  exit 1
fi

print_urls "$LAN_IP"
echo
echo "Starting uvicorn on ${HOST}:${PORT}"
if [ "$RELOAD" = "1" ]; then
  exec "$VENV_PYTHON" -m uvicorn backend.app.main:app --host "$HOST" --port "$PORT" --reload
fi
exec "$VENV_PYTHON" -m uvicorn backend.app.main:app --host "$HOST" --port "$PORT"
