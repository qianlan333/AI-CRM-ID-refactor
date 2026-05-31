from __future__ import annotations

from typing import Any, Protocol

from aicrm_next.shared.errors import ContractError

from .domain import clean_text, normalize_action_payload


class DispatchActionInput(dict):
    pass


class GroupOpsActionPort(Protocol):
    def dispatch(self, input_data: dict[str, Any]) -> dict[str, Any]: ...


def _recipient_external_userid(input_data: dict[str, Any]) -> str:
    recipient = input_data.get("recipient") if isinstance(input_data.get("recipient"), dict) else {}
    return clean_text(
        recipient.get("externalUserId")
        or recipient.get("external_user_id")
        or recipient.get("external_userid")
    )


def _recipient_snapshot(input_data: dict[str, Any]) -> dict[str, str]:
    recipient = input_data.get("recipient") if isinstance(input_data.get("recipient"), dict) else {}
    return {
        "user_id": clean_text(recipient.get("userId") or recipient.get("user_id")),
        "external_user_id": _recipient_external_userid(input_data),
        "wechat_user_id": clean_text(recipient.get("wechatUserId") or recipient.get("wechat_user_id")),
        "group_id": clean_text(recipient.get("groupId") or recipient.get("group_id")),
    }


class DefaultGroupOpsActionPort:
    def dispatch(self, input_data: dict[str, Any]) -> dict[str, Any]:
        action = normalize_action_payload(input_data.get("action"), default_action_type="record_only")
        action_type = action["action_type"]
        if action_type == "record_only":
            return {"ok": True, "status": "recorded", "action_ref_id": "", "side_effect_executed": False}
        if action_type == "enqueue":
            return self._enqueue(input_data, action)
        if action_type == "send_message":
            return self._send_message(input_data, action)
        if action_type == "add_to_audience":
            return {
                "ok": True,
                "status": "added",
                "action_ref_id": action.get("audience_id") or "",
                "side_effect_executed": False,
            }
        if action_type == "publish_task":
            return self._enqueue(input_data, {**action, "action_type": "publish_task"})
        raise ContractError(f"unsupported group ops action: {action_type}")

    def _enqueue(self, input_data: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        external_userid = _recipient_external_userid(input_data)
        if not external_userid:
            raise ContractError("external_user_id is required for enqueue")
        from aicrm_next.integration_gateway.legacy_flask_facade import _legacy_app, legacy_broadcast_enqueue_job

        plan_id = int(input_data.get("planId") or input_data.get("plan_id") or 0)
        trigger_event_id = clean_text(input_data.get("triggerEventId") or input_data.get("trigger_event_id"))
        content = clean_text(action.get("content"))
        with _legacy_app().app_context():
            job_id = legacy_broadcast_enqueue_job(
                source_type="workflow",
                source_table="automation_group_ops_plans",
                source_id=f"{plan_id}:trigger:{trigger_event_id}",
                idempotency_key=f"group_ops:{plan_id}:{trigger_event_id}:{external_userid}:{action['action_type']}",
                business_domain="group_ops",
                channel="wecom_private",
                target_kind="external_userid",
                scheduled_for=None,
                target_external_userids=[external_userid],
                target_summary="1 external contact",
                content_type="private_message",
                content_payload={
                    "channel": "wecom_private",
                    "sender": clean_text(input_data.get("operatorMemberId") or input_data.get("operator_member_id")),
                    "external_userid": [external_userid],
                    "text": {"content": content} if content else {},
                    "action": action,
                },
                content_summary=content[:500],
                created_by=clean_text(input_data.get("operatorAccount") or input_data.get("operator_account") or "group_ops_webhook"),
            )
        return {"ok": True, "status": "queued", "action_ref_id": str(job_id), "side_effect_executed": False}

    def _send_message(self, input_data: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        external_userid = _recipient_external_userid(input_data)
        if not external_userid:
            raise ContractError("external_user_id is required for send_message")
        content = clean_text(action.get("content"))
        if not content:
            raise ContractError("content is required for send_message")
        sender = clean_text(
            input_data.get("operatorMemberId")
            or input_data.get("operator_member_id")
            or input_data.get("operatorAccount")
            or input_data.get("operator_account")
        )
        if not sender:
            raise ContractError("operatorMemberId or operatorAccount is required for send_message")
        try:
            from aicrm_next.integration_gateway.legacy_flask_facade import _legacy_app
            from wecom_ability_service.domains.tasks.service import dispatch_wecom_task
        except Exception as exc:
            raise ContractError("未找到真实消息发送端口") from exc

        request_payload = {
            "chat_type": "single",
            "sender": sender,
            "external_userid": [external_userid],
            "text": {"content": content},
        }
        with _legacy_app().app_context():
            result = dispatch_wecom_task("private_message", "create_private_message_task", request_payload)
        return {
            "ok": True,
            "status": "sent",
            "action_ref_id": str(result.get("task_id") or ""),
            "side_effect_executed": True,
            "wecom_result": result.get("wecom_result") or {},
            "recipient": _recipient_snapshot(input_data),
        }


def build_group_ops_action_port() -> GroupOpsActionPort:
    return DefaultGroupOpsActionPort()
