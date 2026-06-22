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
    assert {reason["code"] for reason in item["blocking_reasons"]} == {
        "missing_operator_approval",
        "missing_receiver_allowlist",
        "missing_receiver_token",
    }
    assert item["operator_evidence"]["evidence_status"] == "READINESS_ONLY"
    assert item["operator_evidence"]["operator_action_required"] is True
    assert item["real_external_call_executed"] is False
    assert item["production_write_executed"] is False


def test_group_ops_execute_request_blocks_receiver_outside_allowlist() -> None:
    env = {
        "AICRM_GROUP_OPS_GRAY_SEND_APPROVED": "true",
        "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST": "receiver-a",
    }
    payload = run(scenario="group_ops_gray_send", execute=True, receiver_token="receiver-b", env=env)
    item = payload["items"][0]

    assert payload["ok"] is False
    assert item["operator_execute_allowed"] is False
    assert [reason["code"] for reason in item["blocking_reasons"]] == ["receiver_not_allowlisted"]
    assert item["real_external_call_executed"] is False


def test_execute_readiness_redacts_receiver_and_env_values() -> None:
    env = {
        "AICRM_GROUP_OPS_GRAY_SEND_APPROVED": "true",
        "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST": "receiver-a",
    }
    payload = run(
        scenario="group_ops_gray_send",
        execute=True,
        receiver_token="receiver-a",
        plan_id="plan_42",
        event_id="evt_42",
        effect_job_id="101",
        attempt_id="eea_42",
        push_center_job_id="pcj_42",
        env=env,
    )
    item = payload["items"][0]

    assert payload["ok"] is True
    assert item["operator_execute_allowed"] is True
    assert item["dry_run"] is False
    assert item["inputs"]["receiver_token"] == "[redacted]"
    assert all(row["value"] == "[redacted]" for row in item["required_env"])
    assert "receiver-a" not in json.dumps(payload, ensure_ascii=False)
    assert item["operator_evidence"] == {
        "evidence_status": "READY_FOR_OPERATOR_COLLECTION",
        "plan_id": "plan_42",
        "event_id": "evt_42",
        "effect_job_id": "101",
        "attempt_id": "eea_42",
        "push_center_job_id": "pcj_42",
        "push_center_status": "ready_for_operator_reconciliation",
        "push_center_reconciliation_route": "/api/admin/push-center/jobs/pcj_42/reconciliation",
        "retryable": False,
        "operator_action_required": False,
        "business_explanation": "Gray-send readiness checks passed; collect real job/effect/attempt evidence only during an approved operator run.",
        "next_action_label": "Collect Push Center reconciliation",
    }
    assert item["real_external_call_executed"] is False


def test_group_ops_evidence_skeleton_uses_not_provided_placeholders() -> None:
    payload = run(scenario="group_ops_gray_send", env={})
    evidence = payload["items"][0]["operator_evidence"]

    assert evidence["plan_id"] == "not_provided"
    assert evidence["effect_job_id"] == "not_provided"
    assert evidence["attempt_id"] == "not_provided"
    assert evidence["push_center_job_id"] == "not_provided"
    assert evidence["push_center_reconciliation_route"] == "/api/admin/push-center/jobs/{job_id}/reconciliation"


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


def test_group_ops_evidence_template_forbids_secrets_and_raw_ids() -> None:
    template = (ROOT / "docs" / "reports" / "group_ops_gray_send_evidence_template.md").read_text(encoding="utf-8")

    assert "READINESS_ONLY" in template
    assert "不得提交真实 receiver_token" in template
    assert "不得提交 raw external_userid" in template
    assert "/api/admin/push-center/jobs/{job_id}/reconciliation" in template
