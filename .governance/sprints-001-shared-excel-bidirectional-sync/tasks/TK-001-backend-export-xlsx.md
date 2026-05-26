# TK-001 — 后端对账导出 XLSX(服务 + 端点 + 测试)

> 字段契约对齐 automation workspace guide `codex-context-standard.md`。

## Goal
新增后端能力:接收一份 Excel/CSV 对账文件,重跑 reconcile preview,渲染一份修正后的 XLSX 流式返回供下载。

## Context
- 项目:TagLedger (`wyl2607/tagledger`),局域网工厂工作台,FastAPI + SQLite。
- 当前状态:已有 `preview_inventory_reconcile`(`backend/app/services/inventory_service.py:448`)产出四类对账结果;`POST /api/inventory/reconcile/preview-file`(`routes/inventory.py:211`)是"传文件→跑 preview"范式;`export_inventory_locations_csv` + `GET /api/inventory/export.csv` 是导出范式(`require_supervisor` + attachment);`_safe_inventory_csv_cell`(`inventory_service.py:114`)是公式注入防护;`parse_inventory_file_rows`(`inventory_excel.py:106`)是文件解析。openpyxl 已是依赖。
- 设计依据:`.governance/specs/001-shared-excel-bidirectional-sync/draft.md` §2、`.governance/sprints-001-shared-excel-bidirectional-sync/RFC.md`。

## Relationship to Existing Systems (RC-002)
- 共存:复用 `preview_inventory_reconcile`、`parse_inventory_file_rows`,不另起平行对账实现。
- 替代:无。
- 衔接:完成后 TK-002 接其端点契约;Sprint 结束时 Experience 抽提候选规则。

## Constraints
- write_scope:
  - `backend/app/services/inventory_excel.py`
  - `backend/app/routes/inventory.py`
  - `backend/tests/test_inventory_reconcile_export.py`
- 禁止修改:
  - `backend/app/services/inventory_service.py`(只读复用 `preview_inventory_reconcile`)
  - 任何现有 `backend/tests/test_*.py`
  - `backend/app/models.py` / alembic(本 TK 无数据库变更)
- 只读:导出不得写 `InventoryLocation` / `InventoryMovement` / `AuditLog`,不落 `data/` 磁盘,不修改共享 Excel。
- 不跳过 hooks;不做破坏性 git 操作。

## 实现要点
- 新增 `render_reconcile_export_xlsx(preview_result: dict) -> bytes`,放 `inventory_excel.py`:
  - 单 sheet,首行机器键表头:`factory_id, part_key, location_code, quantity, excel_quantity, delta, category, note`。
  - `quantity` = `system_quantity`(`excel_new` 行写 0);`excel_quantity` 在 `excel_missing` 行留空。
  - 行序:`category` 分组(quantity_mismatch / excel_missing / excel_new 在前,matched 在后)再按 `part_key, location_code` 稳定排序。
  - 字符串单元格(`part_key`/`location_code`/`category`/`note`)做公式注入防护:以 `= + - @` 开头时前缀 `'`。复用或内联与 `_safe_inventory_csv_cell` 等价逻辑。
  - 用 openpyxl `Workbook`,写入内存 `BytesIO`,返回 `bytes`。
- 新增端点 `POST /api/inventory/reconcile/export-file`,`require_supervisor`:
  - 入参 `UploadFile`;流程 `parse_inventory_file_rows` → `preview_inventory_reconcile` → `render_reconcile_export_xlsx`。
  - 返回 `Response`,media_type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,`Content-Disposition: attachment; filename=tagledger-reconcile-export-<YYYYMMDD>.xlsx`。
  - 异常处理对齐 `preview-file`:`RuntimeError` → 409,解析类异常 → 400。

## Done criteria
- [ ] `render_reconcile_export_xlsx` 产出可被 openpyxl 重新读取的 XLSX,八列齐全。
- [ ] `quantity` 列为系统值;`excel_new` 行为 0;`excel_missing` 行 `excel_quantity` 为空。
- [ ] 字符串单元格做公式注入防护(测试覆盖 `=`/`+`/`-`/`@` 开头值)。
- [ ] 导出 XLSX 前 4 列可被 `parse_inventory_file_rows` 再解析成功。
- [ ] 端点 `require_supervisor`;operator 调用返回 403。
- [ ] 导出过程无 `InventoryLocation`/`InventoryMovement`/`AuditLog` 写入(测试断言计数不变)。
- [ ] `backend/tests/test_inventory_reconcile_export.py` 覆盖上述项。
- [ ] `./scripts/run_preflight.sh` 全绿,现有 reconcile 测试无回归。

## 验证命令
```bash
source .venv/bin/activate
pytest backend/tests/test_inventory_reconcile_export.py backend/tests/test_inventory.py -v
./scripts/run_preflight.sh
```

## 状态历史
- 2026-05-22 18:50 CST: planned
- 2026-05-22 18:54 CST: executing — Scheduler 选定,进入 Execution
- 2026-05-22 18:58 CST: 派 Codex /goal 执行(codex exec gpt-5.5-medium,后台 id bq8fxihnd)
- 2026-05-22 19:00 CST: Codex 交付 3 文件(exit 0),47 测试通过
- 2026-05-22 19:05 CST: CR-001 resolved — 初评 clean,独立验证 pytest 47 + preflight 303 全绿
- 2026-05-22 19:06 CST: done
