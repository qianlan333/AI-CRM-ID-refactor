from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4p_profile_segment_template_production_dry_run_plan.py"
PLAN_YAML = ROOT / "docs/development/phase_4p_profile_segment_template_production_dry_run_plan.yaml"
PLAN_MD = ROOT / "docs/development/phase_4p_profile_segment_template_production_dry_run_plan.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml() -> dict:
    return _load_module(CHECKER, "phase4p_checker").load_yaml(PLAN_YAML)


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
        "production_repository_enablement_authorized",
        "production_route_ownership_switch_authorized",
        "fallback_removal_authorized",
        "production_compat_change_authorized",
        "production_write_canary_authorized",
        "real_external_call_authorized",
        "delete_ready",
    ):
        assert data[field] is False


def test_preconditions_complete() -> None:
    preconditions = _load_yaml()["preconditions"]
    assert preconditions
    assert all(value is True for value in preconditions.values())


def test_dry_run_levels_0_to_4_exist_and_only_level_0_authorized() -> None:
    levels = {item["level"]: item for item in _load_yaml()["dry_run_levels"]}
    assert set(levels) == {0, 1, 2, 3, 4}
    assert levels[0]["authorized_now"] is True
    assert levels[0]["production_data_access_allowed"] is False
    for level in (1, 2, 3, 4):
        assert levels[level]["authorized_now"] is False
    assert levels[4]["name"] == "production_write_canary"


def test_future_scope_contains_read_only_write_shadow_and_forbidden_items() -> None:
    scope = _load_yaml()["future_scope"]
    assert set(scope["read_only"]) >= {"catalog", "list", "options", "detail"}
    assert set(scope["write_shadow"]) >= {
        "create_validation_only",
        "update_validation_only",
        "idempotency_conflict_simulation",
        "rollback_payload_generation",
    }
    assert set(scope["forbidden"]) >= {
        "route_owner_switch",
        "fallback_removal",
        "production_write_canary",
        "external_call",
        "workflow_activation",
        "automation_execution",
        "customer_pool_state_change",
    }


def test_data_safety_complete() -> None:
    data_safety = _load_yaml()["data_safety"]
    assert data_safety
    assert all(value is True for value in data_safety.values())


def test_evidence_package_complete() -> None:
    required = set(_load_yaml()["evidence_package"]["required"])
    assert required >= {
        "command",
        "config_summary_without_secrets",
        "route_owner_unchanged_evidence",
        "production_compat_retained_evidence",
        "read_parity_summary",
        "validation_shadow_summary",
        "failed_skipped_details",
        "side_effect_safety_summary",
        "fallback_validation",
        "operator_timestamp",
        "owner_signoff",
    }


def test_stop_conditions_complete() -> None:
    assert set(_load_yaml()["stop_conditions"]) >= {
        "production_config_review_incomplete",
        "owner_approval_missing",
        "fallback_validation_failed",
        "side_effect_safety_failed",
        "external_call_detected",
        "route_owner_changed",
        "production_compat_changed",
        "unexpected_write_attempted",
        "secret_redaction_failed",
    }


def test_phase4q_recommendation_blocks_unsafe_next_steps() -> None:
    rec = _load_yaml()["phase_4q_recommendation"]
    assert rec["recommended_next_step"]
    assert rec["production_dry_run_execution_allowed_without_owner_approval"] is False
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
        "production dry-run executed",
        "production repository enabled",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ):
        assert forbidden not in text
