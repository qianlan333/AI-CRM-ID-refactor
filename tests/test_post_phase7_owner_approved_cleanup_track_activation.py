from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_owner_approved_cleanup_track_activation as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_owner_approved_cleanup_track_activation.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_owner_approved_cleanup_track_activation.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_feature_selection_paused_and_cleanup_authorized() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["feature_selection_paused"] is True
    assert data["business_feature_implementation_authorized"] is False
    assert data["cleanup_track_authorized"] is True


def test_authorizations_keep_high_risk_cleanup_false() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    for key in checker.REQUIRED_AUTHORIZATIONS:
        assert authorizations[key] is False


def test_handoff_keeps_post_phase7b_intake_unimplemented() -> None:
    handoff = checker.load_yaml(PLAN_YAML)["phase_handoff"]
    assert handoff["post_phase7b_selected_feature_status"] == "pending_owner_selection"
    assert handoff["post_phase7b_implementation_authorized"] is False
    assert handoff["fallback_retained"] is True
    assert handoff["production_compat_retained"] is True
    assert handoff["legacy_runtime_retained"] is True
    assert handoff["delete_ready"] is False


def test_first_cleanup_candidates_are_route_specific() -> None:
    candidates = set(checker.load_yaml(PLAN_YAML)["first_cleanup_candidates"])
    assert checker.REQUIRED_CANDIDATES <= candidates
    assert "wildcard_production_compat_cleanup" not in candidates
    assert "fallback_broad_removal" not in candidates


def test_docs_do_not_claim_cleanup_execution() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "fallback removed: true",
        "production_compat behavior changed: true",
        "wildcard cleanup executed",
        "legacy runtime deleted",
        "delete_ready true",
        "delete_ready: true",
        "business feature implemented",
    }
    assert not any(claim in text for claim in forbidden_claims)
