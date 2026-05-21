from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_D8_MARKERS = ("delete" + "_ready", "production" + "_ready", "production" + "_approved")


def test_d8_2_preflight_doc_is_present_and_preflight_only() -> None:
    doc = REPO_ROOT / "docs/d8_2_legacy_fallback_route_lockdown_preflight.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert "Status: preflight only." in text
    assert "does not create runtime enforcement" in text
    assert "does not create a `legacy_flask/` archive package" in text
    assert "does not add `wecom_ability_service/legacy_lockdown.py`" in text
    assert "No runtime work is approved by this report" in text
    for marker in FORBIDDEN_D8_MARKERS:
        assert marker not in text


def test_d8_2_preflight_checker_reports_not_ready_without_runtime_changes() -> None:
    checker = importlib.import_module("tools.check_d8_2_legacy_lockdown_preflight")
    report = checker.build_report()
    assert report["ok"] is True, report["hard_failures"]
    assert report["ready_for_enforcement"] is False
    assert report["checks"]["default_next_runtime"] is True
    assert report["checks"]["explicit_fallback"] is True
    assert report["checks"]["legacy_help_ok"] is True
    assert report["checks"]["legacy_import_ok"] is True
    assert report["checks"]["d8_2_runtime_absent"]["legacy_flask"] is True
    assert report["checks"]["d8_2_runtime_absent"]["wecom_ability_service/legacy_lockdown.py"] is True

    blockers = "\n".join(report["readiness_blockers"])
    assert "D1 Media old readonly routes" in blockers
    assert "D6 Automation old readonly routes" in blockers
    assert "operational diagnostics" in blockers


def test_d8_2_preflight_cli_writes_reports(tmp_path: Path) -> None:
    output_md = tmp_path / "preflight.md"
    output_json = tmp_path / "preflight.json"
    completed = subprocess.run(
        [
            sys.executable,
            "tools/check_d8_2_legacy_lockdown_preflight.py",
            "--output-md",
            str(output_md),
            "--output-json",
            str(output_json),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "overall: PASS" in completed.stdout
    assert "ready_for_enforcement: False" in completed.stdout
    assert output_md.exists()
    assert output_json.exists()


def test_d8_2_preflight_keeps_runtime_guard_and_archive_package_absent() -> None:
    assert not (REPO_ROOT / "legacy_flask").exists()
    assert not (REPO_ROOT / "wecom_ability_service/legacy_lockdown.py").exists()
    assert (REPO_ROOT / "legacy_flask_app.py").exists()
    assert (REPO_ROOT / "wecom_ability_service").exists()
    assert (REPO_ROOT / "openclaw_service").exists()


def test_d8_2_preflight_does_not_modify_production_config_paths() -> None:
    checker = importlib.import_module("tools.check_d8_2_legacy_lockdown_preflight")
    report = checker.build_report()
    assert report["checks"]["production_config_changes"] == []
