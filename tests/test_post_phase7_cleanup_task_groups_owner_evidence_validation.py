from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_task_groups_owner_evidence_validation as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_cleanup_task_groups_owner_evidence_validation.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_task_groups_owner_evidence_validation.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_allow_validation_only() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    assert authorizations["evidence_validation_authorized"] is True
    for key, expected in checker.REQUIRED_AUTHORIZATIONS.items():
        assert authorizations[key] is expected


def test_owner_evidence_is_recorded() -> None:
    owner = checker.load_yaml(PLAN_YAML)["owner_evidence"]
    assert owner["route_specific_owner_approval"]["status"] == "granted"
    assert owner["route_specific_owner_approval"]["owner"] == "qianlan"
    assert owner["rollback_owner"]["owner"] == "qianlan"
    assert owner["risk_acceptance"]["status"] == "granted_conditionally"
    assert owner["approval_timestamp"]["status"] == "recorded"


def test_shadow_compare_and_rollback_remain_not_executed() -> None:
    fields = checker.load_yaml(PLAN_YAML)["validation_fields"]
    assert fields["latest_main_shadow_compare"]["shadow_compare_executed"] is False
    assert fields["latest_main_shadow_compare"]["shadow_compare_passed"] is False
    assert fields["latest_main_shadow_compare"]["production_behavior_changed"] is False
    assert fields["rollback_execution_evidence"]["rollback_executed"] is False
    assert fields["rollback_execution_evidence"]["production_behavior_changed"] is False


def test_route_and_production_compat_proofs_are_collected_without_wildcard_cleanup() -> None:
    fields = checker.load_yaml(PLAN_YAML)["validation_fields"]
    assert fields["route_ownership_proof"]["status"] == "collected"
    assert fields["production_compat_exact_entry_proof"]["exact_entry_found"] is True
    assert fields["production_compat_exact_entry_proof"]["wildcard_cleanup_required"] is False


def test_validation_is_blocked_and_cleanup_retry_not_ready() -> None:
    result = checker.load_yaml(PLAN_YAML)["validation_result"]
    assert result["validation_blocked"] is True
    assert result["ready_for_exact_route_cleanup_retry"] is False
    assert result["ready_for_exact_route_fallback_cleanup"] is False
    assert result["ready_for_exact_route_production_compat_cleanup"] is False


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
