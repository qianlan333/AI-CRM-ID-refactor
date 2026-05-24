from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4z_profile_segment_template_approval_wait_and_next_candidate.py"
DOC = ROOT / "docs/development/phase_4z_profile_segment_template_approval_wait_and_next_candidate.md"
YAML = ROOT / "docs/development/phase_4z_profile_segment_template_approval_wait_and_next_candidate.yaml"
REQUIRED_ASSETS = {
    "next_native_contract",
    "companion_schema",
    "sql_alchemy_adapter_behind_flag",
    "local_test_db_parity_harness",
    "staging_smoke_package",
    "production_readonly_runner",
    "production_readonly_preflight",
    "final_gate",
}
REQUIRED_BLOCKERS = {
    "owner_approval_missing",
    "production_config_review_missing",
    "production_db_env_not_confirmed",
    "read_only_no_write_flags_not_confirmed",
    "rollback_owner_not_assigned",
    "evidence_path_not_agreed",
    "fallback_validation_plan_not_confirmed",
}
REQUIRED_RESUME = {
    "automation_engine_owner_approval",
    "integration_gateway_owner_approval",
    "db_config_owner_approval",
    "business_owner_approval",
    "rollback_owner_assigned",
    "dry_run_operator_assigned",
    "release_config_reviewer_approval",
    "security_data_reviewer_approval",
    "production_config_review_completed",
    "production_db_env_confirmed",
    "read_only_flags_confirmed",
    "evidence_path_confirmed",
    "fallback_validation_plan_confirmed",
    "secret_redaction_confirmed",
    "pii_redaction_confirmed",
}
AUTH_FIELDS = {
    "production_dry_run_execution_authorized",
    "production_data_connection_authorized",
    "production_write_authorized",
    "production_repository_route_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4z_profile_segment_template_approval_wait_and_next_candidate.md",
    "docs/development/phase_4z_profile_segment_template_approval_wait_and_next_candidate.yaml",
    "tools/check_phase4z_profile_segment_template_approval_wait_and_next_candidate.py",
    "tests/test_phase4z_profile_segment_template_approval_wait_and_next_candidate.py",
    "tools/check_phase4y_profile_segment_template_production_readonly_preflight.py",
    "tools/check_phase4x_profile_segment_template_production_readonly_final_gate.py",
    "tools/check_phase4w_profile_segment_template_production_readonly_execution_ready_gate.py",
    "tools/check_phase4v_profile_segment_template_production_readonly_execution_blocker_and_readiness.py",
}
PROTECTED_PREFIXES = (
    "aicrm_next/",
    "wecom_ability_service/",
    "migrations/",
    "deploy/",
    "systemd/",
    "nginx/",
)
PROTECTED_EXACT = {"app.py", "legacy_flask_app.py"}


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _load_yaml(path: Path = YAML) -> dict:
    spec = importlib.util.spec_from_file_location("phase4z_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_yaml(path)


def _items(values: list) -> set[str]:
    result = set()
    for item in values:
        result.add(str(item.get("item") if isinstance(item, dict) else item))
    return result


def test_checker_current_repo_passes() -> None:
    proc = _run([sys.executable, str(CHECKER)])
    assert proc.returncode == 0, proc.stdout
    assert "overall: PASS" in proc.stdout


def test_profile_segment_template_status_is_approval_wait() -> None:
    profile = _load_yaml()["profile_segment_template"]
    assert profile["status"] == "awaiting_production_approval_config"


def test_authorizations_false() -> None:
    data = _load_yaml()
    profile = data["profile_segment_template"]
    assert profile["production_dry_run_executed"] is False
    assert profile["production_route_owner_switch_authorized"] is False
    assert profile["fallback_removal_authorized"] is False
    assert profile["production_write_authorized"] is False
    assert profile["delete_ready"] is False
    for field in AUTH_FIELDS:
        assert data["authorizations"][field] is False


def test_completed_assets_include_required_assets() -> None:
    profile = _load_yaml()["profile_segment_template"]
    assert REQUIRED_ASSETS <= set(profile["completed_assets"])


def test_blockers_and_resume_conditions_complete() -> None:
    profile = _load_yaml()["profile_segment_template"]
    assert REQUIRED_BLOCKERS <= set(profile["blockers"])
    assert REQUIRED_RESUME <= set(profile["resume_conditions"])


def test_next_candidate_selected_and_valid() -> None:
    candidate = _load_yaml()["next_candidate"]
    assert candidate["selected_route_family"] == "/api/admin/automation-conversion/action-templates*"
    assert candidate["capability_owner"] == "aicrm_next.automation_engine"
    assert candidate["replacement_phase"] == "phase_4_internal_write"
    assert candidate["replacement_category"] == "internal_write"
    assert candidate["rollback_requirement"]
    assert candidate["business_continuity_requirement"]


def test_next_candidate_excludes_high_risk_side_effects() -> None:
    candidate = _load_yaml()["next_candidate"]
    excluded = _items(candidate["excluded_side_effects"])
    required = {
        "payment",
        "oauth",
        "wecom external",
        "callback",
        "run-due",
        "timer",
        "execution",
        "send",
        "upload",
        "openclaw",
        "mcp",
        "public submit",
        "external push",
    }
    assert required <= excluded


def test_phase_4aa_recommendation_forbids_high_risk_next_steps() -> None:
    rec = _load_yaml()["phase_4aa_recommendation"]
    assert rec["recommended_next_step"]
    assert rec["production_write_allowed"] is False
    assert rec["production_route_switch_allowed"] is False
    assert rec["fallback_removal_allowed"] is False
    assert rec["production_write_canary_allowed"] is False


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    changed = set()
    for command in (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        proc = _run(command)
        if proc.returncode != 0:
            continue
        changed.update(line.strip() for line in proc.stdout.splitlines() if line.strip())
    unexpected = changed - ALLOWED_CHANGED_FILES
    protected = {
        path
        for path in changed
        if path not in ALLOWED_CHANGED_FILES
        and (path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES))
    }
    assert unexpected == set()
    assert protected == set()


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "profile-segment-template production dry-run executed",
        "production route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ]
    for phrase in forbidden:
        assert phrase not in text
