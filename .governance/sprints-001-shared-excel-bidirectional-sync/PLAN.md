# PLAN — sprints-001-shared-excel-bidirectional-sync

## 目标
让 TagLedger 主管能把一次 Excel 对账的结果导出为修正后的 XLSX 文件下载,用于人工回填共享通讯文档,避免系统与 Excel 两套来源继续漂移。

## 接续点
首个 Sprint,无上游。来源:`.governance/specs/001-shared-excel-bidirectional-sync/`(requirement.md 已确认 + draft.md)。`/sdd-review`(draft 双评)经用户指示跳过;代码生成后的 Review Loop 仍按 self-healing-execution.md 强制执行。

## 范围
- 包含:
  - 后端 XLSX 渲染服务 `render_reconcile_export_xlsx`(`backend/app/services/inventory_excel.py`)
  - 后端端点 `POST /api/inventory/reconcile/export-file`(`require_supervisor`,内存流式返回)
  - 后端测试 `backend/tests/test_inventory_reconcile_export.py`
  - `/inventory` 页 preview 面板新增"导出回填 XLSX"按钮
  - i18n 三语 key(zh/en/de)
- 明确不做:
  - requirement 的 (b) Excel snapshot 元数据与逐项值追踪(后续切片)
  - 系统直接写回共享 Excel 文件
  - 自动化无人值守双向同步
  - 新表 / 数据库迁移 / 导出文件落盘
  - 按区域/库位筛选导出(增强项)

## 车道（并行 lanes）
| lane | TKs | write_scope 摘要 |
|------|-----|-----------------|
| L-A  | TK-001 | backend/app/services/inventory_excel.py, backend/app/routes/inventory.py, backend/tests/** |
| L-B  | TK-002 | backend/app/static/inventory.html, backend/app/static/i18n/** |

L-B 依赖 L-A 的端点契约,串行执行(TK-002 blocked_by TK-001)。

## Checklist（与 TK done 状态保持一致）
- [x] TK-001 后端对账导出 XLSX(服务 + 端点 + 测试)
- [x] TK-002 /inventory 导出回填按钮 + i18n 三语

## 退出条件
- 所有 TK done
- 所有 CR closed(无 pending finding)
- `./scripts/run_preflight.sh` 全绿,现有 reconcile 测试无回归
- Experience 子 Agent 已抽提候选规则
- 无未解释的失败模式
