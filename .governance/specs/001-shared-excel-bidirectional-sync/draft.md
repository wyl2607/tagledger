# Draft 001 — (a) 对账结果导出回填

- spec_id: `001`
- slug: `shared-excel-bidirectional-sync`
- phase: `draft`
- status: `awaiting-review`
- scope: 仅 requirement 的 (a);(b) Excel snapshot 留作后续切片
- created: 2026-05-22
- author: Coordinator (Claude)

## 1. 现状摸底(既有可复用件)

| 件 | 位置 | 复用方式 |
|---|---|---|
| `preview_inventory_reconcile` | `backend/app/services/inventory_service.py:448` | 产出四类对账结果(每行含 `system_quantity` / `excel_quantity` / `delta`),导出直接消费它 |
| `POST /reconcile/preview-file` | `backend/app/routes/inventory.py:211` | "传 Excel → 跑 preview" 的范式,新导出端点照抄 |
| `parse_inventory_file_rows` | `backend/app/services/inventory_excel.py:106` | 已有的 Excel/CSV 解析;新增的 XLSX 写出放同一模块 |
| `export_inventory_locations_csv` + `GET /export.csv` | `inventory_service.py:123` / `inventory.py:120` | 导出范式:`require_supervisor` + `Content-Disposition` attachment |
| `_safe_inventory_csv_cell` / `DANGEROUS_CSV_PREFIXES` | `inventory_service.py:114` | 公式注入防护逻辑,XLSX 写出需等价处理 |
| `openpyxl>=3.1.0` | 已在 `pyproject.toml` / `requirements-runtime.txt` | XLSX 写出,无需新依赖 |

关键事实:`_rows_from_table` 只保留 `REQUIRED_COLUMNS | OPTIONAL_COLUMNS`(`part_key/location_code/quantity/factory_id`)之外的列会被忽略 → **导出文件可同时是"可再导入文件"和"人工可读差异表"**。

## 2. 技术方案(选定)

**无状态导出端点**,在服务端重跑 preview,产出内存 XLSX 流式下载。

### 2.1 端点

```
POST /api/inventory/reconcile/export-file
  权限: require_supervisor
  入参: UploadFile(同 preview-file 的 Excel/CSV)
  流程: parse_inventory_file_rows → preview_inventory_reconcile → render XLSX
  返回: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
        Content-Disposition: attachment; filename=tagledger-reconcile-export-<date>.xlsx
```

为什么重新上传文件而不是回传 preview JSON:preview 结果里的 `excel_quantity` 必须由服务端从文件重算,不能信任客户端回传值(可篡改)。preview 是纯函数且廉价,重跑成本可忽略。UI 侧把已上传文件留在浏览器内存,导出按钮复用该文件再 POST 一次。

### 2.2 XLSX 列结构

单 sheet,首行表头用**机器键**(保证可再导入):

| 列 | 来源 | 说明 |
|---|---|---|
| `factory_id` | 对账行 | 导入必需键 |
| `part_key` | 对账行 | 导入必需键 |
| `location_code` | 对账行 | 导入必需键 |
| `quantity` | system_quantity | **系统值**,作为可再导入的 `quantity` 列 |
| `excel_quantity` | 对账行 | 注解列,再导入时被忽略 |
| `delta` | excel - system | 注解列 |
| `category` | matched / quantity_mismatch / excel_missing / excel_new | 注解列 |
| `note` | 派生的人工提示 | 注解列 |

行序:按 `category` 分组(差异类在前)再按 `part_key/location_code` 稳定排序。
`excel_new` 行系统无库存,`quantity` 写 0;`excel_missing` 行 `excel_quantity` 留空。

### 2.3 导出范围

默认导出**全部四类**,靠 `category` 列让人工聚焦差异。不在本切片做按区域/库位筛选(留作增强)。

### 2.4 公式注入防护

openpyxl 写入以 `= + - @` 开头的字符串会被 Excel 当公式。`part_key` / `location_code` 等字符串单元格复用与 `_safe_inventory_csv_cell` 等价的前缀 `'` 处理(抽成共享 helper 或在写出函数内联同款判断)。

### 2.5 代码落点

| 文件 | 改动 |
|---|---|
| `backend/app/services/inventory_excel.py` | 新增 `render_reconcile_export_xlsx(preview_result) -> bytes` |
| `backend/app/routes/inventory.py` | 新增 `POST /reconcile/export-file` 端点 |
| `backend/app/static/`(`/inventory` 页 HTML/JS/CSS) | preview 面板下新增"导出回填 XLSX"按钮,复用内存中的已上传文件 |
| `backend/app/static/i18n/{zh,en,de}.json` | 新增 `inventory.reconcile.export_*` key |
| `backend/tests/test_inventory_reconcile_export.py`(新) | 后端测试 |

### 2.6 落盘策略

导出走内存 `BytesIO` 流式返回,**不落 `data/` 磁盘**——直接消解 requirement 开放问题"导出文件落盘位置 / .gitignore"。

## 3. 备选项

| 方案 | 取舍 |
|---|---|
| **A. 无状态 export-file 端点(选定)** | 服务端重算,无新表无迁移,只读零回归;代价是文件需在浏览器再 POST 一次 |
| B. 持久化 reconcile 结果后按 id 导出 | 需新表,与"(b) 留作后续 / 本切片不引入持久化"冲突 → 否决 |
| C. 客户端回传 preview JSON 给导出端点 | 免二次上传,但信任客户端数量值(可篡改)、事实源分裂 → 否决 |
| D. 纯"系统库存 → XLSX"(export.csv 的 XLSX 双胞胎) | 不带 Excel 差异,无法"避免两套来源漂移" → 否决为主方案 |
| 格式 CSV vs XLSX | 用户已选 XLSX;CSV 全量导出已由 `/export.csv` 覆盖 |

## 4. 影响面

- **修改路径**:`inventory_excel.py`、`routes/inventory.py`、`/inventory` 静态资源、i18n 三语。
- **新增依赖**:无(openpyxl 已在)。
- **数据库**:无新表、无迁移。
- **兼容性**:纯新增 + 只读;不写 `InventoryLocation`/`InventoryMovement`/`AuditLog`,不动现有 reconcile preview/apply 行为,对现有测试零回归。
- **权限**:`require_supervisor`,与现有 `/export.csv` 一致。

## 5. requirement 开放问题收敛((a) 相关)

| 开放问题 | 本 draft 结论 |
|---|---|
| 导出权限 | `require_supervisor`,与 `/export.csv` 一致 |
| 导出范围 / 筛选 | 默认全四类 + `category` 列;区域/库位筛选不在本切片 |
| 列结构是否对齐共享 Excel | 前 4 列用机器键 `factory_id/part_key/location_code/quantity`,与导入 schema 对齐 → 导出文件可再导入;注解列再导入时被忽略 |
| 导出文件落盘位置 | 不落盘,内存流式返回 |

## 6. 未解决问题(留给 /sdd-review 与 /sdd-rfc)

1. 表头用机器键保证可再导入,但对人工不够友好。是否需要第二行中文说明行,或单独提供一个"人类可读版"sheet?(权衡:多 sheet 增加复杂度)
2. `matched` 行是否纳入导出?当前方案纳入(给全貌)。若数据量大,matched 行可能淹没差异行——是否默认折叠/单独 sheet?
3. `note` 列的文案与是否需要 i18n(导出文件内的文案目前倾向固定中文,因现场用户为中文)。
4. 公式注入防护:抽成 `inventory_excel.py` 内共享 helper,还是与 `inventory_service._safe_inventory_csv_cell` 合并到一处?(reviewer 架构 lens 定)
5. 导出文件名是否需含厂区/时间精度到秒以避免覆盖。
6. 大文件:超大 Excel 上传 + 重跑 preview 的体量上限是否需限制(与 preview-file 现有行为保持一致即可,但 review 需确认 preview-file 是否已有大小限制)。
