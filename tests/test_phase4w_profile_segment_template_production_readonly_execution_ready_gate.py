from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4w_profile_segment_template_production_readonly_execution_ready_gate.py"
PLAN_YAML = ROOT / "docs/development/phase_4w_profile_segment_template_production_readonly_execution_ready_gate.yaml"
PLAN_MD = ROOT / "docs/development/phase_4w_profile_segment_template_production_readonly_execution_ready_gate.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml() -> dict:
    return _load_module(CHECKER, "phase4w_checker").load_yaml(PLAN_YAML)


def test_checker_current_repo_passes() -> None:
    proc = subprocess.run(
        ["python3", str(CHECKER.relative_to(ROOT))],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout
    assert "overall: PASS" in proc.stdout


def test_yaml_top_level_flags_false() -> None:
    data = _load_yaml()
    for field in (
        "production_dry_run_execution_authorized",
        "production_data_connection_authorized",
        "production_write_authorized",
        "production_repository_route_enablement_authorized",
        "production_route_ownership_switch_authorized",
        "fallback_removal_authorized",
        "production_compat_change_authorized",
        "production_write_canary_authorized",
        "real_external_call_authorized",
        "delete_ready",
    ):
        assert data[field] is False


def test_blocker_history_complete() -> None:
    history = _load_yaml()["blocker_history"]
    assert all(value is True for value in history.values())


def test_approval_closure_pending() -> None:
    approvals = _load_yaml()["approval_closure"]
    assert approvals
    assert all(value == "pending" for value in approvals.values())


def test_config_closure_complete() -> None:
    config = _load_yaml()["config_closure"]
    assert config
    assert all(value is True for value in config.values())


def test_execution_ready_false_with_missing_items_and_unblock_actions() -> None:
    ready = _load_yaml()["execution_ready"]
    assert ready["ready_for_phase_4x_execution"] is False
    assert ready["missing_items"]
    assert ready["unblock_actions"]


def test_phase_4x_constraints_forbid_unsafe_work() -> None:
    constraints = _load_yaml()["phase_4x_constraints"]
    assert constraints["read_only_only"] is True
    assert constraints["create_update_delete_forbidden"] is True
    assert constraints["production_write_forbidden"] is True
    assert constraints["route_switch_forbidden"] is True
    assert constraints["fallback_removal_forbidden"] is True
    assert constraints["production_compat_change_forbidden"] is True
    assert constraints["external_calls_forbidden"] is True


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    changed, _warnings = _load_module(CHECKER, "phase4w_checker_scope")._changed_files_from_git()
    protected_prefixes = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "systemd/", "nginx/")
    protected_exact = {"app.py", "legacy_flask_app.py"}
    assert not [
        path
        for path in changed
        if path in protected_exact or any(path.startswith(prefix) for prefix in protected_prefixes)
    ]


def test_docs_do_not_claim_forbidden_states() -> None:
    text = PLAN_MD.read_text(encoding="utf-8").lower()
    for forbidden in (
        "production dry-run executed",
        "production data connected",
        "production write executed",
        "production repository enabled as route owner",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ):
        assert forbidden not in text
