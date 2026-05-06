# Mammotion 签收 SaaS 集成规格

> 阶段 1 探测产物。在 Windows ARM `guozhen` 笔记本 WSL Ubuntu-26.04 上用 Playwright Python 1.59 + Chromium 147 实测。
> 探测日期：2026-05-06。截图与 storage_state 留在 `~/projects/saas-probe/out/` 不入库。

## 1. 业务流程总览

两设备协同：

```
[Phone] 工人 A 在现场                [PC + 扫码枪] 工人 B 在仓库
  打开手机端拍照页                    扫 Identcode (00)18位
  连续拍多张（箱子/产品背面/SN）      SaaS sweepSign 自动定位单
  IndexedDB 持久保存                  点 Sign for / 进 RMA 详情
  OCR 出 Identcode、Device Name       人工最终确认 + Save
  「一键同步」上传后端                       ▲
                  │                          │
                  ▼                          │
        我们的后端（Identcode 撮合键）────────┘
                  │
                  ▼
        PC Chrome/Edge 扩展（监听 SaaS URL，注入填表 + 拖图上传）
```

撮合键：**Identcode**（DHL 标签上 `(00)` 开头 18 位条码，等同于 Pickup Tracking No.）。

## 2. SaaS 登录流程

### 2.1 三步 OAuth（实测可复用 storage_state）

| 步骤 | URL / 动作 | Selector / 数据 |
|---|---|---|
| 1. 租户填写 | `https://mscs.mammotion.com/` | `input#txt_tenant` ← `mammotionpro`，回车或点 OK |
| 2. Keycloak 重定向 | `https://apeu1.fscloud.com.cn/auth/realms/mammotionpro/protocol/openid-connect/auth?...` | `input#username` ← `info@vitechgmbh.com`；`input#password` ← `<env>`；`button:has-text('Sign In')` |
| 3. 登录后落点 | `https://mscs.mammotion.com/t/mammotionpro/?mainNavName=xrm#/dashboardview` | Dashboard，含 To Sign / To Be Repaired / Pending Delivery 等统计 |

**凭据来源（绝不入库，写本地 `.env` / 1Password）**：
```
SIGNOFF_SAAS_TENANT=mammotionpro
SIGNOFF_SAAS_USERNAME=info@vitechgmbh.com
SIGNOFF_SAAS_PASSWORD=<已提供>
```

storage_state.json 实测可复用，免重复 OAuth；按域名 `*.mammotion.com` + `*.fscloud.com.cn` 分别保存 cookie。

## 3. 关键页面 & Selectors

### 3.1 sweepSign — 扫码触发主页

URL：`https://mscs.mammotion.com/t/mammotionpro/?mainNavName=xrm#/sweepSign/newSweepCodeSign`

| 元素 | Selector | 说明 |
|---|---|---|
| 搜索框 | `input[placeholder^="Please enter No./Device Name/Tracking No./Phone"]` | bbox≈(635,150,516×23)；扫码枪 / 程序填入 Identcode 后回车触发查询 |
| 搜索按钮 | 搜索框右侧蓝色放大镜按钮（同表单提交） | 实测 Enter 也能触发 |
| 结果表头 | `No.` / `Application Category` / `Return Status` / `Contact` / `Phone` / `Pickup Tracking No.` / `SN` / `Product Model` / `Product Name` / `Process Stage` / `Inspection Result` / `Delivery Status` / `Operation` | 列顺序固定 |
| 单号链接 | `a:has-text("TH...")` 或 `a:has-text("DR...")` | 进 RMA 详情页 |
| Operation 列按钮 | `button:has-text("Sign for")` / `button:has-text("Print Labels")` | **Sign for 仅在 Return Status = `To Pick up` 时出现**；状态为 `Tested` 时只剩 Print Labels |

实测：搜 `00340434647786315104` → 命中 `TH202604240102 / Return / Tested / Hendrik Me / 01752010431 / Yuka-VPYE5US8 / Yuka 2025 Series`。
该单已签收完毕，故 Sign for 按钮缺失；要补全 Sign for 弹窗 selectors，需要一个 `To Pick up` 状态的 Identcode（**TODO，等用户给**）。

### 3.2 Sign for 弹窗（Sign for 表单）

> 来自用户实拍 IMG_7607.JPG，Selectors **未在自动化里实测**，待补一轮。

| 字段 | 类型 | 推断 Selector | 备注 |
|---|---|---|---|
| SN Check * | text input | label `text=SN Check` 临近的 `input` | 必填，校验 Device Name 是否吻合（如 `Yuka-VPYE5US8`）|
| Qty. Received | number | 默认 1 | 一般无需改 |
| Material Type | tag (display only) | — | 截图为 `End Product`（绿色 tag）|
| Product Name * | autocomplete | `text=Product Name` 临近 input | 由后端 Identcode 命中后自动带出，**不需要前端填** |
| In Stock * | el-select 下拉 | 见 3.4 默认仓库 | **多个选项，工人长期固定一个**，扩展自动选默认值 |
| Return the accessories | el-select 下拉 | label `text=Return the accessories` | 语义未定，先不动，留 placeholder |
| Return appearance grading | el-select 下拉 | label `text=Return appearance grading` | **A / C 两档**（B 暂不用），手机端拍照前预选 |
| Acceptance result | text | label `text=Acceptance result` | 默认 `--`，不必填 |
| Attachment | 文件上传 | `input[type='file']` 隐藏，可见按钮 `button:has-text('Upload')` 与 `button:has-text('Take photos and upload')` | **多张图，用 `set_input_files()` 批量传，不要走拖拽 UI** |
| Save | submit | `button:has-text('Save')` | 扩展只点 dry-run 不点 Save，直到 5+ 条人工核对通过 |
| Reset | reset | `button:has-text('Reset')` | dry-run 失败回退 |

### 3.3 RMA 详情页

URL 模板：`https://mscs.mammotion.com/t/mammotionpro/?mainNavName=xrm#/vform2/new_srv_rma/productreturn/<uuid>`

实测打开 `ffc05dfc-1d15-0600-c9ee-4c485c000001` → 显示 `RMA TH202604240102 已完成 全部签收`，三个 Tab：

- `Return and exchange information`（默认）
- `Process Information`
- `Old Parts Received`（流程进度）

顶部按钮：`Save` / `Print Waybill` / `Logistics` / `Copy` / `Back`

字段（从截图对照）：

| Section | 字段 |
|---|---|
| Basic Information | Contact phone, Email, Contact name, Customer, Country/Region, State/Province, City, Address, Postal Code, Channel(Shopify), Application Type, Return Method, Pickup Method, Return Reason*, Reason Notes, Site, Order#, 第三方单号, Service rep |
| Products 表格 | 车牌号 / 产品名称* / 备件编码 / 产品型号 / 销退等级 (A/C) / 质保 / Operation |
| Pick-up Info | (滚到下方) |
| 右侧栏 | Processing Progress 时间轴 / New Parts Information / Attachments（已上传图列表 + Download/Delete）|

### 3.4 In Stock 仓库下拉（待补完整选项）

实测探测受阻于 Identcode 已签收。下拉选项需在新单上重新枚举。

**默认值策略**：
- 配置项 `signoff.default_warehouse` 写在 `config/settings.yaml`
- 工人在手机端可临时切换，本次提交生效但不持久（避免误改）
- 长期切换走"设置默认仓库"独立按钮 → 写回 settings + 同步到所有终端

实拍 IMG_7607 中默认值为 `Vitech-DE Defective Warehouse`；正常入库可能是 `Vitech-DE Stock Warehouse` 之类，待用户确认完整列表。

## 4. 单号前缀分类（关键业务规则）

Kundenreferenz / 内部 No. 前两位决定走向：

| 前缀 | 含义 | SaaS 流向 |
|---|---|---|
| `TH` | 退货单（Return） | sweepSign → Sign for → RMA 详情（new_srv_rma/productreturn）|
| `DR` | 维修单（Repair） | 进 Depot Repair 模块 → 不同入口（待补） |

OCR parser 规则：

```regex
^(TH|DR)\d{12,}$
```

匹配后，前端 `flow_type` 自动设为 `return` 或 `repair`，PC 扩展据此选择不同的填表脚本。

## 5. OCR 目标（最简版）

只需识别 **2 个码 + 1 个前缀**：

| 目标 | 来源 | 格式 | 用途 |
|---|---|---|---|
| Identcode | DHL/Colissimo/Deutsche Post 标签右下大 Code128 | `(00)` 开头共 20 位（NVE/SSCC），用户填入搜索框时去括号取 18 位数字 | 撮合键 |
| Device Name | 产品背面铭牌（如 Mammotion YUKA） | `Yuka-XXXXXXXX`、`Luba-XXX` 等品牌前缀 + 8 位字母数字 | 填 SN Check |
| TH/DR 前缀 | DHL 标签上 Kundenreferenz 字段 / 系统内部 No. | `(TH\|DR)\d{12,}` | 路由判定 |

无须识别 Sendungsnummer / Leitcode / Abrechnungsnr 等 DHL 内部码，SaaS 数据库已索引。

## 6. 撮合机制（后端）

```
POST /signoff/photo                   手机端上传一张照片 + 当前选择的 Identcode（OCR/手输）
  → 后端：保存图，按 Identcode 入 Redis Set  signoff:photos:{identcode}
  → 推 WebSocket 通道 ws://.../bridge?identcode={identcode}（PC 扩展订阅）

GET  /signoff/photos?identcode=XXX    PC 扩展拉取该 Identcode 下所有照片元数据
GET  /signoff/photos/{photo_id}/raw   PC 扩展拉单张图（供 set_input_files / FileList API 注入）

WebSocket 事件：
  { type: "photo_ready", identcode, photo_id, ocr: { device_name, prefix } }
  { type: "warehouse_pref", identcode, warehouse, grading }
  { type: "consumed", identcode }     // 扩展填好后回执，后端把照片标记为已用
```

**TTL**：未消费照片保留 7 天，消费后保留 30 天审计可查（与现有 dry-run 截图同期）。

## 7. PC 浏览器扩展职责（Manifest v3）

权限：
- `host_permissions`: `https://mscs.mammotion.com/*`
- `storage`：保存默认仓库 / 默认 grading
- 后台连 WebSocket：`wss://<our-backend>/bridge`

行为：

1. **content_script 注入** sweepSign / RMA 详情页
2. 监听 hash 路由变化（`hashchange`），命中 `#/sweepSign/newSweepCodeSign` 或 `#/vform2/new_srv_rma/productreturn/...` 后激活
3. 从页面 DOM 抓 `Pickup Tracking No.` → 即 Identcode → 问后端要照片
4. 自动操作：
   - **Sign for 弹窗**：若打开 → 填 SN Check → 选 In Stock 默认值 → 选 grading → 上传图（用 `DataTransfer` + `dispatchEvent('change')` 注入 FileList，规避真实拖拽 chromium 限制）
   - **RMA 详情页**：补充上传图到 Attachments
5. 完成后向后端发 `{type:"consumed", identcode}`，本地浮窗显示绿色对勾
6. **绝不点 Save 按钮**——人工最终确认

dry-run 期间：扩展只填字段不上传图，截图保留给人工核对（参考现有 [backend/app/saas/client.py](../backend/app/saas/client.py) 的 dry_run 模式）。

## 8. 跨平台基础设施约束

参见主计划 [`/Users/yumei/.claude/plans/codex-cli-joyful-wozniak.md`](../../../../.claude/plans/codex-cli-joyful-wozniak.md) §跨平台约束。本 spec 不重复，仅强调：

- WSL Ubuntu-26.04 ARM64 上 Playwright 装 Chromium 需 `apt install libnss3 libnspr4 libasound2t64`，且系统校验需用 `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-arm64` 旁路
- 浏览器扩展是 manifest v3，跑在 Edge / Chrome 都行，包内不写绝对路径
- 后端 WebSocket 监听 `0.0.0.0`，OpenVPN 内网即可联调

## 9. 待补漏洞（下一轮探测要素）

| TODO | 具体内容 |
|---|---|
| Sign for 弹窗 selectors 实测 | 用户提供一个 `Return Status = To Pick up` 的 Identcode |
| In Stock 完整选项 | 同上 |
| Return the accessories 选项 + 语义 | 用户口头确认或截图 |
| DR 维修单 SaaS 流向 | 找一个 DR 开头的样本单子探一遍 |
| Sign for 触发后实际网络请求 | 抓 fetch / xhr，看是否能直接调 API（绕开 UI 注入） |
| Sign for 弹窗 Attachment 真实接受文件类型 / 大小限制 | 实测 |

## 10. 验证方式

```bash
# Mac 开发端
source .venv/bin/activate
pytest backend/tests/test_signoff_provider.py
pytest backend/tests/test_identcode_parser.py

# Windows guozhen 上跑端到端
ssh vitec@192.168.1.147
wsl -d Ubuntu-26.04
cd ~/projects/saas-probe && . .venv/bin/activate
python3 probe.py    # storage_state 复用，秒登
```

5 条 dry-run 通过后切真实提交，按主计划阶段 5 走。
