from __future__ import annotations

from pathlib import Path

import tools.check_phase5y_media_upload_family_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5y_media_upload_family_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_5y_media_upload_family_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_authorizations_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())


def test_completed_stages_cover_media_5u_to_5x() -> None:
    data = checker.load_yaml(PLAN_YAML)
    stages = {item["stage"] for item in data["completed_stages"]}
    assert {"phase_5u_contract_fake_stub", "phase_5v_live_adapter_behind_flag", "phase_5w_staging_live_canary_gate", "phase_5x_production_canary_tooling"} <= stages


def test_acceptance_decision_and_rollout_boundary_are_safe() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["acceptance_decision"]["status"] in data["acceptance_decision"]["allowed_values"]
    assert data["acceptance_decision"]["production_canary_passed"] is False
    assert data["rollout_boundary"]["wider_rollout_authorized"] is False
    assert data["rollout_boundary"]["batch_upload_authorized"] is False
    assert data["rollout_boundary"]["destructive_delete_authorized"] is False


def test_next_family_selected_payment_contract_fake_stub() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["next_family"]["selected_next_bundle"] == checker.NEXT_BUNDLE
    assert data["next_family"]["route_family"] == "/api/admin/wechat-pay*"
    assert data["next_family"]["live_external_call_allowed"] is False


def test_business_continuity_true() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is True for value in data["business_continuity"].values())


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["wider rollout enabled", "route owner switched", "fallback removed", "production_compat changed", "public media url publication enabled", "destructive delete enabled", "batch upload enabled", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
