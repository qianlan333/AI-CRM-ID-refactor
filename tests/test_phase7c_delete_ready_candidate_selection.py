from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase7c_delete_ready_candidate_selection as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_7c_delete_ready_candidate_selection.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_remain_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for key in checker.FALSE_AUTHORIZATIONS:
        assert data["authorizations"][key] is False


def test_required_candidate_categories_exist() -> None:
    data = checker.load_yaml(PLAN_YAML)
    categories = data["candidate_categories"]
    assert checker.REQUIRED_CATEGORIES <= set(categories)
    assert all(categories[key] for key in checker.REQUIRED_CATEGORIES)


def test_every_candidate_has_required_fields_and_no_delete_authorization() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for item in checker._candidate_items(data["candidate_categories"]):
        assert item["candidate_id"]
        assert item["required_evidence"]
        assert item["rollback_strategy"]
        assert item["delete_ready_authorized"] is False


def test_phase_7d_candidate_is_no_runtime_cleanup() -> None:
    data = checker.load_yaml(PLAN_YAML)
    selected = data["phase_7d_first_cleanup_candidate"]
    assert selected["selected_candidate_id"] == "legacy_import_checker_baseline_followup"
    assert selected["fallback_removal_allowed"] is False
    assert selected["production_compat_behavior_change_allowed"] is False
    assert selected["legacy_runtime_deletion_allowed"] is False
    assert selected["delete_ready_authorized"] is False
    assert data["next"] == [checker.NEXT_BUNDLE]
