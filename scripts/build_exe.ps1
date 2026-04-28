$ErrorActionPreference = 'Stop'

# PyInstaller delivery skeleton for a future Windows .exe package.
# This is intentionally not part of the current v1 deployment path.
#
# Why onefile:
# - Produces one application executable that is easier for non-technical users to move.
#
# Why add-data:
# - Runtime config and the static demo page are external resources in development.
# - PyInstaller needs them bundled explicitly so the executable can find them.
#
# Why Tesseract is still separate:
# - pytesseract calls the native tesseract.exe binary.
# - Bundling Tesseract itself into onefile is brittle because it also needs traineddata
#   files and native runtime paths. For v3, require users to install Tesseract and add it
#   to PATH, or ship a managed installer that lays Tesseract down beside the app.
#
# Prerequisites for a future v3:
# .\.venv\Scripts\python.exe -m pip install pyinstaller
#
# Candidate command:
# .\.venv\Scripts\pyinstaller.exe --onefile `
#     --add-data "config;config" `
#     --add-data "backend/app/static;backend/app/static" `
#     backend/app/main.py

Write-Host 'PyInstaller skeleton only. Current Windows delivery is git clone/zip plus scripts.'
