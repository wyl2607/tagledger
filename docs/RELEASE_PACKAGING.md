# Release Packaging

Use the release scripts to create a sanitized source package that can be uploaded, downloaded, and installed later on macOS or Windows.

## What Is Included

- Backend source code.
- Static pages: capture, mobile, history, dashboard.
- Config files.
- Scripts for macOS and Windows startup.
- Documentation.
- Empty runtime directories:
  - `data/uploads/.gitkeep`
  - `data/screenshots/.gitkeep`
  - `logs/.gitkeep`

## What Is Excluded

- `.venv/`
- `.git/`
- `.omx/`
- `.env` and `.env.*`
- `data/app.db`
- `data/storage_state.json`
- uploaded photos under `data/uploads/`
- screenshots under `data/screenshots/`
- logs under `logs/`
- caches and build outputs

## Build On macOS

```bash
VERSION=0.1.0 ./scripts/make_release.sh
```

Output:

```text
dist/release/tagledger-0.1.0.zip
```

## Build On Windows

```powershell
$env:VERSION='0.1.0'
.\scripts\make_release.ps1
```

Output:

```text
dist\release\tagledger-0.1.0.zip
```

## Install From The Package

macOS:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev,barcode,ocr]"
PORT=8001 ./scripts/run_mobile_test.sh
```

Windows:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install_windows.ps1
.\scripts\run_dev.ps1
```

## OCR Notes

Tesseract is installed outside the release package.

- macOS: `brew install tesseract`
- Windows: https://github.com/UB-Mannheim/tesseract/wiki

The release package is a source package, not a single executable. A future PyInstaller package can be added later when the app interface and OCR dependencies stabilize.

## Desktop Launcher (M3)

Windows beta builds use a Tauri v2 launcher wrapped around the M2 PyInstaller onedir sidecar. Build the sidecar first, because the Tauri build fails if `dist/tagledger-server/tagledger_server.exe` is missing.

```powershell
pwsh -File packaging/windows/build_backend.ps1
cd desktop
npm install
```

Dev mode:

```powershell
npm run tauri dev
```

Release build:

```powershell
npm run tauri build
```

Outputs:

```text
desktop/src-tauri/target/release/bundle/msi/
desktop/src-tauri/target/release/bundle/nsis/
```

M3 is Windows-only and unsigned. macOS and Linux desktop bundles are intentionally out of scope for this beta.
