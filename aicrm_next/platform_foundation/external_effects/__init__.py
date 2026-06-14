from __future__ import annotations

from .models import (
    AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK,
    AI_ASSIST_CAMPAIGN_MESSAGE_PLAN,
    WEBHOOK_CUSTOMER_AUTOMATION_RETRY,
    WEBHOOK_CUSTOMER_AUTOMATION_RETRY_DUE,
    WEBHOOK_ORDER_PAID_PUSH,
    WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    GROUP_OPS_MESSAGE_LOOPBACK,
    GROUP_OPS_WEBHOOK_ACTION_LOOPBACK,
    WECOM_CONTACT_TAG_MARK,
    WECOM_CONTACT_TAG_UNMARK,
    ExternalEffectDispatchResult,
    ExternalEffectJob,
)
from .repo import InMemoryExternalEffectRepository, reset_external_effect_fixture_state
from .service import ExternalEffectService

__all__ = [
    "ExternalEffectDispatchResult",
    "ExternalEffectJob",
    "ExternalEffectService",
    "InMemoryExternalEffectRepository",
    "AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK",
    "AI_ASSIST_CAMPAIGN_MESSAGE_PLAN",
    "WEBHOOK_CUSTOMER_AUTOMATION_RETRY",
    "WEBHOOK_CUSTOMER_AUTOMATION_RETRY_DUE",
    "WEBHOOK_ORDER_PAID_PUSH",
    "WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH",
    "GROUP_OPS_MESSAGE_LOOPBACK",
    "GROUP_OPS_WEBHOOK_ACTION_LOOPBACK",
    "WECOM_CONTACT_TAG_MARK",
    "WECOM_CONTACT_TAG_UNMARK",
    "reset_external_effect_fixture_state",
]
