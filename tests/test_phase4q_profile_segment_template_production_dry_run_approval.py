from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4q_profile_segment_template_production_dry_run_approval.py"
PLAN_YAML = ROOT / "docs/development/phase_4q_profile_segment_template_production_dry_run_approval.yaml"
PLAN_MD = ROOT / "docs/development/phase_4q_profile_segment_template_production_dry_run_approval.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml() -> dict:
    return _load_module(CHECKER, "phase4q_checker").load_yaml(PLAN_YAML)


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


def test_top_level_flags_false() -> None:
    data = _load_yaml()
    for field in (
        "production_dry_run_execution_authorized",
        "production_data_connection_authorized",
        "production_repository_enablement_authorized",
        "production_route_ownership_switch_authorized",
        "fallback_removal_authorized",
        "production_compat_change_authorized",
        "production_write_canary_authorized",
        "real_external_call_authorized",
        "delete_ready",
    ):
        assert data[field] is False


def test_all_approvals_pending() -> None:
    approval = _load_yaml()["approval"]
    assert approval
    assert all(value == "pending" for value in approval.values())


def test_allowed_future_levels_only_allow_level_1_and_2_requests() -> None:
    levels = _load_yaml()["allowed_future_levels"]
    assert levels["level_1_read_only_parity_can_be_requested"] is True
    assert levels["level_2_validation_shadow_can_be_requested"] is True
    assert levels["level_3_safe_namespace_write_dry_run_can_be_requested"] is False
    assert levels["level_4_write_canary_can_be_requested"] is False


def test_environment_confirmation_complete() -> None:
    env = _load_yaml()["environment_confirmation"]
    assert env
    assert all(value is True for value in env.values())


def test_execution_plan_forbids_writes_and_ci_default() -> None:
    plan = _load_yaml()["execution_plan"]
    assert plan["manual_execution_required"] is True
    assert plan["run_in_ci_by_default"] is False
    assert plan["read_only_first_required"] is True
    assert plan["writes_allowed"] is False
    assert plan["evidence_required"] is True


def test_stop_conditions_complete() -> None:
    assert set(_load_yaml()["stop_conditions"]) >= {
        "owner_approval_missing",
        "production_config_review_incomplete",
        "route_owner_changed",
        "production_compat_changed",
        "fallback_validation_failed",
        "external_call_detected",
        "write_attempted_in_read_only_dry_run",
        "secret_redaction_failed",
        "pii_redaction_failed",
        "side_effect_safety_failed",
        "unexpected_production_data_mutation",
    }


def test_rollback_abort_plan_complete() -> None:
    plan = _load_yaml()["rollback_abort_plan"]
    assert plan
    assert all(value is True for value in plan.values())


def test_evidence_package_complete() -> None:
    required = set(_load_yaml()["evidence_package"]["required"])
    assert required >= {
        "runner_json_report",
        "runner_markdown_report",
        "approval_snapshot",
        "config_summary_without_secrets",
        "route_owner_unchanged_evidence",
        "production_compat_retained_evidence",
        "fallback_validation",
        "read_parity_summary",
        "validation_shadow_summary_if_applicable",
        "skipped_write_blocked_summary",
        "side_effect_safety_summary",
        "redaction_summary",
        "operator_timestamp",
        "owner_signoff",
    }


def test_phase4r_recommendation_only_allows_runner_implementation() -> None:
    rec = _load_yaml()["phase_4r_recommendation"]
    assert rec["recommended_next_step"] == "production_read_only_dry_run_runner_implementation"
    assert rec["production_dry_run_execution_allowed_without_owner_approval"] is False
    assert rec["production_route_switch_allowed"] is False
    assert rec["production_write_canary_allowed"] is False
    assert rec["fallback_removal_allowed"] is False


def test_no_runtime_files_changed_if_git_available() -> None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    assert not any(path.startswith("aicrm_next/") for path in changed)
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)
    assert "app.py" not in changed
    assert "legacy_flask_app.py" not in changed


def test_docs_do_not_claim_forbidden_states() -> None:
    text = PLAN_MD.read_text(encoding="utf-8").lower()
    for forbidden in (
        "production dry-run executed",
        "production data connected",
        "production repository enabled",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ):
        assert forbidden not in text
