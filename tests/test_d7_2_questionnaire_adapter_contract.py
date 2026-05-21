from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "tools" / "check_d7_2_questionnaire_adapter_contract.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_d7_2_questionnaire_adapter_contract", CHECKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _d7_2_docs() -> str:
    paths = [
        "docs/d7_2_questionnaire_submit_oauth_wecom_tag_adapter_contract.md",
        "docs/d7_2_questionnaire_adapter_implementation_report.md",
        "docs/d7_adapter_contract_catalog.md",
        "docs/d7_capability_readiness_matrix.md",
        "docs/d7_write_external_blocker_matrix.md",
        "docs/legacy_delete_batches.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]
    return "\n".join((REPO_ROOT / path).read_text(encoding="utf-8") for path in paths)


def test_wechat_oauth_adapter_contract_exists() -> None:
    from aicrm_next.integration_gateway.questionnaire_adapters import WeChatOAuthAdapter

    for method in ["build_authorize_url", "exchange_code", "fetch_userinfo", "resolve_oauth_identity"]:
        assert hasattr(WeChatOAuthAdapter, method)


def test_wecom_tag_adapter_contract_exists() -> None:
    from aicrm_next.integration_gateway.questionnaire_adapters import WeComTagAdapter

    for method in ["mark_external_contact_tags", "unmark_external_contact_tags", "validate_tag_ids", "build_tag_operation_preview"]:
        assert hasattr(WeComTagAdapter, method)


def test_questionnaire_external_push_adapter_contract_exists() -> None:
    from aicrm_next.integration_gateway.questionnaire_adapters import QuestionnaireExternalPushAdapter

    for method in ["push_submission_event", "push_score_result_event", "retry_push_event", "build_push_preview"]:
        assert hasattr(QuestionnaireExternalPushAdapter, method)


def test_questionnaire_submit_side_effect_gateway_exists() -> None:
    from aicrm_next.integration_gateway.questionnaire_adapters import QuestionnaireSubmitSideEffectGateway

    for method in ["apply_tags", "emit_external_push", "emit_automation_questionnaire_result", "record_side_effect_audit"]:
        assert hasattr(QuestionnaireSubmitSideEffectGateway, method)


def test_fake_oauth_build_exchange_userinfo_returns_deterministic_fake_identity() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.questionnaire_adapters import WeChatOAuthAdapter

    reset_idempotency_store()
    adapter = WeChatOAuthAdapter("fake")
    authorize = adapter.build_authorize_url(slug="hxc-activation-v1", openid="openid_fake")
    first = adapter.exchange_code(code="code-1", state="hxc-activation-v1")
    second = adapter.exchange_code(code="code-1", state="hxc-activation-v1")
    userinfo = adapter.fetch_userinfo(openid=first["result"]["openid"], unionid=first["result"]["unionid"])
    assert authorize["ok"] is True
    assert first["result"] == second["result"]
    assert userinfo["result"]["openid"] == first["result"]["openid"]
    assert first["side_effect_executed"] is False


def test_fake_wecom_tag_operation_returns_deterministic_fake_tag_result() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.questionnaire_adapters import WeComTagAdapter

    reset_idempotency_store()
    adapter = WeComTagAdapter("fake")
    first = adapter.mark_external_contact_tags(external_userid="external_1", tag_ids=["tag_b", "tag_a"], questionnaire_id=1, submission_id="sub_1")
    second = adapter.mark_external_contact_tags(external_userid="external_1", tag_ids=["tag_a", "tag_b"], questionnaire_id=1, submission_id="sub_1")
    assert first["ok"] is True
    assert first["result"] == second["result"]
    assert first["result"]["applied"] is False


def test_fake_external_push_returns_deterministic_fake_push_result() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.questionnaire_adapters import QuestionnaireExternalPushAdapter

    reset_idempotency_store()
    adapter = QuestionnaireExternalPushAdapter("fake")
    first = adapter.push_submission_event(questionnaire_id=1, submission_id="sub_1", webhook_url="https://example.invalid/hook")
    second = adapter.push_submission_event(questionnaire_id=1, submission_id="sub_1", webhook_url="https://example.invalid/hook")
    assert first["ok"] is True
    assert first["result"] == second["result"]
    assert first["result"]["delivered"] is False


def test_repeated_call_with_same_idempotency_key_returns_same_result() -> None:
    from aicrm_next.integration_gateway.questionnaire_adapters import WeComTagAdapter

    adapter = WeComTagAdapter("fake")
    first = adapter.mark_external_contact_tags(external_userid="external_1", tag_ids=["tag_a"], idempotency_key="idem-tag-1")
    second = adapter.mark_external_contact_tags(external_userid="external_2", tag_ids=["tag_b"], idempotency_key="idem-tag-1")
    assert first["result"] == second["result"]


def test_disabled_mode_returns_stable_disabled_error() -> None:
    from aicrm_next.integration_gateway.questionnaire_adapters import QuestionnaireExternalPushAdapter

    result = QuestionnaireExternalPushAdapter("disabled").push_submission_event(questionnaire_id=1, submission_id="sub_1")
    assert result["ok"] is False
    assert result["error_code"] == "adapter_disabled"
    assert result["side_effect_executed"] is False


def test_production_mode_without_explicit_env_flag_fails_closed(monkeypatch) -> None:
    from aicrm_next.integration_gateway.questionnaire_adapters import QuestionnaireExternalPushAdapter, WeChatOAuthAdapter, WeComTagAdapter

    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_WECHAT_OAUTH", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_WECOM_TAG", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_QUESTIONNAIRE_WEBHOOK", raising=False)
    results = [
        WeChatOAuthAdapter("production").exchange_code(code="code-1"),
        WeComTagAdapter("production").mark_external_contact_tags(external_userid="external_1", tag_ids=["tag_a"]),
        QuestionnaireExternalPushAdapter("production").push_submission_event(questionnaire_id=1, submission_id="sub_1"),
    ]
    assert all(result["ok"] is False for result in results)
    assert all(result["error_code"] == "production_guard_failed" for result in results)
    assert all(result["side_effect_executed"] is False for result in results)


def test_side_effect_executed_is_false_in_fake_disabled_staging_guarded_production(monkeypatch) -> None:
    from aicrm_next.integration_gateway.questionnaire_adapters import WeChatOAuthAdapter

    monkeypatch.setenv("AICRM_NEXT_ENABLE_REAL_WECHAT_OAUTH", "true")
    results = [
        WeChatOAuthAdapter("fake").exchange_code(code="code-1"),
        WeChatOAuthAdapter("disabled").exchange_code(code="code-1"),
        WeChatOAuthAdapter("staging").exchange_code(code="code-1"),
        WeChatOAuthAdapter("production").exchange_code(code="code-1"),
    ]
    assert all(result["side_effect_executed"] is False for result in results)
    assert results[-1]["error_code"] == "production_not_implemented"


def test_audit_record_is_created_for_oauth_tag_and_external_push() -> None:
    from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
    from aicrm_next.integration_gateway.questionnaire_adapters import QuestionnaireExternalPushAdapter, WeChatOAuthAdapter, WeComTagAdapter

    reset_audit_events()
    WeChatOAuthAdapter("fake").exchange_code(code="code-1")
    WeComTagAdapter("fake").mark_external_contact_tags(external_userid="external_1", tag_ids=["tag_a"])
    QuestionnaireExternalPushAdapter("fake").push_submission_event(questionnaire_id=1, submission_id="sub_1")
    events = list_audit_events()
    assert [event["adapter"] for event in events[-3:]] == ["WeChatOAuthAdapter", "WeComTagAdapter", "QuestionnaireExternalPushAdapter"]
    assert all(event["side_effect_executed"] is False for event in events[-3:])


class _SpySideEffectGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def apply_tags(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("apply_tags")
        return {"ok": True, "adapter": "SpyTag", "mode": "fake", "operation": "apply_tags", "idempotency_key": "spy-tag", "target": kwargs, "result": {}, "audit_id": "spy-audit-tag", "side_effect_executed": False, "error_code": "", "error_message": ""}

    def emit_external_push(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("emit_external_push")
        return {"ok": True, "adapter": "SpyPush", "mode": "fake", "operation": "emit_external_push", "idempotency_key": "spy-push", "target": kwargs, "result": {}, "audit_id": "spy-audit-push", "side_effect_executed": False, "error_code": "", "error_message": ""}

    def emit_automation_questionnaire_result(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("emit_automation_questionnaire_result")
        return {"ok": True, "adapter": "SpyAutomation", "mode": "fake", "operation": "emit_automation_questionnaire_result", "idempotency_key": "spy-auto", "target": {}, "result": {"source_status": "fixture_boundary", "followup_type": "normal"}, "audit_id": "spy-audit-auto", "side_effect_executed": False, "error_code": "", "error_message": ""}

    def side_effect_safety(self) -> dict[str, Any]:
        return {"real_oauth_executed": False, "real_wecom_tag_executed": False, "real_external_webhook_executed": False, "side_effect_executed": False}


def test_questionnaire_submit_pipeline_uses_side_effect_gateway() -> None:
    from aicrm_next.questionnaire.application import SubmitQuestionnaireCommand
    from aicrm_next.questionnaire.dto import QuestionnaireSubmitRequest
    from aicrm_next.questionnaire.repo import reset_questionnaire_fixture_state

    reset_questionnaire_fixture_state()
    gateway = _SpySideEffectGateway()
    result = SubmitQuestionnaireCommand(side_effect_gateway=gateway)(
        "hxc-activation-v1",
        QuestionnaireSubmitRequest(answers={"q_activation": "activated"}, respondent_identity={"mobile": "13800138000"}),
    )
    assert result["ok"] is True
    assert gateway.calls == ["apply_tags", "emit_external_push", "emit_automation_questionnaire_result"]
    assert result["side_effect_safety"]["real_wecom_tag_executed"] is False


def test_oauth_callback_fake_path_uses_wechat_oauth_adapter_boundary() -> None:
    from aicrm_next.questionnaire.application import CompleteWechatOAuthCallbackCommand
    from aicrm_next.questionnaire.dto import OAuthCallbackRequest

    class SpyOAuthAdapter:
        def __init__(self) -> None:
            self.called = False

        def resolve_oauth_identity(self, **kwargs: Any) -> dict[str, Any]:
            self.called = True
            return {
                "ok": True,
                "result": {"openid": "openid_spy", "unionid": "unionid_spy", "external_userid": "external_spy", "redirect_url": "/s/hxc-activation-v1", "state": "hxc-activation-v1", "source_status": "fake"},
            }

    adapter = SpyOAuthAdapter()
    result = CompleteWechatOAuthCallbackCommand(adapter=adapter)(OAuthCallbackRequest(state="hxc-activation-v1"))
    assert adapter.called is True
    assert result["openid"] == "openid_spy"


def test_wecom_tag_fake_path_uses_wecom_tag_adapter_boundary() -> None:
    from aicrm_next.integration_gateway.questionnaire_adapters import QuestionnaireSubmitSideEffectGateway, WeComTagAdapter

    result = QuestionnaireSubmitSideEffectGateway(tag_adapter=WeComTagAdapter("fake")).apply_tags(
        questionnaire_id=1,
        submission_id="sub_1",
        external_userid="external_1",
        tag_ids=["tag_a"],
    )
    assert result["adapter"] == "WeComTagAdapter"
    assert result["side_effect_executed"] is False


def test_external_push_fake_path_uses_questionnaire_external_push_adapter_boundary() -> None:
    from aicrm_next.integration_gateway.questionnaire_adapters import QuestionnaireExternalPushAdapter, QuestionnaireSubmitSideEffectGateway

    result = QuestionnaireSubmitSideEffectGateway(push_adapter=QuestionnaireExternalPushAdapter("fake")).emit_external_push(
        questionnaire_id=1,
        submission_id="sub_1",
        webhook_url="https://example.invalid/hook",
        payload_summary={"score": 10},
    )
    assert result["adapter"] == "QuestionnaireExternalPushAdapter"
    assert result["side_effect_executed"] is False


def test_questionnaire_readonly_smoke_and_parity_remain_passable() -> None:
    checker = _load_checker()
    report = checker.build_report()
    assert report["questionnaire_smoke"]["ok"] is True
    assert report["questionnaire_parity"]["ok"] is True


def test_docs_do_not_mark_production_ready_or_delete_ready() -> None:
    text = _d7_2_docs()
    assert "production_ready" not in text
    assert "delete_ready" not in text


def test_no_old_backend_imports_in_aicrm_next() -> None:
    for path in (REPO_ROOT / "aicrm_next").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "wecom_ability_service" not in source
        assert "openclaw_service" not in source
