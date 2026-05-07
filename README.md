# TagLedger

![Status](https://img.shields.io/badge/Status-Factory%20Workbench-brightgreen)
![OS](https://img.shields.io/badge/OS-macOS%20%2F%20Windows-blue)

TagLedger 是面向工厂现场的局域网 Web 工作台：中心 Windows 电脑启动 FastAPI 服务，手机扫码进入移动录入页，其他电脑通过内网浏览器进入账号化工作台。主线目标是把发货单扫码、OCR 标签录入、调拨、统计和账号权限收束到同一个本地优先系统。

当前已接入账号登录、角色化工作台、出库核对、移动扫码、真实 Tesseract OCR、条码识别和 Playwright/SaaS dry-run 提交骨架。旧桌面 OCR demo 保留为 `/capture` 子功能，不再作为产品首页。

## 功能范围

- FastAPI 后端服务
- SQLite 本地数据库
- 初始化页 `/setup`，首次安装创建管理员账号
- 登录页 `/login` 和角色化工作台 `/workbench`
- 首页 `/` 智能入口：未初始化跳 `/setup`，未登录跳 `/login`，已登录跳 `/workbench`
- 现场移动页 `/mobile`，支持扫码、拍照、OCR 和当前发货单录入
- 出库核对页 `/outbound`，按账号权限限制可见发货单
- 调拨页 `/transfers` 和后台管理页 `/admin`
- 图片上传 API，上传时选择品类 `A` / `B` / `C`
- 批量图片上传 API，串行复用单图上传/OCR 入库逻辑
- MockOCR 后台任务，上传后立即返回 `job_id`
- Parser 抽取 `model`、`vin_or_bin`、`serial_number`
- VIN/SN 应用层查重和数据库唯一索引兜底
- 人工确认 API，可修改字段后写入 `confirmed`
- 任务列表 API，支持状态筛选和分页
- CSV 导出 API，支持状态筛选
- 历史记录页，支持状态/关键字/日期筛选、缩略图查看和 CSV 导出
- 旧桌面 OCR demo `/capture`，用于标签录入和历史 OCR 兼容
- Playwright/SaaS 提交骨架，默认 dry-run，不点击真实提交按钮
- parser 和查重单元测试

## 本机启动

```bash
cd /path/to/tagledger
./scripts/run_mac_demo.sh
```

打开：`http://127.0.0.1:8000`

首次安装会进入 `/setup` 创建管理员账号；之后访问 `/` 会按登录状态进入 `/login` 或 `/workbench`。

Finder 双击启动：`Start Mac Demo.command`

端口被占用时另开端口：

```bash
PORT=8010 ./scripts/run_mac_demo.sh
```

先跑一遍测试和依赖安装：

```bash
./scripts/smoke_mac_demo.sh
```

旧 OCR demo 可从 `/capture` 打开。更多本机启动说明见 `MAC_DEMO.md`。

## 局域网现场测试

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

局域网测试阶段默认只做本地扫码、OCR 和本地入库，`config/settings.yaml` 中 `enable_saas_submit: false` 会阻止确认后触发 SaaS/Playwright 提交。

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

启动后访问：`http://127.0.0.1:8000`

局域网手机访问时，把 `127.0.0.1` 换成 Windows 主机局域网 IP。

现场局域网一键启动，推荐用二维码脚本：

```powershell
.\scripts\run_lan.ps1
```

也可以双击 `Start Windows LAN.cmd`。脚本会监听 `0.0.0.0`、自动打印手机访问地址和二维码，手机同一 Wi-Fi 下扫码打开 `/mobile`。

Windows exe 或系统服务包装属于第二阶段交付：先保持 FastAPI + Web UI 的现场流程稳定，再用 PyInstaller、NSSM、Windows 服务或 Tauri 包装启动器。核心服务仍是局域网 Web 工作台，因为手机扫码和多设备访问都依赖浏览器入口。

## Windows 部署

推荐从一键安装脚本开始：

```powershell
.\scripts\install_windows.ps1
.\scripts\run_dev.ps1
```

Tesseract、PATH、防火墙、局域网访问和常见错误处理见 `docs/WINDOWS_DEPLOY.md`。

首次使用出库、调拨和后台管理前，打开 `/setup` 创建第一个管理员账号；之后用 `/login` 登录。

## SaaS 桥接边界

内置 `backend/app/saas/` 是 Playwright dry-run 提交骨架，用于验证第三方页面自动填表流程。Chrome 插件如果后续加入，只作为外部 SaaS/Mammotion 页面中的登录态桥接、填表和附件上传模块，不替代 TagLedger 主工作台。

## Git 同步规则

中心仓库是私有 GitHub 仓库 `https://github.com/wyl2607/tagledger.git`。Mac、Windows 和服务器之间只通过这个 remote 同步代码；本地数据库、上传图片、日志、截图、`.omx/` 和 private docs 不进 Git。

同步规则见 `docs/SYNC_RULES.md`。推送前至少运行：

```bash
./.venv/bin/python -m pytest backend/tests -q
./scripts/security_check.sh
./scripts/review_push_guard.sh origin/main
```

## Phase 1 验证

```powershell
pytest
```

Windows 一键安装依赖并跑测试：

```powershell
.\scripts\smoke_phase1.ps1
```

## 语言支持

主要静态页面支持 English、Deutsch、中文三语切换。页面启动时会按浏览器语言自动选择：`zh*` 使用中文，`de*` 使用德文，其他语言使用英文；用户在顶部 `EN | DE | 中` 切换后会写入 `localStorage`，后续页面保持同一语言。

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

页面右上角提供 `EN | DE | 中文` 切换，覆盖 `/workbench`、`/mobile`、`/history`、`/outbound` 等主要静态页面。选择会保存到浏览器 `localStorage`；也可以用 `?lang=en`、`?lang=de`、`?lang=zh` 指定首次打开语言。

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
