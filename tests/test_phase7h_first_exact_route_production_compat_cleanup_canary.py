from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase7h_first_exact_route_production_compat_cleanup_canary as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_7h_first_exact_route_production_compat_cleanup_canary.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_remain_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for key in checker.FALSE_AUTHORIZATIONS:
        assert data["authorizations"][key] is False


def test_selected_route_and_candidate() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["selected_route_family"] == checker.SELECTED_ROUTE
    assert data["cleanup_candidate"] == checker.SELECTED_CANDIDATE


def test_production_compat_cleanup_is_blocked_without_behavior_change() -> None:
    outcome = checker.load_yaml(PLAN_YAML)["outcome"]
    assert outcome["production_compat_cleanup_blocked"] is True
    assert outcome["exact_route_production_compat_cleanup_executed"] is False
    assert outcome["production_behavior_changed"] is False
    assert outcome["wildcard_cleanup_touched"] is False
    assert outcome["runtime_deleted"] is False
    assert outcome["delete_ready"] is False


def test_next_bundle_is_phase_7i() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["next"] == [checker.NEXT_BUNDLE]
