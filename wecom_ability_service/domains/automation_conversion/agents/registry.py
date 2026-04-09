from __future__ import annotations

from typing import Any


AGENT_PROMPT_DEFINITIONS = (
    {
        "agent_code": "central_router_agent",
        "display_name": "中央路由 Agent",
        "prompt_text": (
            "你是 CRM 自动化转化中央路由 Agent。"
            "请先理解客户最新上下文，再判断应由哪个执行 Agent 接手，并输出清晰的路由决策。"
        ),
    },
    {
        "agent_code": "welcome_agent",
        "display_name": "欢迎接待 Agent",
        "prompt_text": (
            "你是 CRM 自动化转化欢迎接待 Agent。"
            "目标是在首次接触时快速建立关系、确认客户当前诉求，并生成自然的跟进建议。"
        ),
    },
    {
        "agent_code": "pricing_agent",
        "display_name": "价格答疑 Agent",
        "prompt_text": (
            "你是 CRM 自动化转化价格答疑 Agent。"
            "请围绕价格、套餐、支付方式、价值说明生成清晰且克制的回复建议。"
        ),
    },
    {
        "agent_code": "proof_agent",
        "display_name": "案例证明 Agent",
        "prompt_text": (
            "你是 CRM 自动化转化案例证明 Agent。"
            "请基于客户当前疑虑，生成更适合用于建立信任的案例、证据和证明性表达。"
        ),
    },
    {
        "agent_code": "closing_agent",
        "display_name": "成交推进 Agent",
        "prompt_text": (
            "你是 CRM 自动化转化成交推进 Agent。"
            "请在不夸张承诺的前提下，帮助推进下一步行动、预约、付款或明确成交条件。"
        ),
    },
)

AGENT_PROMPT_DEFINITION_MAP = {str(item["agent_code"]): dict(item) for item in AGENT_PROMPT_DEFINITIONS}
AGENT_PROMPT_ORDER = [str(item["agent_code"]) for item in AGENT_PROMPT_DEFINITIONS]


def default_agent_prompt_payloads() -> list[dict[str, Any]]:
    return [
        {
            "agent_code": str(item["agent_code"]),
            "display_name": str(item["display_name"]),
            "prompt_text": str(item["prompt_text"]),
            "enabled": True,
            "version": 1,
        }
        for item in AGENT_PROMPT_DEFINITIONS
    ]
