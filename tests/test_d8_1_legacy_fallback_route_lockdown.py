from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_D8_MARKERS = ("delete" + "_ready", "production" + "_ready", "production" + "_approved")


def test_d8_1_docs_are_planning_only_without_runtime_enforcement() -> None:
    plan = (REPO_ROOT / "docs/d8_1_legacy_fallback_route_lockdown_plan.md").read_text(encoding="utf-8")
    matrix = (REPO_ROOT / "docs/d8_1_legacy_fallback_route_matrix.md").read_text(encoding="utf-8")
    combined = plan + "\n" + matrix

    assert "Status: planning/readiness only." in plan
    assert "does not register a runtime guard" in plan
    assert "does not modify Flask route registration" in plan
    assert "This matrix is the D8.1 docs source" in matrix
    assert "does not change route behavior" in matrix
    assert "No runtime guard is registered" in matrix
    for marker in FORBIDDEN_D8_MARKERS:
        assert marker not in combined


def test_d8_1_matrix_covers_high_risk_fallback_categories() -> None:
    matrix = (REPO_ROOT / "docs/d8_1_legacy_fallback_route_matrix.md").read_text(encoding="utf-8")
    for category in [
        "Payment checkout/notify/admin",
        "Questionnaire submit/OAuth/write/external push",
        "User Ops write/WeCom dispatch/deferred jobs",
        "Automation write/webhook/runtime/agent/OpenClaw",
        "Archive/contacts/identity",
        "Media cloud/WeCom upload",
        "MCP/OpenClaw adapter",
        "Legacy shell entry",
    ]:
        assert category in matrix
    assert "keep fallback" in matrix


def test_d8_1_checker_passes_without_runtime_guard_package() -> None:
    checker = importlib.import_module("tools.check_d8_1_legacy_fallback_route_lockdown")
    report = checker.build_report()
    assert report["ok"] is True, report["blockers"]
    assert report["checks"]["planning_only"] is True
    assert report["checks"]["no_runtime_enforcement"] is True
    assert report["checks"]["runtime_guard_absent"] is True
    assert report["checks"]["archive_package_absent"] is True

    completed = subprocess.run(
        [
            sys.executable,
            "tools/check_d8_1_legacy_fallback_route_lockdown.py",
            "--output-md",
            "/tmp/d8_1_legacy_fallback_route_lockdown.md",
            "--output-json",
            "/tmp/d8_1_legacy_fallback_route_lockdown.json",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "overall: PASS" in completed.stdout


def test_d8_1_does_not_create_runtime_lockdown_or_archive_package() -> None:
    assert not (REPO_ROOT / "legacy_flask").exists()
    assert not (REPO_ROOT / "wecom_ability_service/legacy_lockdown.py").exists()
    for protected in ["legacy_flask_app.py", "wecom_ability_service"]:
        assert (REPO_ROOT / protected).exists()
    assert not (REPO_ROOT / "openclaw_service").exists()
