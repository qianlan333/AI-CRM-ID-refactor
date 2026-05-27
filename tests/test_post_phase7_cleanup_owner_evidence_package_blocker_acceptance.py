from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_owner_evidence_package_blocker_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_package_blocker_acceptance.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_package_blocker_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_are_all_false() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    for key in checker.REQUIRED_AUTHORIZATIONS:
        assert authorizations[key] is False


def test_source_prs_are_recorded() -> None:
    source_prs = checker.load_yaml(PLAN_YAML)["source_prs"]
    assert source_prs["owner_evidence_waiting_acceptance"] == 806
    assert source_prs["owner_evidence_package_generation"] == 807


def test_missing_owner_only_evidence_is_complete() -> None:
    missing = set(checker.load_yaml(PLAN_YAML)["missing_owner_only_evidence"])
    assert checker.REQUIRED_MISSING_OWNER_EVIDENCE <= missing


def test_all_routes_are_blocked_and_not_ready() -> None:
    routes = checker.load_yaml(PLAN_YAML)["blocked_routes"]
    assert {item["route_family"] for item in routes} == checker.REQUIRED_ROUTES
    for route in routes:
        assert route["ready_for_validation"] is False
        assert route["ready_for_exact_route_cleanup"] is False


def test_cleanup_execution_is_all_false() -> None:
    for route in checker.load_yaml(PLAN_YAML)["blocked_routes"]:
        assert route["fallback_removal_executed"] is False
        assert route["production_compat_cleanup_executed"] is False
        assert route["runtime_deletion_executed"] is False


def test_resume_rules_block_without_owner_evidence() -> None:
    resume = checker.load_yaml(PLAN_YAML)["resume_rules"]
    assert resume["cleanup_track_status"] == "blocked_waiting_owner_only_evidence"
    assert resume["next_allowed_action_without_owner_evidence"] == "none"
    assert resume["next_if_owner_evidence_complete"] == "post_phase7_cleanup_owner_evidence_validation_bundle"


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
