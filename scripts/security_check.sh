#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== security_check: tracked file boundary ==="

forbidden_paths='(^|/)(\.omx|\.claude|\.venv|\.pytest_cache|\.ruff_cache|data/app\.db|data/storage_state\.json|data/backups|data/outbound|data/ocr-scratch|logs/|docs/private|docs/ops/private|PRIVATE_REQUIREMENTS|dist/|build/|.*\.egg-info/|__pycache__/|\.env($|\.))'
if matches=$(git ls-files | grep -E "$forbidden_paths"); then
  echo "ERROR: tracked forbidden paths:" >&2
  echo "$matches" >&2
  exit 1
fi

forbidden_content='(/Users/[^$<{/\\][^/\\[:space:]]*|/home/[^$<{/\\][^/\\[:space:]]*|C:[/\\]Users[/\\][^$<{/\\][^/\\[:space:]]*|192\.168\.)'
if matches=$(git ls-files -z | grep -z -v '^scripts/security_check\.sh$' | xargs -0 rg -n --hidden --glob '!*.png' --glob '!*.jpg' --glob '!*.jpeg' --glob '!*.webp' --glob '!*.pdf' "$forbidden_content"); then
  echo "ERROR: tracked forbidden local/private references:" >&2
  echo "$matches" >&2
  exit 1
fi

echo "security_check passed"
