from __future__ import annotations

from pathlib import Path

import tools.check_phase6b_task_groups_owner_switch_canary_plan as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_6b_task_groups_owner_switch_canary_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_6b_task_groups_owner_switch_canary_plan.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_required_yaml_fields_and_route_identity() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_TOP_LEVEL <= set(data)
    assert data["route_family"] == "/api/admin/automation-conversion/task-groups*"
    assert data["capability_owner"] == "aicrm_next.automation_engine"
    assert data["proposed_owner"] == "aicrm_next.automation_engine"


def test_no_owner_switch_execution_or_runtime_boundary_change() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["owner_switch_execution_authorized"] is False
    assert data["production_compat_unchanged"] is True
    assert data["fallback_retained"] is True
    assert data["canary_plan"]["default_owner_switch_allowed"] is False
    assert data["canary_plan"]["production_compat_behavior_change_allowed"] is False
    assert data["canary_plan"]["fallback_removal_allowed"] is False


def test_shadow_compare_and_rollback_are_required() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["shadow_compare_required"] is True
    assert data["rollback_required"] is True
    assert data["shadow_compare_plan"]["default_blocked"] is True
    assert data["shadow_compare_plan"]["required_evidence"]
    assert data["rollback_plan"]["required"] is True
    assert data["rollback_plan"]["fallback_must_remain"] is True
    assert data["rollback_plan"]["destructive_migration_required"] is False


def test_phase6b_forbids_timer_execution_send_and_delete_ready() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["timer_execution_authorized"] is False
    assert data["automation_execution_authorized"] is False
    assert data["outbound_send_authorized"] is False
    assert data["delete_ready"] is False


def test_next_bundle_is_phase6c_without_execution_authorization() -> None:
    next_bundle = checker.load_yaml(PLAN_YAML)["next_bundle"]
    assert next_bundle["recommended_next_step"] == "phase_6c_task_groups_owner_switch_tooling_bundle"
    assert next_bundle["owner_switch_execution_allowed"] is False
    assert next_bundle["production_compat_change_allowed"] is False
    assert next_bundle["fallback_removal_allowed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "owner switch executed",
        "fallback removed",
        "production_compat changed",
        "timer enabled",
        "automation execution enabled",
        "outbound send enabled",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
