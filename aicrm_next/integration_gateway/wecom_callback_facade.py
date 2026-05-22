from __future__ import annotations

from fastapi import Request
from fastapi.responses import Response

from .legacy_flask_facade import forward_to_legacy_flask


async def handle_wecom_callback_via_legacy(request: Request) -> Response:
    """Next-owned compatibility boundary for WeCom callback fallback routes."""

    return await forward_to_legacy_flask(request)
