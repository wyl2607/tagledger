# PyInstaller spec for the TagLedger backend sidecar (Windows, onedir).
# Run via: pyinstaller packaging/windows/tagledger_server.spec --noconfirm
# Produces: dist/tagledger-server/ (folder containing tagledger_server.exe + _internal/)

# ruff: noqa
from pathlib import Path

import PyInstaller.config

REPO_ROOT = Path(SPECPATH).resolve().parents[1].parent  # packaging/windows -> repo root
PyInstaller.config.CONF['workpath'] = str(REPO_ROOT / 'build' / 'pyinstaller')

# --- Bundled data ---
datas = [
    (str(REPO_ROOT / 'backend' / 'app' / 'static'), 'backend/app/static'),
    (str(REPO_ROOT / 'config'),                     'config'),
    (str(REPO_ROOT / 'alembic.ini'),                '.'),
    (str(REPO_ROOT / 'alembic'),                    'alembic'),
    # Vendored Tesseract (entire folder including tessdata/).
    (str(REPO_ROOT / 'packaging' / 'windows' / 'vendor' / 'tesseract'), 'tesseract'),
]

# --- Hidden imports (PyInstaller misses dynamic imports) ---
hiddenimports = [
    # uvicorn workers + lifespan
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    # SQLAlchemy SQLite dialect (Postgres pruned in requirements-runtime.txt)
    'sqlalchemy.dialects.sqlite',
    # Alembic env
    'alembic.runtime.migration',
    'alembic.script',
    # FastAPI/starlette dynamic
    'email.mime.multipart',
    'email.mime.text',
    # OCR/barcode
    'pytesseract',
    'pyzbar.pyzbar',
    'PIL.Image',
    'PIL.ImageOps',
]

# Pull in every backend.app.routes.* module so router includes don't dangle.
import importlib
import pkgutil
import sys
sys.path.insert(0, str(REPO_ROOT))
import backend.app.routes as routes_pkg
hiddenimports += [
    f'backend.app.routes.{m.name}' for m in pkgutil.iter_modules(routes_pkg.__path__)
]
import backend.app.workers as workers_pkg
hiddenimports += [
    f'backend.app.workers.{m.name}' for m in pkgutil.iter_modules(workers_pkg.__path__)
]
import backend.app.services as services_pkg
hiddenimports += [
    f'backend.app.services.{m.name}' for m in pkgutil.iter_modules(services_pkg.__path__)
]

# --- Excludes (keep bundle small) ---
excludes = [
    'tkinter',
    'matplotlib',
    'notebook',
    'IPython',
    'pytest',
    'tests',
    'psycopg',           # SQLite-only desktop build
    'psycopg2',
    'opencv',            # we use opencv-python-headless
]

a = Analysis(
    [str(REPO_ROOT / 'backend' / 'app' / 'cli.py')],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='tagledger_server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,            # keep console; launcher launches detached
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='tagledger-server',
)
