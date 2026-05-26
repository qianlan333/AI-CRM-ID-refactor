from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_owner_evidence_waiting_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_waiting_acceptance.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_waiting_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_are_all_false() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    for key in checker.REQUIRED_AUTHORIZATIONS:
        assert authorizations[key] is False


def test_source_prs_are_recorded() -> None:
    source_prs = checker.load_yaml(PLAN_YAML)["source_prs"]
    assert source_prs["task_groups_evidence_refresh"] == 798
    assert source_prs["workflow_nodes_evidence_refresh"] == 799
    assert source_prs["blocker_acceptance"] == 801
    assert source_prs["owner_evidence_collection"] == 802


def test_blocked_routes_are_task_groups_and_workflow_nodes() -> None:
    blocked_routes = set(checker.load_yaml(PLAN_YAML)["blocked_routes"])
    assert blocked_routes == checker.REQUIRED_ROUTES


def test_owner_evidence_package_required_fields_are_complete() -> None:
    fields = set(checker.load_yaml(PLAN_YAML)["owner_evidence_package_required_fields"])
    assert checker.REQUIRED_EVIDENCE_FIELDS <= fields


def test_resume_rules_pause_without_owner_evidence() -> None:
    resume = checker.load_yaml(PLAN_YAML)["resume_rules"]
    assert resume["cleanup_track_status"] == "paused_waiting_owner_evidence"
    assert resume["next_allowed_action_without_owner_evidence"] == "none"
    assert resume["next_if_evidence_complete"] == "post_phase7_cleanup_exact_route_retry_bundle"


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
