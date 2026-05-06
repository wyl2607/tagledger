#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BASE_REF="${1:-origin/main}"
BRANCH="$(git branch --show-current || true)"
REMOTE_URL="$(git remote get-url origin 2>/dev/null || echo '<no origin>')"

echo "=== review_push_guard: TagLedger ==="
echo "branch: ${BRANCH:-<detached>}"
echo "origin: $REMOTE_URL"
echo "base: $BASE_REF"

"$ROOT_DIR/scripts/security_check.sh"

if git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  echo "outgoing paths against $BASE_REF:"
  git diff --name-only "$BASE_REF"...HEAD | sed 's/^/  /'
else
  echo "base ref not found locally; validating current HEAD tree only"
fi

if git ls-tree -r --name-only HEAD | grep -E '(^|/)(\.omx|data/app\.db|data/storage_state\.json|data/backups|data/outbound|data/ocr-scratch|logs/|docs/private|docs/ops/private|PRIVATE_REQUIREMENTS|\.env($|\.))'; then
  echo "ERROR: HEAD contains forbidden publish paths" >&2
  exit 1
fi

echo "review_push_guard passed"
