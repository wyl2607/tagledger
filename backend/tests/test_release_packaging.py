from pathlib import Path


def test_release_scripts_fail_closed_on_forbidden_entries() -> None:
    shell_script = Path("scripts/make_release.sh").read_text(encoding="utf-8")
    powershell_script = Path("scripts/make_release.ps1").read_text(encoding="utf-8")

    assert "forbidden_entries=$(" in shell_script
    assert "exit 1" in shell_script
    assert "data/outbound/" in shell_script
    assert "data/ocr-scratch/" in shell_script
    assert "docs/private/" in shell_script
    assert "PRIVATE_REQUIREMENTS/" in shell_script
    assert "data/[^/]+\\.xlsx" in shell_script
    assert "|| true" not in shell_script

    assert "$ForbiddenEntries" in powershell_script
    assert "Write-Error" in powershell_script
    assert "data/outbound/" in powershell_script
    assert "data/ocr-scratch/" in powershell_script
    assert "docs/private" in powershell_script
    assert "PRIVATE_REQUIREMENTS" in powershell_script
    assert "data/[^/]+\\.xlsx" in powershell_script


def test_windows_lan_startup_script_exposes_qr_and_stale_port_checks() -> None:
    script = Path("scripts/run_lan.ps1").read_text(encoding="utf-8")
    qr_script = Path("scripts/print_lan_qr.py").read_text(encoding="utf-8")
    launcher = Path("Start Windows LAN.cmd").read_text(encoding="utf-8")

    assert "--host', '0.0.0.0'" in script
    assert "[string]$Page = 'mobile'" in script
    assert "/api/outbound/summary" in script
    assert "qrcode[pil]>=8.0" in script
    assert "scripts\\print_lan_qr.py" in script
    assert "Phone / scanner:" in script
    assert "[switch]$Help" in script
    assert "Stop-Process" not in script
    assert "taskkill" not in script
    assert "scripts\\run_lan.ps1" in launcher
    assert "ExecutionPolicy Bypass" in launcher
    assert "qrcode.QRCode" in qr_script


def test_docs_describe_smart_entry_and_legacy_capture_boundary() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    windows_deploy = Path("docs/WINDOWS_DEPLOY.md").read_text(encoding="utf-8")

    assert "首页 `/` 智能入口" in readme
    assert "未初始化跳 `/setup`，未登录跳 `/login`，已登录跳 `/workbench`" in readme
    assert "旧桌面 OCR demo 保留为 `/capture`" in readme
    assert "手机同一 Wi-Fi 下扫码打开 `/mobile`" in readme
    assert "`/setup`" in windows_deploy
    assert "`/login`" in windows_deploy
    assert "`/workbench`" in windows_deploy
    assert "`/capture`" in windows_deploy


def test_github_preflight_workflow_runs_required_local_gates() -> None:
    workflow = Path(".github/workflows/preflight.yml").read_text(encoding="utf-8")

    assert "name: preflight" in workflow
    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "python-version: '3.12'" in workflow
    assert 'python -m pip install -e ".[dev,barcode,ocr]"' in workflow
    assert "ruff check backend scripts" in workflow
    assert "python -m pytest backend/tests -q" in workflow


def test_public_docs_do_not_include_private_local_paths_or_tokens() -> None:
    public_text = "\n".join(
        Path(path).read_text(encoding="utf-8") for path in ("README.md", "docs/WINDOWS_DEPLOY.md")
    )

    assert "/Users/" + "yumei" not in public_text
    assert "192." + "168." not in public_text
    assert "sk-" not in public_text
    assert "OPENAI_API_KEY" not in public_text
