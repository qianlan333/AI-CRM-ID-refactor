from __future__ import annotations

import base64
import hmac
import ipaddress
import json
import secrets
import time
from hashlib import sha256
from typing import Any
from urllib.parse import urlparse

from aicrm_next.shared.errors import ContractError


RADAR_LINK_OWNER = "radar_links"
RADAR_STATE_TTL_SECONDS = 10 * 60


def _urlsafe_b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _urlsafe_b64decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode((payload + padding).encode("ascii"))


def _state_secret(secret_key: str | None) -> bytes:
    secret = str(secret_key or "").strip() or "radar-links-local-contract-secret"
    return secret.encode("utf-8")


def sign_radar_state(*, code: str, secret_key: str | None, now: int | None = None) -> str:
    issued_at = int(now if now is not None else time.time())
    payload = {
        "code": str(code or "").strip(),
        "nonce": secrets.token_urlsafe(12),
        "exp": issued_at + RADAR_STATE_TTL_SECONDS,
    }
    if not payload["code"]:
        raise ContractError("code is required")
    body = _urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_state_secret(secret_key), body.encode("ascii"), sha256).hexdigest()
    return f"{body}.{signature}"


def verify_radar_state(state: str | None, *, secret_key: str | None, now: int | None = None) -> dict[str, Any]:
    value = str(state or "").strip()
    if "." not in value:
        raise ContractError("invalid radar oauth state")
    body, signature = value.rsplit(".", 1)
    expected = hmac.new(_state_secret(secret_key), body.encode("ascii"), sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ContractError("invalid radar oauth state")
    try:
        payload = json.loads(_urlsafe_b64decode(body).decode("utf-8"))
    except Exception as exc:
        raise ContractError("invalid radar oauth state") from exc
    allowed_keys = {"code", "nonce", "exp"}
    if set(payload) != allowed_keys:
        raise ContractError("invalid radar oauth state")
    code = str(payload.get("code") or "").strip()
    exp = int(payload.get("exp") or 0)
    if not code:
        raise ContractError("invalid radar oauth state")
    if exp < int(now if now is not None else time.time()):
        raise ContractError("radar oauth state expired")
    return payload


def _is_forbidden_host(hostname: str) -> bool:
    host = hostname.strip().lower().rstrip(".")
    if not host:
        return True
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return bool(
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_original_url(original_url: str) -> str:
    value = str(original_url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ContractError("original_url must use http or https")
    if not parsed.hostname or _is_forbidden_host(parsed.hostname):
        raise ContractError("original_url host is not allowed")
    return value


def normalize_radar_link_payload(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    if not partial or "title" in payload:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ContractError("title is required")
        normalized["title"] = title
    if not partial or "original_url" in payload:
        normalized["original_url"] = validate_original_url(str(payload.get("original_url") or ""))
    for key in ("enabled", "auth_required"):
        if not partial or key in payload:
            normalized[key] = bool(payload.get(key))
    for key in ("source_channel", "campaign_id", "staff_id"):
        if not partial or key in payload:
            normalized[key] = str(payload.get(key) or "").strip()
    return normalized


def radar_link_projection(item: dict[str, Any], *, base_url: str = "") -> dict[str, Any]:
    code = str(item.get("code") or "").strip()
    wrapper_path = f"/r/{code}" if code else ""
    wrapper_url = f"{base_url.rstrip('/')}{wrapper_path}" if base_url and wrapper_path else wrapper_path
    return {
        "id": int(item.get("id") or 0),
        "link_id": int(item.get("id") or 0),
        "code": code,
        "title": str(item.get("title") or ""),
        "original_url": str(item.get("original_url") or ""),
        "wrapper_url": wrapper_url,
        "enabled": bool(item.get("enabled", True)),
        "auth_required": bool(item.get("auth_required", False)),
        "source_channel": str(item.get("source_channel") or ""),
        "campaign_id": str(item.get("campaign_id") or ""),
        "staff_id": str(item.get("staff_id") or ""),
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
    }

