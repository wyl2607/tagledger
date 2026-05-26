# Requirement 001 — 共享 Excel 双向对账闭环

- spec_id: `001`
- slug: `shared-excel-bidirectional-sync`
- project: TagLedger (GitHub `wyl2607/tagledger`)
- phase: `specify`
- status: `confirmed`
- created: 2026-05-22
- confirmed: 2026-05-22
- author: Coordinator (Claude)
- dev_scope_this_round: 仅 (a) 对账结果导出回填;(b) Excel snapshot 元数据 + 逐项值追踪留作后续切片

## 背景

TagLedger 现有 Excel 对账能力:

- `backend/app/services/inventory_excel.py` 服务层。
- `POST /api/inventory/reconcile/preview-file` — 只读 preview,产出四类:`matched` / `quantity_mismatch` / `excel_missing` / `excel_new`。
- `POST /api/inventory/reconcile/apply` — 受控 apply,supervisor/admin 人工确认后写流水/审计。

当前缺口(来自 `TODO.md`):

- P1 对账应用流程未完项:"支持把确认后的系统结果导出给人工回填共享 Excel,避免两套来源继续漂移"。
- P3 现场数据治理未完项:"建立每日或每次导入的 Excel snapshot 元数据:文件名、导入时间、操作者、行数、hash";"对同一物料/库位保留最近一次 Excel 值、系统值、差异状态和处理状态"。

## 目标

让 TagLedger 系统库存与外部"共享通讯文档 Excel"之间形成**可追溯、半自动、人工把关**的对账闭环,避免两套数据来源在对账后继续漂移。

## 动机

- Excel 来自共享通讯文档,通常较新但不是唯一真相;TagLedger 也不是唯一真相。两者在过渡期必须共存对账。
- 现有 reconcile 只覆盖 "Excel → 系统" 方向的人工确认;反方向 "系统确认结果 → Excel" 没有出口,导致对账后两边继续漂移。
- 每次 Excel 导入没有版本化记录,无法追溯差异来源,也无法回答"上一次 Excel 值是多少"。

## 范围(In scope)

本轮固化 (a) 与 (b) 两块。

### (a) 对账结果导出回填

- 提供导出能力:把"对账确认后的系统库存结果"导出为修正后的 XLSX(或 CSV)文件供下载。
- 导出内容至少含:物料号、库位编码、系统数量(整数);在存在 snapshot 时标注与上一次 Excel 值的差异。
- 导出为只读动作:不修改 `InventoryLocation` / `InventoryMovement` / `AuditLog`,也不写共享 Excel 文件本身。
- 人工下载该文件后自行更新共享通讯文档;**系统不直接触碰共享文件**。

### (b) Excel snapshot 元数据 + 逐项值追踪

- 每次 Excel 导入(经 `preview-file`)生成一条 snapshot 记录:文件名、文件 hash、导入人、导入时间、解析行数、预检结果。
- 重复导入相同 hash 的文件应提示,不静默覆盖。
- 对同一(物料, 库位)保留:最近一次 Excel 值、当前系统值、差异分类(沿用四类)、处理状态。
- snapshot 与逐项追踪为 (a) 的导出回填提供"上一次 Excel 值"基线。

## 明确不做(Out of scope)

- 不做系统直接覆盖写回共享 Excel 文件。
- 不做自动化无人值守的双向同步;import 仍走现有人工确认的 reconcile/apply,export 仍是人工把关的"下载-回填"。
- 不引入外部 SaaS / 云存储依赖;保持局域网本地优先。
- 不重写现有 reconcile preview/apply 的四类分类逻辑与权限模型(仅复用/扩展)。
- 不支持小数库存;数量保持整数整件。
- 不做 Excel 文件的实时协同编辑。

## 约束(Constraints)

- 局域网本地优先,SQLite。
- 库存数量整数整件;CSV/XLSX 含小数应拒绝(沿用现有规则)。
- 所有库存数量变化必须经流水/审计可追溯;本需求的导出与 snapshot 记录不得绕过这条。
- Excel preview 保持只读。
- apply 仍需人工确认,权限限 supervisor/admin。
- 复用现有 `inventory_excel.py` 服务与 reconcile 接口,不另起一套平行实现。
- 私有需求文档(`docs/private/*`)不提交 Git、不同步远端。

## Done criteria(可验收)

1. 存在导出接口 + UI 入口,可下载一份修正后的 XLSX,内容含物料号、库位、系统数量,且在有 snapshot 时标注与上一次 Excel 值的差异。
2. 导出动作不写 `InventoryLocation` / `InventoryMovement` / `AuditLog`,不修改共享 Excel 文件。
3. 每次 Excel 导入产生一条 snapshot 记录,含文件名、hash、导入人、导入时间、行数、预检结果;重复 hash 有提示。
4. 可按(物料, 库位)查询最近一次 Excel 值、系统值、差异分类、处理状态。
5. 新增能力有后端测试覆盖:导出内容、snapshot 写入、重复 hash 提示、逐项值查询。
6. `./scripts/run_preflight.sh` 全绿;现有 reconcile 相关测试无回归。
7. 关键页面有真实浏览器 smoke:导出下载、snapshot 列表展示。

## 开放问题(留给 `/sdd-draft`)

- 导出权限:仅 supervisor/admin,还是所有登录用户可只读导出?
- 导出范围:全量库存,还是仅含差异/对账涉及的物料?是否支持按区域/库位筛选导出?
- snapshot 存储:新增独立表,还是扩展现有结构?逐项值追踪是独立表还是 snapshot 明细?
- 导出文件是否需与共享 Excel 的列结构(列名/顺序)对齐,便于人工直接粘贴回填?
- 处理状态的取值集合需在 draft 阶段定义。
- snapshot 保留时长与是否需要清理策略。
- 导出文件落盘位置(`data/` 下)与是否纳入 `.gitignore`。
