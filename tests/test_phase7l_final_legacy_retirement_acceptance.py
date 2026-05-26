from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase7l_final_legacy_retirement_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_7l_final_legacy_retirement_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_final_acceptance_marks_phase_7_complete_with_retained_runtime() -> None:
    final = checker.load_yaml(PLAN_YAML)["final_acceptance"]
    assert final["phase_7_completed"] is True
    assert final["fallback_retained"] is True
    assert final["production_compat_retained"] is True
    assert final["legacy_runtime_retained"] is True
    assert final["broad_runtime_deletion_completed"] is False
    assert final["delete_ready"] is False


def test_final_acceptance_does_not_enable_side_effects() -> None:
    side_effects = checker.load_yaml(PLAN_YAML)["side_effects"]
    assert all(value is False for value in side_effects.values())


def test_autopilot_does_not_auto_start_cleanup() -> None:
    autopilot = checker.load_yaml(PLAN_YAML)["autopilot_state"]
    assert autopilot["mark_phase_7_complete"] is True
    assert autopilot["auto_start_runtime_deletion"] is False
    assert autopilot["auto_start_fallback_removal"] is False
    assert autopilot["auto_start_production_compat_deletion"] is False


def test_next_allowed_actions_are_post_phase7_tracks() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert set(data["next_allowed_actions"]) == checker.NEXT_ALLOWED
