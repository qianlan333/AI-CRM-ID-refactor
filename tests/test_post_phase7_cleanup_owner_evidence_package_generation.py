from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_owner_evidence_package_generation as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_package_generation.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_package_generation.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_are_all_false() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    for key in checker.REQUIRED_AUTHORIZATIONS:
        assert authorizations[key] is False


def test_evidence_packages_cover_task_groups_and_workflow_nodes() -> None:
    packages = checker.load_yaml(PLAN_YAML)["evidence_packages"]
    assert {item["route_family"] for item in packages} == checker.REQUIRED_ROUTES


def test_owner_fields_remain_required() -> None:
    for package in checker.load_yaml(PLAN_YAML)["evidence_packages"]:
        assert package["owner_approval"]["status"] == "owner_required"
        assert package["owner_approval"]["source"] == "none"
        assert package["rollback_owner"]["status"] == "owner_required"
        assert package["risk_acceptance"]["status"] == "owner_required"
        assert package["approval_timestamp"]["status"] == "owner_required"
        assert package["ready_for_validation"] is False


def test_generated_evidence_is_no_behavior_change() -> None:
    for package in checker.load_yaml(PLAN_YAML)["evidence_packages"]:
        assert package["latest_main_shadow_compare"]["production_behavior_changed"] is False
        assert package["rollback_execution_evidence"]["production_behavior_changed"] is False
        assert package["production_compat_exact_entry_proof"]["wildcard_cleanup_required"] is False


def test_all_routes_remain_blocked_for_validation() -> None:
    outcomes = checker.load_yaml(PLAN_YAML)["outcomes"]
    assert outcomes["task_groups_ready_for_validation"] is False
    assert outcomes["workflow_nodes_ready_for_validation"] is False
    assert outcomes["all_blocked_owner_required"] is True


def test_no_cleanup_or_delete_ready_claimed() -> None:
    outcomes = checker.load_yaml(PLAN_YAML)["outcomes"]
    assert outcomes["fallback_removals_executed"] == []
    assert outcomes["production_compat_cleanups_executed"] == []
    assert outcomes["runtime_deletions_executed"] == []
    assert outcomes["delete_ready"] is False


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
