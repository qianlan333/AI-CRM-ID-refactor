from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase7b_baseline_legacy_import_remediation as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_7b_baseline_legacy_import_remediation.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_target_blockers_reduced_to_zero() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["target_blockers"]["before_count"] == 3
    assert data["target_blockers"]["after_count"] == 0


def test_authorizations_remain_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for key in checker.FALSE_AUTHORIZATIONS:
        assert data["authorizations"][key] is False


def test_legacy_facade_growth_freeze_boundary_passes() -> None:
    result = checker.check_aicrm_next_legacy_import_boundary(checker.ROOT)
    assert result["ok"] is True
    assert result["findings"] == []


def test_runtime_files_no_longer_directly_import_legacy_modules() -> None:
    for relpath in (
        "aicrm_next/automation_engine/group_ops/domain.py",
        "aicrm_next/integration_gateway/wecom_group_adapter.py",
    ):
        text = (ROOT / relpath).read_text(encoding="utf-8")
        for legacy_import in checker.REMEDIATED_IMPORTS:
            assert f"from {legacy_import} import" not in text
            assert f"import {legacy_import}" not in text


def test_verification_evidence_declares_no_behavior_change() -> None:
    data = checker.load_yaml(PLAN_YAML)
    evidence = data["verification_evidence"]
    assert evidence["production_behavior_unchanged"] is True
    assert evidence["fallback_retained"] is True
    assert evidence["production_compat_unchanged"] is True
    assert data["next"] == [checker.NEXT_BUNDLE]
