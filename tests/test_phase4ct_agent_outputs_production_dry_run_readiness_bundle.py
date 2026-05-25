from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import tools.check_phase4ct_agent_outputs_production_dry_run_readiness_bundle as checker


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_phase4ct_agent_outputs_production_readonly_dry_run.py"
PLAN = ROOT / "docs/development/phase_4ct_agent_outputs_production_dry_run_readiness_bundle.yaml"
DOC = ROOT / "docs/development/phase_4ct_agent_outputs_production_dry_run_readiness_bundle.md"


def load_yaml(path: Path) -> dict:
    return checker.load_yaml(path)


def run_runner(args: list[str] | None = None, env: dict[str, str] | None = None) -> dict:
    output = ROOT / ".tmp_phase4ct_runner_test.json"
    if output.exists():
        output.unlink()
    proc_env = os.environ.copy()
    for key in (
        "AICRM_PHASE4CT_PRODUCTION_READONLY_DRY_RUN_APPROVED",
        "AICRM_PHASE4CT_PRODUCTION_CONFIG_REVIEWED",
        "AICRM_AGENT_OUTPUTS_REPO_BACKEND",
        "AICRM_AGENT_OUTPUTS_READONLY_DRY_RUN_DATABASE_URL",
        "DATABASE_URL",
        "AICRM_AGENT_OUTPUTS_TEST_DATABASE_URL",
        "AICRM_AGENT_OUTPUTS_STAGING_DATABASE_URL",
    ):
        proc_env.pop(key, None)
    proc_env.update(env or {})
    cmd = [sys.executable, str(RUNNER), "--output-json", str(output)]
    if args:
        cmd.extend(args)
    proc = subprocess.run(cmd, cwd=ROOT, env=proc_env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert proc.returncode == 0, proc.stderr
    data = checker.json.loads(output.read_text(encoding="utf-8"))
    output.unlink()
    return data


def test_checker_passes_for_phase4ct_bundle() -> None:
    report = checker.build_report()
    assert report["ok"], report["blockers"]
    assert report["autopilot_deliverable"] is True


def test_runner_default_blocked_without_db_connection() -> None:
    data = run_runner()
    assert data["ok"] is True
    assert data["result_status"] == "not_executed_missing_approval"
    assert data["production_dry_run_executed"] is False
    assert data["db_connected"] is False
    assert data["writes_attempted"] is False
    assert data["route_owner_changed"] is False
    assert data["production_compat_changed"] is False
    assert data["fallback_removed"] is False
    assert data["agent_execution_triggered"] is False
    assert data["workflow_execution_triggered"] is False
    assert data["outbound_send_triggered"] is False
    assert data["llm_call_triggered"] is False
    assert data["raw_payload_exported"] is False
    assert data["file_download_triggered"] is False


def test_runner_missing_approval_returns_not_executed_missing_approval() -> None:
    data = run_runner(
        ["--read-only", "--confirm-no-writes"],
        {
            "AICRM_PHASE4CT_PRODUCTION_CONFIG_REVIEWED": "1",
            "AICRM_AGENT_OUTPUTS_REPO_BACKEND": "sqlalchemy",
            "AICRM_AGENT_OUTPUTS_READONLY_DRY_RUN_DATABASE_URL": "sqlite+pysqlite:////tmp/phase4ct_readonly.db",
        },
    )
    assert data["result_status"] == "not_executed_missing_approval"
    assert data["db_connected"] is False


def test_runner_missing_config_review_returns_not_executed_config_not_reviewed() -> None:
    data = run_runner(
        ["--read-only", "--confirm-no-writes"],
        {
            "AICRM_PHASE4CT_PRODUCTION_READONLY_DRY_RUN_APPROVED": "1",
            "AICRM_AGENT_OUTPUTS_REPO_BACKEND": "sqlalchemy",
            "AICRM_AGENT_OUTPUTS_READONLY_DRY_RUN_DATABASE_URL": "sqlite+pysqlite:////tmp/phase4ct_readonly.db",
        },
    )
    assert data["result_status"] == "not_executed_config_not_reviewed"
    assert data["db_connected"] is False


def test_runner_missing_database_url_returns_not_executed_missing_database_url() -> None:
    data = run_runner(
        ["--read-only", "--confirm-no-writes"],
        {
            "AICRM_PHASE4CT_PRODUCTION_READONLY_DRY_RUN_APPROVED": "1",
            "AICRM_PHASE4CT_PRODUCTION_CONFIG_REVIEWED": "1",
            "AICRM_AGENT_OUTPUTS_REPO_BACKEND": "sqlalchemy",
        },
    )
    assert data["result_status"] == "not_executed_missing_database_url"
    assert data["db_connected"] is False


@pytest.mark.parametrize("args", [[], ["--read-only"], ["--confirm-no-writes"]])
def test_runner_requires_read_only_and_confirm_no_writes(args: list[str]) -> None:
    data = run_runner(
        args,
        {
            "AICRM_PHASE4CT_PRODUCTION_READONLY_DRY_RUN_APPROVED": "1",
            "AICRM_PHASE4CT_PRODUCTION_CONFIG_REVIEWED": "1",
            "AICRM_AGENT_OUTPUTS_REPO_BACKEND": "sqlalchemy",
            "AICRM_AGENT_OUTPUTS_READONLY_DRY_RUN_DATABASE_URL": "sqlite+pysqlite:////tmp/phase4ct_readonly.db",
        },
    )
    assert data["result_status"] == "not_executed_read_only_flags_missing"
    assert data["db_connected"] is False


def test_runner_does_not_fallback_to_database_url() -> None:
    data = run_runner(
        ["--read-only", "--confirm-no-writes"],
        {
            "AICRM_PHASE4CT_PRODUCTION_READONLY_DRY_RUN_APPROVED": "1",
            "AICRM_PHASE4CT_PRODUCTION_CONFIG_REVIEWED": "1",
            "AICRM_AGENT_OUTPUTS_REPO_BACKEND": "sqlalchemy",
            "DATABASE_URL": "sqlite+pysqlite:////tmp/forbidden_shared.db",
            "AICRM_AGENT_OUTPUTS_TEST_DATABASE_URL": "sqlite+pysqlite:////tmp/forbidden_test.db",
            "AICRM_AGENT_OUTPUTS_STAGING_DATABASE_URL": "sqlite+pysqlite:////tmp/forbidden_stage.db",
        },
    )
    assert data["result_status"] == "not_executed_missing_database_url"
    assert data["evidence"]["database_url_fallback_used"] is False
    assert data["evidence"]["test_or_staging_db_fallback_used"] is False
    assert data["db_connected"] is False


def test_runner_does_not_allow_write_execution_send_replay_export_download_or_agent_run() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    for forbidden in (
        ".create_agent_output(",
        ".update_agent_output(",
        ".delete_agent_output(",
        ".start_agent_run(",
        ".dispatch_agent_run(",
        ".execute_agent_run(",
        ".run_due(",
        ".send(",
        ".replay(",
        ".export(",
        ".download(",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
    ):
        assert forbidden not in text
    data = run_runner()
    safety = data["side_effect_safety"]
    assert safety["create_update_delete_executed"] is False
    assert safety["run_due_triggered"] is False
    assert safety["agent_execution_triggered"] is False
    assert safety["agent_run_triggered"] is False
    assert safety["replay_triggered"] is False
    assert safety["task_execution_triggered"] is False
    assert safety["workflow_execution_triggered"] is False
    assert safety["timer_execution_triggered"] is False
    assert safety["outbound_send_triggered"] is False
    assert safety["llm_call_triggered"] is False
    assert safety["raw_payload_exported"] is False
    assert safety["file_download_triggered"] is False


def test_yaml_authorizations_all_false() -> None:
    data = load_yaml(PLAN)
    assert data["route_family"] == "/api/admin/automation-conversion/agent-outputs*"
    assert data["bundle_type"] == "production_readonly_dry_run_readiness_bundle"
    assert data["authorizations"]
    assert all(value is False for value in data["authorizations"].values())


def test_docs_do_not_claim_production_or_canary_approval() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "production approved" not in text
    assert "canary approved" not in text
    assert "delete_ready: true" not in text
    assert "delete_ready true" not in text


def test_runner_blocked_evidence_records_execution_and_output_risk_flags() -> None:
    data = run_runner()
    assert data["agent_execution_triggered"] is False
    assert data["workflow_execution_triggered"] is False
    assert data["outbound_send_triggered"] is False
    assert data["llm_call_triggered"] is False
    assert data["raw_payload_exported"] is False
    assert data["file_download_triggered"] is False
