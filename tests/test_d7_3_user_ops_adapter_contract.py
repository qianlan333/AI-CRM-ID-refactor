from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "tools" / "check_d7_3_user_ops_adapter_contract.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_d7_3_user_ops_adapter_contract", CHECKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _d7_3_docs() -> str:
    paths = [
        "docs/d7_3_user_ops_dnd_batch_send_wecom_dispatch_adapter_contract.md",
        "docs/d7_3_user_ops_adapter_implementation_report.md",
        "docs/d7_adapter_contract_catalog.md",
        "docs/d7_capability_readiness_matrix.md",
        "docs/d7_write_external_blocker_matrix.md",
        "docs/legacy_delete_batches.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]
    return "\n".join((REPO_ROOT / path).read_text(encoding="utf-8") for path in paths)


def test_user_ops_dnd_write_gateway_contract_exists() -> None:
    from aicrm_next.integration_gateway.user_ops_adapters import UserOpsDndWriteGateway

    for method in ["enable_do_not_disturb", "cancel_do_not_disturb", "build_dnd_preview", "record_dnd_audit"]:
        assert hasattr(UserOpsDndWriteGateway, method)


def test_user_ops_batch_send_gateway_contract_exists() -> None:
    from aicrm_next.integration_gateway.user_ops_adapters import UserOpsBatchSendGateway

    for method in ["build_batch_send_preview", "execute_batch_send", "create_send_record", "build_send_result_summary"]:
        assert hasattr(UserOpsBatchSendGateway, method)


def test_wecom_message_dispatch_adapter_contract_exists() -> None:
    from aicrm_next.integration_gateway.user_ops_adapters import WeComMessageDispatchAdapter

    for method in ["send_private_message", "send_group_message", "send_moment", "build_dispatch_preview", "resolve_dispatch_target", "record_dispatch_audit"]:
        assert hasattr(WeComMessageDispatchAdapter, method)


def test_user_ops_deferred_job_gateway_contract_exists() -> None:
    from aicrm_next.integration_gateway.user_ops_adapters import UserOpsDeferredJobGateway

    for method in ["enqueue_deferred_job", "run_due_jobs", "build_deferred_job_preview", "record_deferred_job_audit"]:
        assert hasattr(UserOpsDeferredJobGateway, method)


def test_fake_dnd_enable_cancel_returns_deterministic_fake_result() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.user_ops_adapters import UserOpsDndWriteGateway

    reset_idempotency_store()
    gateway = UserOpsDndWriteGateway("fake")
    first = gateway.enable_do_not_disturb(external_userid="external_1", reason_code="manual")
    second = gateway.enable_do_not_disturb(external_userid="external_1", reason_code="manual")
    cancel = gateway.cancel_do_not_disturb(external_userid="external_1", reason_code="manual")
    assert first["ok"] is True
    assert first["result"] == second["result"]
    assert first["result"]["do_not_disturb"] is True
    assert cancel["result"]["do_not_disturb"] is False
    assert first["side_effect_executed"] is False


def test_fake_batch_send_preview_execute_returns_deterministic_fake_result() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.user_ops_adapters import UserOpsBatchSendGateway

    reset_idempotency_store()
    gateway = UserOpsBatchSendGateway("fake")
    kwargs = {
        "selection_mode": "manual",
        "selected_ids": [1],
        "content": "hello",
        "targets": [{"external_userid": "external_1"}],
        "owner_buckets": [{"owner_userid": "owner_1", "target_count": 1, "external_userids": ["external_1"]}],
    }
    first = gateway.build_batch_send_preview(**kwargs)
    second = gateway.build_batch_send_preview(**kwargs)
    executed = gateway.execute_batch_send(content="hello", owner_buckets=kwargs["owner_buckets"])
    assert first["ok"] is True
    assert first["result"] == second["result"]
    assert executed["result"]["dispatched"] is False
    assert executed["side_effect_executed"] is False


def test_fake_wecom_private_group_moment_dispatch_returns_deterministic_fake_result() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.user_ops_adapters import WeComMessageDispatchAdapter

    reset_idempotency_store()
    adapter = WeComMessageDispatchAdapter("fake")
    first = adapter.send_private_message(external_userid="external_1", owner_userid="owner_1", content="hello")
    second = adapter.send_private_message(external_userid="external_1", owner_userid="owner_1", content="hello")
    group = adapter.send_group_message(group_chat_id="group_1", owner_userid="owner_1", content="hello")
    moment = adapter.send_moment(owner_userid="owner_1", content="hello")
    assert first["result"] == second["result"]
    assert first["result"]["sent"] is False
    assert group["result"]["sent"] is False
    assert moment["result"]["sent"] is False


def test_repeated_call_with_same_idempotency_key_returns_same_result() -> None:
    from aicrm_next.integration_gateway.user_ops_adapters import WeComMessageDispatchAdapter

    adapter = WeComMessageDispatchAdapter("fake")
    first = adapter.send_private_message(external_userid="external_1", content="hello", idempotency_key="idem-dispatch-1")
    second = adapter.send_private_message(external_userid="external_2", content="different", idempotency_key="idem-dispatch-1")
    assert first["result"] == second["result"]


def test_disabled_mode_returns_stable_disabled_error() -> None:
    from aicrm_next.integration_gateway.user_ops_adapters import UserOpsBatchSendGateway

    result = UserOpsBatchSendGateway("disabled").execute_batch_send(content="hello")
    assert result["ok"] is False
    assert result["error_code"] == "adapter_disabled"
    assert result["side_effect_executed"] is False


def test_production_mode_without_explicit_env_flag_fails_closed(monkeypatch) -> None:
    from aicrm_next.integration_gateway.user_ops_adapters import (
        UserOpsBatchSendGateway,
        UserOpsDeferredJobGateway,
        UserOpsDndWriteGateway,
        WeComMessageDispatchAdapter,
    )

    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_USER_OPS_DND", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_USER_OPS_BATCH_SEND", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_WECOM_DISPATCH", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_USER_OPS_DEFERRED_JOBS", raising=False)
    results = [
        UserOpsDndWriteGateway("production").enable_do_not_disturb(external_userid="external_1"),
        UserOpsBatchSendGateway("production").execute_batch_send(content="hello"),
        WeComMessageDispatchAdapter("production").send_private_message(external_userid="external_1", content="hello"),
        UserOpsDeferredJobGateway("production").run_due_jobs(now="2026-05-21T00:00:00Z"),
    ]
    assert all(result["ok"] is False for result in results)
    assert all(result["error_code"] == "production_guard_failed" for result in results)
    assert all(result["side_effect_executed"] is False for result in results)


def test_production_mode_with_env_flag_still_returns_not_implemented(monkeypatch) -> None:
    from aicrm_next.integration_gateway.user_ops_adapters import WeComMessageDispatchAdapter

    monkeypatch.setenv("AICRM_NEXT_ENABLE_REAL_WECOM_DISPATCH", "true")
    result = WeComMessageDispatchAdapter("production").send_private_message(external_userid="external_1", content="hello")
    assert result["ok"] is False
    assert result["error_code"] == "production_not_implemented"
    assert result["side_effect_executed"] is False


def test_side_effect_executed_is_false_in_fake_disabled_staging_guarded_production(monkeypatch) -> None:
    from aicrm_next.integration_gateway.user_ops_adapters import UserOpsDndWriteGateway

    monkeypatch.setenv("AICRM_NEXT_ENABLE_REAL_USER_OPS_DND", "true")
    results = [
        UserOpsDndWriteGateway("fake").enable_do_not_disturb(external_userid="external_1"),
        UserOpsDndWriteGateway("disabled").enable_do_not_disturb(external_userid="external_1"),
        UserOpsDndWriteGateway("staging").enable_do_not_disturb(external_userid="external_1"),
        UserOpsDndWriteGateway("production").enable_do_not_disturb(external_userid="external_1"),
    ]
    assert all(result["side_effect_executed"] is False for result in results)
    assert results[-1]["error_code"] == "production_not_implemented"


def test_audit_record_is_created_for_dnd_batch_send_and_dispatch() -> None:
    from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
    from aicrm_next.integration_gateway.user_ops_adapters import UserOpsBatchSendGateway, UserOpsDndWriteGateway, WeComMessageDispatchAdapter

    reset_audit_events()
    UserOpsDndWriteGateway("fake").enable_do_not_disturb(external_userid="external_1")
    UserOpsBatchSendGateway("fake").execute_batch_send(content="hello")
    WeComMessageDispatchAdapter("fake").send_private_message(external_userid="external_1", content="hello")
    events = list_audit_events()
    assert [event["adapter"] for event in events[-3:]] == ["UserOpsDndWriteGateway", "UserOpsBatchSendGateway", "WeComMessageDispatchAdapter"]
    assert all(event["side_effect_executed"] is False for event in events[-3:])


class _SpyDndGateway:
    mode = "fake"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def enable_do_not_disturb(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("enable_do_not_disturb")
        return {"ok": True, "adapter": "SpyDnd", "mode": "fake", "operation": "enable_do_not_disturb", "idempotency_key": "spy-dnd", "target": kwargs, "result": {}, "audit_id": "spy-audit", "side_effect_executed": False, "error_code": "", "error_message": ""}


class _SpyBatchGateway:
    mode = "fake"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def build_batch_send_preview(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("build_batch_send_preview")
        return {"ok": True, "adapter": "SpyBatch", "mode": "fake", "operation": "build_batch_send_preview", "idempotency_key": "spy-preview", "target": kwargs, "result": {}, "audit_id": "spy-preview-audit", "side_effect_executed": False, "error_code": "", "error_message": ""}

    def execute_batch_send(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("execute_batch_send")
        return {"ok": True, "adapter": "SpyBatch", "mode": "fake", "operation": "execute_batch_send", "idempotency_key": "spy-execute", "target": kwargs, "result": {"dispatched": False}, "audit_id": "spy-execute-audit", "side_effect_executed": False, "error_code": "", "error_message": ""}

    def create_send_record(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("create_send_record")
        return {"ok": True, "adapter": "SpyBatch", "mode": "fake", "operation": "create_send_record", "idempotency_key": "spy-record", "target": kwargs, "result": {"persisted": False}, "audit_id": "spy-record-audit", "side_effect_executed": False, "error_code": "", "error_message": ""}

    def build_send_result_summary(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("build_send_result_summary")
        return {"ok": True, "adapter": "SpyBatch", "mode": "fake", "operation": "build_send_result_summary", "idempotency_key": "spy-summary", "target": kwargs, "result": {}, "audit_id": "spy-summary-audit", "side_effect_executed": False, "error_code": "", "error_message": ""}


class _SpyDispatchAdapter:
    mode = "fake"

    def __init__(self) -> None:
        self.called = False

    def send_private_message(self, **kwargs: Any) -> dict[str, Any]:
        self.called = True
        return {
            "ok": True,
            "adapter": "SpyDispatch",
            "mode": "fake",
            "operation": "send_private_message",
            "idempotency_key": "spy-dispatch",
            "target": kwargs,
            "result": {"task_id": "spy-task", "status": "created", "status_label": "已创建任务", "error_message": "", "dispatch_adapter": "fake_wecom", "sent": False},
            "audit_id": "spy-dispatch-audit",
            "side_effect_executed": False,
            "error_code": "",
            "error_message": "",
        }


def test_dnd_api_uses_user_ops_dnd_write_gateway_boundary() -> None:
    from aicrm_next.ops_enrollment.application import SetUserOpsDoNotDisturbCommand, reset_user_ops_fixture_state
    from aicrm_next.ops_enrollment.dto import DoNotDisturbRequest

    reset_user_ops_fixture_state()
    gateway = _SpyDndGateway()
    result = SetUserOpsDoNotDisturbCommand(dnd_gateway=gateway)(DoNotDisturbRequest(external_userid="wx_ext_001"))
    assert result["ok"] is True
    assert gateway.calls == ["enable_do_not_disturb"]
    assert result["adapter_contract"]["dnd_write"]["adapter"] == "SpyDnd"


def test_batch_send_execute_uses_batch_gateway_and_wecom_dispatch_boundary() -> None:
    from aicrm_next.ops_enrollment.application import ExecuteUserOpsBatchSendCommand, reset_user_ops_fixture_state
    from aicrm_next.ops_enrollment.dto import BatchSendRequest

    reset_user_ops_fixture_state()
    batch_gateway = _SpyBatchGateway()
    dispatch_adapter = _SpyDispatchAdapter()
    result = ExecuteUserOpsBatchSendCommand(batch_gateway=batch_gateway, dispatch_adapter=dispatch_adapter)(
        BatchSendRequest(selection_mode="manual", selected_ids=[1], content="hello", confirm=True)
    )
    assert result["ok"] is True
    assert batch_gateway.calls == ["build_batch_send_preview", "execute_batch_send", "create_send_record", "build_send_result_summary"]
    assert dispatch_adapter.called is True
    assert result["side_effect_safety"]["real_wecom_dispatch_executed"] is False


def test_deferred_job_fake_path_uses_user_ops_deferred_job_gateway_boundary() -> None:
    from aicrm_next.integration_gateway.user_ops_adapters import UserOpsDeferredJobGateway
    from aicrm_next.ops_enrollment.application import RunDueUserOpsDeferredJobsCommand

    result = RunDueUserOpsDeferredJobsCommand(gateway=UserOpsDeferredJobGateway("fake"))(now="2026-05-21T00:00:00Z", limit=5)
    assert result["adapter"] == "UserOpsDeferredJobGateway"
    assert result["result"]["executed"] is False
    assert result["side_effect_executed"] is False


def test_user_ops_readonly_smoke_and_parity_remain_passable() -> None:
    checker = _load_checker()
    report = checker.build_report()
    assert report["user_ops_smoke"]["ok"] is True
    assert report["user_ops_parity"]["ok"] is True


def test_docs_do_not_mark_forbidden_d7_3_statuses() -> None:
    text = _d7_3_docs()
    assert "production_ready" not in text
    assert "delete_ready" not in text


def test_no_old_backend_imports_in_aicrm_next() -> None:
    for path in (REPO_ROOT / "aicrm_next").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert "wecom_ability_service" not in text
        assert "openclaw_service" not in text
