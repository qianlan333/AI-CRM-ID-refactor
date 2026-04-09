from __future__ import annotations

from typing import Any

from .contracts import ROUTER_ALLOWED_AGENT_CODES
from .exceptions import LobsterRouterParseError


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def parse_router_response_payload(
    response_payload: Any,
    *,
    expected_external_userid: str = "",
) -> dict[str, str]:
    normalized_expected_external_userid = _normalized_text(expected_external_userid)
    candidate: dict[str, Any] | None = None
    if isinstance(response_payload, list):
        if response_payload:
            first_item = response_payload[0]
            if isinstance(first_item, dict):
                candidate = dict(first_item)
    elif isinstance(response_payload, dict):
        if isinstance(response_payload.get("data"), list) and response_payload["data"]:
            first_item = response_payload["data"][0]
            if isinstance(first_item, dict):
                candidate = dict(first_item)
        elif isinstance(response_payload.get("results"), list) and response_payload["results"]:
            first_item = response_payload["results"][0]
            if isinstance(first_item, dict):
                candidate = dict(first_item)
        else:
            candidate = dict(response_payload)
    if not candidate:
        raise LobsterRouterParseError("router_response_empty")

    external_userid = _normalized_text(candidate.get("external_userid"))
    agent_code = _normalized_text(candidate.get("agent_code"))
    if normalized_expected_external_userid and external_userid != normalized_expected_external_userid:
        raise LobsterRouterParseError("router_external_userid_mismatch")
    if not external_userid:
        raise LobsterRouterParseError("router_external_userid_missing")
    if agent_code not in ROUTER_ALLOWED_AGENT_CODES:
        raise LobsterRouterParseError("router_agent_code_invalid")
    return {
        "external_userid": external_userid,
        "agent_code": agent_code,
    }
