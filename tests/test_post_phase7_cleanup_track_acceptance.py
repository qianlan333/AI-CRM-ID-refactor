from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_track_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_track_acceptance.yaml"
DOC = ROOT / "docs/development/post_phase7_cleanup_track_acceptance.md"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_source_prs_are_recorded() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["source_prs"] == {
        "owner_evidence_waiting": 806,
        "first_validation": 811,
        "validation_blocker_acceptance": 812,
        "shadow_rollback_evidence": 813,
        "revalidation": 814,
        "exact_route_cleanup_retry": 815,
        "legacy_runtime_recheck": 816,
    }


def test_task_groups_cleanup_results_are_recorded() -> None:
    cleanup = checker.load_yaml(PLAN_YAML)["cleanup_results"]
    assert "/api/admin/automation-conversion/task-groups*" in cleanup["fallback_removals_executed"]
    assert "/api/admin/automation-conversion/task-groups*" in cleanup["production_compat_cleanups_executed"]
    assert cleanup["wildcard_cleanup_executed"] is False


def test_runtime_deletions_empty_and_delete_ready_false() -> None:
    cleanup = checker.load_yaml(PLAN_YAML)["cleanup_results"]
    assert cleanup["runtime_deletions_executed"] == []
    assert cleanup["delete_ready"] is False


def test_rollback_available_for_task_groups_cleanup() -> None:
    rollback = checker.load_yaml(PLAN_YAML)["rollback"]
    assert rollback["available"] is True
    assert rollback["rollback_method"] == "revert_merge_commit"
    assert rollback["rollback_commit"] == "809e6861c2fb9a344c312452d5ac22d131e293e8"


def test_runtime_deletion_blocker_reasons_are_recorded() -> None:
    runtime_recheck = checker.load_yaml(PLAN_YAML)["runtime_recheck"]
    assert runtime_recheck["source_pr"] == 816
    assert runtime_recheck["safe_runtime_cleanup_candidate_selected"] is False
    assert runtime_recheck["blocker_reasons"]


def test_authorizations_remain_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for value in data["authorizations"].values():
        assert value is False


def test_docs_do_not_claim_forbidden_cleanup() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "runtime deletion executed: true",
        "runtime deletions executed: true",
        "wildcard cleanup executed: true",
        "delete_ready true",
        "delete_ready: true",
        "legacy runtime deleted",
    }
    assert not any(claim in text for claim in forbidden_claims)
