# CLAUDE.md

## 项目约束

- 默认用中文沟通。
- 当前产品主线是 TagLedger 工厂局域网 Web 工作台，OCR 和 SaaS 自动化是子模块。
- 不提交 `.env*`、本地数据库、上传图片、日志或截图。
- Git 同步规则以 `docs/SYNC_RULES.md` 为准；不要推送旧 `slice/*` / `claude/*` 本地历史分支。

## 开发命令

```powershell
# Windows
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
.\scripts\run_dev.ps1
.\scripts\run_lan.ps1   # 局域网手机扫码入口，打印 /mobile 二维码
.\scripts\smoke_phase1.ps1
```

```bash
# macOS
source .venv/bin/activate
pip install -e ".[dev,barcode,ocr,submit]"
pytest
./scripts/security_check.sh
./scripts/review_push_guard.sh origin/main
./scripts/run_mac_demo.sh
```

## 架构边界

- `/` 是智能入口：未初始化跳 `/setup`，未登录跳 `/login`，已登录跳 `/workbench`。
- 主工作台页面是 `/workbench`；移动现场入口是 `/mobile`；旧 OCR demo 保留在 `/capture`。
- Windows 交付优先 LAN 一键启动；exe、Windows 服务或 Tauri 启动器属于第二阶段包装，不改变 FastAPI + Web UI 核心。
- `backend/app/ocr/base.py` 是 OCR Provider 抽象入口。
- `backend/app/ocr/tesseract_provider.py` + `barcode_provider.py` 已可用，通过 `config/settings.yaml` 切换。
- `backend/app/services/dedup.py` 是 VIN/SN 查重唯一入口。
- `backend/app/workers/submit_worker.py` 和 `backend/app/saas/` 已接入，默认 `DRY_RUN=true` 只截图不真实提交。
- Chrome 插件只适合作为外部 SaaS/Mammotion 页面自动填表桥接模块，不作为主 App。
- 真实 SaaS 只有生产环境，Playwright 提交前必须人工核对 5 条 dry-run 截图。
- 不提交 `.env*`、本地数据库、上传图片、日志或截图。

## 质量检查

```bash
# macOS
./scripts/run_preflight.sh

# Windows
.\scripts\run_preflight.ps1
```
