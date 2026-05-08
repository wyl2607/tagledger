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
