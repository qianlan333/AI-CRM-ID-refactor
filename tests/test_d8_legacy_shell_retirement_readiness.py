from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_D8_MARKERS = ("delete" + "_ready", "production" + "_ready", "production" + "_approved")


def test_d8_0_docs_are_planning_only_and_keep_fallbacks() -> None:
    plan = (REPO_ROOT / "docs/d8_legacy_flask_shell_retirement_plan.md").read_text(encoding="utf-8")
    inventory = (REPO_ROOT / "docs/d8_legacy_shell_dependency_inventory.md").read_text(encoding="utf-8")
    matrix = (REPO_ROOT / "docs/d8_legacy_shell_allowed_fallback_matrix.md").read_text(encoding="utf-8")
    combined = "\n".join([plan, inventory, matrix])

    assert "Status: planning/readiness only." in plan
    assert "No D8 shell deletion" in plan
    assert "No D8.2-D8.5 work" in plan
    assert "No `legacy_flask/` package creation" in plan
    assert "No runtime route lockdown implementation" in plan
    assert "Default AI-CRM Next entry" in inventory
    assert "explicit legacy fallback commands" in inventory
    assert "not runtime enforcement" in matrix
    for path in ("legacy_flask_app.py", "wecom_ability_service/__init__.py", "openclaw_service/"):
        assert path in combined


def test_d8_0_deletion_gate_lists_required_evidence_without_claiming_ready() -> None:
    plan = (REPO_ROOT / "docs/d8_legacy_flask_shell_retirement_plan.md").read_text(encoding="utf-8")
    for required in [
        "D7 real external replacement evidence",
        "Production observation window",
        "No legacy route hits",
        "Rollback no longer requires Flask shell",
        "Deploy/systemd Next-only path",
        "Human signoff",
    ]:
        assert required in plan
    for marker in FORBIDDEN_D8_MARKERS:
        assert marker not in plan


def test_d8_0_checker_passes_and_protects_runtime_shape() -> None:
    checker = importlib.import_module("tools.check_d8_legacy_shell_retirement_readiness")
    report = checker.build_report()
    assert report["ok"] is True, report["blockers"]
    assert report["checks"]["default_next_runtime"] is True
    assert report["checks"]["explicit_fallback"] is True
    assert report["checks"]["absent_runtime_paths"]["legacy_flask"] is True
    assert report["checks"]["absent_runtime_paths"]["wecom_ability_service/legacy_lockdown.py"] is True

    completed = subprocess.run(
        [
            sys.executable,
            "tools/check_d8_legacy_shell_retirement_readiness.py",
            "--output-md",
            "/tmp/d8_legacy_shell_readiness.md",
            "--output-json",
            "/tmp/d8_legacy_shell_readiness.json",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "overall: PASS" in completed.stdout


def test_d8_0_protected_fallback_files_still_exist() -> None:
    for path in [
        "app.py",
        "legacy_flask_app.py",
        "wecom_ability_service",
        "wecom_ability_service/__init__.py",
        "wecom_ability_service/routes.py",
        "wecom_ability_service/http/__init__.py",
        "openclaw_service",
    ]:
        assert (REPO_ROOT / path).exists(), path

    assert not (REPO_ROOT / "legacy_flask").exists()
    assert not (REPO_ROOT / "wecom_ability_service/legacy_lockdown.py").exists()


def test_d8_0_docs_do_not_use_forbidden_readiness_markers() -> None:
    for path in [
        REPO_ROOT / "docs/d8_legacy_flask_shell_retirement_plan.md",
        REPO_ROOT / "docs/d8_legacy_shell_dependency_inventory.md",
        REPO_ROOT / "docs/d8_legacy_shell_allowed_fallback_matrix.md",
    ]:
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_D8_MARKERS:
            assert marker not in text, path
