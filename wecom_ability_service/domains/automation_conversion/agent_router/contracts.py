from __future__ import annotations

from typing import TypedDict


ROUTER_ALLOWED_AGENT_CODES = {
    "welcome_agent",
    "pricing_agent",
    "proof_agent",
    "closing_agent",
}


class RouterMessage(TypedDict):
    role: str
    content: str
    timestamp: str


class RouterRequestPayload(TypedDict):
    external_userid: str
    messages: list[RouterMessage]


class RouterDecision(TypedDict):
    external_userid: str
    agent_code: str
