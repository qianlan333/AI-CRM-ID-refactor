from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4r_profile_segment_template_production_readonly_dry_run_runner.py"
RUNNER = ROOT / "tools/run_phase4r_profile_segment_template_production_readonly_dry_run.py"
PLAN_YAML = ROOT / "docs/development/phase_4r_profile_segment_template_production_readonly_dry_run_runner.yaml"
PLAN_MD = ROOT / "docs/development/phase_4r_profile_segment_template_production_readonly_dry_run_runner.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml() -> dict:
    return _load_module(CHECKER, "phase4r_checker").load_yaml(PLAN_YAML)


def _run_runner(tmp_path: Path, env: dict[str, str], *extra_args: str) -> dict:
    output = tmp_path / "phase4r.json"
    proc = subprocess.run(
        ["python3", str(RUNNER.relative_to(ROOT)), *extra_args, "--output-json", str(output)],
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


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED",
        "AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND",
        "DATABASE_URL",
        "AICRM_NEXT_TEST_DATABASE_URL",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL",
    ):
        env.pop(key, None)
    return env


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


def test_runner_returns_blocked_if_approval_env_missing(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"] = "1"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"] = "sqlalchemy"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"] = "postgresql://user:secret@db/prod_aicrm"
    data = _run_runner(tmp_path, env, "--read-only", "--confirm-no-writes")
    assert data["_returncode"] == 1
    assert data["execution_status"] == "not_executed_missing_approval"
    assert data["production_data_access_requested"] is False
    assert data["writes_attempted"] is False


def test_runner_returns_blocked_if_config_review_env_missing(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"] = "1"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"] = "sqlalchemy"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"] = "postgresql://user:secret@db/prod_aicrm"
    data = _run_runner(tmp_path, env, "--read-only", "--confirm-no-writes")
    assert data["_returncode"] == 1
    assert data["execution_status"] == "not_executed_config_not_reviewed"
    assert data["production_data_access_requested"] is False


def test_runner_returns_blocked_if_production_db_env_missing(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"] = "1"
    env["AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"] = "1"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"] = "sqlalchemy"
    data = _run_runner(tmp_path, env, "--read-only", "--confirm-no-writes")
    assert data["_returncode"] == 1
    assert data["execution_status"] == "not_executed_missing_production_db"
    assert data["db_url_redacted"] is None


def test_runner_returns_blocked_if_read_only_args_missing(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"] = "1"
    env["AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"] = "1"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"] = "sqlalchemy"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"] = "postgresql://user:secret@db/prod_aicrm"
    data = _run_runner(tmp_path, env)
    assert data["_returncode"] == 1
    assert data["execution_status"] == "not_executed_read_only_flags_missing"
    assert data["production_data_access_requested"] is False


def test_runner_does_not_use_database_url_fallback(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"] = "1"
    env["AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"] = "1"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"] = "sqlalchemy"
    env["DATABASE_URL"] = "postgresql://user:secret@db/prod_aicrm"
    data = _run_runner(tmp_path, env, "--read-only", "--confirm-no-writes")
    assert data["_returncode"] == 1
    assert data["execution_status"] == "not_executed_missing_production_db"
    assert data["db_url_redacted"] is None


def test_runner_redacts_db_url_secrets(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"] = "1"
    env["AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"] = "1"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"] = "sqlalchemy"
    env["AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"] = "postgresql://user:topsecret@db/prod_aicrm"
    data = _run_runner(tmp_path, env)
    assert data["_returncode"] == 1
    assert data["execution_status"] == "not_executed_read_only_flags_missing"
    assert data["db_url_redacted"] == "postgresql://<redacted>@db/prod_aicrm"
    assert "topsecret" not in json.dumps(data)


def test_runner_source_does_not_call_write_methods() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert ".create_profile_segment_template(" not in source
    assert ".update_profile_segment_template(" not in source
    assert ".delete_profile_segment_template(" not in source


def test_yaml_flags_false() -> None:
    data = _load_yaml()
    for field in (
        "production_dry_run_execution_authorized",
        "production_repository_enablement_authorized",
        "production_route_ownership_switch_authorized",
        "fallback_removal_authorized",
        "production_compat_change_authorized",
        "production_write_authorized",
        "real_external_call_authorized",
        "delete_ready",
    ):
        assert data[field] is False


def test_no_runtime_files_changed_if_git_available() -> None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    assert not any(path.startswith("aicrm_next/") for path in changed)
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)
    assert "app.py" not in changed
    assert "legacy_flask_app.py" not in changed


def test_docs_do_not_claim_forbidden_states() -> None:
    text = PLAN_MD.read_text(encoding="utf-8").lower()
    for forbidden in (
        "production dry-run executed",
        "production repository enabled",
        "production route switch authorized",
        "production write authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ):
        assert forbidden not in text
