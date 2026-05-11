#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== preflight: tagledger ==="

# 1. ruff lint
echo ""
echo "[1/3] ruff lint ..."
if [ -d "$PROJECT_DIR/.venv" ]; then
    RUFF="$PROJECT_DIR/.venv/bin/ruff"
else
    RUFF="ruff"
fi
if command -v "$RUFF" &>/dev/null; then
    "$RUFF" check "$PROJECT_DIR/backend" --select E,F,B,I --ignore E501
    echo "ruff: OK"
else
    echo "ruff not installed, skipping (pip install ruff)"
fi

# 2. UI contract smoke
echo ""
echo "[2/4] ui contracts ..."
bash "$PROJECT_DIR/scripts/check_ui_contracts.sh"

# 3. pytest
echo ""
echo "[3/4] pytest ..."
if [ -d "$PROJECT_DIR/.venv" ]; then
    "$PROJECT_DIR/.venv/bin/python" -m pytest "$PROJECT_DIR/backend/tests" -v
else
    python3 -m pytest "$PROJECT_DIR/backend/tests" -v
fi

# 4. basic import check
echo ""
echo "[4/4] import check ..."
if [ -d "$PROJECT_DIR/.venv" ]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi
$PYTHON -c "
from backend.app.main import app
from backend.app.models import Record, RecordStatus, Category
from backend.app.schemas import (
    UploadResponse, ConfirmRequest, ConfirmResponse,
    RecordRead, RecordListItem, RetryResponse,
)
print('All imports OK')
print(f'Routes: {len(app.routes)} registered')
"

echo ""
echo "=== preflight: PASSED ==="
