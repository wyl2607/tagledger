# TODO

## Phase 1

- [x] 建项目骨架
- [x] 写 README / REQUIREMENTS / ARCHITECTURE / TODO / CLAUDE.md
- [x] FastAPI + SQLite
- [x] 上传 API
- [x] MockOCR
- [x] parser
- [x] 查重服务
- [x] 确认 API
- [x] CSV 导出
- [x] parser 和查重单测
- [x] 上传/查询/确认/导出 API 集成测试
- [x] Windows Phase 1 smoke 脚本
- [x] `GET /jobs` 状态筛选和分页
- [x] `/export.csv?status=confirmed` 状态筛选
- [x] 上传文件扩展名校验
- [x] macOS 一键演示脚本
- [x] macOS 极简静态演示页

## Phase 2

- [x] 移动端友好的上传页面 (/mobile)
- [x] OCR 结果确认页面
- [x] A/B/C 下拉
- [x] 查重弹窗

## Phase 3

- [x] Tesseract Provider
- [x] 图像预处理
- [x] 用真实样本完善字段正则
- [x] 条形码/QR Provider (Track A)
- [x] OCR + 条码集成入上传流程

## Phase 4

- [x] Playwright dry-run 提交流程
- [x] SaaS selector 配置
- [x] 失败截图和重试记录
- [x] /jobs/retry API + retry_failed.ps1 脚本
- [x] pre-commit git hook + ruff lint

## Phase 5

- [ ] 替换 saas_selectors.yaml 占位符为真实 SaaS URL/selector
- [ ] 设置 SAAS_USERNAME / SAAS_PASSWORD 环境变量
- [ ] 人工核对 5 条 dry-run 结果
- [ ] 开启 enable_saas_submit: true + dry_run: false
- [ ] 可选: cleanup_old_images.ps1 自动化调度

## Windows / LAN Field Validation

- [ ] 在真实 Windows 现场机上用 `scripts/run_lan.ps1` 启动并确认二维码 URL 可被同 Wi-Fi 手机打开。
- [ ] 现场确认 Windows 防火墙入站规则策略：默认不自动改防火墙，必要时由管理员显式执行 `-AddFirewallRule` 或手动放行端口。
- [ ] 用手机摄像头扫码进入 `/mobile`，完成登录、选择发货单、扫码/手输料号、提交出库的端到端验证。
- [ ] 在现场网络验证 `/login?next=...`、登出后受保护页面跳转、发货员越权访问调拨/后台的权限提示。
- [ ] 如需在 Windows 本机跑浏览器自动化，安装 Playwright Chromium 后复测浏览器角色流。
- [ ] 如需启用真实 OCR，安装 Tesseract 可执行文件并复测 `test_tesseract_provider.py`。

## Inventory / Location Roadmap

### 已完成基线

- [x] 解析标准库位编码，例如 `A-A01-011`、`A-A01-023`、`B-C02-032`。
- [x] 支持临时库位、楼上库位、待整理/未识别库位的分类。
- [x] `/api/inventory/location-map` 聚合 A/B 区库位、临时区、楼上区和待整理池。
- [x] `/inventory` 显示 2D 库位图，支持点击库位查看物料。
- [x] 普通登录用户可以查看库存、查看库位图、执行库位调拨。
- [x] 主管/管理员才可以做手动数量校正。
- [x] 库位调拨支持部分数量，不默认移动整库位。
- [x] 当调拨数量大于系统数量时，自动写入 `manual_adjust` 盘点差异，再写出入库位流水。
- [x] Excel 对账 preview API 支持 `matched`、`quantity_mismatch`、`excel_missing`、`excel_new` 分类。
- [x] CSV/XLSX 文件 preview 后端支持 `part_key`、`location_code`、`quantity`、可选 `factory_id`。
- [x] 拣货推荐 API/UI 支持临时库位优先、数量少优先、库位顺序稳定排序。

### P0: 现场 UI 验收和缺陷修复

- [ ] 用真实浏览器验收 `/inventory`：桌面 1366x900/1440x900、手机 390x844。
- [ ] operator 登录后验证：库位地图、库位详情、调拨、对账 preview、拣货推荐都可用。
- [ ] supervisor 登录后验证：数量校正面板可见，operator 不可见。
- [ ] 验证多物料库位：调拨前必须选择具体物料，不允许含糊移动整个库位。
- [ ] 验证超量调拨：现场数量大于系统数量时，系统允许调拨并写盘点差异流水。
- [ ] 验证临时库位清空后隐藏，永久库位清空后保留并提示补货。
- [ ] 检查浏览器 console error、移动端按钮遮挡、表格/卡片文字溢出、滚动可用性。
- [ ] 修复 QA 发现的问题后补静态 HTML/API 测试，必要时补 Playwright smoke。

### P1: Excel 文件上传对账 UI

- [ ] 在 `/inventory` 增加文件上传 preview 面板，调用 `/api/inventory/reconcile/preview-file`。
- [ ] 支持上传 CSV/XLSX 后显示解析行数、文件名、summary 和四类结果。
- [ ] 上传 preview 只读，不写 `InventoryLocation`、`InventoryMovement`、`AuditLog`。
- [ ] 对错误文件给明确提示：缺表头、缺列、数量不是整数、负数、文件类型不支持。
- [ ] 文件 preview 与 JSON rows preview 共用展示组件，避免两套 UI 行为不一致。
- [ ] 保留 JSON rows preview 作为调试/开发入口，现场默认引导使用文件上传。

### P1: 出库拣货工作流集成

- [ ] 将拣货推荐接入出库单/检货单场景，而不是只在库存页手动输入。
- [ ] 电子检货单和纸质出货单字段保持一致，至少包含物料号、名称、需求数量、推荐库位、建议拣货数量。
- [ ] 推荐顺序保持：临时库位优先，其次数量少的先清空，再按 `location_profile.sort_key` 排序。
- [ ] 当推荐库存不足时，在 UI 上明确显示缺口数量，不自动修改库存。
- [ ] 出库扫码成功后，应能反映对应库位库存变化；如果出库模块已有逻辑，优先复用现有出库流水。
- [ ] 暂不做最短路径算法；等 2D 物理通道关系更明确后再加路线优化。

### P1: 对账应用流程

- [ ] 在 preview 之后增加受控 apply 流程，但第一版不要自动覆盖全部差异。
- [ ] `matched` 默认无需操作。
- [ ] `quantity_mismatch` 需要用户确认采用 Excel、采用系统、或进入盘点复核。
- [ ] `excel_missing` 标记为 Excel 缺失，不能自动删除系统库存。
- [ ] `excel_new` 标记为 Excel 新增，不能自动创建正式库存，除非用户确认导入。
- [ ] apply 必须写入流水或审计记录，保留操作者、原因、来源文件名、差异前后数量。
- [ ] apply 权限建议先限制为 supervisor/admin；operator 只能查看 preview 和发起问题标记。
- [ ] 支持把确认后的系统结果导出给人工回填共享 Excel，避免两套来源继续漂移。

### P2: 库位整理和盘点闭环

- [ ] 建立“待整理库位池”：未识别编码、楼上无固定位置、临时库位、混放库位进入整理队列。
- [ ] 混放库位提示应区分“可接受混放”和“建议迁移到 B 区/待整理区”。
- [ ] 支持库位整理任务：选择源库位、目标库位、物料、数量、原因，默认原因是“整理库位”。
- [ ] 支持盘点任务：对某个物料或库位发起盘点，确认后按盘点结果更新系统并生成流水。
- [ ] 支持差异报表：系统数量、盘点数量、Excel 数量、差异来源、最近操作者。
- [ ] 支持永久库位空库存补货提醒和“暂时无货/等待补货”状态。

### P2: 2D 空间关系细化

- [ ] 持续补充 A/B 区空间关系，不依赖 3D 扫描作为唯一事实源。
- [ ] A 区当前规则：`A01` 是 A 列第 1 个架子，向远离大门方向递增；三层；末三位为 `0 + 层 + 近远位`。
- [ ] B 区当前先按同类编码规则解析，C/G/D、E/F、L 区等真实关系后续逐步补齐。
- [ ] 临时库位暂无固定编码，先按关键词和人工备注分类。
- [ ] 楼上区可有编码，但第一版不要求固定到精确物理格位。
- [ ] 先做结构化 2D 地图和可点击库位；拖拽、3D 模型、iPhone LiDAR 只作为后续增强。

### P3: 现场数据治理

- [ ] 建立每日或每次导入的 Excel snapshot 元数据：文件名、导入时间、操作者、行数、hash。
- [ ] 对同一物料/库位保留最近一次 Excel 值、系统值、差异状态和处理状态。
- [ ] 建立“系统外移动”标记：超量调拨、盘点差异、Excel 突变都应能进入差异追踪。
- [ ] 保留整数数量约束；不支持小数库存。
- [ ] 任何库存数量变化都必须通过流水或审计记录可追溯。
