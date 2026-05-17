#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GITHUB_REMOTE_URL="${GITHUB_REMOTE_URL:-https://github.com/wyl2607/tagledger.git}"
COCO_REMOTE_NAME="${COCO_REMOTE_NAME:-coco}"
COCO_REMOTE_URL="${COCO_REMOTE_URL:-coco:tagledger.git}"
DRY_RUN="${DRY_RUN:-1}"

usage() {
  cat <<'USAGE'
Configure TagLedger development sync remotes.

Default behavior is dry-run. Use --apply or DRY_RUN=0 to update local git remote
configuration.

Defaults:
  origin -> https://github.com/wyl2607/tagledger.git
  coco   -> coco:tagledger.git

Override examples:
  COCO_REMOTE_URL=coco:/srv/git/tagledger.git scripts/configure_sync_remotes.sh --apply
  COCO_REMOTE_NAME=macmini COCO_REMOTE_URL=macmini:tagledger.git scripts/configure_sync_remotes.sh --apply

This script only edits local git remote configuration. It does not contact
remotes or copy files.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --apply)
      DRY_RUN=0
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$ROOT_DIR"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not inside a git worktree: $ROOT_DIR" >&2
  exit 1
fi

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  if [[ "$DRY_RUN" == "0" ]]; then
    "$@"
  fi
}

ensure_remote() {
  local name="$1"
  local url="$2"

  if git remote get-url "$name" >/dev/null 2>&1; then
    if [[ "$name" == "origin" ]]; then
      run git remote set-url origin "$url"
    else
      run git remote set-url "$name" "$url"
    fi
  else
    run git remote add "$name" "$url"
  fi
}

echo "TagLedger sync remotes"
echo "mode: $([[ "$DRY_RUN" == "0" ]] && echo apply || echo dry-run)"
echo "origin: $GITHUB_REMOTE_URL"
echo "$COCO_REMOTE_NAME: $COCO_REMOTE_URL"

ensure_remote "origin" "$GITHUB_REMOTE_URL"
ensure_remote "$COCO_REMOTE_NAME" "$COCO_REMOTE_URL"

if [[ "$DRY_RUN" != "0" ]]; then
  echo "Dry-run only. Re-run with --apply or DRY_RUN=0 to update local git config."
fi
