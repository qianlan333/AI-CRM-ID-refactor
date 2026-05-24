from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4aa_action_templates_implementation_plan.py"
DOC = ROOT / "docs/development/phase_4aa_action_templates_implementation_plan.md"
YAML = ROOT / "docs/development/phase_4aa_action_templates_implementation_plan.yaml"
AUTH_FIELDS = {
    "runtime_change_authorized",
    "production_repository_authorized",
    "migration_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "delete_ready",
}
OUT_OF_SCOPE = {
    "run_due",
    "automation_execution",
    "outbound_send",
    "wecom_external_call",
    "openclaw_call",
    "mcp_real_call",
    "timer",
    "workflow_activation",
    "customer_pool_state_change",
    "agent_runtime_execution",
    "fallback_removal",
    "production_compat_narrowing",
}
GUARDRAILS = {
    "idempotency_required_for_create",
    "duplicate_protection_required",
    "audit_operator_identity_required",
    "before_after_snapshot_required_for_update",
    "rollback_payload_required",
    "dangerous_fields_rejected",
    "no_real_external_side_effect",
    "no_automation_execution",
    "fallback_retained",
    "checker_required",
    "smoke_required",
}
REPOSITORY_OPTIONS = {
    "reuse_legacy_tables",
    "legacy_service_adapter",
    "new_next_tables",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4aa_action_templates_implementation_plan.md",
    "docs/development/phase_4aa_action_templates_implementation_plan.yaml",
    "tools/check_phase4aa_action_templates_implementation_plan.py",
    "tests/test_phase4aa_action_templates_implementation_plan.py",
    "tools/check_phase4z_profile_segment_template_approval_wait_and_next_candidate.py",
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
    spec = importlib.util.spec_from_file_location("phase4aa_checker", CHECKER)
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


def test_authorizations_all_false() -> None:
    auth = _load_yaml()["authorizations"]
    for field in AUTH_FIELDS:
        assert auth[field] is False


def test_route_family_and_owner_correct() -> None:
    data = _load_yaml()
    assert data["route_family"] == "/api/admin/automation-conversion/action-templates*"
    assert data["capability_owner"] == "aicrm_next.automation_engine"
    assert data["integration_fallback_boundary"] == "aicrm_next.integration_gateway"


def test_legacy_discovery_documented_or_explicitly_needs_confirmation() -> None:
    discovery = _load_yaml()["legacy_discovery"]
    assert discovery["status"] in {"documented", "needs_legacy_confirmation"}
    if discovery["status"] == "documented":
        assert discovery["routes"]
        assert discovery["services"]
    assert discovery["persistence"]["status"] in {"documented", "needs_legacy_confirmation"}


def test_scope_excludes_dangerous_side_effect_categories() -> None:
    scope = _load_yaml()["scope"]
    assert _items(scope["in_scope"])
    assert OUT_OF_SCOPE <= set(scope["out_of_scope"])


def test_native_contract_exists_or_marks_needs_confirmation() -> None:
    contract = _load_yaml()["native_contract"]
    assert contract["status"] in {"proposed", "needs_legacy_confirmation"}
    assert contract["fields"] or contract["status"] == "needs_legacy_confirmation"


def test_guardrails_all_true() -> None:
    guardrails = _load_yaml()["required_guardrails"]
    for field in GUARDRAILS:
        assert guardrails[field] is True


def test_repository_strategy_includes_three_options() -> None:
    strategy = _load_yaml()["repository_strategy"]
    assert strategy["selected_strategy"] or strategy["selection_status"]
    option_ids = {option["id"] for option in strategy["options"]}
    assert REPOSITORY_OPTIONS <= option_ids


def test_phase_4ab_recommendation_forbids_high_risk_next_steps() -> None:
    rec = _load_yaml()["phase_4ab_recommendation"]
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
        "runtime implemented",
        "production repository enabled",
        "production write authorized",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ]
    for phrase in forbidden:
        assert phrase not in text
