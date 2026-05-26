# REVIEWS — sprints-001-shared-excel-bidirectional-sync

> 状态枚举：`open | needs_fix | resolved | rejected | escalated`
> 每条 CR 的详情写在 `reviews/CR-NNN.md`，本表只做索引。

| CR | TK | rounds | status | last_action |
|----|----|--------|--------|-------------|
| CR-001 | TK-001 | 1 | resolved | 2026-05-22 19:05 CST: 初评 clean,2 findings 均 rejected,独立验证 47+303 全绿 |
| CR-002 | TK-002 | 1 | resolved | 2026-05-22 19:25 CST: 初评 clean,运行态 smoke 页面+路由+鉴权确认;交互式 smoke 留现场 |

## 字段说明
- **rounds**：已完成 review 轮数（initial = 1，第一次 recheck = 2，以此类推）
- **status**：
  - `open` 创建后未 review
  - `needs_fix` 有 accepted finding 待修
  - `resolved` 收敛通过
  - `rejected` 全部 finding 被驳回并留痕
  - `escalated` 轮次 > 5 熔断
- **last_action**：CST 时间 + 一句摘要
