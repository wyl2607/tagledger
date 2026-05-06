# TagLedger Git Sync Rules

This document defines the only supported sync path for TagLedger development across Mac, GitHub, Windows, and servers.

## Source Of Truth

- Center remote: `https://github.com/wyl2607/tagledger.git`
- Visibility: private GitHub repository.
- Default branch: `main`.
- Current UI work branch: `ui/mobile-history-v1`.

The GitHub remote is the source of truth for code sync. Local databases, uploaded images, screenshots, logs, OCR scratch files, browser storage state, and private requirement notes are never synced through Git.

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
