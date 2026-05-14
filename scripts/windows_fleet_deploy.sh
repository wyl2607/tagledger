#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_PARENT="$(dirname "$ROOT_DIR")"
REPO_NAME="$(basename "$ROOT_DIR")"

DEVICES_FILE="$ROOT_DIR/scripts/windows_fleet_devices.txt"
IDENTITY_FILE="${IDENTITY_FILE:-$HOME/.ssh/win_key}"
SERVICE_PORT="${SERVICE_PORT:-8000}"
SSH_PORT="${SSH_PORT:-22}"
CONNECT_TIMEOUT="${CONNECT_TIMEOUT:-10}"
RUN_INSTALL=1
KEEP_ARCHIVE=0
OPEN_ADMIN=0

usage() {
  cat <<'EOF_USAGE'
Usage:
  ./scripts/windows_fleet_deploy.sh [options]

Options:
  --devices <file>      Device list file (default: scripts/windows_fleet_devices.txt)
  --identity <path>     SSH private key path (default: ~/.ssh/win_key)
  --service-port <int>  TagLedger service port on Windows (default: 8000)
  --ssh-port <int>      SSH port (default: 22)
  --skip-install        Skip install_windows.ps1 (faster, use when deps unchanged)
  --open-admin          Open the Windows default browser to /admin after health passes
  --keep-archive        Keep local temp archive
  -h, --help            Show help

Device file format:
  target[|app_dir][|port]

Examples:
  operator@win-floor-01
  operator@win-floor-02|C:\TagLedger\app
  operator@win-floor-03||8010
EOF_USAGE
}

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: missing command '$1'" >&2
    exit 1
  fi
}

is_valid_port() {
  local value="$1"
  [[ "$value" =~ ^[0-9]+$ ]] && ((value >= 1 && value <= 65535))
}

while (($# > 0)); do
  case "$1" in
    --devices)
      if (($# < 2)); then
        echo "ERROR: --devices requires a file path" >&2
        exit 1
      fi
      DEVICES_FILE="$2"
      shift 2
      ;;
    --identity)
      if (($# < 2)); then
        echo "ERROR: --identity requires a file path" >&2
        exit 1
      fi
      IDENTITY_FILE="$2"
      shift 2
      ;;
    --service-port)
      if (($# < 2)); then
        echo "ERROR: --service-port requires an integer" >&2
        exit 1
      fi
      SERVICE_PORT="$2"
      shift 2
      ;;
    --ssh-port)
      if (($# < 2)); then
        echo "ERROR: --ssh-port requires an integer" >&2
        exit 1
      fi
      SSH_PORT="$2"
      shift 2
      ;;
    --skip-install)
      RUN_INSTALL=0
      shift
      ;;
    --open-admin)
      OPEN_ADMIN=1
      shift
      ;;
    --keep-archive)
      KEEP_ARCHIVE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown arg: $1" >&2
      usage
      exit 1
      ;;
  esac
done

require_cmd tar
require_cmd ssh
require_cmd scp
require_cmd git

if ! is_valid_port "$SERVICE_PORT"; then
  echo "ERROR: invalid --service-port: $SERVICE_PORT" >&2
  exit 1
fi

if ! is_valid_port "$SSH_PORT"; then
  echo "ERROR: invalid --ssh-port: $SSH_PORT" >&2
  exit 1
fi

if [[ ! -f "$DEVICES_FILE" ]]; then
  echo "ERROR: devices file not found: $DEVICES_FILE" >&2
  exit 1
fi

if [[ ! -f "$IDENTITY_FILE" ]]; then
  echo "ERROR: identity file not found: $IDENTITY_FILE" >&2
  exit 1
fi

if [[ ! -f "$ROOT_DIR/scripts/install_windows.ps1" ]]; then
  echo "ERROR: required file missing: scripts/install_windows.ps1" >&2
  exit 1
fi

if [[ ! -f "$ROOT_DIR/scripts/remote_start_tagledger.ps1" ]]; then
  echo "ERROR: required file missing: scripts/remote_start_tagledger.ps1" >&2
  exit 1
fi

echo "== TagLedger Windows Fleet Deploy =="
echo "repo: $ROOT_DIR"
echo "devices: $DEVICES_FILE"
echo "identity: $IDENTITY_FILE"
echo "service port: $SERVICE_PORT"
echo "run install: $RUN_INSTALL"
echo "open admin: $OPEN_ADMIN"
echo

TMP_DEPLOY_DIR="$(mktemp -d "${TMPDIR:-/tmp}/tagledger-fleet.XXXXXX")"
ARCHIVE_PATH="$TMP_DEPLOY_DIR/tagledger-fleet-$(date +%Y%m%d-%H%M%S).tgz"
cleanup() {
  if [[ "$KEEP_ARCHIVE" -eq 0 ]]; then
    rm -rf "$TMP_DEPLOY_DIR"
  else
    echo "archive kept at: $ARCHIVE_PATH"
  fi
}
trap cleanup EXIT

echo "Packing source archive..."
tar -czf "$ARCHIVE_PATH" \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='.omx' \
  --exclude='.claude' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.egg-info' \
  --exclude='dist' \
  --exclude='logs' \
  --exclude='data/app.db' \
  --exclude='data/outbound' \
  --exclude='data/ocr-scratch' \
  --exclude='data/storage_state.json' \
  --exclude='data/uploads/*' \
  --exclude='data/screenshots/*' \
  --exclude='.DS_Store' \
  -C "$REPO_PARENT" "$REPO_NAME"
echo "Archive ready: $ARCHIVE_PATH"
echo

SUCCESS=0
FAIL=0

ssh_base=(ssh -o BatchMode=yes -o ConnectTimeout="$CONNECT_TIMEOUT" -o StrictHostKeyChecking=accept-new -i "$IDENTITY_FILE" -p "$SSH_PORT")
scp_base=(scp -o BatchMode=yes -o ConnectTimeout="$CONNECT_TIMEOUT" -o StrictHostKeyChecking=accept-new -i "$IDENTITY_FILE" -P "$SSH_PORT")

while IFS= read -r raw || [[ -n "$raw" ]]; do
  line="$(trim "$raw")"
  if [[ -z "$line" || "${line:0:1}" == "#" ]]; then
    continue
  fi

  IFS='|' read -r target raw_app_dir raw_port <<<"$line"
  target="$(trim "$target")"
  app_dir="$(trim "${raw_app_dir:-}")"
  device_port="$(trim "${raw_port:-}")"

  if [[ -z "$target" ]]; then
    continue
  fi

  user="${target%@*}"
  if [[ "$user" == "$target" ]]; then
    echo "[$target] ERROR: target must include user@host"
    FAIL=$((FAIL + 1))
    continue
  fi

  if [[ -z "$device_port" ]]; then
    device_port="$SERVICE_PORT"
  fi
  if ! is_valid_port "$device_port"; then
    echo "[$target] ERROR: invalid service port: $device_port"
    FAIL=$((FAIL + 1))
    continue
  fi

  if [[ -z "$app_dir" ]]; then
    remote_profile="$("${ssh_base[@]}" "$target" "powershell -NoProfile -ExecutionPolicy Bypass -Command \"\$env:USERPROFILE\"" 2>/dev/null | tr -d '\r' | sed '/^[[:space:]]*$/d' | tail -n1 || true)"
    remote_profile="$(trim "$remote_profile")"
    if [[ -n "$remote_profile" ]]; then
      remote_profile="${remote_profile//\\//}"
      app_dir="${remote_profile}/tagledger"
    else
      app_dir="C:/Users/$user/tagledger"
    fi
  fi

  app_parent="$(printf '%s' "$app_dir" | sed -E 's#[/\\][^/\\]+$##')"
  remote_archive="$app_parent/tagledger-fleet-deploy.tgz"
  scp_archive_dest="/$(printf '%s' "$remote_archive" | sed 's#\\#/#g')"

  echo "[$target] Deploying..."

  if ! "${ssh_base[@]}" "$target" "hostname" >/dev/null; then
    echo "[$target] ERROR: ssh connectivity failed"
    FAIL=$((FAIL + 1))
    continue
  fi

  if ! "${ssh_base[@]}" "$target" "powershell -NoProfile -ExecutionPolicy Bypass -Command \"New-Item -ItemType Directory -Force -Path '$app_dir' | Out-Null; New-Item -ItemType Directory -Force -Path '$app_parent' | Out-Null\""; then
    echo "[$target] ERROR: failed to ensure app directory"
    FAIL=$((FAIL + 1))
    continue
  fi

  if ! "${scp_base[@]}" "$ARCHIVE_PATH" "$target:$scp_archive_dest" >/dev/null; then
    echo "[$target] ERROR: upload failed"
    FAIL=$((FAIL + 1))
    continue
  fi

  if ! "${ssh_base[@]}" "$target" "powershell -NoProfile -ExecutionPolicy Bypass -Command \"tar -xzf '$remote_archive' -C '$app_parent'\""; then
    echo "[$target] ERROR: extract failed"
    FAIL=$((FAIL + 1))
    continue
  fi

  if [[ "$RUN_INSTALL" -eq 1 ]]; then
    if ! "${ssh_base[@]}" "$target" "powershell -NoProfile -ExecutionPolicy Bypass -File '$app_dir\\scripts\\install_windows.ps1'"; then
      echo "[$target] ERROR: install failed"
      FAIL=$((FAIL + 1))
      continue
    fi
  fi

  open_arg=""
  if [[ "$OPEN_ADMIN" -eq 1 ]]; then
    open_arg=" -OpenPath '/admin'"
  fi

  start_output="$(${ssh_base[@]} "$target" "powershell -NoProfile -ExecutionPolicy Bypass -Command \"Set-Location -LiteralPath '$app_dir'; & '.\\scripts\\remote_start_tagledger.ps1' -Port $device_port -DetachedTask$open_arg\"" 2>&1 || true)"
  if [[ "$start_output" != *"PID="* ]]; then
    echo "[$target] ERROR: start failed"
    echo "$start_output"
    FAIL=$((FAIL + 1))
    continue
  fi
  echo "$start_output"

  health_ok=0
  for _ in $(seq 1 30); do
    if "${ssh_base[@]}" "$target" "powershell -NoProfile -ExecutionPolicy Bypass -Command \"if ((Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:$device_port/health' -TimeoutSec 4).StatusCode -ne 200) { exit 1 }\"" >/dev/null 2>&1; then
      health_ok=1
      break
    fi
    sleep 1
  done
  if [[ "$health_ok" -ne 1 ]]; then
    echo "[$target] ERROR: health check failed"
    FAIL=$((FAIL + 1))
    continue
  fi

  host="${target#*@}"
  echo "[$target] OK  http://$host:$device_port/mobile"
  if [[ "$OPEN_ADMIN" -eq 1 ]]; then
    echo "[$target] ADMIN  http://$host:$device_port/admin"
  fi
  SUCCESS=$((SUCCESS + 1))
done < "$DEVICES_FILE"

echo
echo "Deploy summary: success=$SUCCESS fail=$FAIL"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
