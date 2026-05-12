# Requirements

## 当前阶段: 工厂账号化工作台收束

本系统是局域网 Web 工厂工作台：中心 Windows 电脑启动服务，同事先通过浏览器进入 `/` 中心入口，再选择 `/mobile`、`/outbound`、`/workbench` 或其他子页面。主线是账号化出库核对、现场扫码、调拨、统计和后台管理；OCR 标签录入和 SaaS 自动填表是子模块。

## 已完成功能

### 后端 API
- FastAPI + SQLite 后端服务
- 初始化、登录、会话和账号管理 API (`/api/auth/*`, `/api/admin/*`)
- 工作台 API (`GET /api/workbench`)，按角色返回可见模块、账号范围、本人统计和全局统计
- 出库核对 API，按账号限制可见发货单和扫描记录
- 调拨 API，主管及以上角色可管理跨场子调拨
- 图片上传 API (`POST /upload`, `POST /upload/batch`)，支持品类 A/B/C
- OCR 后台处理 (Tesseract + 图像预处理 + 条码识别)
- 字段 Parser 抽取 Model / VIN-BIN / SN
- VIN/SN 查重 (应用层 + DB 唯一索引)
- 人工确认 API (`POST /confirm/{id}`)
- 任务列表 API (`GET /jobs`)，支持状态筛选和分页
- CSV 导出 API (`GET /export.csv`)，支持状态/关键字/日期筛选
- 原始图片读取 API (`GET /records/{id}/image`)
- 提交失败重试 API (`POST /jobs/retry`, `POST /jobs/retry/{id}`)
- 重启自动扫描 confirmed 记录重新入队

### 前端页面
- `/` — 中心入口；未初始化跳 `/setup`，初始化后显示所有工具入口和未完成模块占位
- `/setup` — 首次安装创建管理员账号
- `/login` — 账号登录
- `/workbench` — 按角色收口的工厂工作台
- `/mobile` — 手机拍照版 (camera-first, 前端图片压缩, 轮询 OCR, 确认入库)
- `/outbound` — 当前账号可见的出库核对页
- `/transfers` — 跨场子调拨页
- `/inventory` — 库存与库位页，包含库存列表、2D 库位图、库位调拨、Excel 对账 preview 和拣货推荐
- `/admin` — 账号与权限后台
- `/history` — 历史记录页 (筛选, 缩略图, 导出 CSV, 查看原图/OCR 文本)
- `/capture` — 旧桌面 OCR demo，保留为标签录入/历史 OCR 子功能

### 库存与库位
- 库存总账与厂区库位图必须放在同一入口 `/inventory`。
- 库存数据按物料、库位、数量进行管理；供应商、订单号不是库存管理第一阶段的关键字段。
- 一个库位可以有多个物料；一个物料也可以分散在多个库位。
- 总账视图可以合并展示同物料总量，但查询“物料在哪里”时必须按库位独立展开。
- 库存数量必须是整数整件，不支持小数数量；CSV/XLSX 导入 preview 遇到小数应拒绝。
- 数量为 0 是合法业务值，尤其用于永久库位补货提醒和 Excel 对账。
- 所有数量变化、库位调拨、盘点差异都必须可追溯到流水或审计记录。
- 普通登录用户可以查看库存、查看库位图、执行库位调拨。
- 主管/管理员才可以执行手动数量校正；开放调拨权限不等于开放手动校正权限。

### 库位编码与空间关系
- 推荐标准库位编码格式为 `A-A01-011`、`A-A01-023`、`B-C02-032`。
- 编码含义：`区域-列架-0层近远位`。
- `A01` 表示 A 列第 1 个架子，`A02` 表示 A 列第 2 个架子；从进门向远处递增。
- 末三位第一位固定为 `0`；第二位表示层数，当前只有 1、2、3 层；第三位表示离厂房中线的近远程度。
- 第三位 `1` 最靠近厂房中线/大门进来的主线，`3` 最远离中线。
- A/B 区先共享同一编码解析规则；B 区真实 C/G/D、E/F、L 区空间关系后续逐步补齐。
- A 区的业务理解：一层多为小件，二层多为储存件，三层多为较重或整箱大件；具体分类可结合物料名称分析。
- 临时库位暂无固定编码，通过 `临时`、`TMP`、`暂存`、`收货口`、`门口`、`地上`、`待入库` 等关键词或人工备注识别。
- 楼上区可有编码，但第一阶段不要求固定到精确货架格位。
- 2D 可计算库位图优先于 3D 模型；iPhone LiDAR、3D 扫描和点云只作为空间理解和后续可视化增强，不作为库存事实源。

### 临时库位、永久库位和补货
- 临时库位用于临时放货、入库暂存或待整理；临时库位清空后应自动隐藏或进入已退役状态。
- 永久库位清空后不能隐藏；必须保留在库位图和列表中，并显示补货/暂时无货提示。
- 永久库位空库存可以由任何登录用户看到，用于提醒入库人员或仓储管理处理。
- 后续应支持“暂时无货”“等待补货”“待整理”等状态，状态变更需要审计。
- 混放库位允许存在，但应被标记；混放过多的库位应进入整理建议。

### 库位调拨和盘点差异
- 库位调拨默认是部分数量移动，不是默认移动整库位。
- 调拨原因默认可以是“整理库位”，用户也可以填写现场原因或备注位置。
- 如果用户调拨数量大于系统源库位数量，系统不应直接拒绝；这代表现场发现系统外移动或历史数量不准。
- 超量调拨流程：先写一条 `manual_adjust` 盘点差异，把源库位数量修正到现场可移动数量，再写 `manual_move_out` 和 `manual_move_in`。
- 超量调拨必须保留操作者、原因、调整前数量、调整后数量和差异数量。
- 如果现场确实有货，系统要允许录入最新事实，但必须通过流水暴露差异。

### Excel 对账和事实源
- Excel 来自共享通讯文档导出，通常较新，但不是唯一真相。
- TagLedger 系统也不是唯一真相；系统和 Excel 在一段过渡期内必须共存并对账。
- 导入 Excel 不能盲目覆盖系统库存，必须先生成 preview。
- 对账分类至少包括：
  - `matched`: Excel 和系统同物料/同库位数量一致。
  - `quantity_mismatch`: Excel 和系统都有，但数量不同。
  - `excel_missing`: 系统有，Excel 没有。
  - `excel_new`: Excel 有，系统没有。
- Excel preview 只读，不修改 `InventoryLocation`、`InventoryMovement` 或 `AuditLog`。
- CSV/XLSX 文件 preview 解析后必须复用同一套 preview 逻辑。
- 后续 apply 流程必须人工确认，不能自动把所有差异写入系统。
- 当专门组织人员盘点某物料或库位时，盘点确认结果可以成为更高优先级事实，并用于更新系统及回填 Excel。
- 后续需要记录每次 Excel snapshot 的文件名、行数、操作者、时间和 hash，便于追踪差异来源。

### 拣货推荐
- 拣货推荐目标是减少找货时间和清理临时库位，不要求第一版做最短路线算法。
- 推荐顺序必须先清临时库位，再在同类库位中优先清数量少的库位，最后按库位空间排序稳定输出。
- 推荐结果应包含库位、可用数量、建议拣货数量、是否临时库位、是否库存不足。
- 库存不足时只显示缺口，不自动修改库存。
- 后续应接入出库单/检货单，使电子检货单和纸质出货单保持一致。
- 出库扫码成功后，应该能反映到对应库位库存；若已有出库模块逻辑，优先复用现有流水和权限模型。

### SaaS / 外部页面桥接
- Playwright dry-run 骨架 (默认 DRY_RUN=true, 填表+截图, 不真实点击提交)
- Selector 集中在 `config/saas_selectors.yaml`
- 失败自动重试 (3 次, 5s/30s/2min 退避)
- 失败记录 `submission_failed` + 错误截图路径
- Chrome 插件只作为外部 SaaS/Mammotion 页面自动填表、上传附件和复用浏览器登录态的桥接模块，不作为主 App

### 运维
- macOS: `scripts/run_mac_demo.sh`, `Start Mac Demo.command`
- Windows: `scripts/run_dev.ps1`, `scripts/run_lan.ps1`, `scripts/install_windows.ps1`, `Start Windows LAN.cmd`
- 质量检查: `scripts/run_preflight.sh` (ruff + pytest + import check)
- 重试脚本: `scripts/retry_failed.ps1`
- LAN 交付优先一键启动和二维码访问；exe、Windows 服务或 Tauri 启动器作为第二阶段包装

## 状态机

```
uploaded → ocr_done → confirmed → submitted
                ↘ needs_review      ↙
                                   submission_failed
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12+ / FastAPI / Uvicorn / SQLModel / SQLite |
| OCR | Tesseract (eng) + pytesseract + OpenCV 预处理 |
| 条码 | pyzbar / zbar |
| SaaS 填表 | Playwright (Chromium, headless, 可选依赖) |
| 前端 | Vanilla HTML/CSS/JS (无框架, 移动端优先) |
| 测试 | pytest + httpx + ruff |

## 下一阶段待完成

- [ ] 收口 `/workbench` 导航和角色模块，减少旧 OCR demo 入口权重
- [ ] 用真实现场账号和发货单验证 `/setup`、`/login`、`/workbench`、`/mobile`、`/outbound`、`/transfers`、`/admin`
- [ ] 用真实库存数据验证 `/inventory` 库位地图、库位调拨、Excel 对账 preview、CSV/XLSX 文件 preview 和拣货推荐
- [ ] 把 `/api/inventory/reconcile/preview-file` 接到 `/inventory` 文件上传 UI
- [ ] 将拣货推荐接入出库单/检货单流程
- [ ] 设计 Excel 对账 apply 流程，要求人工确认和流水审计，不能自动覆盖系统库存
- [ ] 建立待整理库位、混放库位、盘点差异和补货提醒的现场处理闭环
- [ ] 人工核对 5 条 SaaS dry-run 截图
- [ ] 替换 `config/saas_selectors.yaml` 为真实 SaaS URL 和 selector
- [ ] 评估 Chrome 插件或 `/saas-bridge` 作为外部 SaaS 登录态桥接
- [ ] 在 Web 流程稳定后再评估 PyInstaller、NSSM、Windows 服务或 Tauri 启动器
