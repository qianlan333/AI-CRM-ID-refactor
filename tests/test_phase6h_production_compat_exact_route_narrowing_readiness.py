from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import tools.check_phase6h_production_compat_exact_route_narrowing_readiness as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_6h_production_compat_exact_route_narrowing_readiness.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_authorizations_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())


def test_candidate_routes_are_exact_and_expected() -> None:
    data = checker.load_yaml(PLAN_YAML)
    route_keys = {(item["method"], item["exact_route"]) for item in data["candidate_exact_routes"]}
    assert route_keys == checker.EXPECTED_ROUTES
    assert all("*" not in item["exact_route"] for item in data["candidate_exact_routes"])
    assert all(item["proposed_narrowing_only"] is True for item in data["candidate_exact_routes"])
    assert all(item["shadow_compare_required"] is True for item in data["candidate_exact_routes"])
    assert all(item["rollback_required"] is True for item in data["candidate_exact_routes"])


def test_runner_outputs_proposed_narrowing_only_without_side_effects() -> None:
    proc = subprocess.run([sys.executable, str(checker.RUNNER.relative_to(ROOT))], cwd=ROOT, text=True, stdout=subprocess.PIPE, check=True)
    evidence = json.loads(proc.stdout)
    assert evidence["result_status"] == "proposed_narrowing_only"
    for key in checker.FALSE_RUNNER_KEYS:
        assert evidence[key] is False


def test_exclusions_and_business_continuity() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert {item["family"] for item in data["excluded_routes"]} == checker.EXCLUDED
    assert all(value is True for value in data["business_continuity"].values())
    assert data["next"] == ["phase_6i_external_enablement_and_compat_readiness_acceptance_bundle"]
