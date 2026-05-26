from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import tools.check_phase6g_low_risk_external_adapter_enablement_tooling as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_6g_low_risk_external_adapter_enablement_tooling.yaml"


def _run(path: Path) -> dict[str, object]:
    proc = subprocess.run([sys.executable, str(path.relative_to(ROOT))], cwd=ROOT, text=True, stdout=subprocess.PIPE, check=True)
    return json.loads(proc.stdout)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_authorizations_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())


def test_selected_and_excluded_families() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert {item["family_key"] for item in data["selected_families"]} == checker.SELECTED
    assert {item["family_key"] for item in data["excluded_families"]} == checker.EXCLUDED


def test_default_runners_are_blocked_and_side_effect_free() -> None:
    for runner in checker.RUNNERS.values():
        evidence = _run(runner)
        assert evidence["ok"] is True
        assert evidence["result_status"] == "blocked_missing_required_gates"
        assert evidence["missing_env_gates"]
        for key in checker.FALSE_DEFAULT_KEYS:
            assert evidence[key] is False


def test_business_continuity_and_next_bundle() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is True for value in data["business_continuity"].values())
    assert data["next"] == ["phase_6h_production_compat_exact_route_narrowing_readiness_bundle"]
