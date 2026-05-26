from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase7k_final_route_ownership_manifest_cleanup as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_7k_final_route_ownership_manifest_cleanup.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_authorizations_remain_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for key in checker.FALSE_AUTHORIZATIONS:
        assert data["authorizations"][key] is False


def test_all_required_route_families_are_present() -> None:
    families = {item["family"] for item in checker.load_yaml(PLAN_YAML)["route_families"]}
    assert checker.REQUIRED_FAMILIES <= families


def test_every_family_retains_fallback_compat_and_delete_ready_false() -> None:
    for item in checker.load_yaml(PLAN_YAML)["route_families"]:
        assert item["fallback_retained"] is True
        assert item["production_compat_retained"] is True
        assert item["delete_ready"] is False


def test_next_bundle_is_phase_7l() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["next"] == [checker.NEXT_BUNDLE]
