from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_new_feature_development_rules as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_new_feature_development_rules.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_new_feature_development_rules.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_phase_7_handoff_is_safe_retained_state() -> None:
    handoff = checker.load_yaml(PLAN_YAML)["phase_7_handoff"]
    assert handoff["phase_7_completed"] is True
    assert handoff["fallback_retained"] is True
    assert handoff["production_compat_retained"] is True
    assert handoff["legacy_runtime_retained"] is True
    assert handoff["delete_ready"] is False


def test_legacy_primary_paths_are_forbidden() -> None:
    rules = checker.load_yaml(PLAN_YAML)["default_new_feature_rules"]
    assert rules["production_compat_as_primary_implementation_allowed"] is False
    assert rules["wecom_ability_service_new_business_logic_allowed"] is False
    assert rules["direct_legacy_import_allowed"] is False
    assert rules["fallback_as_primary_path_allowed"] is False


def test_risky_categories_are_gated() -> None:
    categories = {item["category"]: item for item in checker.load_yaml(PLAN_YAML)["feature_categories"]}
    assert categories["external_adapter"]["feature_flag_required"] is True
    assert categories["external_adapter"]["owner_approval_required"] is True
    assert categories["execution"]["default_on_allowed"] is False
    assert categories["payment"]["default_money_movement_allowed"] is False
    assert categories["payment"]["owner_approval_required"] is True
    assert categories["oauth_identity"]["callback_cutover_default_allowed"] is False
    assert categories["wecom"]["outbound_send_default_allowed"] is False
    assert categories["wecom"]["owner_approval_required"] is True


def test_required_pr_sections_are_complete() -> None:
    sections = set(checker.load_yaml(PLAN_YAML)["required_pr_sections"])
    assert checker.REQUIRED_PR_SECTIONS <= sections


def test_docs_do_not_claim_deleted_or_delete_ready() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "fallback deleted",
        "fallback removed: true",
        "production_compat deleted",
        "production_compat removed: true",
        "delete_ready: true",
        "legacy runtime deleted",
    }
    assert not any(claim in text for claim in forbidden_claims)
