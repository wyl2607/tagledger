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


def test_windows_packaging_layout_present() -> None:
    """M2 desktop-beta packaging skeleton exists and references the M1 entry point."""
    spec = Path("packaging/windows/tagledger_server.spec").read_text(encoding="utf-8")
    build = Path("packaging/windows/build_backend.ps1").read_text(encoding="utf-8")
    vendor = Path("packaging/windows/vendor_tesseract.ps1").read_text(encoding="utf-8")
    runtime_reqs = Path("requirements-runtime.txt").read_text(encoding="utf-8")

    # Spec must point at backend/app/cli.py (the M1 launcher entry).
    assert "'backend' / 'app' / 'cli.py'" in spec or "backend/app/cli.py" in spec
    # Onedir, console build, no UPX (AV friendliness).
    assert "console=True" in spec
    assert "upx=False" in spec
    # Tesseract bundle is wired through datas with destination 'tesseract'.
    assert "vendor" in spec and "tesseract" in spec
    # Postgres driver excluded (desktop is SQLite-only); opencv excluded in
    # favor of opencv-python-headless.
    assert "psycopg" in spec
    assert "opencv" in spec

    # Build orchestrator runs vendor → pip install → pyinstaller → smoke.
    assert "vendor_tesseract.ps1" in build
    assert "requirements-runtime.txt" in build
    assert "tagledger_server.spec" in build
    # Smoke must hit /health and assert bad Host returns 421.
    assert "/health" in build
    assert "421" in build

    # Vendor script must verify chi_sim integrity (placeholder OK; mismatch path
    # must throw on first proper run).
    assert "chi_sim.traineddata" in vendor
    assert "SHA256" in vendor.upper()
    assert "throw" in vendor

    # Runtime deps must drop dev-only and Postgres tooling.
    deps = [
        line.strip()
        for line in runtime_reqs.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    deps_blob = "\n".join(deps)
    assert "pytest" not in deps_blob
    assert "ruff" not in deps_blob
    assert "psycopg" not in deps_blob
    assert "uvicorn[standard]" in deps_blob
    assert "pytesseract" in deps_blob


def test_windows_packaging_vendor_directory_excluded() -> None:
    gitignore = Path("packaging/windows/.gitignore").read_text(encoding="utf-8")
    # The downloaded Tesseract binary + tessdata are large and license-bundled
    # separately; they must not enter version control.
    assert "vendor/" in gitignore


def test_public_docs_do_not_include_private_local_paths_or_tokens() -> None:
    public_text = "\n".join(
        Path(path).read_text(encoding="utf-8") for path in ("README.md", "docs/WINDOWS_DEPLOY.md")
    )

    assert "/Users/" + "yumei" not in public_text
    assert "192." + "168." not in public_text
    assert "sk-" not in public_text
    assert "OPENAI_API_KEY" not in public_text
