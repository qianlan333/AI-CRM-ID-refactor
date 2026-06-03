from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

from aicrm_next.platform_foundation.audit_ledger import InMemoryAuditLedger
from aicrm_next.shared.runtime import production_environment


DEFAULT_JS_API_LIST = ("getContext", "getCurExternalContact", "sendChatMessage")
_audit_ledger = InMemoryAuditLedger()


@dataclass(frozen=True)
class ExternalCallAttempt:
    adapter_name: str
    adapter_mode: str
    operation: str
    target_url: str
    status: str
    real_external_call_executed: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SidebarJSSDKInputError(ValueError):
    pass


def reset_sidebar_jssdk_attempts() -> None:
    global _audit_ledger
    _audit_ledger = InMemoryAuditLedger()


def list_sidebar_jssdk_attempts() -> list[dict[str, Any]]:
    return [event.to_dict() for event in _audit_ledger.list_events()]


def sidebar_jssdk_adapter_mode() -> str:
    explicit = str(os.getenv("AICRM_SIDEBAR_JSSDK_ADAPTER_MODE") or "").strip().lower()
    if explicit in {"fake", "sandbox", "real_blocked"}:
        return explicit
    if explicit == "real_enabled" and _env_flag("AICRM_SIDEBAR_JSSDK_REAL_ENABLED"):
        return "real_enabled"
    if production_environment():
        return "real_blocked"
    return "fake"


def build_sidebar_jssdk_config(
    *,
    url: str,
    js_api_list: list[str] | tuple[str, ...] | None = None,
    debug: bool = False,
    corp_context: dict[str, str] | None = None,
    adapter_mode: str | None = None,
) -> dict[str, Any]:
    mode = adapter_mode or sidebar_jssdk_adapter_mode()
    normalized_url = normalize_jssdk_url(url)
    context = dict(corp_context or {})
    corp_id = str(context.get("corp_id") or os.getenv("WECOM_CORP_ID") or "ww-next-sidebar-fixture").strip()
    agent_id = str(context.get("agent_id") or os.getenv("WECOM_AGENT_ID") or "1000002").strip()
    apis = [str(item).strip() for item in (js_api_list or DEFAULT_JS_API_LIST) if str(item).strip()]
    timestamp = "1700000000"
    nonce = "next-sidebar-jssdk-nonce"
    config_signature = _fake_signature("config", mode, corp_id, agent_id, normalized_url, timestamp, nonce)
    agent_signature = _fake_signature("agent", mode, corp_id, agent_id, normalized_url, timestamp, nonce)
    blocked = mode in {"real_blocked", "real_enabled"}
    attempt = ExternalCallAttempt(
        adapter_name="wecom_jssdk",
        adapter_mode=mode,
        operation="build_jssdk_config",
        target_url=normalized_url,
        status="blocked" if blocked else "planned",
        reason="real_wecom_signing_blocked_by_default" if blocked else "fake_contract_generated",
    )
    _record_attempt(attempt)
    config = {
        "url": normalized_url,
        "debug": bool(debug),
        "timestamp": timestamp,
        "nonceStr": nonce,
        "signature": config_signature,
        "jsApiList": apis,
    }
    agent_config = {
        "url": normalized_url,
        "timestamp": timestamp,
        "nonceStr": nonce,
        "signature": agent_signature,
        "jsApiList": apis,
    }
    return {
        "ok": True,
        "appId": corp_id,
        "corpId": corp_id,
        "corp_id": corp_id,
        "agentId": agent_id,
        "agent_id": agent_id,
        "timestamp": timestamp,
        "nonceStr": nonce,
        "signature": config_signature,
        "jsApiList": apis,
        "config": config,
        "agent_config": agent_config,
        "source_status": "next_jssdk_adapter",
        "adapter_mode": mode,
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "real_external_call_executed": False,
        "external_call_blocked": blocked,
        "external_call_attempt": attempt.to_dict(),
    }


def normalize_jssdk_url(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    if not value:
        raise SidebarJSSDKInputError("url is required")
    if value.startswith("/"):
        value = f"http://localhost{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SidebarJSSDKInputError("url must be an absolute http(s) URL or a relative path starting with /")
    return parsed._replace(fragment="").geturl()


def _fake_signature(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _record_attempt(attempt: ExternalCallAttempt) -> None:
    _audit_ledger.record_event(
        event_type=f"sidebar.jssdk.{attempt.status}",
        actor_id="sidebar_jssdk_adapter",
        actor_type="system",
        target_type="url",
        target_id=attempt.target_url,
        source_route="/api/sidebar/jssdk-config",
        payload={
            "adapter_mode": attempt.adapter_mode,
            "operation": attempt.operation,
            "status": attempt.status,
            "reason": attempt.reason,
            "real_external_call_executed": False,
        },
    )


def _env_flag(name: str) -> bool:
    value = str(os.getenv(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}
