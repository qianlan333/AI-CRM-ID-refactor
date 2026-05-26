from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_blocker_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_cleanup_blocker_acceptance.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_blocker_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_keep_cleanup_execution_false() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    for key in checker.REQUIRED_AUTHORIZATIONS:
        assert authorizations[key] is False


def test_task_groups_and_workflow_nodes_are_blocked() -> None:
    routes = {item["route_family"]: item for item in checker.load_yaml(PLAN_YAML)["blocked_route_families"]}
    assert routes["/api/admin/automation-conversion/task-groups*"]["source_pr"] == 798
    assert routes["/api/admin/automation-conversion/workflow-nodes*"]["source_pr"] == 799
    for item in routes.values():
        assert item["fallback_cleanup_status"] == "blocked"
        assert item["production_compat_cleanup_status"] == "blocked"
        assert checker.REQUIRED_MISSING_EVIDENCE <= set(item["missing_evidence"])


def test_owner_action_list_is_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_OWNER_ACTIONS <= set(data["owner_action_list"])


def test_cleanup_summary_keeps_execution_empty() -> None:
    summary = checker.load_yaml(PLAN_YAML)["cleanup_summary"]
    assert summary["fallback_removals_executed"] == []
    assert summary["production_compat_cleanups_executed"] == []
    assert summary["runtime_deletions_executed"] == []
    assert summary["delete_ready_true_items"] == []
    assert summary["legacy_runtime_recheck_allowed"] is False
    assert summary["legacy_runtime_recheck_blocked_reason"] == "no_exact_route_cleanup_executed"


def test_docs_do_not_claim_cleanup_execution() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "fallback removed: true",
        "fallback_removal_occurred: true",
        "production_compat behavior changed: true",
        "production_compat_cleanup_executed: true",
        "wildcard cleanup executed",
        "legacy runtime deleted",
        "delete_ready true",
        "delete_ready: true",
    }
    assert not any(claim in text for claim in forbidden_claims)
