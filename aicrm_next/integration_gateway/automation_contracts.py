from __future__ import annotations

from typing import Any, Literal, Protocol


Json = dict[str, Any]
AdapterMode = Literal["fake", "disabled", "staging", "production"]

REQUIRED_AUTOMATION_ADAPTER_RESULT_FIELDS = (
    "ok",
    "adapter",
    "mode",
    "operation",
    "idempotency_key",
    "target",
    "result",
    "audit_id",
    "side_effect_executed",
    "error_code",
    "error_message",
)


class AutomationActivationGatewayContract(Protocol):
    def receive_activation_event(self, *, activation_event_id: str = "", member_id: str = "", external_userid: str = "", mobile: str = "", source: str = "activation_webhook", idempotency_key: str | None = None) -> Json: ...
    def normalize_activation_payload(self, *, activation_event_id: str = "", payload: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json: ...
    def build_activation_preview(self, *, activation_event_id: str = "", member_id: str = "", external_userid: str = "", mobile: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json: ...
    def record_activation_audit(self, *, operation: str, target: dict[str, Any], result: dict[str, Any] | None = None, error_code: str = "", idempotency_key: str | None = None) -> Json: ...


class AutomationAgentRuntimeAdapterContract(Protocol):
    def run_agent_task(self, *, agent_task_id: str, member_id: str = "", workflow_id: str = "", execution_id: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json: ...
    def generate_agent_output(self, *, agent_task_id: str, member_id: str = "", workflow_id: str = "", execution_id: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json: ...
    def review_agent_output(self, *, agent_task_id: str, output_id: str = "", reviewer: str = "system", decision: str = "preview", idempotency_key: str | None = None) -> Json: ...
    def build_agent_runtime_preview(self, *, agent_task_id: str = "", member_id: str = "", workflow_id: str = "", execution_id: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json: ...
    def record_agent_runtime_audit(self, *, operation: str, target: dict[str, Any], result: dict[str, Any] | None = None, error_code: str = "", idempotency_key: str | None = None) -> Json: ...
