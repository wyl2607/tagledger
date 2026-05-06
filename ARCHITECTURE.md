# Architecture

## 当前阶段

本仓库当前以 Phase 0 + Phase 1 后端 MVP 为核心。系统最终以 Windows 主机为中心，手机/电脑未来通过局域网浏览器上传图片。为了先做 macOS 本机展示，当前额外挂载了一个极简静态演示页，不引入独立前端工程。

## 目录结构

```text
tagledger/
├── CLAUDE.md / README.md / REQUIREMENTS.md / ARCHITECTURE.md / TODO.md
├── config/
│   ├── settings.yaml
│   └── saas_selectors.yaml
├── backend/app/
│   ├── main.py
│   ├── config.py / database.py / models.py / schemas.py
│   ├── ocr/
│   │   ├── base.py
│   │   ├── mock_provider.py
│   │   ├── tesseract_provider.py
│   │   ├── preprocessor.py
│   │   └── parser.py
│   ├── routes/
│   │   ├── upload.py
│   │   ├── jobs.py
│   │   ├── confirm.py
│   │   └── export.py
│   ├── workers/
│   │   ├── ocr_worker.py
│   │   └── submit_worker.py
│   ├── saas/
│   │   ├── client.py
│   │   └── session.py
│   └── services/
│       ├── file_storage.py
│       ├── dedup.py
│       └── export.py
│   └── static/demo.html       macOS 快速演示页
├── backend/tests/
├── data/{uploads,screenshots,app.db}
├── logs/
└── scripts/{run_dev.ps1,run_mac_demo.sh,smoke_mac_demo.sh}
```

## 状态机

```text
uploaded -> ocr_done -> confirmed
```

Phase 4 会扩展：

```text
confirmed -> submitted | submission_failed
```

## 数据模型

核心表为 `records`，包含图片路径、品类、OCR 字段、原始 OCR 文本、置信度、状态、提交重试字段和时间戳。

数据库层使用两个部分唯一索引兜底；`duplicate` 暂存记录不参与唯一约束，否则无法保存“待用户选择覆盖/放弃”的重复上传：

- `vin_or_bin IS NOT NULL AND status != 'duplicate'` 时唯一
- `serial_number IS NOT NULL AND status != 'duplicate'` 时唯一

## API

- `POST /upload`：保存图片、创建记录、后台执行 MockOCR。
- `GET /jobs`：按状态分页列出记录，列表不返回完整 OCR 原文。
- `GET /jobs/{id}`：查询记录/OCR 状态，含错误和时间戳。
- `POST /confirm/{id}`：人工确认或覆盖重复记录。
- `GET /export.csv`：导出记录 CSV，可用 `status` 筛选。
- `GET /`：macOS 本机快速演示页。

## 后续阶段预留

- `ocr/base.py` 定义 Provider 抽象，未来接 Tesseract/PaddleOCR。
- `workers/submit_worker.py` 和 `saas/` 目前为占位，Phase 4 再接 Playwright。
- `config/saas_selectors.yaml` 目前为空模板，Phase 4 拿到 SaaS 页面后补 selector。
