# RFC — sprints-001-shared-excel-bidirectional-sync

> 由 `/sdd-rfc` 从 `.governance/specs/001-shared-excel-bidirectional-sync/draft.md` 收敛而来。
> `/sdd-review` 经用户指示跳过,无 draft.review.md。
> 一旦本 Sprint 启动,本文件冻结;后续变更新开 RFC。

## 背景与动机
TagLedger 已有 Excel 对账(`/api/inventory/reconcile/preview-file` 产出 matched/quantity_mismatch/excel_missing/excel_new 四类)。但缺"系统结果 → Excel"方向的出口,对账后系统与共享 Excel 仍持续漂移。本 Sprint 实现 requirement (a):把对账结果导出为修正后 XLSX 供人工回填。

## 协议 / 接口决策
- 新端点 `POST /api/inventory/reconcile/export-file`,入参为 `UploadFile`(Excel/CSV,同 `preview-file`)。
- 服务端流程:`parse_inventory_file_rows` → `preview_inventory_reconcile` → `render_reconcile_export_xlsx`。
- 服务端**重新解析上传文件并重跑 preview**,不接受客户端回传的 preview JSON(防篡改、单一事实源)。
- 返回 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,`Content-Disposition: attachment; filename=tagledger-reconcile-export-<date>.xlsx`。
- XLSX 单 sheet,首行机器键表头:`factory_id, part_key, location_code, quantity, excel_quantity, delta, category, note`。
  - 前 4 列 `quantity=system_quantity`,与导入 schema(`REQUIRED_COLUMNS`)对齐 → 导出文件可再导入。
  - 后 4 列为注解列,再导入时被 `_rows_from_table` 自动忽略。
- 行序:按 `category` 分组(差异类在前)再按 `part_key/location_code` 稳定排序。
- `excel_new` 行 `quantity` 写 0;`excel_missing` 行 `excel_quantity` 留空。

## 架构选择
- 无状态导出:不持久化 reconcile 结果,内存 `BytesIO` 流式返回,不落 `data/` 磁盘。
- XLSX 渲染落在 `inventory_excel.py`(既有 Excel I/O 模块),与既有 `_parse_xlsx` 同模块。
- 端点落在 `routes/inventory.py`,照抄 `preview-file` / `export.csv` 范式。
- 复用 `preview_inventory_reconcile`,不另起平行对账实现。

## 安全决策
- 权限 `require_supervisor`,与既有 `/api/inventory/export.csv` 一致。
- 公式注入防护:openpyxl 写入以 `= + - @` 开头的字符串会被 Excel 当公式;`part_key`/`location_code`/`note` 等字符串单元格须复用与 `_safe_inventory_csv_cell` 等价的前缀 `'` 处理。
- 只读:不写 `InventoryLocation` / `InventoryMovement` / `AuditLog`,不修改共享 Excel 文件。
- 文件大小/解析异常沿用 `preview-file` 现有处理(`RuntimeError` → 409,解析异常 → 400)。

## 已被驳回的备选项
- **持久化 reconcile 结果后按 id 导出**:需新表,与本 Sprint"不引入持久化 / (b) 延后"冲突。
- **客户端回传 preview JSON 给导出端点**:信任客户端数量值(可篡改),事实源分裂。
- **纯"系统库存 → XLSX"(export.csv 的 XLSX 双胞胎)**:不带 Excel 差异,无法实现"避免两套来源漂移"。

## 影响面
- 修改路径:`backend/app/services/inventory_excel.py`、`backend/app/routes/inventory.py`、`backend/app/static/inventory.html`、`backend/app/static/i18n/{zh,en,de}.json`;新增 `backend/tests/test_inventory_reconcile_export.py`。
- 新增依赖:无(openpyxl 已在 `pyproject.toml` / `requirements-runtime.txt`)。
- 兼容性:纯新增 + 只读;无数据库变更/迁移;对现有 reconcile preview/apply 行为零改动,对现有测试零回归。

## Done criteria
- `POST /api/inventory/reconcile/export-file` 接收 Excel/CSV,返回修正后 XLSX,内容含八列且 `quantity` 为系统值。
- 导出动作不写 `InventoryLocation`/`InventoryMovement`/`AuditLog`,不落盘。
- 字符串单元格做公式注入防护。
- 导出 XLSX 的前 4 列可被现有 `parse_inventory_file_rows` 再解析。
- `/inventory` preview 面板有"导出回填 XLSX"按钮,复用浏览器内已上传文件触发下载;有 i18n 三语。
- `backend/tests/test_inventory_reconcile_export.py` 覆盖:导出列内容、系统值正确、注入防护、四类行序、无写库。
- `./scripts/run_preflight.sh` 全绿,现有 reconcile 测试无回归。
- 关键路径有真实浏览器 smoke(导出按钮触发下载)。
