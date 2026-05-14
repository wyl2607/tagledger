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
    mobile_script = Path("scripts/run_mobile_test.sh").read_text(encoding="utf-8")
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
    assert "TagLedger factory LAN server" in mobile_script
    assert "Center entry:" in mobile_script
    assert "http://${lan_ip}:${PORT}/" in mobile_script
    assert "Phone picking:" in mobile_script
    assert 'TAGLEDGER_PAIRING_ENABLED="${TAGLEDGER_PAIRING_ENABLED:-0}"' in mobile_script
    assert "Set TAGLEDGER_PAIRING_ENABLED=1" in mobile_script


def test_docs_describe_smart_entry_and_legacy_capture_boundary() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    windows_deploy = Path("docs/WINDOWS_DEPLOY.md").read_text(encoding="utf-8")

    assert "首页 `/` 中心入口" in readme
    assert "初始化后显示所有工具和后续模块占位" in readme
    assert "旧桌面 OCR demo 保留为 `/capture`" in readme
    assert "手机同一 Wi-Fi 下扫码打开 `/mobile`" in readme
    assert "TAGLEDGER_PAIRING_ENABLED=0" in readme
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


def test_desktop_launcher_layout_present() -> None:
    """M3 Tauri launcher exists and is wired to the M2 sidecar bundle."""
    cfg = Path("desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    assert '"productName"' in cfg
    # Must bundle the M2 onedir as a resource (not externalBin; onedir is a folder).
    assert "tagledger-server" in cfg
    assert "externalBin" not in cfg
    # Windows-only beta: msi + nsis, no other targets.
    assert '"msi"' in cfg
    assert '"nsis"' in cfg
    for forbidden in ('"dmg"', '"appimage"', '"deb"', '"rpm"'):
        assert forbidden not in cfg, f"M3 must not enable {forbidden}"

    cargo = Path("desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8")
    # Tauri v2, single-instance plugin wired.
    assert "tauri = " in cargo
    assert "tauri-plugin-single-instance" in cargo

    # Build script must hard-fail if the M2 sidecar bundle is missing,
    # so contributors don't ship a Windows launcher with no backend. macOS is
    # scaffold-only until the signed sidecar bundle lands.
    build_rs = Path("desktop/src-tauri/build.rs").read_text(encoding="utf-8")
    assert "tagledger_server.exe" in build_rs
    assert "dist-macos" in build_rs
    assert "cargo:warning=macOS sidecar bundle missing" in build_rs
    assert "panic!" in build_rs or "compile_error" in build_rs

    gitignore = Path("desktop/.gitignore").read_text(encoding="utf-8")
    for pat in ("target/", "node_modules/", "dist/", "src-tauri/gen/"):
        assert pat in gitignore


def test_public_docs_do_not_include_private_local_paths_or_tokens() -> None:
    public_text = "\n".join(
        Path(path).read_text(encoding="utf-8") for path in ("README.md", "docs/WINDOWS_DEPLOY.md")
    )

    assert f"{chr(47)}Users{chr(47)}" + "example-user" not in public_text
    assert "192." + "168." not in public_text
    assert "sk-" not in public_text
    assert "OPENAI_API_KEY" not in public_text


def test_windows_fleet_files_and_safety_guards_present() -> None:
    deploy_script = Path("scripts/windows_fleet_deploy.sh").read_text(encoding="utf-8")
    devices_example = Path("scripts/windows_fleet_devices.txt.example").read_text(encoding="utf-8")
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "scripts/windows_fleet_devices.txt" in gitignore
    assert "scripts/ai_trigger_fleet_deploy.sh" in gitignore

    assert "windows_fleet_devices.txt.example" not in gitignore
    assert "operator@win-floor-01" in devices_example
    assert "192." + "168." not in devices_example

    assert "mktemp -d" in deploy_script
    assert "/private/tmp" not in deploy_script
    assert "--service-port <int>" in deploy_script
    assert "target[|app_dir][|port]" in deploy_script
    assert "$env:USERPROFILE" in deploy_script
    assert "C:/Users/$user/tagledger" in deploy_script
    assert 'remote_profile="${remote_profile//\\\\//}"' in deploy_script
    assert "findstr 200" not in deploy_script
    assert "$StatusCode" not in deploy_script
    assert "-DetachedTask" in deploy_script
    assert "--open-admin" in deploy_script
    assert "-OpenPath '/admin'" in deploy_script
    assert (
        "Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:$device_port/health'"
        in deploy_script
    )


def test_windows_remote_start_scripts_support_port_and_fail_fast() -> None:
    remote_start = Path("scripts/remote_start_tagledger.ps1").read_text(encoding="utf-8")
    start_cmd = Path("Start TagLedger Service.cmd").read_text(encoding="utf-8")
    remote_diag = Path("scripts/remote_diag_start.ps1").read_text(encoding="utf-8")

    assert "[ValidateRange(1, 65535)]" in remote_start
    assert "[int]$Port = 8000" in remote_start
    assert "TagLedger health check timeout" in remote_start
    assert "TagLedger exited during startup on port" in remote_start
    assert "Invoke-WebRequest -UseBasicParsing -Uri $HealthUri" in remote_start
    assert 'Write-Output "PORT=$Port"' in remote_start
    assert "[switch]$DetachedTask" in remote_start
    assert "[string]$OpenPath = ''" in remote_start
    assert "schtasks.exe /Create" in remote_start
    assert 'Write-Output "TASK=$TaskName"' in remote_start
    assert "Start-Process $OpenUri" in remote_start
    assert 'Write-Output "OPENED=$OpenUri"' in remote_start

    assert "TAGLEDGER_PORT" in start_cmd
    assert "-Port %PORT%" in start_cmd
    assert "uvicorn.err.log" in start_cmd

    assert "param(" in remote_diag
    assert "[int]$Port = 8000" in remote_diag
    assert "--port $Port" in remote_diag


def test_windows_fleet_assets_do_not_embed_private_local_paths() -> None:
    fleet_blob = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "scripts/windows_fleet_deploy.sh",
            "scripts/windows_fleet_devices.txt.example",
            "scripts/remote_start_tagledger.ps1",
            "scripts/remote_diag_start.ps1",
            "docs/WINDOWS_DEPLOY.md",
        )
    )

    assert "/Users/" + "yumei" not in fleet_blob
    assert "192." + "168." not in fleet_blob
    assert "C:\\Users\\vitec" not in fleet_blob


def test_seed_user_account_does_not_embed_site_passwords() -> None:
    script = Path("scripts/seed_user_account.py").read_text(encoding="utf-8")

    assert "TAGLEDGER_USER_PASSWORD" in script
    assert "getpass.getpass" in script
    assert "Picker2026" not in script
    assert "remote_seed_picker96" not in script
    assert "SO202605060078" not in script
