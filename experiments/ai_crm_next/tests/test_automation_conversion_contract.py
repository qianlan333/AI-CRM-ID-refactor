from __future__ import annotations

from conftest import make_client

from aicrm_next.automation_engine.dto import (
    ApplyActivationFactRequest,
    ApplyQuestionnaireResultRequest,
    ApplyTrialOpenedFactRequest,
    AutomationActionRequest,
    OverrideFollowupTypeRequest,
)
from aicrm_next.automation_engine.application import (
    ApplyActivationFactCommand,
    ApplyQuestionnaireResultCommand,
    ApplyTrialOpenedFactCommand,
    ConfirmConversionCommand,
    EnterSilentPoolCommand,
    ExitMarketingCommand,
    OverrideFollowupTypeCommand,
)
from aicrm_next.automation_engine.parity_spec import MEMBER_ITEM_KEYS, POOL_ITEM_KEYS
from aicrm_next.automation_engine.repo import InMemoryAutomationRepository
from aicrm_next.automation_engine.state_machine import POOL_KEYS


def test_state_machine_new_member_starts_in_new_user() -> None:
    repo = InMemoryAutomationRepository(members=[])
    result = ApplyQuestionnaireResultCommand(repo)(
        ApplyQuestionnaireResultRequest(mobile="mobile_fixture_new", followup_type="normal", submission_id="sub_new")
    )
    assert result["member"]["current_pool"] == "new_user"
    assert result["history"]["before_pool"] == "new_user"


def test_state_machine_questionnaire_normal_and_trial_opened_to_unactivated_normal() -> None:
    repo = InMemoryAutomationRepository(members=[])
    member = ApplyQuestionnaireResultCommand(repo)(
        ApplyQuestionnaireResultRequest(mobile="mobile_fixture_normal", followup_type="normal")
    )["member"]
    opened = ApplyTrialOpenedFactCommand(repo)(ApplyTrialOpenedFactRequest(member_id=member["member_id"]))
    assert opened["member"]["current_pool"] == "unactivated_normal"


def test_state_machine_questionnaire_priority_and_trial_opened_to_unactivated_priority() -> None:
    repo = InMemoryAutomationRepository(members=[])
    member = ApplyQuestionnaireResultCommand(repo)(
        ApplyQuestionnaireResultRequest(mobile="mobile_fixture_priority", followup_type="priority")
    )["member"]
    opened = ApplyTrialOpenedFactCommand(repo)(ApplyTrialOpenedFactRequest(member_id=member["member_id"]))
    assert opened["member"]["current_pool"] == "unactivated_priority"


def test_second_questionnaire_result_does_not_change_initial_split() -> None:
    repo = InMemoryAutomationRepository(members=[])
    command = ApplyQuestionnaireResultCommand(repo)
    member = command(ApplyQuestionnaireResultRequest(mobile="mobile_fixture_repeat", followup_type="priority"))["member"]
    opened = ApplyTrialOpenedFactCommand(repo)(ApplyTrialOpenedFactRequest(member_id=member["member_id"]))["member"]
    assert opened["current_pool"] == "unactivated_priority"

    repeated = command(ApplyQuestionnaireResultRequest(mobile="mobile_fixture_repeat", followup_type="normal"))["member"]
    assert repeated["questionnaire_followup_type"] == "priority"
    assert repeated["followup_type"] == "priority"
    assert repeated["current_pool"] == "unactivated_priority"
    assert repo.list_history(member["member_id"])[-1]["trigger"] == "questionnaire_result_ignored"


def test_second_questionnaire_result_does_not_override_manual_followup_type() -> None:
    repo = InMemoryAutomationRepository(members=[])
    command = ApplyQuestionnaireResultCommand(repo)
    member = command(ApplyQuestionnaireResultRequest(mobile="mobile_fixture_manual", followup_type="normal"))["member"]
    ApplyTrialOpenedFactCommand(repo)(ApplyTrialOpenedFactRequest(member_id=member["member_id"]))
    overridden = OverrideFollowupTypeCommand(repo)(
        member["member_id"], OverrideFollowupTypeRequest(followup_type="priority", reason="人工改判")
    )["member"]
    assert overridden["current_pool"] == "unactivated_priority"

    repeated = command(ApplyQuestionnaireResultRequest(mobile="mobile_fixture_manual", followup_type="normal"))["member"]
    assert repeated["manual_followup_type"] == "priority"
    assert repeated["followup_type"] == "priority"
    assert repeated["current_pool"] == "unactivated_priority"


def test_second_questionnaire_result_after_activation_does_not_reroute_branch() -> None:
    repo = InMemoryAutomationRepository(members=[])
    command = ApplyQuestionnaireResultCommand(repo)
    member = command(ApplyQuestionnaireResultRequest(mobile="mobile_fixture_activated", followup_type="priority"))["member"]
    ApplyTrialOpenedFactCommand(repo)(ApplyTrialOpenedFactRequest(member_id=member["member_id"]))
    activated = ApplyActivationFactCommand(repo)(ApplyActivationFactRequest(member_id=member["member_id"]))["member"]
    assert activated["current_pool"] == "activated_priority"

    repeated = command(ApplyQuestionnaireResultRequest(mobile="mobile_fixture_activated", followup_type="normal"))["member"]
    assert repeated["questionnaire_followup_type"] == "priority"
    assert repeated["followup_type"] == "priority"
    assert repeated["current_pool"] == "activated_priority"


def test_activation_moves_normal_and_priority_branches() -> None:
    repo = InMemoryAutomationRepository()
    normal = ApplyTrialOpenedFactCommand(repo)(ApplyTrialOpenedFactRequest(member_id="member_001"))["member"]
    assert normal["current_pool"] == "unactivated_normal"
    activated_normal = ApplyActivationFactCommand(repo)(ApplyActivationFactRequest(member_id="member_001"))["member"]
    assert activated_normal["current_pool"] == "activated_normal"

    activated_priority = ApplyActivationFactCommand(repo)(ApplyActivationFactRequest(member_id="member_002"))["member"]
    assert activated_priority["current_pool"] == "activated_priority"


def test_manual_override_changes_current_pool_branch() -> None:
    repo = InMemoryAutomationRepository()
    ApplyTrialOpenedFactCommand(repo)(ApplyTrialOpenedFactRequest(member_id="member_001"))
    priority = OverrideFollowupTypeCommand(repo)(
        "member_001", OverrideFollowupTypeRequest(followup_type="priority", reason="人工重点")
    )["member"]
    assert priority["current_pool"] == "unactivated_priority"
    normal = OverrideFollowupTypeCommand(repo)("member_001", OverrideFollowupTypeRequest(followup_type="normal"))["member"]
    assert normal["current_pool"] == "unactivated_normal"


def test_conversion_silent_exit_and_terminal_no_reentry() -> None:
    repo = InMemoryAutomationRepository()
    converted = ConfirmConversionCommand(repo)("member_002", AutomationActionRequest(reason="成交确认"))["member"]
    assert converted["current_pool"] == "converted"
    assert converted["exited"] is True
    noop = ApplyActivationFactCommand(repo)(ApplyActivationFactRequest(member_id="member_002"))["member"]
    assert noop["current_pool"] == "converted"

    silent = EnterSilentPoolCommand(repo)("member_001", AutomationActionRequest(reason="免打扰"))["member"]
    assert silent["current_pool"] == "silent"
    exited = ExitMarketingCommand(repo)("member_001", AutomationActionRequest(reason="退出"))["member"]
    assert exited["current_pool"] == "exited"


def test_admin_automation_overview_pools_members_contract() -> None:
    client = make_client()
    overview = client.get("/api/admin/automation-conversion/overview").json()
    assert overview["ok"] is True
    assert len(overview["cards"]) >= 8

    pools = client.get("/api/admin/automation-conversion/pools").json()
    assert pools["ok"] is True
    assert set(POOL_KEYS) <= {item["pool_key"] for item in pools["pools"]}
    assert set(POOL_ITEM_KEYS) <= set(pools["pools"][0])

    members = client.get("/api/admin/automation-conversion/members").json()
    assert members["ok"] is True
    assert set(MEMBER_ITEM_KEYS) <= set(members["items"][0])


def test_admin_automation_member_detail_and_actions() -> None:
    client = make_client()
    detail = client.get("/api/admin/automation-conversion/members/member_002").json()
    assert detail["ok"] is True
    assert {"member", "history", "customer_context", "recent_timeline_events", "warnings"} <= set(detail)

    overridden = client.post(
        "/api/admin/automation-conversion/members/member_002/override-followup-type",
        json={"followup_type": "normal", "operator": "tester", "reason": "验收"},
    )
    assert overridden.status_code == 200
    assert overridden.json()["member"]["current_pool"] == "unactivated_normal"

    converted = client.post("/api/admin/automation-conversion/members/member_002/confirm-conversion", json={"reason": "成交"})
    assert converted.status_code == 200
    assert converted.json()["member"]["current_pool"] == "converted"

    silent = client.post("/api/admin/automation-conversion/members/member_001/enter-silent", json={"reason": "静默"})
    assert silent.status_code == 200
    assert silent.json()["member"]["current_pool"] == "silent"

    exited = client.post("/api/admin/automation-conversion/members/member_001/exit-marketing", json={"reason": "退出"})
    assert exited.status_code == 200
    assert exited.json()["member"]["current_pool"] == "exited"


def test_activation_webhook_and_openclaw_fake_push_contract() -> None:
    client = make_client()
    response = client.post(
        "/api/customer-automation/activation-webhook",
        json={"mobile": "13800138001", "activated_at": "2026-05-20T12:00:00Z", "source": "unit"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["previous_pool"] == "unactivated_priority"
    assert payload["current_pool"] == "activated_priority"

    missing_target = client.post("/api/customer-automation/activation-webhook", json={})
    assert missing_target.status_code == 400

    fake_push = client.post("/api/admin/automation-conversion/members/member_002/push-openclaw-context", json={})
    assert fake_push.status_code == 200
    pushed = fake_push.json()
    assert pushed["delivery_status"] == "fake"
    assert {"customer_context", "current_pool", "recent_timeline_events"} <= set(pushed["payload_preview"])
    assert "openclaw_not_called" in pushed["warnings"]


def test_execution_records_and_frontend_adapter() -> None:
    client = make_client()
    records = client.get("/api/admin/automation-conversion/execution-records").json()
    assert records["ok"] is True
    assert {"items", "total", "limit", "offset"} <= set(records)

    response = client.get("/admin/automation-conversion")
    assert response.status_code == 200
    html = response.text
    assert "方案列表" in html
    assert "默认转化方案" in html
    for bad in ("New UI", "redesign", "TODO replace old frontend", "experimental replacement UI", "待复刻页面"):
        assert bad not in html


def test_questionnaire_submit_emits_automation_boundary_event_without_real_wecom() -> None:
    response = make_client().post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {"q_activation": "activated", "q_interest": ["ai_tools"]}, "respondent_identity": {"mobile": "13800138000"}},
    )
    assert response.status_code == 200
    event = response.json()["automation_event"]
    assert event["ok"] is True
    assert event["source_status"] == "fixture_boundary"
    assert event["followup_type"] == "priority"
