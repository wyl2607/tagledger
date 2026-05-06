# TagLedger

![Status](https://img.shields.io/badge/Status-Phase%204%20dry--run%20%E5%AE%8C%E6%88%90-brightgreen)
![OS](https://img.shields.io/badge/OS-macOS%20%2F%20Windows-blue)

本项目是机器/车辆产品标签 OCR 自动入库系统的 Phase 0 + Phase 1 后端 MVP。目标是先把本地闭环跑通：上传图片、MockOCR、抽取 Model/VIN/SN、查重、人工确认写库、导出 CSV。

当前已接入真实 Tesseract OCR、条码识别和 Playwright/SaaS dry-run 提交骨架。macOS 版提供一个极简演示页用于快速展示，不作为最终前端交付。

## 功能范围

- FastAPI 后端服务
- SQLite 本地数据库
- 图片上传 API，上传时选择品类 `A` / `B` / `C`
- 批量图片上传 API，串行复用单图上传/OCR 入库逻辑
- MockOCR 后台任务，上传后立即返回 `job_id`
- Parser 抽取 `model`、`vin_or_bin`、`serial_number`
- VIN/SN 应用层查重和数据库唯一索引兜底
- 人工确认 API，可修改字段后写入 `confirmed`
- 任务列表 API，支持状态筛选和分页
- CSV 导出 API，支持状态筛选
- macOS 本机极简演示页
- 手机录入页 `/mobile`，支持拍照后自动上传识别、选择图片、OCR 原文查看和本地入库确认
- 历史记录页，支持状态/关键字/日期筛选、缩略图查看和 CSV 导出
- Playwright/SaaS 提交骨架，默认 dry-run，不点击真实提交按钮
- parser 和查重单元测试

## macOS 快速演示

```bash
cd /path/to/tagledger
./scripts/run_mac_demo.sh
```

打开：`http://127.0.0.1:8000`

Finder 双击启动：`Start Mac Demo.command`

端口被占用时另开端口：

```bash
PORT=8010 ./scripts/run_mac_demo.sh
```

先跑一遍测试和依赖安装：

```bash
./scripts/smoke_mac_demo.sh
```

更多说明见 `MAC_DEMO.md`。

## 手机测试

推荐用手机测试脚本启动，它会自动监听局域网并打印 iPhone 可访问地址：

```bash
./scripts/run_mobile_test.sh
```

然后用手机访问脚本打印的 `/mobile` 地址，例如：

```text
http://<电脑局域网IP>:8001/mobile
```

端口被占用时：

```bash
PORT=8010 ./scripts/run_mobile_test.sh
```

开发时如需热重载：

```bash
RELOAD=1 ./scripts/run_mobile_test.sh
```

ADB 有线调试时可用反向端口映射：

```bash
adb reverse tcp:8000 tcp:8000
```

然后在手机浏览器打开：

```text
http://127.0.0.1:8000/mobile
```

手机测试阶段默认只做本地 OCR 和本地入库，`config/settings.yaml` 中 `enable_saas_submit: false` 会阻止确认后触发 SaaS/Playwright 提交。

手机页顶部会显示当前 OCR、条码和 SaaS 提交开关。按「拍照识别」并在相机里确认照片后，会自动压缩、上传并轮询 OCR；「选择图片」保留为手动预览后上传。

清理本地测试数据：

```bash
./scripts/reset_test_data.sh --yes
```

Windows：

```powershell
.\scripts\reset_test_data.ps1 --yes
```

## PowerShell 启动

Windows 完整部署说明见 `docs/WINDOWS_DEPLOY.md`。

```powershell
cd C:\path\to\tagledger
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
.\scripts\run_dev.ps1
```

启动后访问：`http://127.0.0.1:8000/docs`

局域网手机访问时，把 `127.0.0.1` 换成 Windows 主机局域网 IP。

## Windows 部署

推荐从一键安装脚本开始：

```powershell
.\scripts\install_windows.ps1
.\scripts\run_dev.ps1
```

Tesseract、PATH、防火墙、局域网访问和常见错误处理见 `docs/WINDOWS_DEPLOY.md`。

## Phase 1 验证

```powershell
pytest
```

Windows 一键安装依赖并跑测试：

```powershell
.\scripts\smoke_phase1.ps1
```

## 语言支持

三个静态页面 `/`、`/mobile`、`/history` 支持 English、Deutsch、中文三语切换。页面启动时会按浏览器语言自动选择：`zh*` 使用中文，`de*` 使用德文，其他语言使用英文；用户在顶部 `🌐 EN | DE | 中` 切换后会写入 `localStorage`，后续页面保持同一语言。

翻译文件位于 `backend/app/static/i18n/`，中文 `zh.json` 是 source of truth。新增用户可见文本时，先在 `zh.json` 增加扁平 key，再同步到 `en.json` 和 `de.json`，HTML 用 `data-i18n="key"`，占位符用 `data-i18n-placeholder="key"`。

## 示例 API

上传：

```powershell
curl.exe -F "category=A" -F "file=@sample.jpg" http://127.0.0.1:8000/upload
```

批量上传：

```powershell
curl.exe -F "category=A" -F "files=@sample-1.jpg" -F "files=@sample-2.jpg" http://127.0.0.1:8000/upload/batch
```

查询 OCR 任务：

```powershell
curl.exe http://127.0.0.1:8000/jobs/1
```

列出待确认任务：

```powershell
curl.exe "http://127.0.0.1:8000/jobs?status=ocr_done&limit=50&offset=0"
```

确认：

```powershell
curl.exe -X POST http://127.0.0.1:8000/confirm/1 -H "Content-Type: application/json" -d '{"category":"A","model":"MODEL-X","vin_or_bin":"VIN123456","serial_number":"SN123456","duplicate_action":"overwrite"}'
```

导出 CSV：

```powershell
curl.exe -o records.csv http://127.0.0.1:8000/export.csv
```

只导出已确认记录：

```powershell
curl.exe -o confirmed.csv "http://127.0.0.1:8000/export.csv?status=confirmed"
```

## 条形码 / QR 识别

安装：

```bash
brew install zbar && pip install -e ".[barcode]"
```

Windows：

```powershell
pip install -e ".[barcode]"
```

用法示例：

```python
from pathlib import Path
from backend.app.ocr.barcode_provider import BarcodeProvider

results = BarcodeProvider().detect(Path("sample-label.jpg"))
print([(item.type, item.data) for item in results])
```

当前支持 QR / EAN-13 / CODE128；底层使用 pyzbar，可识别 pyzbar 支持的其他码制。

## 语言切换

页面右上角提供 `EN | DE | 中文` 切换，覆盖 `/`、`/history`、`/mobile` 三个静态页面。选择会保存到浏览器 `localStorage`；也可以用 `?lang=en`、`?lang=de`、`?lang=zh` 指定首次打开语言。

## 贡献仪表板

`/dashboard` 展示已入库数量、SaaS 提交数量、重复入库拦截、估算节省工时、OCR 质量和 30 天吞吐趋势。指标 API 位于 `/api/metrics/*`，计算公式见 `docs/CONTRIBUTION_METRICS.md`。

## 脱敏 Release 包

生成可上传/下载的脱敏源码包：

```bash
VERSION=0.1.0 ./scripts/make_release.sh
```

Windows:

```powershell
$env:VERSION='0.1.0'
.\scripts\make_release.ps1
```

输出位于 `dist/release/`。包内不包含本地数据库、上传图片、截图、日志、`.env`、虚拟环境或 git/OMX 元数据。完整说明见 `docs/RELEASE_PACKAGING.md`。
