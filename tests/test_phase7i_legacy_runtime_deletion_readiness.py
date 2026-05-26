from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase7i_legacy_runtime_deletion_readiness as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_7i_legacy_runtime_deletion_readiness.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_runtime_deletion_authorizations_remain_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for key in checker.FALSE_AUTHORIZATIONS:
        assert data["authorizations"][key] is False


def test_no_safe_runtime_candidate_is_selected() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["selected_runtime_cleanup_candidate"] == "none"
    assert data["delete_candidate_matrix"]["safe_to_delete_candidate"] == []


def test_runtime_cleanup_is_blocked_without_behavior_change() -> None:
    outcome = checker.load_yaml(PLAN_YAML)["outcome"]
    assert outcome["runtime_cleanup_blocked"] is True
    assert outcome["legacy_runtime_deletion_executed"] is False
    assert outcome["fallback_removed"] is False
    assert outcome["production_compat_behavior_changed"] is False
    assert outcome["wildcard_cleanup"] is False
    assert outcome["delete_ready"] is False


def test_next_bundle_is_phase_7j_blocker_acceptance() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["next"] == [checker.NEXT_BUNDLE]
