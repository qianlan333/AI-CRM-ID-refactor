from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4m_profile_segment_template_staging_smoke_package.py"
RUNNER = ROOT / "tools/run_phase4m_profile_segment_template_staging_smoke.py"
PLAN_YAML = ROOT / "docs/development/phase_4m_profile_segment_template_staging_smoke_package.yaml"
PLAN_MD = ROOT / "docs/development/phase_4m_profile_segment_template_staging_smoke_package.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml() -> dict:
    return _load_module(CHECKER, "phase4m_checker").load_yaml(PLAN_YAML)


def _run_runner(tmp_path: Path, env: dict[str, str], *extra_args: str) -> dict:
    output = tmp_path / "runner.json"
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


def test_yaml_flags_false_and_runner_defaults() -> None:
    data = _load_yaml()
    for field in (
        "staging_smoke_execution_authorized",
        "production_data_allowed",
        "production_repository_enablement_authorized",
        "production_route_ownership_switch_authorized",
        "fallback_removal_authorized",
        "production_compat_change_authorized",
        "real_external_call_authorized",
        "delete_ready",
    ):
        assert data[field] is False
    assert data["runner"]["default_mode"] == "dry_run"
    assert data["runner"]["execute_writes_requires_flag"] is True
    assert "DATABASE_URL" in data["runner"]["forbidden_env_fallbacks"]


def test_runner_rejects_production_looking_urls(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND": "sqlalchemy",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL": "postgresql://user:pass@db/aicrm_production",
    }
    data = _run_runner(tmp_path, env)
    assert data["_returncode"] == 1
    assert data["ok"] is False
    assert data["db_url_safety"]["ok"] is False
    assert "production" in data["db_url_safety"]["matched_forbidden_markers"]


def test_runner_rejects_allowed_and_forbidden_marker_mix(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND": "sqlalchemy",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL": "postgresql://user:pass@db/staging_prod_shadow",
    }
    data = _run_runner(tmp_path, env)
    assert data["_returncode"] == 1
    assert data["db_url_safety"]["matched_allowed_markers"]
    assert data["db_url_safety"]["matched_forbidden_markers"]


def test_runner_does_not_fallback_to_database_url(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql://user:pass@db/staging_ai_crm",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND": "sqlalchemy",
    }
    env.pop("AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL", None)
    data = _run_runner(tmp_path, env)
    assert data["_returncode"] == 1
    assert data["db_url_safety"]["reason"] == "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL is required"
    assert data["db_url_safety"]["connected"] is False


def test_runner_defaults_to_dry_run_and_requires_execute_flag_for_write_mode(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND": "sqlalchemy",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL": "postgresql://user:pass@db/staging_ai_crm",
    }
    dry = _run_runner(tmp_path, env)
    assert dry["_returncode"] == 0, dry["_stdout"]
    assert dry["dry_run"] is True
    assert dry["execute_writes"] is False
    assert any(item.get("skipped") for item in dry["details"])

    execute = _run_runner(tmp_path, env | {"AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL": "postgresql://user:pass@db/prod_stage"}, "--execute-writes")
    assert execute["_returncode"] == 1
    assert execute["execute_writes"] is True
    assert execute["dry_run"] is False
    assert execute["db_url_safety"]["matched_forbidden_markers"]


def test_smoke_matrix_and_side_effect_safety_complete() -> None:
    data = _load_yaml()
    assert set(data["smoke_matrix"]["read"]) >= {"catalog", "list", "options", "detail"}
    assert set(data["smoke_matrix"]["write"]) >= {
        "create_with_idempotency",
        "create_replay",
        "create_conflict",
        "duplicate_template_rejected",
        "update_existing",
        "update_missing",
        "invalid_payload_rejected",
        "dangerous_field_rejected",
        "audit_log_created",
        "rollback_payload_present",
        "side_effect_safety_false",
    }
    assert all(value is False for value in data["side_effect_safety"].values())


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
        "staging smoke executed",
        "production dry-run authorized",
        "production repository enabled",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ):
        assert forbidden not in text
