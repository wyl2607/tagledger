# AGENTS.md — TagLedger AI 开发入口

> Scope: `/Users/yumei/tagledger`
> Project: TagLedger
> Current branch family: `ui/mobile-history-v1`

## Read First

- 先读本文件，再读 `CLAUDE.md`、`README.md`、`docs/SYNC_RULES.md`。
- 非琐碎实现、调试或交付前，先查 `/Users/yumei/tools/automation/runtime/ai-trace/*.jsonl`：

```bash
bash /Users/yumei/tools/automation/scripts/ai-trace.sh find "tagledger <keyword>"
```

- 形成稳定根因、可复用流程或交付边界后，必须写回 `ai-trace` session；可复用规则写 solution。

## Repository Boundaries

- 不提交 `.env*`、本地数据库、上传图片、日志、截图、`.omx/`、`.automation/`、`.claude/worktrees/`、`dist/`、`.pytest_cache/`。
- Git 同步规则以 `docs/SYNC_RULES.md` 为准。
- 推送、PR、发布、部署、节点同步、SSH、rsync 都不属于普通实现链；必须先跑 release/readiness gate，并等用户显式批准远端动作。

## Grouped Commit Policy

多组改动必须先走 `grouped-commit-cycle` dry-run，再按组提交。禁止把行为/API/UI、i18n、docs、scripts 混在一个 commit。

```bash
python3 /Users/yumei/tools/automation/workspace-guides/skill-chains/chain-gates/grouped_commit_cycle.py \
  --repo /Users/yumei/tagledger \
  --project tagledger \
  --dry-run
```

需要本地自动逐组提交时：

```bash
python3 /Users/yumei/tools/automation/workspace-guides/skill-chains/chain-gates/grouped_commit_cycle.py \
  --repo /Users/yumei/tagledger \
  --project tagledger \
  --execute
```

### Group 1: Feature / API / UI / Refactor

允许：

- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/routes/**`
- `backend/app/services/**`
- `backend/app/static/*.html`
- `backend/tests/**`

禁止混入：

- `backend/app/static/i18n/*.json`
- `docs/**`
- `README.md`
- `CLAUDE.md`
- `AGENTS.md`
- `scripts/**`
- release/deploy/sync/SSH/rsync 配置

必跑：

```bash
ruff check backend scripts
PATH=.venv/bin:$PATH python -m pytest backend/tests/test_auth.py backend/tests/test_api.py backend/tests/test_scan_verification.py -q
```

### Group 2: I18n Only

允许：

- `backend/app/static/i18n/zh.json`
- `backend/app/static/i18n/en.json`
- `backend/app/static/i18n/de.json`

禁止混入：

- HTML、Python、测试、docs、scripts 的行为变更

必跑：

```bash
PATH=.venv/bin:$PATH python -m pytest backend/tests/test_i18n.py -q
PATH=.venv/bin:$PATH python -m pytest backend/tests/test_api.py -q -k static_i18n_keys_exist_for_three_languages
python -m json.tool backend/app/static/i18n/zh.json >/tmp/tagledger-zh-json.out
python -m json.tool backend/app/static/i18n/en.json >/tmp/tagledger-en-json.out
python -m json.tool backend/app/static/i18n/de.json >/tmp/tagledger-de-json.out
```

### Group 3: Docs / Plan / Progress

允许：

- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `PROJECT_PROGRESS.md`
- `INCIDENT_LOG.md`
- `docs/**/*.md`

禁止混入：

- backend/source/test behavior changes
- scripts/release/deploy changes
- private local machine notes not suitable for repo

必跑：

```bash
git diff --check -- AGENTS.md CLAUDE.md README.md docs
```

### Group 4: Scripts / Release / Ops

允许：

- `scripts/**`
- `Start Windows LAN.cmd`
- `backend/tests/test_release_packaging.py`

禁止混入：

- backend feature/API/UI behavior not required by the script
- i18n JSON
- docs-only plan/progress updates
- real release, deploy, sync, SSH, rsync actions

必跑：

```bash
ruff format backend scripts
ruff check backend scripts
PATH=.venv/bin:$PATH python -m pytest backend/tests/test_release_packaging.py -q
```

## Default Validation

实现改动后先跑最小相关 gate，再按风险扩大。常用全量本地 gate：

```bash
./scripts/run_preflight.sh
./scripts/security_check.sh
./scripts/review_push_guard.sh origin/main
```

Windows 对应：

```powershell
.\scripts\run_preflight.ps1
```
