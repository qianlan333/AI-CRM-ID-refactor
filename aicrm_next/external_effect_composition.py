from __future__ import annotations

from .automation_agents.external_effect_continuation import AUTOMATION_AGENT_AUDIENCE_WEBHOOK_CONTINUATION
from .platform_foundation.external_effects.continuations import ExternalEffectContinuationRegistry
from .questionnaire.external_effect_continuation import QUESTIONNAIRE_CONTACT_TAGS_CONTINUATION


def build_external_effect_continuation_registry() -> ExternalEffectContinuationRegistry:
    return ExternalEffectContinuationRegistry(
        (
            QUESTIONNAIRE_CONTACT_TAGS_CONTINUATION,
            AUTOMATION_AGENT_AUDIENCE_WEBHOOK_CONTINUATION,
        )
    )
