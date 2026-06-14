from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from typing import Any, Protocol

import requests

from .models import (
    AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK,
    GROUP_OPS_MESSAGE_LOOPBACK,
    GROUP_OPS_WEBHOOK_ACTION_LOOPBACK,
    WEBHOOK_ORDER_PAID_PUSH,
    WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    WECOM_MESSAGE_PRIVATE_SEND,
    ExternalEffectDispatchResult,
    ExternalEffectJob,
)
from .retry_policy import http_error_code

LOW_RISK_WEBHOOK_EFFECT_TYPES = frozenset(
    {
        WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        WEBHOOK_ORDER_PAID_PUSH,
        AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK,
        GROUP_OPS_MESSAGE_LOOPBACK,
        GROUP_OPS_WEBHOOK_ACTION_LOOPBACK,
    }
)


class ExternalEffectAdapter(Protocol):
    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        ...


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str) -> set[str]:
    raw = str(os.getenv(name, "") or "").strip()
    return {item.strip() for item in re.split(r"[,\s]+", raw) if item.strip()}


def webhook_execution_settings() -> dict[str, Any]:
    return {
        "enabled": _enabled("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE"),
        "allowed_types": sorted(_csv_env("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")),
        "supported_types": sorted(LOW_RISK_WEBHOOK_EFFECT_TYPES),
    }


class DisabledAdapter:
    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        return ExternalEffectDispatchResult(
            status="blocked",
            adapter_mode=job.execution_mode or "disabled",
            request_summary={"effect_type": job.effect_type, "target_type": job.target_type, "target_id": job.target_id},
            response_summary={"blocked": True, "real_external_call_executed": False},
            error_code="adapter_blocked",
            error_message="External effect adapter execution is disabled in MVP.",
            real_external_call_executed=False,
        )


class WebhookAdapter:
    def __init__(self, http_post=None) -> None:
        self._http_post = http_post or requests.post

    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        gate_error = self._execution_gate_error(job)
        if gate_error:
            return ExternalEffectDispatchResult(
                status="blocked",
                adapter_mode=job.execution_mode or "shadow",
                request_summary={
                    "effect_type": job.effect_type,
                    "operation": job.operation,
                    "target_type": job.target_type,
                    "target_id": job.target_id,
                },
                response_summary={"blocked": True, "execution_gate": gate_error, "real_external_call_executed": False},
                error_code=gate_error,
                error_message="Webhook adapter execution is blocked by external effect execution gates.",
                real_external_call_executed=False,
            )

        payload = dict(job.payload_json or {})
        url = str(payload.get("webhook_url") or payload.get("target_url") or "").strip()
        body = self._request_body(payload)
        if not url:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode="execute",
                request_summary={"target_url_present": False, "effect_type": job.effect_type},
                response_summary={"real_external_call_executed": False},
                error_code="config_missing",
                error_message="webhook_url is required",
                real_external_call_executed=False,
            )
        if body is None:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode="execute",
                request_summary={"target_url_present": True, "effect_type": job.effect_type},
                response_summary={"real_external_call_executed": False},
                error_code="payload_invalid",
                error_message="webhook payload body must be a JSON object or array",
                real_external_call_executed=False,
            )
        timeout = float(os.getenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_TIMEOUT_SECONDS") or "5")
        headers, signature_configured = self._headers(payload=payload, body=body)
        request_summary = {
            "effect_type": job.effect_type,
            "operation": job.operation,
            "target_url_present": True,
            "timeout_seconds": timeout,
            "body_type": type(body).__name__,
            "signature_configured": signature_configured,
        }
        try:
            response = self._http_post(url, json=body, headers=headers, timeout=timeout)
        except requests.Timeout:
            return ExternalEffectDispatchResult(
                status="failed_retryable",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={"real_external_call_executed": True},
                error_code="timeout",
                error_message="webhook request timed out",
                real_external_call_executed=True,
            )
        except requests.RequestException as exc:
            return ExternalEffectDispatchResult(
                status="failed_retryable",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={"real_external_call_executed": True},
                error_code="network_error",
                error_message=str(exc),
                real_external_call_executed=True,
            )

        status_code = int(response.status_code)
        if 200 <= status_code < 300:
            status = "succeeded"
        elif status_code in {408, 429} or status_code >= 500:
            status = "failed_retryable"
        else:
            status = "failed_terminal"
        return ExternalEffectDispatchResult(
            status=status,
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary={"status_code": status_code, "real_external_call_executed": True},
            error_code="" if status == "succeeded" else http_error_code(status_code),
            error_message="" if status == "succeeded" else response.text[:500],
            real_external_call_executed=True,
        )

    def _execution_gate_error(self, job: ExternalEffectJob) -> str:
        if job.execution_mode in {"disabled", "shadow", "plan_only", "execute_dryrun"}:
            return "shadow_only"
        if not _enabled("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE"):
            return "execution_disabled"
        if job.effect_type not in LOW_RISK_WEBHOOK_EFFECT_TYPES:
            return "unsupported_effect_type"
        allowed = _csv_env("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")
        if job.effect_type not in allowed:
            return "effect_type_not_allowed"
        return ""

    def _request_body(self, payload: dict[str, Any]) -> dict[str, Any] | list[Any] | None:
        if "body" in payload:
            body = payload.get("body")
        elif "payload" in payload:
            body = payload.get("payload")
        else:
            body = {
                key: value
                for key, value in payload.items()
                if key not in {"webhook_url", "target_url", "signature_secret", "signing_secret"}
            }
        return body if isinstance(body, (dict, list)) else None

    def _headers(self, *, payload: dict[str, Any], body: dict[str, Any] | list[Any]) -> tuple[dict[str, str], bool]:
        headers = {"Content-Type": "application/json"}
        secret = str(
            payload.get("signature_secret")
            or payload.get("signing_secret")
            or os.getenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_SIGNING_SECRET")
            or ""
        ).strip()
        if not secret:
            return headers, False
        canonical_body = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(secret.encode("utf-8"), canonical_body.encode("utf-8"), hashlib.sha256).hexdigest()
        headers["X-AICRM-External-Effect-Signature"] = signature
        headers["X-AICRM-External-Effect-Signature-Alg"] = "hmac-sha256"
        return headers, True


class WeComPrivateMessageAdapter:
    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        payload = dict(job.payload_json or {})
        external_userids = [str(item or "").strip() for item in list(payload.get("external_userids") or []) if str(item or "").strip()]
        owner_userid = str(payload.get("owner_userid") or payload.get("sender") or "").strip()
        content_text = str(payload.get("content_text") or "").strip()
        gate_error = self._execution_gate_error(job=job, payload=payload, external_userids=external_userids, owner_userid=owner_userid)
        request_summary = {
            "effect_type": job.effect_type,
            "operation": job.operation,
            "target_type": job.target_type,
            "target_id": job.target_id,
            "owner_userid": owner_userid,
            "external_userid_count": len(external_userids),
            "content_text_length": len(content_text),
            "attachment_count": len(payload.get("attachments") or []) if isinstance(payload.get("attachments"), list) else 0,
        }
        if gate_error:
            return ExternalEffectDispatchResult(
                status="blocked",
                adapter_mode=job.execution_mode or "execute",
                request_summary=request_summary,
                response_summary={"blocked": True, "execution_gate": gate_error, "real_external_call_executed": False, "wecom_send_executed": False},
                error_code=gate_error,
                error_message="WeCom private-message adapter execution is blocked by external effect execution gates.",
                real_external_call_executed=False,
            )
        adapter_payload: dict[str, Any] = {
            "sender": owner_userid,
            "external_userids": external_userids,
        }
        if content_text:
            adapter_payload["text"] = {"content": content_text}
        attachments = payload.get("attachments")
        if isinstance(attachments, list) and attachments:
            adapter_payload["attachments"] = attachments
        try:
            from aicrm_next.integration_gateway.wecom_private_adapter import build_wecom_private_message_adapter

            result = build_wecom_private_message_adapter().create_private_message_task(
                adapter_payload,
                idempotency_key=job.idempotency_key or str(job.id),
            )
        except Exception as exc:
            return ExternalEffectDispatchResult(
                status="failed_retryable",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={"real_external_call_executed": True, "wecom_send_executed": False},
                error_code="adapter_exception",
                error_message=str(exc),
                real_external_call_executed=True,
            )
        side_effect_executed = bool(result.get("side_effect_executed"))
        ok = bool(result.get("ok"))
        error_code = str(result.get("error_code") or "").strip()
        response_summary = {
            "real_external_call_executed": side_effect_executed,
            "wecom_send_executed": side_effect_executed,
            "adapter_mode": str(result.get("mode") or ""),
            "exact_target_verified": bool(result.get("exact_target_verified")),
            "requested_external_userid_count": len(result.get("requested_external_userids") or external_userids),
            "wecom_msgid_present": bool(str(result.get("wecom_msgid") or "").strip()),
        }
        if ok:
            return ExternalEffectDispatchResult(
                status="succeeded",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary=response_summary,
                real_external_call_executed=side_effect_executed,
            )
        if not side_effect_executed:
            return ExternalEffectDispatchResult(
                status="blocked",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary=response_summary,
                error_code=error_code or "adapter_blocked",
                error_message=str(result.get("error_message") or "WeCom private-message adapter blocked before external call."),
                real_external_call_executed=False,
            )
        retryable = error_code in {"external_call_unknown", "adapter_exception", "network_error", "timeout", "rate_limited"}
        return ExternalEffectDispatchResult(
            status="failed_retryable" if retryable else "failed_terminal",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary=response_summary,
            error_code=error_code or "wecom_private_send_failed",
            error_message=str(result.get("error_message") or "WeCom private-message send failed."),
            real_external_call_executed=True,
        )

    def _execution_gate_error(
        self,
        *,
        job: ExternalEffectJob,
        payload: dict[str, Any],
        external_userids: list[str],
        owner_userid: str,
    ) -> str:
        if job.execution_mode in {"disabled", "shadow", "plan_only", "execute_dryrun"}:
            return "shadow_only"
        if job.effect_type != WECOM_MESSAGE_PRIVATE_SEND:
            return "unsupported_effect_type"
        if not _enabled("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE"):
            return "wecom_execution_disabled"
        allowed_types = _csv_env("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")
        if job.effect_type not in allowed_types:
            return "effect_type_not_allowed"
        if len(external_userids) != 1:
            return "single_target_required"
        target_id = str(job.target_id or "").strip()
        if target_id != external_userids[0]:
            return "target_mismatch"
        allowed_targets = _csv_env("AICRM_EXTERNAL_EFFECT_ALLOWED_TARGET_EXTERNAL_USERIDS")
        if external_userids[0] not in allowed_targets:
            return "target_not_allowed"
        allowed_owners = _csv_env("AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS")
        if owner_userid not in allowed_owners:
            return "owner_not_allowed"
        if str(payload.get("channel") or "").strip() != "wecom_private":
            return "channel_not_allowed"
        has_text = bool(str(payload.get("content_text") or "").strip())
        has_attachments = isinstance(payload.get("attachments"), list) and bool(payload.get("attachments"))
        if not has_text and not has_attachments:
            return "payload_invalid"
        return ""


class ExternalEffectAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ExternalEffectAdapter] = {
            "outbound_webhook": WebhookAdapter(),
            "webhook": WebhookAdapter(),
            "wecom_private_message": WeComPrivateMessageAdapter(),
        }
        self._disabled = DisabledAdapter()

    def get(self, adapter_name: str) -> ExternalEffectAdapter:
        return self._adapters.get(str(adapter_name or "").strip(), self._disabled)


DEFAULT_ADAPTER_REGISTRY = ExternalEffectAdapterRegistry()
