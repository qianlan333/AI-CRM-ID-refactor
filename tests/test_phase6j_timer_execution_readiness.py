from __future__ import annotations

from pathlib import Path

import tools.check_phase6j_timer_execution_readiness as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_6j_timer_execution_readiness.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_authorizations_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())


def test_candidate_inventory_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    candidates = {item["candidate"] for item in data["execution_candidate_inventory"]}
    assert candidates == checker.REQUIRED_CANDIDATES
    assert all(item["can_be_dry_run"] is True for item in data["execution_candidate_inventory"])


def test_first_candidate_is_internal_no_send_no_live_call() -> None:
    selected = checker.load_yaml(PLAN_YAML)["first_execution_canary_candidate"]
    assert selected["selected_candidate"] == "workflow-nodes"
    assert selected["requires_outbound_send"] is False
    assert selected["requires_timer"] is False
    assert selected["requires_live_external_call"] is False
    assert selected["can_be_dry_run"] is True
    assert selected["can_be_single_scope_canary"] is True


def test_business_continuity_and_next_bundle() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is True for value in data["business_continuity"].values())
    assert data["next"] == ["phase_6k_single_scope_execution_canary_tooling_bundle"]
