from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase7j_legacy_runtime_cleanup_blocker_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_7j_legacy_runtime_cleanup_blocker_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_remain_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for key in checker.FALSE_AUTHORIZATIONS:
        assert data["authorizations"][key] is False


def test_accepts_blocked_runtime_cleanup() -> None:
    decision = checker.load_yaml(PLAN_YAML)["acceptance_decision"]
    assert decision["status"] == "accepted_blocked_runtime_cleanup"
    assert set(decision["reason"]) == {"fallback_retained", "production_compat_retained", "no_safe_runtime_candidate"}
    assert decision["future_cleanup_track_required"] is True


def test_no_cleanup_or_behavior_change_occurred() -> None:
    accepted = checker.load_yaml(PLAN_YAML)["accepted_results"]
    assert accepted["fallback_removal_occurred"] is False
    assert accepted["production_compat_behavior_changed"] is False
    assert accepted["legacy_runtime_deletion_occurred"] is False
    assert accepted["safe_runtime_cleanup_candidate_selected"] is False
    assert accepted["delete_ready"] is False


def test_next_bundle_is_phase_7k() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["next"] == [checker.NEXT_BUNDLE]
