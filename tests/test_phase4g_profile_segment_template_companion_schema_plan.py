from __future__ import annotations

import json

from tools import check_phase4g_profile_segment_template_companion_schema_plan as checker


def test_phase4g_checker_passes_current_repo() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report.get("blockers", []), ensure_ascii=False, indent=2)


def test_phase4g_authorization_flags_false() -> None:
    data = checker.load_yaml()
    for field in checker.AUTH_FALSE_FIELDS:
        assert data[field] is False


def test_phase4g_schema_need_requires_guardrail_storage() -> None:
    result = checker.check_schema_need()
    assert result["ok"], result
    need = checker.load_yaml()["schema_need"]
    assert need["idempotency_storage_required"] is True
    assert need["audit_storage_required"] is True
    assert need["before_after_snapshot_required"] is True


def test_phase4g_idempotency_plan_complete() -> None:
    result = checker.check_idempotency_schema_plan()
    assert result["ok"], result
    plan = checker.load_yaml()["idempotency_schema_plan"]
    fields = {item["name"] for item in plan["required_fields"]}
    assert checker.REQUIRED_IDEMPOTENCY_FIELDS.issubset(fields)
    assert plan["unique_constraints"]
    assert plan["conflict_behavior"]
    assert plan["replay_behavior"]
    assert plan["retention_policy"]


def test_phase4g_audit_plan_complete() -> None:
    result = checker.check_audit_schema_plan()
    assert result["ok"], result
    plan = checker.load_yaml()["audit_schema_plan"]
    fields = {item["name"] for item in plan["required_fields"]}
    assert checker.REQUIRED_AUDIT_FIELDS.issubset(fields)
    assert plan["snapshot_policy"]
    assert plan["rollback_payload_policy"]
    assert plan["retention_policy"]


def test_phase4g_phase4h_recommendation_is_guarded() -> None:
    result = checker.check_phase4h_recommendation()
    assert result["ok"], result
    recommendation = checker.load_yaml()["phase_4h_recommendation"]
    assert recommendation["migration_allowed_without_owner_approval"] is False
    assert recommendation["production_repository_allowed_without_owner_approval"] is False
    assert recommendation["route_switch_allowed"] is False


def test_phase4g_no_runtime_files_changed_if_git_available() -> None:
    result = checker.check_no_runtime_changes()
    assert result["ok"], result


def test_phase4g_docs_do_not_claim_approval_or_cutover() -> None:
    result = checker.check_doc_claims()
    assert result["ok"], result
