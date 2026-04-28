# Requirements

## Phase 0 + Phase 1

- 建立项目骨架和核心文档。
- 提供 FastAPI 后端，使用 SQLite 持久化记录。
- 支持上传图片并保存到 `data/uploads/`。
- 上传时必须提供品类：`A`、`B`、`C`。
- 上传后立即返回 job/record id，不阻塞等待 OCR。
- 使用 MockOCR 模拟 OCR 输出，真实 OCR 留到 Phase 3。
- Parser 从 OCR 文本抽取 `model`、`vin_or_bin`、`serial_number`。
- 上传阶段和确认阶段都执行 VIN/SN 查重。
- 查重命中时返回旧记录信息，调用方决定覆盖或放弃。
- 确认 API 允许人工修改 OCR 字段后写入数据库。
- 提供 CSV 导出。
- parser 和查重逻辑必须有单元测试。
- 完成后运行 `pytest`。

## 非目标

- 不写前端页面。
- 不接 Tesseract 或其他真实 OCR。
- 不写 Playwright 或 SaaS 自动提交。
- 不写 Playwright 测试。
