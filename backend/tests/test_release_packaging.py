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
