from __future__ import annotations

from pathlib import Path

import tools.check_phase6f_external_adapter_enablement_readiness as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_6f_external_adapter_enablement_readiness.yaml"
DOC = ROOT / "docs/development/phase_6f_external_adapter_enablement_readiness.md"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_authorizations_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())


def test_candidate_inventory_contains_all_phase5_external_families() -> None:
    data = checker.load_yaml(PLAN_YAML)
    families = {item["family_key"] for item in data["candidate_inventory"]}
    assert families == checker.REQUIRED_FAMILIES
    assert all(item["phase_5_acceptance_status"] == "family_acceptance_complete" for item in data["candidate_inventory"])


def test_first_phase6g_candidates_select_only_low_risk_batch() -> None:
    data = checker.load_yaml(PLAN_YAML)
    first = data["first_phase6g_candidates"]
    assert set(first["selected"]) == checker.SELECTED
    assert set(first["explicitly_not_selected"]) == checker.EXCLUDED
    by_key = {item["family_key"]: item for item in data["candidate_inventory"]}
    assert all(by_key[key]["enablement_ready"] is True for key in checker.SELECTED)
    assert all(by_key[key]["enablement_ready"] is False for key in checker.EXCLUDED)


def test_business_continuity_preserves_current_production_behavior() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is True for value in data["business_continuity"].values())
    assert data["next"] == ["phase_6g_low_risk_external_adapter_enablement_tooling_bundle"]


def test_docs_do_not_claim_forbidden_execution() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = [
        "live external call enabled by default: true",
        "production owner switch executed",
        "production_compat changed",
        "fallback removed",
        "outbound send enabled",
        "payment capture authorized",
        "oauth callback cutover authorized",
        "delete_ready true",
    ]
    for claim in forbidden_claims:
        assert claim not in text
