from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_first_new_feature_intake as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_first_new_feature_intake.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_first_new_feature_intake.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_all_false() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    for key in checker.REQUIRED_AUTHORIZATIONS:
        assert authorizations[key] is False


def test_phase_7_handoff_is_retained_state() -> None:
    handoff = checker.load_yaml(PLAN_YAML)["phase_7_handoff"]
    assert handoff["phase_7_completed"] is True
    assert handoff["fallback_retained"] is True
    assert handoff["production_compat_retained"] is True
    assert handoff["legacy_runtime_retained"] is True
    assert handoff["delete_ready"] is False


def test_post_phase7_rules_are_next_native_and_no_legacy() -> None:
    rules = checker.load_yaml(PLAN_YAML)["post_phase7_rules"]
    assert rules["next_native_required"] is True
    assert rules["production_compat_primary_path_allowed"] is False
    assert rules["wecom_ability_service_new_business_logic_allowed"] is False
    assert rules["direct_legacy_import_allowed"] is False


def test_recommended_candidates_include_required_three() -> None:
    candidate_ids = {item["feature_id"] for item in checker.load_yaml(PLAN_YAML)["recommended_candidates"]}
    assert checker.REQUIRED_CANDIDATES <= candidate_ids


def test_pending_owner_selection_does_not_authorize_implementation() -> None:
    selected = checker.load_yaml(PLAN_YAML)["selected_feature"]
    assert selected["selected_feature_status"] == "pending_owner_selection"
    assert selected["selected_feature_id"] == "none"
    assert selected["implementation_authorized"] is False
    assert selected["owner_selection_required"] is True


def test_docs_do_not_claim_runtime_or_feature_execution() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "business feature implemented",
        "runtime route added",
        "route added",
        "production_compat changed",
        "fallback deleted",
        "fallback removed: true",
        "delete_ready true",
        "delete_ready: true",
    }
    assert not any(claim in text for claim in forbidden_claims)
