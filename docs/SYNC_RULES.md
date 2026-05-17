# TagLedger Git Sync Rules

This document defines the only supported sync path for TagLedger development across Mac, the `coco` Mac mini, GitHub, Windows, and servers.

## Source Of Truth

- Center remote: `https://github.com/wyl2607/tagledger.git`
- Tailscale Mac Mini Mirror: remote name `coco`, default URL `coco:tagledger.git`.
- Visibility: private GitHub repository.
- Default branch: `main`.
- Current UI work branch: `ui/mobile-history-v1`.
- Current desktop beta development branch: `codex/desktop-m4-macos-launcher`.

The GitHub remote is the source of truth for code sync. `origin` remains GitHub so CI, PRs, and release review keep one canonical public target. The `coco` remote uses Tailscale SSH as the local development mirror between this development zone and the Mac mini; it is a speed and availability mirror, not a replacement for GitHub review.

Local databases, uploaded images, screenshots, logs, OCR scratch files, browser storage state, and private requirement notes are never synced through Git.

For the current desktop beta line, the active development baseline is the clean Mac checkout on `codex/desktop-m4-macos-launcher`. Treat the Windows machine as a real build and smoke-test host only until the branch is pushed and reviewed. Do not continue coding from a Windows worktree that was populated by rsync or contains verification scripts, screenshots, installers, or other dirty runtime artifacts.

## Branch Rules

- `main`: sanitized baseline and stable integration branch.
- `ui/mobile-history-v1`: current mobile and history UI lane.
- `codex/*`: temporary Codex work branches are allowed only after `scripts/review_push_guard.sh origin/main` passes.
- `slice/*`, `claude/*`, and old local experiment branches are local-only unless they are rebuilt from the sanitized `main` history first.

Do not push old local branches from the pre-GitHub history. The GitHub repository intentionally starts from one sanitized root commit.

## Files That Must Never Be Pushed

- `.env` and `.env.*`
- `.omx/`
- `.claude/`
- `.venv/`
- `data/app.db`
- `data/storage_state.json`
- `data/backups/`
- `data/outbound/`
- `data/ocr-scratch/`
- uploaded files under `data/uploads/`, except `.gitkeep`
- screenshots under `data/screenshots/`, except `.gitkeep`
- `logs/`
- `docs/private/`
- `docs/ops/private/`
- `PRIVATE_REQUIREMENTS/`
- build outputs such as `dist/`, `build/`, and `*.egg-info/`

The guard scripts check this list before push. If a path is blocked, remove it from Git tracking or move it to a local-only location before continuing.

## Mac Development Flow

Use this flow for normal work from the Mac:

```bash
cd /path/to/tagledger
git fetch origin
git switch ui/mobile-history-v1
git pull --ff-only

./.venv/bin/python -m pytest backend/tests -q
./scripts/security_check.sh
./scripts/review_push_guard.sh origin/main

git add <intended-files>
git commit -m "feat(ui): improve TagLedger mobile and history flows"
./scripts/review_push_guard.sh origin/main
git push origin ui/mobile-history-v1
```

Use explicit `git add <intended-files>`. Do not use broad staging when local runtime files exist.

Configure the default local sync remotes once per checkout:

```bash
scripts/configure_sync_remotes.sh --apply
```

The default configuration keeps `origin` on GitHub and adds a `coco` remote over Tailscale:

```text
origin -> https://github.com/wyl2607/tagledger.git
coco   -> coco:tagledger.git
```

If the Mac mini bare repository lives elsewhere, override the URL without editing the script:

```bash
COCO_REMOTE_URL=coco:tagledger.git scripts/configure_sync_remotes.sh --apply
```

After local validation, synchronize intentionally:

```bash
git push origin <branch>
git push coco <branch>
```

Pull intentionally from the reviewed source of truth unless you are recovering a local-only Mac mini branch:

```bash
git pull --ff-only origin <branch>
```

Do not use file-copy sync as the development baseline. The `coco` path must stay Git-based over the Tailscale SSH address so branch history, forbidden-file checks, and review gates remain meaningful.

For the desktop beta line, continue implementation and commits on the Mac branch:

```bash
cd <tagledger-checkout>
git switch codex/desktop-m4-macos-launcher
git status --short --branch

./scripts/run_preflight.sh
./scripts/security_check.sh
scripts/site_ui_qa.py
cd desktop && npm run build
cd src-tauri && cargo check
```

The expected baseline before Windows handoff is a clean Mac worktree with the desktop branch commits in order. If local docs such as `docs/M4_MACOS_PLAN.md` are still untracked, classify and commit or intentionally keep them local before handoff; do not hide them by syncing a dirty tree.

## Windows Or Server Update Flow

Use this flow on Windows or servers after Mac changes are pushed:

```bash
cd /path/to/tagledger
git fetch origin
git switch ui/mobile-history-v1
git pull --ff-only
python -m pip install -e ".[dev,ocr,barcode]"
python -m pytest backend/tests -q
```

For desktop beta validation before push, Windows is a packaging and physical-device verification host, not the development baseline. Create or refresh a clean Windows test directory from the Mac HEAD instead of reusing a dirty rsync validation tree:

```powershell
# Example target: <clean-windows-test-dir>
git status --short --branch
git clean -ndx
```

Run only the Windows acceptance gates needed for the beta:

```powershell
.\packaging\windows\build_backend.ps1
cd desktop
npm run tauri build
```

Then complete launcher UI smoke and phone LAN QR validation from the built installer or launcher. Verification artifacts such as screenshots, click scripts, temporary PowerShell wrappers, installers, and logs stay on Windows and must not become the next coding baseline.

For PowerShell, use the same Git commands, then:

```powershell
python -m pip install -e ".[dev,ocr,barcode]"
python -m pytest backend/tests -q
```

## Release Package Flow

For a sanitized source package:

```bash
VERSION=<version> ./scripts/make_release.sh
```

The release package must pass its built-in forbidden-entry check. It must not contain private docs, local databases, uploaded images, logs, `.env` files, `.git`, or `.omx`.

## Recovery Rules

If sync goes wrong:

- Prefer `git status`, `git fetch origin`, and `git pull --ff-only`.
- Do not force push.
- Do not run `git reset --hard` against a dirty worktree without first checking whether files are local runtime state or user work.
- If a blocked file was staged, unstage it with `git restore --staged <path>` and update `.gitignore` or the guard scripts if needed.
- If a branch contains old local history, create a new branch from `origin/main` and cherry-pick only reviewed commits.

## Required Verification Before Push

At minimum, run:

```bash
./.venv/bin/python -m pytest backend/tests -q
./scripts/security_check.sh
./scripts/review_push_guard.sh origin/main
```

If UI behavior changes, also start the local app and test `/mobile` and `/history` in a browser before pushing.
