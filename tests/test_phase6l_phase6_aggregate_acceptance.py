from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase6l_phase6_aggregate_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_6l_phase6_aggregate_acceptance.yaml"
DOC = ROOT / "docs/development/phase_6l_phase6_aggregate_acceptance.md"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_phase_6_inventory_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_PHASES <= set(data["phase_6_completed_inventory"])


def test_production_behavior_summary_keeps_phase_6_non_destructive() -> None:
    data = checker.load_yaml(PLAN_YAML)
    summary = data["production_behavior_summary"]
    for key in checker.FALSE_PRODUCTION_KEYS:
        assert summary[key] is False
    assert summary["production_owner_switch_executed_routes"] == []


def test_execution_and_external_side_effects_did_not_occur() -> None:
    data = checker.load_yaml(PLAN_YAML)
    execution = data["execution_readiness_canary_tooling"]
    assert execution["default_blocked"] is True
    assert execution["timer_execution_actual"] is False
    assert execution["run_due_execution_actual"] is False
    assert execution["automation_execution_actual"] is False
    assert execution["outbound_send_actual"] is False
    assert execution["live_external_call_actual"] is False
    assert data["external_adapter_enablement_readiness"]["live_external_default_on"] is False
    assert data["external_adapter_enablement_readiness"]["outbound_send"] is False


def test_phase_7_deferrals_and_next_bundle() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is True for value in data["phase_7_deferrals"].values())
    assert all(value is True for value in data["business_continuity"].values())
    assert data["next"] == ["phase_7a_legacy_retirement_readiness_bundle"]


def test_docs_do_not_claim_forbidden_phase6_actions() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "delete_ready true",
        "fallback removed: true",
        "production_compat behavior changed: true",
        "timer execution default-on: true",
        "outbound send: true",
        "live external default-on: true",
    ]
    for item in forbidden:
        assert item not in text

