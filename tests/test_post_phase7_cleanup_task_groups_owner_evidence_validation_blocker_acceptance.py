from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_task_groups_owner_evidence_validation_blocker_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_cleanup_task_groups_owner_evidence_validation_blocker_acceptance.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_task_groups_owner_evidence_validation_blocker_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_are_all_false() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    for key in checker.REQUIRED_AUTHORIZATIONS:
        assert authorizations[key] is False


def test_source_prs_include_validation_pr_811() -> None:
    source_prs = checker.load_yaml(PLAN_YAML)["source_prs"]
    for key, expected in checker.REQUIRED_SOURCE_PRS.items():
        assert source_prs[key] == expected


def test_owner_evidence_is_recorded_but_cleanup_is_not_authorized() -> None:
    data = checker.load_yaml(PLAN_YAML)
    owner = data["owner_evidence_recorded"]
    assert owner["route_specific_owner_approval"] is True
    assert owner["rollback_owner"] == "qianlan"
    assert owner["risk_acceptance"] == "granted_conditionally"
    assert data["validation_result"]["exact_route_cleanup_retry_authorized"] is False


def test_validation_blockers_are_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_EVIDENCE_PASSED <= set(data["evidence_passed"])
    assert checker.REQUIRED_EVIDENCE_FAILED <= set(data["evidence_failed"])
    assert data["validation_result"]["validation_blocked"] is True
    assert data["validation_result"]["ready_for_exact_route_cleanup_retry"] is False


def test_routes_remain_blocked_without_cleanup_execution() -> None:
    routes = checker.load_yaml(PLAN_YAML)["blocked_routes"]
    assert {item["route_family"] for item in routes} == checker.REQUIRED_ROUTES
    for route in routes:
        assert route["ready_for_exact_route_cleanup"] is False
        assert route["fallback_removal_executed"] is False
        assert route["production_compat_cleanup_executed"] is False
        assert route["runtime_deletion_executed"] is False


def test_resume_rules_do_not_allow_cleanup_retry_from_blocker_acceptance() -> None:
    resume = checker.load_yaml(PLAN_YAML)["resume_rules"]
    assert resume["cleanup_track_status"] == "blocked_waiting_task_groups_shadow_and_rollback_evidence"
    assert resume["next_allowed_action_without_complete_evidence"] == "none"
    assert resume["next_if_evidence_complete"] == "post_phase7_cleanup_task_groups_owner_evidence_validation_bundle"
    assert resume["cleanup_retry_must_not_start_from_this_bundle"] is True


def test_docs_do_not_claim_cleanup_execution_or_delete_ready() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "fallback removed: true",
        "production_compat cleaned: true",
        "production_compat behavior changed: true",
        "runtime deleted: true",
        "legacy runtime deleted",
        "delete_ready true",
        "delete_ready: true",
    }
    assert not any(claim in text for claim in forbidden_claims)
