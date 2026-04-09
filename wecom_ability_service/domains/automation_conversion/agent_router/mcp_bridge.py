from __future__ import annotations

from typing import Any

from .contracts import RouterMessage
from .lobster_router_client import build_router_request_payload, post_router_request
from .parser import parse_router_response_payload


def route_recent_messages(
    *,
    external_userid: str,
    messages: list[RouterMessage],
) -> dict[str, Any]:
    request_payload = build_router_request_payload(
        external_userid=external_userid,
        messages=messages,
    )
    response = post_router_request(request_payload)
    decision = parse_router_response_payload(
        response.get("response_payload"),
        expected_external_userid=external_userid,
    )
    return {
        "request_payload": request_payload,
        "response_payload": response.get("response_payload") or {},
        "decision": decision,
        "status_code": int(response.get("status_code") or 0),
        "headers": dict(response.get("headers") or {}),
    }
