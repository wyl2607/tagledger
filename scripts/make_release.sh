#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="machine-label-ocr"
VERSION="${VERSION:-$(date +%Y%m%d-%H%M%S)}"
BUILD_DIR="$ROOT_DIR/dist/release"
PACKAGE_DIR="$BUILD_DIR/${APP_NAME}-${VERSION}"
ZIP_PATH="$BUILD_DIR/${APP_NAME}-${VERSION}.zip"

mkdir -p "$BUILD_DIR"
rm -rf "$PACKAGE_DIR" "$ZIP_PATH"
mkdir -p "$PACKAGE_DIR"

rsync -a \
  --exclude '.git/' \
  --exclude '.omx/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '*.egg-info/' \
  --exclude 'build/' \
  --exclude 'dist/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.DS_Store' \
  --exclude 'data/app.db' \
  --exclude 'data/*.xlsx' \
  --exclude 'data/~$*.xlsx' \
  --exclude 'data/outbound/' \
  --exclude 'data/ocr-scratch/' \
  --exclude 'data/storage_state.json' \
  --exclude 'data/uploads/*' \
  --exclude 'data/screenshots/*' \
  --exclude 'logs/' \
  --include 'data/uploads/.gitkeep' \
  --include 'data/screenshots/.gitkeep' \
  ./ "$PACKAGE_DIR/"

mkdir -p "$PACKAGE_DIR/data/uploads" "$PACKAGE_DIR/data/screenshots" "$PACKAGE_DIR/logs"
touch "$PACKAGE_DIR/data/uploads/.gitkeep" "$PACKAGE_DIR/data/screenshots/.gitkeep" "$PACKAGE_DIR/logs/.gitkeep"

cat > "$PACKAGE_DIR/README_RELEASE.md" <<'EOF'
# Machine Label OCR Release Package

This is a sanitized source release. It does not include local databases, uploaded photos, screenshots, logs, `.env` files, virtual environments, or git/OMX metadata.

## macOS Quick Start

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev,barcode,ocr]"
PORT=8001 ./scripts/run_mobile_test.sh
```

Open:

```text
http://127.0.0.1:8001/
http://127.0.0.1:8001/mobile
http://127.0.0.1:8001/history
http://127.0.0.1:8001/dashboard
```

## Windows Quick Start

Open PowerShell in this folder:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install_windows.ps1
.\scripts\run_dev.ps1
```

Then open:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/mobile
http://127.0.0.1:8000/history
http://127.0.0.1:8000/dashboard
```

## OCR Dependencies

Install Tesseract separately:

- macOS: `brew install tesseract`
- Windows: https://github.com/UB-Mannheim/tesseract/wiki

Barcode support uses `pyzbar`; Windows wheels usually include the needed zbar DLL.
EOF

(
  cd "$BUILD_DIR"
  zip -qr "${APP_NAME}-${VERSION}.zip" "${APP_NAME}-${VERSION}"
)

echo "Release package created:"
echo "$ZIP_PATH"
echo
echo "Sanity check: release package must not contain sensitive local data."
if forbidden_entries=$(unzip -Z1 "$ZIP_PATH" | grep -E '(^|/)(\.git|\.omx)/|(^|/)data/app\.db|(^|/)data/storage_state\.json|(^|/)data/[^/]+\.xlsx|(^|/)data/outbound/|(^|/)data/ocr-scratch/|(^|/)data/uploads/.+\.(jpg|jpeg|png|webp)|(^|/)data/screenshots/.+\.(png|jpg|jpeg|txt)|(^|/)logs/.+\.log|(^|/)\.env($|\.)'); then
  echo "ERROR: release package contains forbidden entries:" >&2
  echo "$forbidden_entries" >&2
  exit 1
fi
echo "Sanity check passed."
