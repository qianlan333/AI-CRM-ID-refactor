from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from aicrm_next.ai_audience_ops.agent_gateway import generate_agent_reply
from aicrm_next.ai_audience_ops.webhook_service import AudienceInboundWebhookService
from aicrm_next.send_content.application import normalize_send_content_package

from .context_builder import build_agent_context, referenced_context_keys, render_chinese_placeholders
from .repository import AutomationAgentRepository, build_automation_agent_repository, _text


class AutomationAgentWorker:
    def __init__(self, repository: AutomationAgentRepository | None = None) -> None:
        self._repo = repository or build_automation_agent_repository()

    def run_batch(self, batch_id: str) -> dict[str, Any]:
        items = self._repo.list_queued_items(batch_id)
        self._repo.mark_batch_status(batch_id, "running")
        succeeded = 0
        failed = 0
        for item in items:
            result = self.run_item(item)
            if result.get("ok"):
                succeeded += 1
            else:
                failed += 1
        status = "succeeded" if failed == 0 else "partial_failed" if succeeded else "failed"
        self._repo.mark_batch_status(batch_id, status)
        return {"ok": failed == 0, "batch_id": batch_id, "succeeded_count": succeeded, "failed_count": failed, "status": status}

    def run_item(self, item: dict[str, Any]) -> dict[str, Any]:
        item_id = int(item.get("id") or 0)
        self._repo.update_item(item_id, {"status": "running", "started_at": "now"})
        agent = self._repo.get_agent_by_code(_text(item.get("agent_code")))
        if not agent:
            return self._fail(item_id, "agent_not_found", "agent not found")
        if _text(agent.get("status")) != "active":
            return self._fail(item_id, "agent_not_active", "agent is not active")
        external_userid = _text(item.get("external_userid"))
        role_prompt = _text(agent.get("published_role_prompt"))
        task_prompt = _text(agent.get("published_task_prompt"))
        keys = referenced_context_keys(role_prompt, task_prompt)
        try:
            context = build_agent_context(external_userid, keys)
        except Exception as exc:
            return self._fail(item_id, "context_build_failed", str(exc))
        owner_userid = _text(context.get("owner_userid"))
        if not owner_userid:
            self._repo.update_item(item_id, {"context_snapshot_json": context})
            return self._fail(item_id, "failed_owner_missing", "owner_userid is required")
        rendered_role = render_chinese_placeholders(role_prompt, context.get("blocks") or {})
        rendered_task = render_chinese_placeholders(task_prompt, context.get("blocks") or {})
        gateway = generate_agent_reply(
            agent_code=_text(agent.get("agent_code")),
            role_prompt=rendered_role,
            task_prompt=rendered_task,
            variables={"external_userid": external_userid, "context_keys": sorted(keys)},
        )
        if not gateway.ok:
            return self._fail(
                item_id,
                gateway.error_code or "agent_generation_failed",
                gateway.error_message,
                context=context,
                owner_userid=owner_userid,
                prompt_preview=f"{rendered_role}\n\n{rendered_task}"[:1000],
            )
        fixed_package = agent.get("fixed_content_package_json") if isinstance(agent.get("fixed_content_package_json"), dict) else {}
        content_package = normalize_send_content_package(
            {**fixed_package, "content_text": gateway.final_text},
            text_enabled=True,
            require_body=True,
        )
        callback_payload = {
            "external_event_id": _text(item.get("external_event_id")),
            "status": "generated",
            "message": {"text": gateway.final_text, "content_package": content_package},
            "action": {
                "type": "enqueue_automation_send_plan",
                "target_external_userid": external_userid,
                "sender_userid": owner_userid,
            },
        }
        package = self._repo.get_package_by_key(_text(agent.get("bound_package_key"))) or {}
        secret = _text(package.get("inbound_webhook_secret"))
        raw = json.dumps(callback_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest() if secret else ""
        callback = AudienceInboundWebhookService().handle(
            _text(agent.get("bound_package_key")),
            callback_payload,
            raw_body=raw,
            signature=signature,
        )
        ok = bool(callback.get("ok"))
        self._repo.update_item(
            item_id,
            {
                "owner_userid": owner_userid,
                "status": "callback_succeeded" if ok else "callback_failed",
                "context_snapshot_json": context,
                "prompt_preview": f"{rendered_role}\n\n{rendered_task}"[:2000],
                "raw_agent_output": gateway.final_text,
                "content_package_json": content_package,
                "callback_payload_json": callback_payload,
                "callback_status": "succeeded" if ok else "failed",
                "callback_response_json": callback,
                "error_code": "" if ok else _text(callback.get("error")),
                "error_message": "" if ok else _text(callback.get("detail") or callback.get("error")),
                "finished_at": "now",
            },
        )
        return {"ok": ok, "item_id": item_id, "callback": callback}

    def _fail(
        self,
        item_id: int,
        error_code: str,
        error_message: str,
        *,
        context: dict[str, Any] | None = None,
        owner_userid: str = "",
        prompt_preview: str = "",
    ) -> dict[str, Any]:
        self._repo.update_item(
            item_id,
            {
                "owner_userid": owner_userid,
                "status": "failed",
                "context_snapshot_json": context or {},
                "prompt_preview": prompt_preview,
                "error_code": error_code,
                "error_message": error_message,
                "finished_at": "now",
            },
        )
        return {"ok": False, "error": error_code, "detail": error_message, "item_id": item_id}

