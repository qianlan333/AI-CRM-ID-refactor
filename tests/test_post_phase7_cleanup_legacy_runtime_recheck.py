from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_legacy_runtime_recheck as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_legacy_runtime_recheck.yaml"
DOC = ROOT / "docs/development/post_phase7_cleanup_legacy_runtime_recheck.md"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_source_and_authorizations() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["source_prs"]["task_groups_exact_route_retry"] == 815
    assert data["source_prs"]["task_groups_legacy_runtime_recheck"] == 816
    assert data["source_prs"]["cleanup_track_acceptance"] == 817
    assert data["source_prs"]["workflow_nodes_owner_approved_cleanup"] == 818
    for value in data["authorizations"].values():
        assert value is False


def test_task_groups_cleanup_handoff_and_no_runtime_deletion() -> None:
    data = checker.load_yaml(PLAN_YAML)
    handoff = data["exact_route_cleanup_handoff"]
    assert handoff["task_groups_fallback_removal_executed"] is True
    assert handoff["task_groups_production_compat_cleanup_executed"] is True
    assert handoff["workflow_nodes_production_compat_cleanup_executed"] is True
    assert handoff["workflow_nodes_production_compat_hook_absent"] is True
    assert handoff["runtime_deletion_executed"] is False
    cleanup = data["cleanup_execution"]
    assert cleanup["runtime_deletion_executed"] is False
    assert cleanup["fallback_removal_executed_in_this_pr"] is False
    assert cleanup["production_compat_cleanup_executed_in_this_pr"] is False


def test_no_safe_runtime_candidate_selected() -> None:
    result = checker.load_yaml(PLAN_YAML)["runtime_candidate_result"]
    assert result["safe_runtime_cleanup_candidate_selected"] is False
    assert result["no_safe_runtime_cleanup_candidate"] is True
    assert result["blocked_reason"]


def test_recheck_proves_task_groups_and_workflow_nodes_absent_but_unrelated_routes_retained() -> None:
    text = checker.PRODUCTION_COMPAT.read_text(encoding="utf-8")
    assert '"/api/admin/automation-conversion/task-groups"' not in text
    assert '"/api/admin/automation-conversion/task-groups/{path:path}"' not in text
    assert '"/api/admin/automation-conversion/workflow-nodes/{path:path}"' not in text
    assert "wildcard_router" in text
    for route in checker.RETAINED_PRODUCTION_COMPAT_ROUTES:
        assert f'"{route}"' in text or f"'{route}'" in text


def test_docs_do_not_claim_runtime_deletion_or_delete_ready() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "runtime deletion executed: true",
        "legacy runtime deleted",
        "delete_ready true",
        "delete_ready: true",
        "safe runtime cleanup candidate selected: true",
    }
    assert not any(claim in text for claim in forbidden_claims)
