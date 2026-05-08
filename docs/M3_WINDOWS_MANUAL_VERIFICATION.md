# M3 Windows Manual Verification Checklist

Status: pending physical-machine validation
Branch: `codex/desktop-beta-m1-lan-guard`
Commit: 2f62c4c (feat(desktop): add Windows Tauri launcher for beta sidecar)

This checklist tracks the four items that could not be verified via SSH during the M3 smoke run. All four must be confirmed on a physical Windows machine before pushing the branch to remote, opening a PR, or shipping the beta installer.

## How to run

1. Install the M3 NSIS or MSI bundle on a Windows 10/11 machine with WebView2 runtime present.
2. Walk through each section below; tick boxes as items pass.
3. If any item fails, do not push. Capture screenshots / log lines, file an issue, fix on `codex/desktop-beta-m1-lan-guard`, re-run M3 smoke, then return here.

## 1. Console / window flash on launch

- [ ] Double-click the installed shortcut from a clean cold-boot session
- [ ] No black console window flashes during startup (the launcher window should appear without any preceding terminal flicker)
- [ ] Repeat the launch twice more to confirm consistency

Failure mode signal: `tagledger-launcher.exe` was built without `windows_subsystem = "windows"`, or the sidecar's PyInstaller config is leaking a console.

## 2. "Open data directory" / "Open log directory" buttons

- [ ] Click the Open Data Directory button — Explorer opens at the data dir, no shell ACL prompt
- [ ] Click the Open Log Directory button — Explorer opens at the log dir, no error
- [ ] Confirm the underlying paths exist and contain expected files (runtime port/pid/pair_token, recent log file)

Failure mode signal: Tauri capabilities (`desktop/src-tauri/capabilities/default.json`) missing the `shell:allow-open` scope, or the path is computed under `Program Files` where User-mode lacks read access.

## 3. Graceful shutdown

- [ ] Click the in-app Stop button — launcher window stays, sidecar process exits within 5s
- [ ] Confirm Task Manager shows zero `tagledger_server.exe` processes after Stop
- [ ] Click the X button on the launcher window — both launcher and sidecar exit cleanly
- [ ] Re-launch — single-instance still works, no zombie sidecar from previous session

Failure mode signal: missing `Drop` impl on the sidecar handle, or sidecar receiving SIGTERM equivalent without flush.

## 4. Mobile QR -> /mobile photo upload

- [ ] Launcher displays a QR code with the LAN URL
- [ ] Phone (same Wi-Fi) scans the QR and opens the URL in mobile browser
- [ ] `/mobile` page loads, capture photo flow works end-to-end (front camera permission prompt -> capture -> upload)
- [ ] Uploaded photo appears in the launcher's data dir

Failure mode signal: `TAGLEDGER_ALLOWED_HOSTS` rejecting the LAN IP, mobile browser blocking insecure context for camera (HTTP without localhost), or pairing token mismatch.

## After all four pass

```bash
cd ~/tagledger
git push origin codex/desktop-beta-m1-lan-guard

gh pr create \
  --base main \
  --head codex/desktop-beta-m1-lan-guard \
  --title "feat(desktop): Windows Tauri launcher for beta sidecar (M3)" \
  --body-file docs/M3_WINDOWS_MANUAL_VERIFICATION.md
```

Do not push to `main` directly. Do not skip this checklist.
