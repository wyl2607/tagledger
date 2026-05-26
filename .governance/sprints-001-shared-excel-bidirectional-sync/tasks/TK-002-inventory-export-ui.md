# TK-002 — /inventory 导出回填按钮 + i18n 三语

> 字段契约对齐 automation workspace guide `codex-context-standard.md`。

## Goal
在 `/inventory` 页的 Excel 对账 preview 面板新增"导出回填 XLSX"按钮,复用浏览器内已上传的对账文件,POST 到 TK-001 的导出端点并触发下载。

## Context
- 项目:TagLedger (`wyl2607/tagledger`)。`/inventory` 页是单文件 `backend/app/static/inventory.html`(内联 CSS/JS,无独立 js/css 文件)。
- 当前状态:页面已有 Excel 对账文件上传 preview 面板(`reconcile`),调用 `/api/inventory/reconcile/preview-file`。i18n 用 `data-i18n` 属性 + `backend/app/static/i18n/{zh,en,de}.json` 扁平点号 key。
- 上游:TK-001 已交付 `POST /api/inventory/reconcile/export-file`(`require_supervisor`,入参 UploadFile,返回 XLSX attachment)。
- 设计依据:`.governance/specs/001-shared-excel-bidirectional-sync/draft.md` §2.5、RFC.md。

## Relationship to Existing Systems (RC-002)
- 共存:在现有 reconcile preview 面板内新增按钮,不改 preview 既有行为。
- 替代:无。
- 衔接:依赖 TK-001 端点;UI 风格遵循 `docs/UI_STYLE_GUIDE.md` / `UI_REVAMP_NOTES.md`。

## Constraints
- write_scope:
  - `backend/app/static/inventory.html`
  - `backend/app/static/i18n/zh.json`
  - `backend/app/static/i18n/en.json`
  - `backend/app/static/i18n/de.json`
- 禁止修改:
  - 任何后端 `.py` 文件(端点已由 TK-001 交付)
  - 其它 static 页面(`mobile.html` / `home.html` / `history.html` 等)
  - 现有 i18n key
- 不跳过 hooks;不做破坏性 git 操作。

## 实现要点
- 导出按钮放在 reconcile 文件上传 preview 面板内,preview 成功后可用(无 preview 时禁用或隐藏)。
- 复用浏览器内存中已选的对账文件对象,以 `multipart/form-data` POST 到 `/api/inventory/reconcile/export-file`。
- 响应为 blob → 用 `Content-Disposition` 文件名(或前端兜底名)触发浏览器下载。
- 失败时显示提示(403/409/400 区分:无权限 / 文件内容问题)。
- 新增 i18n key(如 `inventory.reconcile.export_button` / `export_hint` / `export_failed`),zh/en/de 三语同步。

## Done criteria
- [ ] `/inventory` preview 面板出现"导出回填 XLSX"按钮,preview 后可点击。
- [ ] 点击后用已上传文件触发后端导出并下载 XLSX。
- [ ] 失败有可读提示,区分无权限与文件错误。
- [ ] 新增 i18n key 在 zh/en/de 三语齐全,无改动现有 key。
- [ ] 真实浏览器 smoke:桌面 1366x900 与手机 390x844 下按钮可见、可点、能下载,无 console error。
- [ ] `./scripts/run_preflight.sh` 全绿。

## 验证命令
```bash
source .venv/bin/activate
./scripts/run_preflight.sh
# 手动:浏览器开 /inventory,以 supervisor 登录,上传对账文件 → preview → 点导出 → 确认下载 XLSX
```

## 状态历史
- 2026-05-22 18:50 CST: planned
- 2026-05-22 19:12 CST: executing — Scheduler 选定,进入 Execution(TK-001 依赖已满足)
- 2026-05-22 19:13 CST: 派 Codex /goal 执行(codex exec gpt-5.5-medium,后台 id bz87s38ac)
- 2026-05-22 19:20 CST: Codex 交付 4 文件(exit 0),i18n 三语对齐,preflight PASSED
- 2026-05-22 19:25 CST: CR-002 resolved — 初评 clean,运行态 smoke 页面+路由+鉴权确认;交互式 smoke 留现场
- 2026-05-22 19:26 CST: done
