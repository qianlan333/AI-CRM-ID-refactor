from __future__ import annotations

from aicrm_next.external_effect_composition import build_external_effect_continuation_registry
from aicrm_next.main import create_app


def test_external_effect_continuation_composition_is_explicit_and_deterministic() -> None:
    first = build_external_effect_continuation_registry()
    second = build_external_effect_continuation_registry()

    assert first is not second
    assert first.names == (
        "questionnaire_contact_tags",
        "automation_agent_audience_webhook",
    )
    assert second.names == first.names


def test_web_app_owns_its_external_effect_continuation_registry() -> None:
    first_app = create_app()
    second_app = create_app()

    assert first_app.state.external_effect_continuation_registry.names == (
        "questionnaire_contact_tags",
        "automation_agent_audience_webhook",
    )
    assert first_app.state.external_effect_continuation_registry is not second_app.state.external_effect_continuation_registry
