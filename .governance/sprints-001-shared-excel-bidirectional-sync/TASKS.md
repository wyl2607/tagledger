# TASKS — sprints-001-shared-excel-bidirectional-sync

> 状态枚举：`planned | executing | reviewing | fixing | recheck | done | blocked | split`
> split 用于父 TK：自身不执行，由其子 TK 完成。
> 每次 phase 切换由 Coordinator 同步本表。

| id | title | status | blocked_by | write_scope | reviewer_lanes | notes |
|----|-------|--------|------------|-------------|----------------|-------|
| TK-001 | 后端对账导出 XLSX(服务 + 端点 + 测试) | done | — | backend/app/services/inventory_excel.py, backend/app/routes/inventory.py, backend/tests/test_inventory_reconcile_export.py | default,security | CR-001 resolved;47+303 测试全绿 |
| TK-002 | /inventory 导出回填按钮 + i18n 三语 | done | TK-001 | backend/app/static/inventory.html, backend/app/static/i18n/zh.json, backend/app/static/i18n/en.json, backend/app/static/i18n/de.json | default,security | CR-002 resolved;交互式 smoke 留现场 |

## 字段说明
- **write_scope**：路径前缀白名单，Executor 仅能写其中文件
- **reviewer_lanes**：`default` / `architecture` / `security` / `perf` 任意组合，决定派几个 Reviewer
- **blocked_by**：上游依赖的 TK id，列表
- **notes**：split 时记录子 TK id；blocked 时记录原因
