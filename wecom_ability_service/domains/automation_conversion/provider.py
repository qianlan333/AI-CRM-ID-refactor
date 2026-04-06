from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from flask import current_app

from ...infra.wecom_runtime import get_contact_runtime_client


@dataclass
class AutomationChannelProvider:
    provider_name: str

    def create_default_channel(self, *, owner_staff_id: str) -> dict[str, Any]:
        raise NotImplementedError


STATE_TOKEN_MAX_LENGTH = 30
STATE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,30}$")


def build_default_channel_state_token(*, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now()).strftime("%y%m%d")
    return f"aqr_{timestamp}_{secrets.token_hex(2)}"


def validate_contact_way_state_token(value: str) -> str:
    state_token = str(value or "").strip()
    if not state_token:
        raise ValueError("state 不能为空")
    if len(state_token) > STATE_TOKEN_MAX_LENGTH:
        raise ValueError(f"state 长度不能超过 {STATE_TOKEN_MAX_LENGTH} 个字符")
    if not STATE_TOKEN_PATTERN.fullmatch(state_token):
        raise ValueError("state 只能包含字母、数字、下划线")
    return state_token


@dataclass
class WeComContactWayProvider(AutomationChannelProvider):
    provider_name: str = "wecom_contact_way"

    def create_default_channel(self, *, owner_staff_id: str) -> dict[str, Any]:
        scene_value = validate_contact_way_state_token(build_default_channel_state_token())
        payload = {
            "type": 1,
            "scene": 2,
            "style": 1,
            "skip_verify": False,
            "state": scene_value,
            "user": [owner_staff_id],
        }
        result = get_contact_runtime_client().create_contact_way(payload)
        return {
            "channel_name": "默认渠道二维码",
            "qr_url": str(result.get("qr_code") or "").strip(),
            # The schema already exposes qr_ticket; persist WeCom config_id in this slot.
            "qr_ticket": str(result.get("config_id") or "").strip(),
            "scene_value": scene_value,
            "status": "active",
            "provider_name": self.provider_name,
            "provider_payload": payload,
        }


def load_channel_provider() -> AutomationChannelProvider | None:
    provider_name = str(current_app.config.get("AUTOMATION_CONVERSION_CHANNEL_PROVIDER", "") or "").strip().lower()
    if provider_name in {"", "wecom_contact_way"}:
        return WeComContactWayProvider()
    return None
