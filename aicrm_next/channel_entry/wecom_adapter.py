from __future__ import annotations

import os
import time
from typing import Any

import requests

from .domain import text


class WeComAdapterBlocked(RuntimeError):
    pass


class WeComAPIError(RuntimeError):
    pass


def _bool_env(name: str) -> bool:
    return text(os.getenv(name)).lower() in {"1", "true", "yes", "on"}


def _runtime_env() -> str:
    return text(os.getenv("AICRM_NEXT_ENV") or os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or os.getenv("FLASK_ENV")).lower()


def _wecom_config() -> dict[str, str]:
    return {
        "corp_id": text(os.getenv("WECOM_CORP_ID")),
        "secret": text(os.getenv("WECOM_CONTACT_SECRET") or os.getenv("WECOM_SECRET")),
        "api_base": text(os.getenv("WECOM_API_BASE")) or "https://qyapi.weixin.qq.com",
        "callback_token": text(os.getenv("WECOM_CALLBACK_TOKEN")),
        "callback_aes_key": text(os.getenv("WECOM_CALLBACK_AES_KEY")),
    }


def missing_wecom_config() -> list[str]:
    config = _wecom_config()
    missing = []
    if not config["corp_id"]:
        missing.append("WECOM_CORP_ID")
    if not config["secret"]:
        missing.append("WECOM_CONTACT_SECRET")
    if not config["callback_token"]:
        missing.append("WECOM_CALLBACK_TOKEN")
    if not config["callback_aes_key"]:
        missing.append("WECOM_CALLBACK_AES_KEY")
    return missing


class GuardedWeComAdapter:
    """Adapter boundary for WeCom side effects.

    Real calls are intentionally not enabled here. Tests and staging wiring can
    inject an object with the same methods.
    """

    def send_welcome_msg(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise WeComAdapterBlocked("wecom_welcome_external_call_blocked")

    def mark_external_contact_tags(
        self,
        *,
        external_userid: str,
        follow_user_userid: str,
        add_tags: list[str],
        remove_tags: list[str],
    ) -> dict[str, Any]:
        raise WeComAdapterBlocked("wecom_tag_external_call_blocked")

    def get_external_contact_detail(self, external_userid: str) -> dict[str, Any]:
        raise WeComAdapterBlocked(f"wecom_contact_detail_external_call_blocked:{text(external_userid)}")

    def create_contact_way(self, payload: dict[str, Any]) -> dict[str, Any]:
        reason = describe_wecom_adapter()["real_wecom_adapter_reason"]
        if reason == "missing_config":
            raise WeComAdapterBlocked("missing_wecom_config")
        if reason == "real_calls_disabled":
            raise WeComAdapterBlocked("wecom_real_calls_disabled")
        raise WeComAdapterBlocked("wecom_create_contact_way_external_call_blocked")


class ProductionWeComAdapter:
    def __init__(self, *, http: Any = requests, timeout: float = 8.0) -> None:
        config = _wecom_config()
        self.corp_id = config["corp_id"]
        self.secret = config["secret"]
        self.api_base = config["api_base"].rstrip("/")
        self.timeout = timeout
        self._http = http
        self._access_token = ""
        self._access_token_expires_at = 0.0
        missing = missing_wecom_config()
        if missing:
            raise WeComAdapterBlocked("missing_wecom_config")

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expires_at:
            return self._access_token
        response = self._http.get(
            f"{self.api_base}/cgi-bin/gettoken",
            params={"corpid": self.corp_id, "corpsecret": self.secret},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("errcode") or 0) != 0:
            raise WeComAPIError("wecom_api_error")
        token = text(payload.get("access_token"))
        if not token:
            raise WeComAPIError("wecom_api_error")
        expires_in = int(payload.get("expires_in") or 7200)
        self._access_token = token
        self._access_token_expires_at = now + max(60, expires_in - 300)
        return token

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._http.post(
                f"{self.api_base}{path}",
                params={"access_token": self._get_access_token()},
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except WeComAPIError:
            raise
        except Exception as exc:
            raise WeComAPIError("wecom_api_error") from exc
        return dict(data or {})

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._http.get(
                f"{self.api_base}{path}",
                params={**params, "access_token": self._get_access_token()},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except WeComAPIError:
            raise
        except Exception as exc:
            raise WeComAPIError("wecom_api_error") from exc
        return dict(data or {})

    def send_welcome_msg(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/cgi-bin/externalcontact/send_welcome_msg", payload)

    def mark_external_contact_tags(
        self,
        *,
        external_userid: str,
        follow_user_userid: str,
        add_tags: list[str],
        remove_tags: list[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "userid": text(follow_user_userid),
            "external_userid": text(external_userid),
            "add_tag": [tag for tag in add_tags if text(tag)],
        }
        remove = [tag for tag in remove_tags if text(tag)]
        if remove:
            payload["remove_tag"] = remove
        return self._post("/cgi-bin/externalcontact/mark_tag", payload)

    def create_contact_way(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/cgi-bin/externalcontact/add_contact_way", payload)

    def get_external_contact_detail(self, external_userid: str) -> dict[str, Any]:
        return self._get("/cgi-bin/externalcontact/get", {"external_userid": text(external_userid)})


def normalize_wecom_exception_reason(exc: Exception, *, fallback: str) -> str:
    reason = text(getattr(exc, "reason", "")) or text(str(exc))
    allowed = {
        "wecom_real_calls_disabled",
        "missing_wecom_config",
        "wecom_welcome_external_call_blocked",
        "wecom_tag_external_call_blocked",
        "wecom_api_error",
        "welcome_code_missing",
        "material_resolve_failed",
    }
    if reason in allowed:
        return reason
    if "missing_wecom_config" in reason:
        return "missing_wecom_config"
    if "real_calls_disabled" in reason:
        return "wecom_real_calls_disabled"
    if isinstance(exc, WeComAPIError):
        return "wecom_api_error"
    return fallback


def describe_wecom_adapter() -> dict[str, Any]:
    missing = missing_wecom_config()
    real_enabled = _bool_env("AICRM_NEXT_WECOM_REAL_CALLS_ENABLED")
    if _adapter is not None:
        is_guarded = isinstance(_adapter, GuardedWeComAdapter)
        is_production = isinstance(_adapter, ProductionWeComAdapter)
        reason = "injected_guarded_adapter" if is_guarded else ("production_adapter" if is_production else "injected_adapter")
        return {
            "real_wecom_adapter_enabled": bool(is_production or (not is_guarded and hasattr(_adapter, "send_welcome_msg"))),
            "real_wecom_adapter_reason": reason,
            "missing_config": missing,
            "can_send_welcome": hasattr(_adapter, "send_welcome_msg") and not is_guarded,
            "can_mark_tag": hasattr(_adapter, "mark_external_contact_tags") and not is_guarded,
            "can_create_contact_way": hasattr(_adapter, "create_contact_way") and not is_guarded,
            "runtime_env": _runtime_env(),
            "real_calls_flag_enabled": real_enabled,
        }
    if missing:
        reason = "missing_config"
    elif not real_enabled:
        reason = "real_calls_disabled"
    else:
        reason = "production_adapter"
    enabled = reason == "production_adapter"
    return {
        "real_wecom_adapter_enabled": enabled,
        "real_wecom_adapter_reason": reason,
        "missing_config": missing,
        "can_send_welcome": enabled,
        "can_mark_tag": enabled,
        "can_create_contact_way": enabled,
        "runtime_env": _runtime_env(),
        "real_calls_flag_enabled": real_enabled,
    }


_adapter: Any | None = None
_production_adapter: ProductionWeComAdapter | None = None


def set_wecom_adapter(adapter: Any) -> None:
    global _adapter, _production_adapter
    _adapter = None if isinstance(adapter, GuardedWeComAdapter) else adapter
    if adapter is None or isinstance(adapter, GuardedWeComAdapter):
        _production_adapter = None


def get_wecom_adapter() -> Any:
    global _production_adapter
    if _adapter is not None:
        return _adapter
    diagnosis = describe_wecom_adapter()
    if diagnosis["real_wecom_adapter_enabled"]:
        if _production_adapter is None:
            _production_adapter = ProductionWeComAdapter()
        return _production_adapter
    return GuardedWeComAdapter()
