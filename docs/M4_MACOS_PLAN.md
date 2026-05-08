# M4-A: macOS Launcher Plan

Status: design + scaffold (this branch). Implementation split into A.1 (this branch — code cross-platform clean), A.2 (PyInstaller mac sidecar + bundle wiring), A.3 (ad-hoc signed `.app` smoke).

Branch: `codex/desktop-m4-macos-launcher` (based on `codex/desktop-beta-m1-lan-guard` because M3 launcher source has not yet merged to `main`; will rebase onto `main` once M3 PR lands).

## Goal

Ship the same Tauri launcher on macOS so an end user can open a `.app`, see the QR pairing window, and have the PyInstaller sidecar managed by the launcher — at parity with the M3 Windows behaviour. M4-A scope ends at "developer-machine smoke passes with ad-hoc signature"; Apple Developer ID signing + notarisation + auto-update belong to M4-C / M4-B.

## Context

- M3 already produces a working Windows launcher (NSIS + MSI bundles, ~75–106 MB).
- The Rust code in `desktop/src-tauri/src/sidecar.rs` was already mostly cross-platform: `data_dir()`, `kill_pid()`, `CREATE_NO_WINDOW` were gated with `#[cfg(windows)]` / `#[cfg(not(windows))]`.
- The two real cross-platform leaks were:
  1. `build.rs` hard-failed when `dist/tagledger-server/tagledger_server.exe` was missing — Windows-only.
  2. `sidecar_exe()` joined `tagledger_server.exe` and looked under `dist/` only.
- Both are now gated. macOS path resolves to `dist-macos/tagledger-server/tagledger_server`.

## Constraints

- Must not regress the M3 Windows build. Cargo / cfg gates keep Windows code paths byte-identical.
- No Apple Developer ID work in M4-A. Ad-hoc signing only (`codesign -s -`); user will see Gatekeeper warning on first launch.
- No auto-update infrastructure (Tauri updater plugin) — that's M4-B.
- `tauri.conf.json` `bundle.targets` keeps `nsis`, `msi` only on this branch. Adding `app`, `dmg` is deferred to M4-A.2 once a real macOS PyInstaller binary exists, to avoid build failures on unsuspecting machines.
- `bundle.macOS` config (minimumSystemVersion, signingIdentity, entitlements) deferred to M4-A.2.

## Done criteria (M4-A.1 — this branch)

- [x] `cargo check --manifest-path desktop/src-tauri/Cargo.toml` passes on macOS (aarch64-apple-darwin) with only the known `tauri-plugin-shell::open` deprecation warning.
- [x] `desktop/src-tauri/src/sidecar.rs` resolves the sidecar binary by `cfg(target_os)`: `tagledger_server.exe` under `dist/` on Windows, `tagledger_server` under `dist-macos/` on macOS.
- [x] `desktop/src-tauri/build.rs` enforces sidecar presence on Windows (panic with build hint) and warns on macOS until M4-A.2 lands.
- [x] No changes to backend/, scripts/, CI, or anything outside `desktop/src-tauri/` and this doc.
- [x] Single commit on `codex/desktop-m4-macos-launcher` with conventional message.
- [x] Plan document exists with Goal / Context / Constraints / Done criteria / Acceptance gates / Risks.

## Acceptance gates (M4-A.2 — next branch slice)

Red-before-green tests to write before implementation:

1. **Sidecar binary exists**: `test -x dist-macos/tagledger-server/tagledger_server` after running `packaging/macos/build_backend.sh`. Currently red (script doesn't exist).
2. **Bundle resolves on macOS**: `npm run tauri build -- --bundles app` produces `desktop/src-tauri/target/release/bundle/macos/TagLedger.app/Contents/Resources/tagledger-server/tagledger_server`. Currently red.
3. **App launches windowless sidecar**: launching `TagLedger.app` writes `~/Library/Application Support/TagLedger/runtime/{port,pid,pair_token}` within 5s and `curl http://127.0.0.1:$port/health` returns `{"status":"ok"}`. Currently red.
4. **Single-instance**: launching `TagLedger.app` twice keeps exactly one launcher PID and one `tagledger_server` PID. Currently red.
5. **Graceful shutdown**: clicking Stop in the launcher exits the sidecar within 5s and `pgrep tagledger_server` returns nothing. Currently red.

## Acceptance gates (M4-A.3 — smoke + ad-hoc sign)

6. **Ad-hoc signed app passes Gatekeeper assess**: `spctl -a -t exec -vv TagLedger.app` reports `accepted` (or `rejected source=no usable signature` is acceptable for ad-hoc; `valid on disk` from `codesign -dv` is the real bar).
7. **Cold-boot launch produces no crash log**: no entries in `~/Library/Logs/DiagnosticReports/` matching `TagLedger-*` or `tagledger_server-*` after first launch.
8. **Open Data Dir / Open Log Dir buttons open Finder at correct paths**: `~/Library/Application Support/TagLedger/` and `~/Library/Application Support/TagLedger/logs/` respectively (Tauri-plugin-shell `open()` calls macOS `open` which delegates to Finder).
9. **Mobile QR end-to-end** parity with Windows item 4: phone scans QR → `/mobile` loads → photo upload arrives in launcher data dir.

## Risks

| Risk | Mitigation |
|---|---|
| Tauri-plugin-shell `open()` is deprecated; the recommended replacement is tauri-plugin-opener | Track in M4-A.2; one-line swap, lower priority than mac sidecar |
| `bundle.resources` is a single map; cannot scope by target_os in current Tauri v2 schema | M4-A.2 will produce `dist-macos/tagledger-server/` placeholder via the build script; or split via `bundle.windows.resources` / `bundle.macOS.resources` if the schema supports per-platform overrides (verify in M4-A.2) |
| PyInstaller on macOS produces architecture-specific binaries (arm64 vs x86_64); universal2 needs both compiled and `lipo`'d | M4-A.2 default: arm64-only first (matches user's Mac); universal2 deferred to M4-A.4 if needed |
| Gatekeeper will block first launch on user machines without right-click → Open dance | Explicit user instruction in README; full fix is Developer ID signing + notarisation in M4-C |
| `data_dir()` falls through `dirs::data_dir()` → `~/Library/Application Support/TagLedger`. Logs would land at `~/Library/Application Support/TagLedger/logs/`, not the macOS-idiomatic `~/Library/Logs/TagLedger`. | Acceptable for parity with Windows behaviour where logs live under data dir. Revisit if user feedback objects. |
| Tauri-plugin-single-instance behaviour on macOS uses different IPC (NSDistributedNotificationCenter) than Windows mutex; need explicit smoke test | Listed as acceptance gate 4 |
| `kill_pid` on macOS uses `kill -TERM`/`kill -9` via `Command::new("kill")`. PyInstaller onedir bootloader on macOS sometimes leaves child python processes after parent SIGTERM | Listed as acceptance gate 5; if it fails, switch to process-group kill (`kill -TERM -- -<pgid>`) and tag the child as session leader at spawn |
| Empty stub `dist/tagledger-server/tagledger_server.exe` placeholder used so `tauri-build` resource validation passes during cargo check on macOS | Already present locally (gitignored); document so M4-A.2 doesn't get confused |

## Sequencing

```
M4-A.1 (this branch) ──┐
                       ├─→ M4-A.2 (mac PyInstaller + bundle.macOS config + bundle.targets app/dmg)
M3 PR merged to main ──┘             │
                                     ↓
                              M4-A.3 (ad-hoc signed .app smoke; macOS_MANUAL_VERIFICATION.md)
                                     │
                                     ↓
                              M4-B (auto-update) or M4-C (Developer ID signing)
```

M4-A.1 cannot push to a PR yet because it depends on M3 launcher source which is not on `main`. Two valid paths:

- **Path 1 (recommended)**: hold M4-A.1 local, wait for M3 PR to merge, rebase onto main, then open M4-A.1 PR.
- **Path 2**: open M4-A.1 PR directly against `codex/desktop-beta-m1-lan-guard` (stacked PR). Higher review overhead.

## Out of scope

- Apple Developer ID signing + notarisation (M4-C).
- Tauri auto-updater plugin and update server (M4-B).
- Mobile native shell (separate track).
- Universal2 binary (deferred to M4-A.4 if user demand).
- Replacing `tauri-plugin-shell::open` with `tauri-plugin-opener` (small follow-up).
