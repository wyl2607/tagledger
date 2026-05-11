#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

check_contains() {
  local file="$1"
  local expected="$2"
  if ! grep -Fq "$expected" "$file"; then
    echo "UI contract missing: $file must contain: $expected" >&2
    return 1
  fi
}

check_contains "backend/app/static/portal.html" "先选岗位，再开工"
check_contains "backend/app/static/portal.html" 'href="/mobile"'
check_contains "backend/app/static/portal.html" 'href="/outbound"'
check_contains "backend/app/static/portal.html" 'href="/workbench"'
check_contains "backend/app/static/portal.html" 'href="/inbound"'
check_contains "backend/app/static/home.html" "现场调度台"
check_contains "backend/app/static/home.html" 'data-i18n="workbench.brand">现场调度台'
check_contains "backend/app/static/home.html" "renderModules(payload.modules || [])"
check_contains "backend/app/static/home.html" "payload.global_stats"
check_contains "backend/app/static/i18n/zh.json" '"workbench.brand": "现场调度台"'
check_contains "backend/app/static/inbound.html" "/api/outbound/inventory/inbound"
check_contains "backend/app/static/inbound.html" "采购入库"

echo "ui contracts: OK"
