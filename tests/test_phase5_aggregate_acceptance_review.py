from __future__ import annotations

from pathlib import Path

import tools.check_phase5_aggregate_acceptance_review as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5_aggregate_acceptance_review.md"
PLAN_YAML = ROOT / "docs/development/phase_5_aggregate_acceptance_review.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_all_selected_families_are_accepted() -> None:
    data = checker.load_yaml(PLAN_YAML)
    families = {item["family"] for item in data["families"]}
    assert families == checker.REQUIRED_FAMILIES
    assert all(item["family_acceptance_complete"] is True for item in data["families"])


def test_no_rollout_or_owner_fallback_production_compat_change() -> None:
    data = checker.load_yaml(PLAN_YAML)
    matrix = data["aggregate_matrix"]
    assert matrix["all_selected_families_acceptance_complete"] is True
    assert matrix["live_capabilities_remain_behind_explicit_gates"] is True
    assert matrix["wider_rollout_authorized"] is False
    assert matrix["default_live_external_call_enabled"] is False
    assert matrix["delete_ready"] is False
    for family in data["families"]:
        assert family["owner_switched"] is False
        assert family["fallback_removed"] is False
        assert family["production_compat_changed"] is False


def test_phase6_and_phase7_deferrals_are_explicit() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is True for value in data["phase6_readiness"].values())
    assert all(value is True for value in data["phase7_deferral"].values())
    assert all(value is True for value in data["business_continuity"].values())


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["owner switch authorized", "fallback removal authorized", "production_compat change authorized", "default-on live external call", "outbound send enabled", "automation execution enabled", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
