from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_task_groups_exact_route_retry as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_task_groups_exact_route_retry.yaml"
DOC = ROOT / "docs/development/post_phase7_cleanup_task_groups_exact_route_retry.md"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_source_prs_and_authorizations_are_recorded() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for key, expected in checker.REQUIRED_SOURCE_PRS.items():
        assert data["source_prs"][key] == expected
    assert data["authorizations"]["exact_route_cleanup_retry_authorized"] is True
    for key in checker.REQUIRED_FALSE_AUTHORIZATIONS:
        assert data["authorizations"][key] is False


def test_evidence_used_matches_revalidation_package() -> None:
    evidence = checker.load_yaml(PLAN_YAML)["evidence_used"]
    assert evidence["owner_approval"]["owner"] == "qianlan"
    assert evidence["rollback_owner"]["owner"] == "qianlan"
    assert evidence["shadow_compare"]["source_pr"] == 813
    assert evidence["rollback_rehearsal"]["source_pr"] == 813
    assert evidence["route_ownership_proof"]["source_pr"] == 814
    assert evidence["production_compat_exact_entry_proof"]["wildcard_cleanup_required"] is False


def test_cleanup_executes_only_selected_task_groups_route() -> None:
    data = checker.load_yaml(PLAN_YAML)
    actions = data["cleanup_actions"]
    assert actions["fallback_removal_executed"] is True
    assert actions["production_compat_cleanup_executed"] is True
    assert actions["wildcard_cleanup_executed"] is False
    assert actions["runtime_deletion_executed"] is False
    assert actions["delete_ready"] is False


def test_task_groups_production_compat_hooks_removed_and_unrelated_hooks_retained() -> None:
    text = PRODUCTION_COMPAT.read_text(encoding="utf-8")
    assert '"/api/admin/automation-conversion/task-groups"' not in text
    assert '"/api/admin/automation-conversion/task-groups/{path:path}"' not in text
    assert '"/api/admin/automation-conversion/workflow-nodes/{path:path}"' in text
    assert '"/api/admin/automation-conversion/tasks"' in text
    assert '"/api/admin/automation-conversion/workflows"' in text


def test_manifest_records_next_native_owner_without_delete_ready() -> None:
    entry = checker._route_manifest_entry()
    assert entry["route_pattern"] == "/api/admin/automation-conversion/task-groups*"
    assert entry["current_runtime_owner"] == "aicrm_next.automation_engine"
    assert entry["production_behavior"] == "next_native_exact_route"
    assert entry["legacy_fallback_allowed"] is False
    assert entry["delete_ready"] is False


def test_rollback_is_available() -> None:
    rollback = checker.load_yaml(PLAN_YAML)["rollback"]
    assert rollback["rollback_available"] is True
    assert rollback["rollback_owner"] == "qianlan"
    assert rollback["rollback_command"]
    assert rollback["rollback_validation_command"]


def test_docs_do_not_claim_forbidden_cleanup() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "wildcard cleanup executed: true",
        "runtime deletion executed: true",
        "delete_ready true",
        "delete_ready: true",
        "workflow-nodes cleanup executed: true",
    }
    assert not any(claim in text for claim in forbidden_claims)
