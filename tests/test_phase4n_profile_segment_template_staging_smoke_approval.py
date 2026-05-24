from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4n_profile_segment_template_staging_smoke_approval.py"
PLAN_YAML = ROOT / "docs/development/phase_4n_profile_segment_template_staging_smoke_approval.yaml"
PLAN_MD = ROOT / "docs/development/phase_4n_profile_segment_template_staging_smoke_approval.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml() -> dict:
    return _load_module(CHECKER, "phase4n_checker").load_yaml(PLAN_YAML)


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
        "staging_smoke_execution_authorized",
        "production_data_allowed",
        "production_repository_enablement_authorized",
        "production_route_ownership_switch_authorized",
        "fallback_removal_authorized",
        "production_compat_change_authorized",
        "real_external_call_authorized",
        "delete_ready",
    ):
        assert data[field] is False


def test_all_approvals_pending() -> None:
    approval = _load_yaml()["approval"]
    assert approval
    assert all(value == "pending" for value in approval.values())


def test_environment_confirmation_complete() -> None:
    env = _load_yaml()["environment_confirmation"]
    assert env["staging_db_url_required"] is True
    assert set(env["allowed_db_url_markers"]) >= {"staging", "stage", "test", "local", "dev"}
    assert set(env["forbidden_db_url_markers"]) >= {"prod", "production", "primary", "master"}
    assert set(env["required_feature_flags"]) >= {
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL",
    }
    assert env["database_url_fallback_allowed"] is False
    assert env["production_data_allowed"] is False


def test_execution_plan_requires_manual_dry_run_and_owner_approval() -> None:
    plan = _load_yaml()["execution_plan"]
    assert plan["manual_execution_required"] is True
    assert plan["run_in_ci_by_default"] is False
    assert plan["dry_run_first_required"] is True
    assert plan["execute_writes_requires_owner_approval"] is True
    assert plan["evidence_required"] is True


def test_stop_conditions_complete() -> None:
    assert set(_load_yaml()["stop_conditions"]) >= {
        "db_url_safety_failed",
        "smoke_write_failed",
        "unexpected_idempotency_conflict",
        "audit_row_missing",
        "rollback_payload_missing",
        "side_effect_safety_failed",
        "external_call_detected",
        "production_marker_detected",
        "fallback_validation_failed",
    }


def test_rollback_plan_complete() -> None:
    plan = _load_yaml()["rollback_plan"]
    assert plan["feature_flag_disable_required"] is True
    assert plan["safe_namespace_cleanup_required"] is True
    assert plan["audit_review_required"] is True
    assert plan["evidence_preservation_required"] is True
    assert plan["delete_requires_separate_approval"] is True
    assert plan["fallback_validation_required"] is True


def test_evidence_package_complete() -> None:
    required = set(_load_yaml()["evidence_package"]["required"])
    assert required >= {
        "runner_json_report",
        "runner_markdown_report",
        "db_url_safety_summary_without_secret",
        "smoke_matrix_summary",
        "failed_skipped_details",
        "audit_rollback_evidence",
        "side_effect_safety_summary",
        "operator_timestamp",
        "owner_signoff",
    }


def test_phase4o_recommendation_blocks_unsafe_next_steps() -> None:
    rec = _load_yaml()["phase_4o_recommendation"]
    assert rec["recommended_next_step"]
    assert rec["staging_smoke_execution_allowed_without_owner_approval"] is False
    assert rec["production_dry_run_allowed"] is False
    assert rec["production_route_switch_allowed"] is False
    assert rec["production_write_canary_allowed"] is False


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
        "staging smoke executed",
        "production dry-run authorized",
        "production repository enabled",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ):
        assert forbidden not in text
