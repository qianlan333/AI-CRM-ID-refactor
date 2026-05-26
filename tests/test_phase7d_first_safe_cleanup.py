from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase7d_first_safe_cleanup as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_7d_first_safe_cleanup.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_cleanup_is_no_runtime_no_behavior_change() -> None:
    data = checker.load_yaml(PLAN_YAML)
    cleanup = data["cleanup"]
    assert cleanup["new_recommendation"] == checker.EXPECTED_RECOMMENDATION
    assert cleanup["cleanup_behavior_change"] is False
    assert cleanup["production_behavior_unchanged"] is True
    assert cleanup["fallback_retained"] is True
    assert cleanup["production_compat_unchanged"] is True
    assert cleanup["legacy_runtime_deleted"] is False
    assert cleanup["delete_ready"] is False


def test_authorizations_remain_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for key in checker.FALSE_AUTHORIZATIONS:
        assert data["authorizations"][key] is False


def test_legacy_facade_checker_recommendation_updated() -> None:
    report = checker.legacy_freeze_report(checker.ROOT)
    assert report["overall"] == "PASS"
    assert report["recommendation"] == checker.EXPECTED_RECOMMENDATION


def test_next_bundle_is_phase_7e_readiness() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["next"] == [checker.NEXT_BUNDLE]
