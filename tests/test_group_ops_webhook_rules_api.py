from __future__ import annotations

from tests.group_ops_test_helpers import error_code, group_ops_api_client


def test_create_no_sop_webhook_receiver_returns_one_time_token(group_ops_api_client):
    response = group_ops_api_client.post(
        "/api/automation/group-ops/plans",
        json={
            "name": "核心功能激活计划",
            "type": "webhook_receiver",
            "status": "disabled",
            "operatorMemberId": "HuangYouCan",
            "defaultActionType": "record_only",
            "allowNoSop": True,
            "description": "通过 Webhook 触发核心功能激活任务",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["planId"].startswith("plan_")
    assert body["type"] == "webhook_receiver"
    assert body["webhook"]["endpointKey"]
    assert body["webhook"]["token"]

    detail = group_ops_api_client.get(f"/api/automation/group-ops/plans/{body['id']}")
    assert detail.status_code == 200
    assert "token" not in detail.json()["plan"]["webhook"]
    assert detail.json()["plan"]["allowNoSop"] is True


def test_webhook_direct_recipients_idempotency_and_disabled_guard(group_ops_api_client):
    created = group_ops_api_client.post(
        "/api/automation/group-ops/plans",
        json={
            "name": "Webhook recipient plan",
            "type": "webhook_receiver",
            "status": "disabled",
            "operatorMemberId": "HuangYouCan",
            "defaultActionType": "record_only",
            "allowNoSop": True,
        },
    ).json()
    endpoint_key = created["webhook"]["endpointKey"]
    token = created["webhook"]["token"]
    disabled = group_ops_api_client.post(
        f"/api/automation/group-ops/webhooks/{endpoint_key}",
        headers={"Authorization": f"Bearer {token}", "X-Idempotency-Key": "pytest-disabled"},
        json={
            "event": "core_feature_activation",
            "recipients": [{"external_user_id": "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"}],
            "action": {"action_type": "record_only"},
        },
    )
    assert disabled.status_code == 409
    assert error_code(disabled) == "plan_not_active"

    enabled = group_ops_api_client.post(f"/api/automation/group-ops/plans/{created['id']}/enable")
    assert enabled.status_code == 200

    first = group_ops_api_client.post(
        f"/api/automation/group-ops/webhooks/{endpoint_key}",
        headers={"Authorization": f"Bearer {token}", "X-Idempotency-Key": "pytest-direct-1"},
        json={
            "event": "core_feature_activation",
            "source": "pytest",
            "sender": {"operatorAccount": "HuangYouCan"},
            "recipients": [{"external_user_id": "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"}],
            "action": {"action_type": "record_only"},
        },
    )
    duplicate = group_ops_api_client.post(
        f"/api/automation/group-ops/webhooks/{endpoint_key}",
        headers={"Authorization": f"Bearer {token}", "X-Idempotency-Key": "pytest-direct-1"},
        json={
            "event": "core_feature_activation",
            "recipients": [{"external_user_id": "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"}],
            "action": {"action_type": "record_only"},
        },
    )

    assert first.status_code == 202
    assert first.json()["executed"] == 1
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    logs = group_ops_api_client.get(f"/api/automation/group-ops/plans/{created['id']}/executions")
    assert logs.status_code == 200
    assert logs.json()["total"] == 1
    assert logs.json()["items"][0]["external_user_id"] == "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"


def test_rules_segmentation_and_missing_builtin_data_source_are_explicit(group_ops_api_client):
    rules = group_ops_api_client.get("/api/automation/group-ops/audience-rules")
    assert rules.status_code == 200
    assert "has_used_core_feature" in {item["rule_key"] for item in rules.json()["items"]}

    created = group_ops_api_client.post(
        "/api/automation/group-ops/plans",
        json={"name": "Rule plan", "type": "webhook_receiver", "operatorMemberId": "HuangYouCan"},
    ).json()
    bound = group_ops_api_client.put(
        f"/api/automation/group-ops/plans/{created['id']}/segmentation",
        json={
            "segmentationType": "preset_rule",
            "ruleKey": "has_used_core_feature",
            "ruleVersion": 1,
            "params": {"lookback_days": 30},
            "layerActions": {"high_intent_not_used": {"actionType": "record_only"}},
        },
    )
    assert bound.status_code == 200

    preview = group_ops_api_client.post(
        "/api/automation/group-ops/audience-rules/has_used_core_feature/preview",
        json={"planId": created["id"], "version": 1, "params": {"lookback_days": 30}, "limit": 20},
    )
    assert preview.status_code == 400
    assert error_code(preview) in {"rule_data_source_missing", "contract_error"}


def test_send_message_action_port_uses_real_dispatch_seam(monkeypatch):
    from aicrm_next.automation_engine.group_ops.action_port import DefaultGroupOpsActionPort

    captured: dict = {}

    class DummyApp:
        def app_context(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_dispatch(task_type, fn_name, payload):
        captured.update({"task_type": task_type, "fn_name": fn_name, "payload": payload})
        return {"task_id": 123, "wecom_result": {"errcode": 0, "errmsg": "ok"}}

    monkeypatch.setattr("aicrm_next.integration_gateway.legacy_flask_facade._legacy_app", lambda: DummyApp())
    monkeypatch.setattr("wecom_ability_service.domains.tasks.service.dispatch_wecom_task", fake_dispatch)

    result = DefaultGroupOpsActionPort().dispatch(
        {
            "plan_id": 1,
            "trigger_event_id": "evt_001",
            "operator_member_id": "HuangYouCan",
            "recipient": {"external_user_id": "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"},
            "action": {"action_type": "send_message", "content": "AI-CRM Webhook 触发测试消息"},
        }
    )

    assert result["ok"] is True
    assert result["side_effect_executed"] is True
    assert captured["task_type"] == "private_message"
    assert captured["fn_name"] == "create_private_message_task"
    assert captured["payload"]["sender"] == "HuangYouCan"
    assert captured["payload"]["external_userid"] == ["wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"]
