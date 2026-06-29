from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.customer_tags.live_mutation import execute_wecom_tag_mutation, reset_wecom_tag_live_mutation_fixture_state
from aicrm_next.customer_tags.mutation_commands import PlanCustomerTagAssignmentCommand
from aicrm_next.identity_contact.dto import IdentityResolution
from aicrm_next.main import create_app
from aicrm_next.questionnaire import h5_write


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SECRET_KEY", "wecom-live-mutation-callers")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_sidebar_signup_tag_mutation_remains_plan_only(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post(
        "/api/sidebar/signup-tags/mark",
        json={"external_userid": "wx_ext_001", "tag_id": "tag_fixture_active", "marked": True},
        headers={"Idempotency-Key": "sidebar-tag-plan-only"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_status"] == "next_command"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["side_effect_plan"]["effect_type"] == "wecom.tag.update"
    assert payload["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert payload["side_effect_plan"]["real_external_call_executed"] is False


def test_questionnaire_submit_tag_side_effect_uses_next_plan(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={
            "answers": {"q_activation": "activated", "q_interest": ["ai_tools"]},
            "identity": {"external_userid": "wx_ext_001", "openid": "openid_001", "unionid": "unionid_001"},
        },
        headers={"Idempotency-Key": "questionnaire-tag-plan-only"},
    )

    assert response.status_code == 200
    tag_plan = response.json()["side_effects"]["wecom_tag"]
    assert tag_plan["source_status"] == "next_command"
    assert tag_plan["effect_type"] == "questionnaire.tag.apply"
    assert tag_plan["fallback_used"] is False
    assert tag_plan["real_external_call_executed"] is False
    assert tag_plan["wecom_api_called"] is False
    assert tag_plan["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert tag_plan["side_effect_plan"]["requires_approval"] is True


def test_questionnaire_submit_binds_payload_mobile_when_resolved_identity_has_no_mobile(monkeypatch) -> None:
    mobile_bind_calls: list[dict] = []

    class FakeResolvePersonIdentityQuery:
        def __call__(self, request):
            return IdentityResolution(
                person_id="person-questionnaire-mobile",
                external_userid=request.external_userid,
                mobile="",
                binding_status="bound",
                follow_user_userid="owner-questionnaire",
                matched_by="external_userid",
            )

    class FakeBindMobileToExternalContactCommand:
        def __call__(self, request):
            mobile_bind_calls.append(
                {
                    "external_userid": request.external_userid,
                    "mobile": request.mobile,
                    "owner_userid": request.owner_userid,
                    "bind_by_userid": request.bind_by_userid,
                }
            )
            return {
                "ok": True,
                "external_userid": request.external_userid,
                "mobile": request.mobile,
                "owner_userid": request.owner_userid,
                "person_id": "person-questionnaire-mobile",
                "binding_status": "bound",
            }

    monkeypatch.setattr(h5_write, "ResolvePersonIdentityQuery", FakeResolvePersonIdentityQuery)
    monkeypatch.setattr(h5_write, "BindMobileToExternalContactCommand", FakeBindMobileToExternalContactCommand)
    client = _client(monkeypatch)

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={
            "answers": {"q_activation": "activated", "q_interest": ["ai_tools"]},
            "identity": {"external_userid": "wx_questionnaire_mobile", "mobile": "13800138000"},
        },
        headers={"Idempotency-Key": "questionnaire-mobile-binding"},
    )

    assert response.status_code == 200
    assert mobile_bind_calls == [
        {
            "external_userid": "wx_questionnaire_mobile",
            "mobile": "13800138000",
            "owner_userid": "owner-questionnaire",
            "bind_by_userid": "questionnaire_h5_submit",
        }
    ]
    assert response.json()["side_effects"]["mobile_binding"]["binding_status"] == "bound"


def test_customer_tag_assignment_command_is_plan_only() -> None:
    reset_wecom_tag_live_mutation_fixture_state()

    payload = execute_wecom_tag_mutation(
        PlanCustomerTagAssignmentCommand(
            idempotency_key="customer-assignment-plan",
            actor_id="customer_profile",
            actor_type="system",
            external_userid="wx_ext_001",
            tag_ids=["tag_fixture_active"],
            source_route="/api/admin/customers/profile/tags",
            source_context={"source": "customer_profile_tag_assignment"},
        )
    )

    assert payload["ok"] is True
    assert payload["command_name"] == "wecom.tag.assignment.apply"
    assert payload["effect_type"] == "wecom.tag.assignment.apply"
    assert payload["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert payload["real_external_call_executed"] is False
    assert payload["wecom_api_called"] is False
