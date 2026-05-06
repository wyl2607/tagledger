# Windows Deploy

This guide covers the current Windows delivery path for TagLedger.

## Cross-Platform Review

Backend code uses `pathlib` for project-relative files, uploads, screenshots, static files, and config loading. No backend business-code change was required for Windows packaging.

Observed platform assumptions:

- `scripts/run_mac_demo.sh` and `scripts/smoke_mac_demo.sh` are macOS/Linux shell scripts with `#!/usr/bin/env bash`, `.venv/bin/python`, `python3`, and macOS `open`.
- `MAC_DEMO.md` and the macOS README section use generic POSIX paths, Homebrew, `.venv/bin/pip`, and `brew install zbar tesseract`.
- Windows entrypoints must use `.venv\Scripts\...` and PowerShell activation.
- Tesseract is discovered through PATH by `pytesseract`; Windows users must install Tesseract and add its install directory to PATH.
- `pyzbar` depends on zbar. On Windows, the wheel usually includes the zbar DLL, so `pip install pyzbar` is normally enough.
- `backend/tests/test_tesseract_provider.py` tries macOS fonts first for a generated test image, then falls back to Pillow's default font. This is test-only and not part of deployment.
- `backend/app/database.py` converts SQLite paths with `Path.as_posix()` for the SQLAlchemy URL. This is intentional and works with SQLite URLs.

## Prerequisites

- Windows 10 or newer with PowerShell.
- Python 3.12 or newer from Microsoft Store or python.org.
- Git for Windows from https://git-scm.com/download/win.
- Tesseract for Windows from https://github.com/UB-Mannheim/tesseract/wiki.

After installing Tesseract, add its install directory to PATH. The usual path is:

```powershell
C:\Program Files\Tesseract-OCR
```

Open a new PowerShell window and verify:

```powershell
tesseract --version
```

## zbar / pyzbar

Barcode and QR detection uses `pyzbar`. On Windows, the pyzbar wheel usually ships with the required zbar DLL, so this is normally enough:

```powershell
pip install pyzbar
```

The project install script installs the barcode extra automatically.

## Get The Code

Clone from Git:

```powershell
git clone https://github.com/wyl2607/tagledger.git
cd tagledger
```

Or download and unzip a release/source zip, then `cd` into the extracted folder.

## One-Command Install

Run from the project root:

```powershell
.\scripts\install_windows.ps1
```

If PowerShell blocks local scripts, run this once for the current shell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then rerun the install script.

## Start The API

```powershell
.\scripts\run_dev.ps1
```

The script activates `.venv`, installs the local package if needed, starts uvicorn on port `8000`, and prints local/LAN URLs.

Open on the Windows host:

```text
http://127.0.0.1:8000/docs
```

## LAN Access

To access from a phone or another machine on the same network:

1. Allow inbound TCP port `8000` in Windows Defender Firewall.
2. Find the Windows host IPv4 address:

```powershell
ipconfig
```

3. Open:

```text
http://<Windows-IPv4>:8000
```

`run_dev.ps1` also prints a likely LAN URL using `Get-NetIPAddress`.

## Switch To Real OCR

Edit `config\settings.yaml`:

```yaml
app:
  ocr_provider: tesseract
```

Restart `.\scripts\run_dev.ps1` after changing config.

## Troubleshooting

### Tesseract Not Found

Symptom: OCR fails with a Tesseract executable error, or `tesseract --version` fails.

Fix:

- Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki.
- Add `C:\Program Files\Tesseract-OCR` to PATH.
- Open a new PowerShell window.
- Run `tesseract --version`.

### pyzbar Import Error

Symptom: barcode detection is skipped or `import pyzbar` fails.

Fix:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[barcode]"
.\.venv\Scripts\python.exe -c "import pyzbar"
```

On Windows, pyzbar usually includes the zbar DLL. If a DLL error still appears, reinstall inside a fresh `.venv`.

### Port 8000 In Use

Symptom: uvicorn reports that port `8000` is already in use.

Fix: stop the other process or edit `scripts\run_dev.ps1` temporarily to use another port.

To inspect listeners:

```powershell
netstat -ano | findstr :8000
```

### Firewall Blocks LAN Access

Symptom: `127.0.0.1` works on the Windows host, but another device cannot connect.

Fix: add an inbound Windows Defender Firewall rule for TCP port `8000`, and make sure both devices are on the same LAN.

## Future Delivery Modes

- v1: `git clone` or zip checkout plus PowerShell scripts. This is the current path.
- v2: user downloads a zip package, preferably a GitHub release artifact with source, scripts, and config.
- v3: PyInstaller `.exe`. See `scripts\build_exe.ps1` for the commented skeleton. Tesseract should still be installed separately or handled by a dedicated installer.
