from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase7e_fallback_cleanup_readiness as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_7e_fallback_cleanup_readiness.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_remain_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for key in checker.FALSE_AUTHORIZATIONS:
        assert data["authorizations"][key] is False


def test_selected_candidate_is_exact_route_readiness_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    selected = data["selected_first_fallback_cleanup_candidate"]
    assert selected["candidate_id"] == checker.SELECTED_CANDIDATE
    assert selected["route_family"] == checker.SELECTED_ROUTE
    assert selected["fallback_removed_in_phase_7e"] is False
    assert selected["production_behavior_changed"] is False
    assert selected["production_compat_behavior_changed"] is False
    assert selected["wildcard_fallback_touched"] is False
    assert selected["runtime_deleted"] is False
    assert selected["delete_ready"] is False


def test_high_risk_fallback_is_excluded() -> None:
    data = checker.load_yaml(PLAN_YAML)
    excluded = data["excluded_high_risk_fallback"]
    for key in checker.REQUIRED_EXCLUDED_FLAGS:
        assert excluded[key] is True


def test_next_bundle_is_phase_7f_readiness() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["next"] == [checker.NEXT_BUNDLE]
