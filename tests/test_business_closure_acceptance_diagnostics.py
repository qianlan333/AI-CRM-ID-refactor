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
    payload = run(scenario="external_orders", request_token="secret-token", env={"AUTOMATION_INTERNAL_API_TOKEN": "secret-token"})
    item = payload["items"][0]
    evidence = item["external_orders_evidence"]

    assert item["missing_env"] == []
    assert item["required_env"] == [{"key": "AUTOMATION_INTERNAL_API_TOKEN", "configured": True, "value": "[redacted]"}]
    assert "/api/external/orders" in item["routes"]
    assert item["inputs"]["request_token"] == "[redacted]"
    assert evidence["token_configured"] is True
    assert evidence["token_redacted"] is True
    assert evidence["token_never_logged"] is True
    assert evidence["request_mode"] == "valid_token"
    assert evidence["auth_status"] == "valid_token_readiness"
    assert evidence["route_owner"] == "ai_crm_next"
    assert evidence["fallback_used"] is False
    assert "secret-token" not in json.dumps(payload, ensure_ascii=False)


def test_external_orders_missing_internal_token_is_controlled_disabled() -> None:
    payload = run(scenario="external_orders", env={})
    item = payload["items"][0]
    evidence = item["external_orders_evidence"]

    assert payload["ok"] is True
    assert item["status"] == "controlled_disabled"
    assert evidence["token_configured"] is False
    assert evidence["request_mode"] == "dry_run"
    assert evidence["auth_status"] == "controlled_disabled"
    assert evidence["controlled_disabled_reason"] == "AUTOMATION_INTERNAL_API_TOKEN not configured"
    assert "missing_internal_token_config" in {reason["code"] for reason in evidence["blocking_reasons"]}
    assert evidence["real_external_call_executed"] is False
    assert evidence["production_write_executed"] is False


def test_external_orders_missing_and_invalid_request_token_paths() -> None:
    no_token = run(scenario="external_orders", env={"AUTOMATION_INTERNAL_API_TOKEN": "server-token"})["items"][0][
        "external_orders_evidence"
    ]
    wrong_token_payload = run(
        scenario="external_orders",
        request_token="wrong-token",
        env={"AUTOMATION_INTERNAL_API_TOKEN": "server-token"},
    )
    wrong_token = wrong_token_payload["items"][0]["external_orders_evidence"]

    assert no_token["request_mode"] == "no_token"
    assert "missing_request_token" in {reason["code"] for reason in no_token["blocking_reasons"]}
    assert wrong_token["request_mode"] == "wrong_token"
    assert wrong_token["auth_status"] == "invalid_request_token"
    assert "invalid_request_token" in {reason["code"] for reason in wrong_token["blocking_reasons"]}
    assert "wrong-token" not in json.dumps(wrong_token_payload, ensure_ascii=False)


def test_external_orders_valid_token_remains_readiness_without_order_evidence() -> None:
    payload = run(
        scenario="external_orders",
        request_token="server-token",
        env={"AUTOMATION_INTERNAL_API_TOKEN": "server-token"},
    )
    evidence = payload["items"][0]["external_orders_evidence"]
    codes = {reason["code"] for reason in evidence["blocking_reasons"]}

    assert evidence["request_mode"] == "valid_token"
    assert evidence["reconciliation_status"] == "readiness_only"
    assert evidence["operator_action_required"] is True
    assert "token_configured_but_not_executed" in codes
    assert "missing_order_evidence" in codes
    assert evidence["real_external_call_executed"] is False


def test_external_orders_complete_order_evidence_links_order_without_sensitive_output() -> None:
    payload = run(
        scenario="external_orders",
        request_token="server-token",
        order_no="order_42",
        external_order_id="ext_order_42",
        idempotency_key="idem_42",
        customer_id="cust_42",
        channel_id="channel_42",
        source="gray_partner",
        internal_event_id="evt_42",
        admin_order_visibility="visible",
        env={"AUTOMATION_INTERNAL_API_TOKEN": "server-token"},
    )
    item = payload["items"][0]
    evidence = item["external_orders_evidence"]

    assert item["status"] == "order_linked"
    assert evidence["evidence_status"] == "ORDER_LINKED_EVIDENCE_ATTACHED"
    assert evidence["derived_status"] == "order_linked"
    assert evidence["order_id"] == "order_42"
    assert evidence["external_order_id"] == "ext_order_42"
    assert evidence["idempotency_key"] == "idem_42"
    assert evidence["customer_id"] == "cust_42"
    assert evidence["channel_id"] == "channel_42"
    assert evidence["source"] == "gray_partner"
    assert evidence["internal_event_id"] == "evt_42"
    assert evidence["admin_order_visibility"] == "visible"
    assert evidence["operator_action_required"] is False
    assert evidence["blocking_reasons"] == [
        {
            "code": "order_linked",
            "message": "Order, idempotency, customer/channel/source, event, and admin visibility evidence are attached.",
        }
    ]
    assert "server-token" not in json.dumps(payload, ensure_ascii=False)


def test_ops_plan_e2e_without_plan_id_returns_blocking_reason() -> None:
    payload = run(scenario="ops_plan_to_broadcast", env={})
    item = payload["items"][0]
    evidence = item["e2e_evidence"]

    assert payload["ok"] is True
    assert item["status"] == "missing_plan_id"
    assert item["blocking_reasons"] == [{"code": "missing_plan_id", "message": "--plan-id is required to trace an ops plan approval E2E."}]
    assert evidence["plan_id"] == "not_provided"
    assert evidence["derived_status"] == "missing_plan_id"
    assert evidence["pending_reason"] == "plan_id_not_provided"
    assert item["real_external_call_executed"] is False


def test_ops_plan_e2e_pending_approval_and_missing_internal_event_states() -> None:
    pending = run(scenario="ops_plan_to_broadcast", plan_id="plan_1", approval_status="pending", env={})["items"][0]["e2e_evidence"]
    missing_event = run(
        scenario="ops_plan_to_broadcast",
        plan_id="plan_1",
        approval_status="approved",
        approval_event_id="approval_1",
        env={},
    )["items"][0]["e2e_evidence"]

    assert pending["derived_status"] == "pending_approval"
    assert pending["operator_action_required"] is True
    assert pending["pending_reason"] == "plan_not_approved"
    assert missing_event["derived_status"] == "missing_internal_event"
    assert missing_event["approval_event_id"] == "approval_1"
    assert missing_event["pending_reason"] == "approval_without_internal_event_evidence"


def test_ops_plan_e2e_consumer_pending_failed_and_success_evidence() -> None:
    consumer_pending = run(
        scenario="ops_plan_to_broadcast",
        plan_id="plan_1",
        approval_status="approved",
        internal_event_id="evt_1",
        env={},
    )["items"][0]["e2e_evidence"]
    failed = run(
        scenario="ops_plan_to_broadcast",
        plan_id="plan_1",
        approval_status="approved",
        internal_event_id="evt_1",
        consumer_run_id="run_1",
        consumer_status="failed_retryable",
        env={},
    )["items"][0]["e2e_evidence"]
    success = run(
        scenario="ops_plan_to_broadcast",
        plan_id="plan_1",
        approval_status="approved",
        internal_event_id="evt_1",
        consumer_run_id="run_1",
        consumer_status="succeeded",
        broadcast_job_id="broadcast_1",
        effect_job_id="effect_1",
        push_center_job_id="push_1",
        duplicate_handling="reused_idempotency_key",
        env={},
    )["items"][0]["e2e_evidence"]

    assert consumer_pending["derived_status"] == "consumer_pending"
    assert consumer_pending["pending_reason"] == "internal_event_has_no_consumer_run_evidence"
    assert failed["derived_status"] == "consumer_failed"
    assert failed["retryable"] is True
    assert failed["operator_action_required"] is True
    assert success["evidence_status"] == "E2E_EVIDENCE_ATTACHED"
    assert success["derived_status"] == "job_linked"
    assert success["broadcast_job_id"] == "broadcast_1"
    assert success["external_effect_job_id"] == "effect_1"
    assert success["push_center_reconciliation_route"] == "/api/admin/push-center/jobs/push_1/reconciliation"
    assert success["duplicate_handling"] == "reused_idempotency_key"


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


def test_ops_plan_e2e_evidence_template_forbids_secrets_and_requires_fields() -> None:
    template = (ROOT / "docs" / "reports" / "ops_plan_to_broadcast_e2e_evidence_template.md").read_text(encoding="utf-8")

    assert "approval_event_id" in template
    assert "internal_event_id" in template
    assert "consumer_run_id" in template
    assert "broadcast_job_id" in template
    assert "external_effect_job_id" in template
    assert "不得提交 token" in template
    assert "不得提交 raw external_userid" in template


def test_external_orders_evidence_template_forbids_secrets_and_requires_fields() -> None:
    template = (ROOT / "docs" / "reports" / "external_orders_enablement_evidence_template.md").read_text(encoding="utf-8")

    assert "READINESS_ONLY" in template
    assert "ORDER_LINKED_EVIDENCE_ATTACHED" in template
    assert "token_configured" in template
    assert "idempotency_key" in template
    assert "customer_id" in template
    assert "channel_id" in template
    assert "internal_event_id" in template
    assert "admin_order_visibility" in template
    assert "Do not commit" in template
    assert "Authorization" in template
    assert "raw external_userid" in template
    assert "phone number" in template
