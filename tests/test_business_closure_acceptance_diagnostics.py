from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.diagnose_business_closure_acceptance import SCENARIOS, run

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "diagnose_business_closure_acceptance.py"


def test_all_business_closure_scenarios_are_dry_run_and_safe_by_default() -> None:
    payload = run(scenario="all", env={})

    assert payload["ok"] is True
    assert payload["real_external_call_executed"] is False
    assert payload["production_write_executed"] is False
    assert payload["deploy_or_env_modified"] is False
    assert {item["scenario"] for item in payload["items"]} == set(SCENARIOS)
    assert all(item["dry_run"] is True for item in payload["items"])
    assert all(item["real_external_call_executed"] is False for item in payload["items"])


def test_group_ops_execute_request_is_blocked_without_approval_and_receiver() -> None:
    payload = run(scenario="group_ops_gray_send", execute=True, env={})
    item = payload["items"][0]

    assert payload["ok"] is False
    assert item["status"] == "blocked"
    assert item["operator_execute_allowed"] is False
    assert "AICRM_GROUP_OPS_GRAY_SEND_APPROVED" in item["missing_env"]
    assert item["real_external_call_executed"] is False
    assert item["production_write_executed"] is False


def test_execute_readiness_redacts_receiver_and_env_values() -> None:
    env = {
        "AICRM_GROUP_OPS_GRAY_SEND_APPROVED": "true",
        "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST": "receiver-a",
    }
    payload = run(scenario="group_ops_gray_send", execute=True, receiver_token="receiver-a", env=env)
    item = payload["items"][0]

    assert payload["ok"] is True
    assert item["operator_execute_allowed"] is True
    assert item["dry_run"] is False
    assert item["inputs"]["receiver_token"] == "[redacted]"
    assert all(row["value"] == "[redacted]" for row in item["required_env"])
    assert item["real_external_call_executed"] is False


def test_external_orders_readiness_reports_internal_token_without_leaking_value() -> None:
    payload = run(scenario="external_orders_enablement", env={"AUTOMATION_INTERNAL_API_TOKEN": "secret-token"})
    item = payload["items"][0]

    assert item["missing_env"] == []
    assert item["required_env"] == [{"key": "AUTOMATION_INTERNAL_API_TOKEN", "configured": True, "value": "[redacted]"}]
    assert "/api/external/orders" in item["routes"]


def test_cli_outputs_json_and_blocks_unsafe_execute() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--scenario", "wecom_callback_gray", "--execute"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert payload["ok"] is False
    assert payload["items"][0]["status"] == "blocked"
    assert payload["items"][0]["real_external_call_executed"] is False
