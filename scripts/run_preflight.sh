#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== preflight: machine-label-ocr ==="

# 1. pytest
echo ""
echo "[1/2] pytest ..."
if [ -d "$PROJECT_DIR/.venv" ]; then
    "$PROJECT_DIR/.venv/bin/python" -m pytest "$PROJECT_DIR/backend/tests" -v
else
    python3 -m pytest "$PROJECT_DIR/backend/tests" -v
fi

# 2. basic import check (does the app load without crashing?)
echo ""
echo "[2/2] import check ..."
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
