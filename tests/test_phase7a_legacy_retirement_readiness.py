from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase7a_legacy_retirement_readiness as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_7a_legacy_retirement_readiness.yaml"
DOC = ROOT / "docs/development/phase_7a_legacy_retirement_readiness.md"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_remain_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for key in checker.FALSE_AUTHORIZATIONS:
        assert data["authorizations"][key] is False


def test_baseline_direct_legacy_import_blockers_recorded() -> None:
    data = checker.load_yaml(PLAN_YAML)
    seen = {
        (item["path"], item["line"], item["import"])
        for item in data["baseline_blockers"]["direct_legacy_imports"]
    }
    assert checker.REQUIRED_DIRECT_IMPORT_BLOCKERS <= seen


def test_candidate_classification_covers_required_phase_7_buckets() -> None:
    data = checker.load_yaml(PLAN_YAML)
    classification = data["candidate_classification"]
    assert checker.REQUIRED_CLASSIFICATION_KEYS <= set(classification)
    assert all(classification[key] for key in checker.REQUIRED_CLASSIFICATION_KEYS)


def test_phase_7b_is_only_next_bundle_and_no_behavior_change_allowed() -> None:
    data = checker.load_yaml(PLAN_YAML)
    selection = data["phase_7b_candidate_selection"]
    assert selection["selected_next_bundle"] == checker.NEXT_BUNDLE
    assert selection["behavior_change_allowed"] is False
    assert selection["fallback_removal_allowed"] is False
    assert selection["production_compat_change_allowed"] is False
    assert selection["legacy_runtime_deletion_allowed"] is False
    assert data["next"] == [checker.NEXT_BUNDLE]


def test_docs_do_not_claim_forbidden_cleanup_execution() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = [
        "fallback removed: true",
        "production_compat behavior changed: true",
        "legacy runtime deleted: true",
        "delete_ready true",
        "timer execution authorized: true",
        "outbound send authorized: true",
    ]
    for claim in forbidden_claims:
        assert claim not in text
