# Requirements

## 当前阶段: Phase 4 (dry-run), Phase 5 待开始

本系统实现手机/电脑通过局域网浏览器拍照上传机器标签、本地 OCR 识别 Model/VIN-BIN/SN、人工确认后自动填表提交 SaaS 的完整流程。

## 已完成功能

### 后端 API
- FastAPI + SQLite 后端服务
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
- `/mobile` — 手机拍照版 (camera-first, 前端图片压缩, 轮询 OCR, 确认入库)
- `/` — macOS/桌面演示版 (单张/批量上传, 确认, 记录看板)
- `/history` — 历史记录页 (筛选, 缩略图, 导出 CSV, 查看原图/OCR 文本)

### SaaS 提交 (Phase 4)
- Playwright dry-run 骨架 (默认 DRY_RUN=true, 填表+截图, 不真实点击提交)
- Selector 集中在 `config/saas_selectors.yaml`
- 失败自动重试 (3 次, 5s/30s/2min 退避)
- 失败记录 `submission_failed` + 错误截图路径

### 运维
- macOS: `scripts/run_mac_demo.sh`, `Start Mac Demo.command`
- Windows: `scripts/run_dev.ps1`, `scripts/install_windows.ps1`
- 质量检查: `scripts/run_preflight.sh` (ruff + pytest + import check)
- 重试脚本: `scripts/retry_failed.ps1`
- 测试: 64 个测试 (API / parser / dedup / OCR / SaaS / preprocessor / storage / normalize / session)

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

## Phase 5 待完成

- [ ] 人工核对 5 条 dry-run 截图
- [ ] 替换 `config/saas_selectors.yaml` 为真实 SaaS URL 和 selector
- [ ] 设置 `DRY_RUN=false` 环境变量, 启动生产提交
- [ ] 可选: PyInstaller 打包 .exe, 开机自启
