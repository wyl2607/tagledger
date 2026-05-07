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
    assert "/api/outbound/summary" in script
    assert "qrcode[pil]>=8.0" in script
    assert "scripts\\print_lan_qr.py" in script
    assert "Phone / scanner" in script
    assert "[switch]$Help" in script
    assert "Stop-Process" not in script
    assert "taskkill" not in script
    assert "ExecutionPolicy Bypass" in launcher
    assert "qrcode.QRCode" in qr_script


def test_public_docs_do_not_include_private_local_paths_or_tokens() -> None:
    public_text = "\n".join(
        Path(path).read_text(encoding="utf-8") for path in ("README.md", "docs/WINDOWS_DEPLOY.md")
    )

    assert "/Users/" + "yumei" not in public_text
    assert "192." + "168." not in public_text
    assert "sk-" not in public_text
    assert "OPENAI_API_KEY" not in public_text
