#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ "${1:-}" != "--yes" ]]; then
  cat <<'EOF'
Dry run only.

This removes local test data:
- data/app.db
- data/uploads/* except .gitkeep
- data/screenshots/* except .gitkeep
- logs/playwright.log

Run:
  ./scripts/reset_test_data.sh --yes
EOF
  exit 0
fi

rm -f data/app.db data/app.db-shm data/app.db-wal logs/playwright.log
find data/uploads -mindepth 1 ! -name .gitkeep -delete
find data/screenshots -mindepth 1 ! -name .gitkeep -delete

echo "Local test data reset."
