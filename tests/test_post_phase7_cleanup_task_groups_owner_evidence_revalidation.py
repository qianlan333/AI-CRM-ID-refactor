from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_task_groups_owner_evidence_revalidation as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_cleanup_task_groups_owner_evidence_revalidation.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_task_groups_owner_evidence_revalidation.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_source_prs_are_recorded() -> None:
    source_prs = checker.load_yaml(PLAN_YAML)["source_prs"]
    for key, expected in checker.REQUIRED_SOURCE_PRS.items():
        assert source_prs[key] == expected


def test_cleanup_authorizations_remain_false() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    assert authorizations["evidence_validation_authorized"] is True
    for key in checker.REQUIRED_FALSE_AUTHORIZATIONS:
        assert authorizations[key] is False


def test_owner_evidence_is_complete() -> None:
    owner = checker.load_yaml(PLAN_YAML)["owner_evidence"]
    assert owner["route_specific_owner_approval"]["status"] == "granted"
    assert owner["route_specific_owner_approval"]["owner"] == "qianlan"
    assert owner["rollback_owner"]["owner"] == "qianlan"
    assert owner["risk_acceptance"]["status"] == "granted_conditionally"
    assert owner["approval_timestamp"]["status"] == "recorded"


def test_pr_813_evidence_is_executed_and_passed() -> None:
    evidence = checker.load_yaml(PLAN_YAML)["evidence_from_pr_813"]
    shadow = evidence["latest_main_shadow_compare"]
    rollback = evidence["rollback_rehearsal"]
    assert shadow["status"] == "passed"
    assert shadow["executed"] is True
    assert shadow["passed"] is True
    assert shadow["production_behavior_changed"] is False
    assert rollback["status"] == "passed"
    assert rollback["executed"] is True
    assert rollback["passed"] is True
    assert rollback["production_behavior_changed"] is False


def test_remaining_evidence_is_complete() -> None:
    evidence = checker.load_yaml(PLAN_YAML)["required_remaining_evidence"]
    route = evidence["route_ownership_proof"]
    compat = evidence["production_compat_exact_entry_proof"]
    assert route["status"] == "collected"
    assert route["proof_path"] == "docs/route_ownership/production_route_ownership_manifest.yaml"
    assert compat["status"] == "collected"
    assert compat["exact_entry_found"] is True
    assert compat["wildcard_cleanup_required"] is False


def test_revalidation_is_ready_for_retry_without_executing_cleanup() -> None:
    data = checker.load_yaml(PLAN_YAML)
    result = data["validation_result"]
    assert result["ready_for_exact_route_fallback_cleanup"] is True
    assert result["ready_for_exact_route_production_compat_cleanup"] is True
    assert result["ready_for_exact_route_cleanup_retry"] is True
    assert result["blocked_reason"] == []
    cleanup = data["cleanup_execution"]
    assert cleanup["fallback_removal_executed"] is False
    assert cleanup["production_compat_cleanup_executed"] is False
    assert cleanup["runtime_deletion_executed"] is False
    assert cleanup["delete_ready"] is False


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
