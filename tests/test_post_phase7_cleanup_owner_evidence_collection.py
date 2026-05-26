from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_owner_evidence_collection as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_collection.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_collection.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_are_all_false() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    for key in checker.REQUIRED_AUTHORIZATIONS:
        assert authorizations[key] is False


def test_source_blockers_reference_expected_prs() -> None:
    source_blockers = checker.load_yaml(PLAN_YAML)["source_blockers"]
    assert source_blockers["task_groups_source_pr"] == 798
    assert source_blockers["workflow_nodes_source_pr"] == 799
    assert source_blockers["blocker_acceptance_source_pr"] == 801


def test_evidence_matrix_contains_required_routes_and_fields() -> None:
    routes = {item["route_family"]: item for item in checker.load_yaml(PLAN_YAML)["evidence_matrix"]}
    assert checker.REQUIRED_ROUTES <= set(routes)
    for item in routes.values():
        assert checker.REQUIRED_EVIDENCE_FIELDS <= set(item)


def test_all_routes_remain_not_ready() -> None:
    routes = checker.load_yaml(PLAN_YAML)["evidence_matrix"]
    for item in routes:
        assert item["ready_for_fallback_cleanup"] is False
        assert item["ready_for_production_compat_cleanup"] is False


def test_docs_do_not_claim_cleanup_execution() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "fallback removed: true",
        "fallback_removal_occurred: true",
        "production_compat cleaned: true",
        "production_compat_cleanup_executed: true",
        "runtime deleted: true",
        "legacy runtime deleted",
        "delete_ready true",
        "delete_ready: true",
    }
    assert not any(claim in text for claim in forbidden_claims)
