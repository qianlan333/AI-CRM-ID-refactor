from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_agent_outputs_exact_route_cleanup as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_cleanup_agent_outputs_exact_route_cleanup.md"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_owner_standing_approval_recorded() -> None:
    owner = checker.load_yaml(checker.OWNER_YAML)
    assert owner["owner_approval"]["status"] == "granted"
    assert owner["owner_approval"]["owner"] == "qianlan"
    assert owner["runtime_deletion_policy"]["runtime_deletion_authorized"] is False
    assert owner["delete_ready"] is False


def test_selected_exact_production_compat_entry_removed_but_wildcard_retained() -> None:
    text = checker.PRODUCTION_COMPAT.read_text(encoding="utf-8")
    assert checker.SELECTED_DECORATOR not in text
    assert checker.RETAINED_WILDCARD in text
    assert "wildcard_router" in text


def test_next_native_exact_route_exists() -> None:
    text = checker.NATIVE_API.read_text(encoding="utf-8")
    assert '@router.get("/api/admin/automation-conversion/agent-outputs")' in text


def test_cleanup_result_keeps_runtime_and_delete_ready_blocked() -> None:
    data = checker.load_yaml(checker.PLAN_YAML)
    assert data["cleanup_actions"]["runtime_deletion_executed"] is False
    assert data["cleanup_actions"]["delete_ready"] is False
    assert data["cleanup_result"]["runtime_deletions_executed"] == []
    assert data["cleanup_result"]["delete_ready"] is False
    assert data["cleanup_result"]["wildcard_cleanup_executed"] is False


def test_docs_do_not_claim_runtime_or_wildcard_deletion() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = {
        "runtime deletion executed: true",
        "legacy runtime deleted",
        "delete_ready: true",
        "wildcard cleanup executed: true",
    }
    assert not any(claim in text for claim in forbidden)
