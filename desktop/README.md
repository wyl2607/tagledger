# TagLedger Desktop Launcher

Windows beta launcher for the PyInstaller sidecar created by M2.

Build the backend bundle first:

```powershell
pwsh -File packaging/windows/build_backend.ps1
```

Then install launcher dependencies:

```powershell
cd desktop
npm install
```

Run the Tauri dev launcher:

```powershell
npm run tauri dev
```

Build unsigned beta installers:

```powershell
npm run tauri build
```

The build expects `dist/tagledger-server/tagledger_server.exe` at the repository root and bundles the full `dist/tagledger-server` onedir as a Tauri resource.
