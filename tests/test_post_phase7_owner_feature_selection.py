from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_owner_feature_selection as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_owner_feature_selection.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_owner_feature_selection.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_all_false() -> None:
    authorizations = checker.load_yaml(PLAN_YAML)["authorizations"]
    for key in checker.REQUIRED_AUTHORIZATIONS:
        assert authorizations[key] is False


def test_selected_feature_is_hxc_next_native_broadcast_backend() -> None:
    selected = checker.load_yaml(PLAN_YAML)["selected_feature"]
    assert selected["selected_feature_id"] == "hxc_next_native_broadcast_backend"
    assert selected["selected_feature_name"] == "HXC Next-native broadcast backend"
    assert selected["capability_owner"] == "aicrm_next.send_content"
    assert selected["implementation_authorized"] is False


def test_live_send_and_legacy_paths_are_not_allowed() -> None:
    boundary = checker.load_yaml(PLAN_YAML)["implementation_boundary"]
    assert boundary["live_wecom_send_allowed"] is False
    assert boundary["old_flask_broadcast_call_allowed"] is False
    assert boundary["production_compat_route_allowed"] is False
    assert boundary["wecom_ability_service_business_logic_allowed"] is False
    assert boundary["direct_legacy_import_allowed"] is False


def test_selected_feature_requires_feature_flag_canary_and_owner_approval() -> None:
    selected = checker.load_yaml(PLAN_YAML)["selected_feature"]
    assert selected["requires_feature_flag"] is True
    assert selected["requires_canary_before_live_send"] is True
    assert selected["requires_owner_approval"] is True
    assert selected["external_side_effect_in_first_implementation"] is False


def test_docs_do_not_claim_backend_implementation_or_real_send() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "backend implemented",
        "business feature implemented",
        "runtime route added",
        "live send enabled",
        "real wecom send enabled",
        "old flask broadcast call enabled",
        "production_compat route added",
        "delete_ready true",
        "delete_ready: true",
    }
    assert not any(claim in text for claim in forbidden_claims)
