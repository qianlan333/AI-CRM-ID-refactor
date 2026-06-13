from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from typing import Any, Protocol

import requests

from .models import (
    WEBHOOK_ORDER_PAID_PUSH,
    WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    ExternalEffectDispatchResult,
    ExternalEffectJob,
)
from .retry_policy import http_error_code

LOW_RISK_WEBHOOK_EFFECT_TYPES = frozenset({WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH, WEBHOOK_ORDER_PAID_PUSH})


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


class ExternalEffectAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ExternalEffectAdapter] = {
            "outbound_webhook": WebhookAdapter(),
            "webhook": WebhookAdapter(),
        }
        self._disabled = DisabledAdapter()

    def get(self, adapter_name: str) -> ExternalEffectAdapter:
        return self._adapters.get(str(adapter_name or "").strip(), self._disabled)


DEFAULT_ADAPTER_REGISTRY = ExternalEffectAdapterRegistry()
