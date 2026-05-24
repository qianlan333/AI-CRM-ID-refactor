from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.py"
TOOL = ROOT / "tools/run_phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.py"
PLAN_YAML = ROOT / "docs/development/phase_4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.yaml"
PLAN_MD = ROOT / "docs/development/phase_4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml() -> dict:
    return _load_module(CHECKER, "phase4u_checker").load_yaml(PLAN_YAML)


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED",
        "AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL",
        "DATABASE_URL",
        "AICRM_NEXT_TEST_DATABASE_URL",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL",
    ):
        env.pop(key, None)
    return env


def _run_tool(tmp_path: Path, env: dict[str, str], *extra_args: str) -> dict:
    output = tmp_path / "phase4u.json"
    proc = subprocess.run(
        ["python3", str(TOOL.relative_to(ROOT)), *extra_args, "--output-json", str(output)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    data["_returncode"] = proc.returncode
    data["_stdout"] = proc.stdout
    return data


def test_checker_current_repo_passes() -> None:
    proc = subprocess.run(
        ["python3", str(CHECKER.relative_to(ROOT))],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout
    assert "overall: PASS" in proc.stdout


def test_evidence_tool_returns_missing_approval(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"] = "1"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"] = "sqlalchemy"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"] = "postgresql://user:secret@db/prod_aicrm"
    data = _run_tool(tmp_path, env, "--read-only", "--confirm-no-writes")
    assert data["_returncode"] == 0
    assert data["execution"]["result_status"] == "not_executed_missing_approval"
    assert data["execution"]["lower_runner_called"] is False
    assert data["readiness"]["route_switch_ready"] is False


def test_evidence_tool_returns_config_not_reviewed(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"] = "1"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"] = "sqlalchemy"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"] = "postgresql://user:secret@db/prod_aicrm"
    data = _run_tool(tmp_path, env, "--read-only", "--confirm-no-writes")
    assert data["_returncode"] == 0
    assert data["execution"]["result_status"] == "not_executed_config_not_reviewed"
    assert data["execution"]["lower_runner_called"] is False


def test_evidence_tool_returns_missing_production_db(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"] = "1"
    env["AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"] = "1"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"] = "sqlalchemy"
    data = _run_tool(tmp_path, env, "--read-only", "--confirm-no-writes")
    assert data["_returncode"] == 0
    assert data["execution"]["result_status"] == "not_executed_missing_production_db"
    assert data["execution"]["lower_runner_called"] is False


def test_evidence_tool_refuses_without_read_only_no_write_args(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"] = "1"
    env["AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"] = "1"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"] = "sqlalchemy"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"] = "postgresql://user:secret@db/prod_aicrm"
    data = _run_tool(tmp_path, env)
    assert data["_returncode"] == 0
    assert data["execution"]["result_status"] == "not_executed_read_only_flags_missing"
    assert data["execution"]["lower_runner_called"] is False


def test_yaml_flags_and_safety_fields_false() -> None:
    data = _load_yaml()
    for field in (
        "production_write_authorized",
        "production_repository_route_enablement_authorized",
        "production_route_ownership_switch_authorized",
        "fallback_removal_authorized",
        "production_compat_change_authorized",
        "production_write_canary_authorized",
        "real_external_call_authorized",
        "delete_ready",
    ):
        assert data[field] is False
    assert data["execution"]["writes_attempted"] is False
    assert all(value is False for value in data["side_effect_safety"].values())


def test_readiness_defaults_are_not_ready_for_blocked_evidence() -> None:
    readiness = _load_yaml()["readiness"]
    assert readiness["route_switch_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["blockers"]


def test_docs_do_not_claim_forbidden_states() -> None:
    text = PLAN_MD.read_text(encoding="utf-8").lower()
    for forbidden in (
        "production write executed",
        "production repository enabled as route owner",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ):
        assert forbidden not in text
