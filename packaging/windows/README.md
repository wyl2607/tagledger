# Windows Packaging (M2)

Produces `dist/tagledger-server/` — a PyInstaller onedir bundle containing the
FastAPI sidecar plus a vendored Tesseract OCR runtime. Consumed by the M3 Tauri
launcher and the M4 GitHub Actions release workflow.

## Layout
```
packaging/windows/
├── build_backend.ps1        # one-shot: vendor + venv + pyinstaller + smoke
├── vendor_tesseract.ps1     # downloads Tesseract + chi_sim/eng tessdata
├── tagledger_server.spec    # PyInstaller spec (onedir)
├── vendor/                  # gitignored; populated by vendor_tesseract.ps1
└── README.md
```

## Local build (Windows host)
```powershell
pwsh -File packaging/windows/build_backend.ps1
```

Requires: Python 3.12+, Chocolatey (or pass `-UseExisting` to vendor script).

## Output
- `dist/tagledger-server/tagledger_server.exe` — sidecar entrypoint (calls `backend.app.cli:main`)
- `dist/tagledger-server/_internal/` — Python runtime + bundled deps + Tesseract

The M3 launcher invokes `tagledger_server.exe --host 0.0.0.0 --port 0 --data-dir <user>`.

## Why onedir, not onefile
- Faster cold start (no per-launch unpack to temp).
- Smaller AV false-positive surface (PyInstaller onefile triggers Defender heuristics more often).
- Easier Tauri sidecar packaging (whole folder shipped as a resource).
