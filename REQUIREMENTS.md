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
- `/admin` — 账号与权限后台
- `/history` — 历史记录页 (筛选, 缩略图, 导出 CSV, 查看原图/OCR 文本)
- `/capture` — 旧桌面 OCR demo，保留为标签录入/历史 OCR 子功能

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
- [ ] 人工核对 5 条 SaaS dry-run 截图
- [ ] 替换 `config/saas_selectors.yaml` 为真实 SaaS URL 和 selector
- [ ] 评估 Chrome 插件或 `/saas-bridge` 作为外部 SaaS 登录态桥接
- [ ] 在 Web 流程稳定后再评估 PyInstaller、NSSM、Windows 服务或 Tauri 启动器
