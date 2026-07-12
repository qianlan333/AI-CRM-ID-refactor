from __future__ import annotations

from aicrm_next.admin_config import application as admin_application
from aicrm_next.admin_config import application_support as admin_support
from aicrm_next.customer_read_model import application as customer_application
from aicrm_next.customer_read_model import application_customer360_support as customer_application_support
from aicrm_next.customer_read_model import repo as customer_repository
from aicrm_next.customer_read_model import repo_fixture as customer_fixture_repository
from aicrm_next.customer_read_model import repo_live_source as customer_live_repository
from aicrm_next.platform_foundation.external_effects import repo as effect_repository
from aicrm_next.platform_foundation.external_effects import repo_memory as effect_memory_repository
from aicrm_next.platform_foundation.internal_events import repository as event_repository
from aicrm_next.platform_foundation.internal_events import repository_memory as event_memory
from aicrm_next.questionnaire import repo as questionnaire_repository
from aicrm_next.questionnaire import repo_memory as questionnaire_memory


def test_internal_event_repository_facade_preserves_public_imports() -> None:
    assert event_repository.InMemoryInternalEventRepository is event_memory.InMemoryInternalEventRepository
    assert event_repository.SQLAlchemyInternalEventRepository.__module__ == event_repository.__name__
    assert callable(event_repository.build_internal_event_repository)
    assert callable(event_repository.reset_internal_event_fixture_state)


def test_questionnaire_repository_facade_preserves_public_imports_and_patch_seams() -> None:
    assert questionnaire_repository.InMemoryQuestionnaireRepository is questionnaire_memory.InMemoryQuestionnaireRepository
    assert questionnaire_repository.PostgresQuestionnaireReadRepository.__module__ == questionnaire_repository.__name__
    assert callable(questionnaire_repository._jsonb)
    assert callable(questionnaire_repository.build_questionnaire_repository)
    assert callable(questionnaire_repository.reset_questionnaire_fixture_state)


def test_admin_config_application_keeps_services_and_support_seams_on_facade() -> None:
    assert admin_application.AdminConfigReadService.__module__ == admin_application.__name__
    assert admin_application.AdminConfigWriteCommand.__module__ == admin_application.__name__
    assert admin_application._text is admin_support._text
    assert admin_application.AdminConfigRepository is admin_support.AdminConfigRepository


def test_external_effect_repository_facade_preserves_repository_classes() -> None:
    assert effect_repository.InMemoryExternalEffectRepository is effect_memory_repository.InMemoryExternalEffectRepository
    assert effect_repository.SQLAlchemyExternalEffectRepository.__module__ == effect_repository.__name__
    assert callable(effect_repository.build_external_effect_repository)
    assert callable(effect_repository.reset_external_effect_fixture_state)


def test_customer_read_repository_facade_preserves_all_repository_variants() -> None:
    assert customer_repository.FixtureCustomerReadRepository is customer_fixture_repository.FixtureCustomerReadRepository
    assert customer_repository.LiveSourceCustomerReadRepository is customer_live_repository.LiveSourceCustomerReadRepository
    assert customer_repository.SqlAlchemyCustomerReadModelRepository.__module__ == customer_repository.__name__
    assert callable(customer_repository.build_customer_read_model_repository)
    assert callable(customer_repository.build_customer_live_source_repository)


def test_customer_application_facade_preserves_customer_360_helpers() -> None:
    assert customer_application._customer_360_identity is customer_application_support._customer_360_identity
    assert customer_application.GetCustomer360ProfileQuery.__module__ == customer_application.__name__
