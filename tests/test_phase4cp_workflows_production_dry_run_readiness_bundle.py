from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import tools.check_phase4cp_workflows_production_dry_run_readiness_bundle as checker
import tools.run_phase4cp_workflows_production_readonly_dry_run as runner


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_phase4cp_workflows_production_readonly_dry_run.py"


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "AICRM_PHASE4CP_PRODUCTION_READONLY_DRY_RUN_APPROVED",
        "AICRM_PHASE4CP_PRODUCTION_CONFIG_REVIEWED",
        "AICRM_WORKFLOWS_READONLY_DRY_RUN_DATABASE_URL",
        "AICRM_WORKFLOWS_REPO_BACKEND",
        "DATABASE_URL",
        "AICRM_WORKFLOWS_TEST_DATABASE_URL",
        "AICRM_WORKFLOWS_STAGING_DATABASE_URL",
    ):
        env.pop(key, None)
    return env


def _run_tool(tmp_path: Path, env: dict[str, str], *extra_args: str) -> dict:
    output = tmp_path / "phase4cp.json"
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
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)
    assert report["autopilot_deliverable"] is True


def test_default_missing_approval_returns_blocked_evidence(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_PHASE4CP_PRODUCTION_READONLY_DRY_RUN_APPROVED", raising=False)
    monkeypatch.delenv("AICRM_PHASE4CP_PRODUCTION_CONFIG_REVIEWED", raising=False)
    monkeypatch.delenv("AICRM_WORKFLOWS_READONLY_DRY_RUN_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@prod.example/main")
    report = runner.run(type("Args", (), {"read_only": False, "confirm_no_writes": False})())
    assert report["ok"] is True
    assert report["execution"]["result_status"] == "not_executed_missing_approval"
    assert report["execution"]["db_connection_attempted"] is False
    assert report["execution"]["read_only_dry_run_executed"] is False
    assert report["evidence"]["database_url_fallback_used"] is False


def test_runner_requires_config_db_backend_and_readonly_flags(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4CP_PRODUCTION_READONLY_DRY_RUN_APPROVED"] = "1"
    data = _run_tool(tmp_path, env, "--read-only", "--confirm-no-writes")
    assert data["execution"]["result_status"] == "not_executed_config_not_reviewed"
    env["AICRM_PHASE4CP_PRODUCTION_CONFIG_REVIEWED"] = "1"
    data = _run_tool(tmp_path, env, "--read-only", "--confirm-no-writes")
    assert data["execution"]["result_status"] == "not_executed_missing_dry_run_db"
    env["AICRM_WORKFLOWS_READONLY_DRY_RUN_DATABASE_URL"] = "postgresql://user:secret@db/prod_aicrm"
    data = _run_tool(tmp_path, env)
    assert data["execution"]["result_status"] == "not_executed_read_only_flags_missing"
    data = _run_tool(tmp_path, env, "--read-only", "--confirm-no-writes")
    assert data["execution"]["result_status"] == "not_executed_backend_not_enabled"


def test_runner_does_not_use_database_url_test_or_staging_fallback(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4CP_PRODUCTION_READONLY_DRY_RUN_APPROVED"] = "1"
    env["AICRM_PHASE4CP_PRODUCTION_CONFIG_REVIEWED"] = "1"
    env["AICRM_WORKFLOWS_REPO_BACKEND"] = "sqlalchemy"
    env["DATABASE_URL"] = "postgresql://user:secret@db/prod_aicrm"
    env["AICRM_WORKFLOWS_TEST_DATABASE_URL"] = "postgresql://user:secret@db/test_aicrm"
    env["AICRM_WORKFLOWS_STAGING_DATABASE_URL"] = "postgresql://user:secret@db/stage_aicrm"
    data = _run_tool(tmp_path, env, "--read-only", "--confirm-no-writes")
    assert data["execution"]["result_status"] == "not_executed_missing_dry_run_db"
    assert data["evidence"]["db_url_redacted"] is None
    assert data["evidence"]["database_url_fallback_used"] is False
    assert data["evidence"]["test_or_staging_db_fallback_used"] is False


def test_runner_redacts_dry_run_db_url(tmp_path: Path) -> None:
    env = _clean_env()
    env["AICRM_PHASE4CP_PRODUCTION_READONLY_DRY_RUN_APPROVED"] = "1"
    env["AICRM_PHASE4CP_PRODUCTION_CONFIG_REVIEWED"] = "1"
    env["AICRM_WORKFLOWS_REPO_BACKEND"] = "sqlalchemy"
    env["AICRM_WORKFLOWS_READONLY_DRY_RUN_DATABASE_URL"] = "postgresql://user:topsecret@db/prod_aicrm"
    data = _run_tool(tmp_path, env)
    assert data["execution"]["result_status"] == "not_executed_read_only_flags_missing"
    assert data["evidence"]["db_url_redacted"] == "postgresql://<redacted>@db/prod_aicrm"
    assert "topsecret" not in json.dumps(data)


def test_runner_source_does_not_call_write_methods() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert ".create_workflow(" not in source
    assert ".insert(" not in source
    assert ".delete(" not in source


def test_yaml_and_phase_state_record_phase4cp_readiness() -> None:
    data = checker.load_yaml(checker.PLAN_YAML)
    state = checker.load_yaml(checker.STATE)
    assert data["bundle"]["type"] == "production_read_only_dry_run_readiness_bundle"
    assert data["safety"]["production_write_authorized"] is False
    assert data["safety"]["fallback_removal_authorized"] is False
    assert data["baseline_blockers"]["legacy_facade_growth_freeze"]["this_pr_adds_legacy_growth"] is False
    assert checker.COMPLETED_STEP in state["completed_steps"]
    assert state["active_candidate"] == checker.WORKFLOW_NODES
    assert state["recommended_next_pr"] == checker.NEXT_BUNDLE
    readiness = state["workflows_readiness"]
    assert readiness["production_dry_run_readiness_bundle_completed"] is True
    assert readiness["production_readonly_dry_run_executed"] is False
    assert readiness["production_readonly_db_url_flag"] == "AICRM_WORKFLOWS_READONLY_DRY_RUN_DATABASE_URL"


def test_docs_do_not_claim_forbidden_states() -> None:
    text = checker.DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_CLAIMS:
        assert phrase not in text
