from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4l_profile_segment_template_staging_smoke_plan.py"
PLAN_YAML = ROOT / "docs/development/phase_4l_profile_segment_template_staging_smoke_plan.yaml"
PLAN_MD = ROOT / "docs/development/phase_4l_profile_segment_template_staging_smoke_plan.md"


def _load_yaml() -> dict:
    spec = importlib.util.spec_from_file_location("phase4l_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_yaml(PLAN_YAML)


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


def test_staging_prerequisites_complete() -> None:
    prereq = _load_yaml()["staging_prerequisites"]
    assert prereq["db_url_required"] is True
    assert {"staging", "stage", "test", "local", "dev"} <= set(prereq["db_url_allowed_markers"])
    assert prereq["companion_tables_required"] is True
    assert prereq["main_tables_required"] is True
    assert {"AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND", "AICRM_PROFILE_SEGMENT_TEMPLATE_DATABASE_URL"} <= set(
        prereq["feature_flags_required"]
    )
    assert prereq["production_route_owner_unchanged"] is True
    assert prereq["production_compat_retained"] is True


def test_smoke_matrix_complete() -> None:
    matrix = _load_yaml()["smoke_matrix"]
    assert set(matrix["read"]) >= {"catalog", "list", "options", "detail"}
    assert set(matrix["write"]) >= {
        "create_with_idempotency",
        "create_replay",
        "create_conflict",
        "duplicate_template_rejected",
        "update_existing",
        "update_missing",
        "invalid_payload_rejected",
        "dangerous_field_rejected",
        "audit_log_created",
        "rollback_payload_present",
        "side_effect_safety_false",
        "fallback_unchanged",
    }


def test_safe_namespace_and_execution_rules() -> None:
    data = _load_yaml()
    namespace = data["safe_namespace"]
    assert namespace["template_code_prefix"]
    assert namespace["operator"]
    assert namespace["idempotency_key_prefix"]
    assert namespace["cleanup_strategy"]
    assert namespace["delete_required"] is False

    rules = data["execution_rules"]
    assert rules["manual_approval_required"] is True
    assert rules["run_in_ci_by_default"] is False
    assert rules["production_db_forbidden"] is True
    assert rules["external_calls_forbidden"] is True
    assert rules["automation_execution_forbidden"] is True
    assert rules["outbound_send_forbidden"] is True
    assert rules["customer_pool_state_change_forbidden"] is True


def test_failure_handling_owner_approval_and_phase4m() -> None:
    data = _load_yaml()
    handling = data["failure_handling"]
    for field in (
        "stop_on_first_write_failure",
        "feature_flag_disable_required",
        "rollback_required",
        "audit_review_required",
        "fallback_validation_required",
    ):
        assert handling[field] is True
    assert all(value == "pending" for value in data["owner_approval"].values())
    recommendation = data["phase_4m_recommendation"]
    assert recommendation["recommended_next_step"]
    assert recommendation["production_dry_run_allowed"] is False
    assert recommendation["production_route_switch_allowed"] is False
    assert recommendation["production_write_canary_allowed"] is False


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
