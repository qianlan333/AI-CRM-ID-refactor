from __future__ import annotations

import secrets
from datetime import datetime
from dataclasses import dataclass
from typing import Any

from flask import current_app

from ...infra.wecom_runtime import get_contact_runtime_client


@dataclass
class AutomationChannelProvider:
    provider_name: str

    def create_default_channel(self, *, owner_staff_id: str) -> dict[str, Any]:
        raise NotImplementedError


@dataclass
class WeComContactWayProvider(AutomationChannelProvider):
    provider_name: str = "wecom_contact_way"

    def create_default_channel(self, *, owner_staff_id: str) -> dict[str, Any]:
        scene_value = f"automation_default_qrcode_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}"
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
