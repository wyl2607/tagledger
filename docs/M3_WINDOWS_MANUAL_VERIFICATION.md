# M3 Windows Manual Verification Checklist

Status: partial — item 1 confirmed; item 4 has Android LAN/browser evidence but still needs QR and final UI-upload confirmation; items 2–3 still pending
Branch: `codex/desktop-beta-m1-lan-guard`
Commits: 2f62c4c, 8cafecd, 97b6d14, 9167fc8, d35a6c6
Verification mode: lightweight screen-share — Codex pulls Windows screenshots + sends remote clicks; Android checks use ADB + scrcpy + Chrome DevTools.

This checklist tracks the four items that could not be verified via SSH during the M3 smoke run. All four must be confirmed on a physical Windows machine before pushing the branch to remote, opening a PR, or shipping the beta installer.

## How to run

1. Install the M3 NSIS or MSI bundle on a Windows 10/11 machine with WebView2 runtime present.
2. Walk through each section below; tick boxes as items pass.
3. If any item fails, do not push. Capture screenshots / log lines, file an issue, fix on `codex/desktop-beta-m1-lan-guard`, re-run M3 smoke, then return here.

## 1. Console / window flash on launch — PASS (2026-05-08)

- [x] Launcher started via scheduled task; screenshot shows the launcher window with QR + LAN IP, no transient `tagledger_server` console
- [x] `tagledger-launcher.exe` window is the only visible window for the app stack (the black cmd visible in capture is the screenshot scheduler itself, not the sidecar)
- [x] `CREATE_NO_WINDOW` confirmed effective — `tagledger_server.exe` runs windowless

Note: cold-boot triple-launch repeat deferred; behaviour stable across the two interactive launches done during single-instance check.

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

Evidence gathered on 2026-05-08:

- Windows launcher showed a private LAN URL and the sidecar accepted LAN mobile traffic.
- Android Chrome on the OnePlus device opened the LAN URL after pairing regeneration and reached `/mobile#capture`.
- Pairing, auth setup/session cookie, CSRF headers, `/upload`, `/jobs/{id}`, and Tesseract OCR were exercised from the Android Chrome session; the backend returned `ocr_done` for a mobile-origin upload.
- The phone browser could invoke the Android camera and system gallery from the mobile capture page.
- `9167fc8` improved the mobile capture layout and `d35a6c6` records the Pixel/OPPO viewport baseline in `docs/UI_REVAMP_NOTES.md`.

Remaining item 4 work:

- Re-test from the launcher QR itself, not an ADB-opened URL.
- Use a clean single browser tab; old local dev TagLedger tabs caused Android to return selected images to the wrong tab during earlier tests.
- Confirm the final visible UI path: select/capture photo -> sticky "上传并识别" appears -> tap upload -> edit/review screen appears -> uploaded file is present under `%APPDATA%\TagLedger\uploads`.

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
