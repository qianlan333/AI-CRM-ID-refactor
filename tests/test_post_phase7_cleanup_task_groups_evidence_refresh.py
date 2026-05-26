from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_task_groups_evidence_refresh as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_cleanup_task_groups_evidence_refresh.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_task_groups_evidence_refresh.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_keep_cleanup_execution_false() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    for key in checker.REQUIRED_AUTHORIZATIONS:
        assert authorizations[key] is False


def test_task_groups_route_family_and_no_behavior_change() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["route_family"] == "/api/admin/automation-conversion/task-groups*"
    assert data["no_behavior_change"] is True


def test_evidence_refresh_records_phase7_blockers() -> None:
    evidence = checker.load_yaml(PLAN_YAML)["evidence"]
    assert evidence["phase7g_fallback_removal_blocked"] is True
    assert evidence["phase7h_production_compat_cleanup_blocked"] is True
    assert evidence["shadow_compare_evidence"] == "missing"
    assert evidence["rollback_execution_evidence"] == "missing"
    assert evidence["route_specific_owner_approval_for_cleanup"] == "missing"


def test_decision_blocks_exact_route_cleanup_without_evidence() -> None:
    decision = checker.load_yaml(PLAN_YAML)["decision"]
    assert decision["ready_for_exact_route_fallback_cleanup"] is False
    assert decision["ready_for_exact_route_production_compat_cleanup"] is False
    assert decision["blocked_with_missing_evidence"] is True
    assert checker.REQUIRED_MISSING_EVIDENCE <= set(decision["missing_evidence"])


def test_no_external_side_effects_are_authorized() -> None:
    evidence = checker.load_yaml(PLAN_YAML)["evidence"]
    assert evidence["no_outbound_send"] is True
    assert evidence["no_timer_execution"] is True
    assert evidence["no_external_live_call"] is True
    assert evidence["no_payment_or_oauth_or_wecom_callback"] is True
    assert evidence["no_public_submit_cutover"] is True


def test_docs_do_not_claim_cleanup_execution() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "fallback removed: true",
        "fallback_removal_executed: true",
        "production_compat behavior changed: true",
        "production_compat_cleanup_executed: true",
        "wildcard cleanup executed",
        "legacy runtime deleted",
        "delete_ready true",
        "delete_ready: true",
    }
    assert not any(claim in text for claim in forbidden_claims)
