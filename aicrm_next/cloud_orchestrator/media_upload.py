from __future__ import annotations

import base64
import hashlib
import os
import uuid
from dataclasses import dataclass
from typing import Any

from aicrm_next.integration_gateway.media_adapters import WeComMediaAdapter
from aicrm_next.shared import runtime

SOURCE_STATUS = "next_cloud_orchestrator_media_upload"
ROUTE_OWNER = "ai_crm_next"
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def _text(value: Any) -> str:
    return str(value or "").strip()


def _adapter_mode() -> str:
    configured = _text(os.getenv("AICRM_NEXT_CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_MODE")).lower()
    if configured in {"fake", "local", "real_blocked"}:
        return configured
    if runtime.production_environment():
        return "real_blocked"
    return "real_blocked"


def _fake_media_id(*, file_name: str, file_bytes: bytes, idempotency_key: str) -> str:
    digest = hashlib.sha256()
    digest.update(file_name.encode("utf-8"))
    digest.update(b":")
    digest.update(file_bytes)
    digest.update(b":")
    digest.update(idempotency_key.encode("utf-8"))
    return "fake_media_" + digest.hexdigest()[:24]


def _payload_summary(*, file_name: str, content_type: str, size: int) -> dict[str, Any]:
    return {
        "file_name": file_name,
        "content_type": content_type,
        "size": size,
        "payload_bytes_redacted": True,
    }


def _side_effect_plan(
    *,
    idempotency_key: str,
    file_name: str,
    content_type: str,
    size: int,
    adapter_mode: str,
) -> dict[str, Any]:
    return {
        "effect_type": "wecom.media.upload",
        "adapter_name": "wecom_media",
        "adapter_mode": adapter_mode,
        "requires_approval": True,
        "real_external_call_executed": False,
        "wecom_media_upload_executed": False,
        "idempotency_key": idempotency_key,
        "payload_summary": _payload_summary(file_name=file_name, content_type=content_type, size=size),
    }


@dataclass(frozen=True)
class UploadCloudOrchestratorMediaCommand:
    command_id: str
    idempotency_key: str
    actor_id: str
    actor_type: str
    source_route: str = "/api/admin/cloud-orchestrator/media/upload"
    trace_id: str = ""
    dry_run: bool = True

    def __call__(self, *, file_name: str, file_bytes: bytes, content_type: str) -> dict[str, Any]:
        normalized_name = _text(file_name) or "cloud-orchestrator-image.png"
        normalized_type = _text(content_type).lower()
        size = len(file_bytes or b"")
        if not size:
            raise ValueError("empty_image")
        if size > MAX_IMAGE_BYTES:
            raise ValueError("image_too_large")
        if not normalized_type.startswith("image/"):
            raise ValueError("invalid_content_type")

        adapter_mode = _adapter_mode()
        media_id = _fake_media_id(
            file_name=normalized_name,
            file_bytes=file_bytes,
            idempotency_key=self.idempotency_key or self.command_id,
        )
        adapter_result: dict[str, Any] = {
            "ok": True,
            "adapter": "WeComMediaAdapter",
            "mode": adapter_mode,
            "operation": "upload_image",
            "idempotency_key": self.idempotency_key,
            "media_id": media_id,
            "reference_url": f"fake://cloud-orchestrator/wecom-media/{media_id}",
            "side_effect_executed": False,
            "error_code": "",
            "error_message": "",
        }
        if adapter_mode in {"fake", "local"}:
            adapter_result = WeComMediaAdapter("fake").upload_image(
                data_base64=base64.b64encode(file_bytes).decode("ascii"),
                file_name=normalized_name,
                idempotency_key=self.idempotency_key or self.command_id,
            )
            media_id = _text(adapter_result.get("media_id")) or media_id

        side_effect_plan = _side_effect_plan(
            idempotency_key=self.idempotency_key,
            file_name=normalized_name,
            content_type=normalized_type,
            size=size,
            adapter_mode=adapter_mode,
        )
        return {
            "ok": True,
            "media_id": media_id,
            "file_name": normalized_name,
            "content_type": normalized_type,
            "size": size,
            "command_id": self.command_id,
            "source_status": SOURCE_STATUS,
            "route_owner": ROUTE_OWNER,
            "fallback_used": False,
            "adapter_mode": adapter_mode,
            "real_external_call_executed": False,
            "wecom_media_upload_executed": False,
            "side_effect_plan": side_effect_plan,
            "adapter_result": adapter_result,
            "actor": {"id": self.actor_id, "type": self.actor_type},
            "source_route": self.source_route,
            "trace_id": self.trace_id,
            "dry_run": self.dry_run,
        }


def build_upload_command(
    *,
    idempotency_key: str = "",
    actor_id: str = "",
    actor_type: str = "admin",
    trace_id: str = "",
) -> UploadCloudOrchestratorMediaCommand:
    command_id = "cmd_cloud_media_" + uuid.uuid4().hex
    key = _text(idempotency_key) or command_id
    return UploadCloudOrchestratorMediaCommand(
        command_id=command_id,
        idempotency_key=key,
        actor_id=_text(actor_id) or "admin_ui",
        actor_type=_text(actor_type) or "admin",
        trace_id=_text(trace_id),
    )


def diagnostics_payload() -> dict[str, Any]:
    adapter_mode = _adapter_mode()
    return {
        "ok": True,
        "source_status": SOURCE_STATUS,
        "route_owner": ROUTE_OWNER,
        "fallback_used": False,
        "adapter_mode": adapter_mode,
        "real_external_call_executed": False,
        "wecom_media_upload_executed": False,
        "side_effect_plan": {
            "effect_type": "wecom.media.upload",
            "adapter_name": "wecom_media",
            "adapter_mode": adapter_mode,
            "requires_approval": True,
            "real_external_call_executed": False,
            "wecom_media_upload_executed": False,
            "payload_summary": {},
        },
    }
