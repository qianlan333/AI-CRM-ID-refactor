from __future__ import annotations

from typing import Any, cast

from ..customer_read_model.dto import (
    SignupConversionBatchDetailQueryDTO,
    SignupConversionBatchDetailResultDTO,
    SignupConversionBatchListQueryDTO,
    SignupConversionBatchListResultDTO,
)


class ListSignupConversionBatchesQuery:
    """Wave 1 skeleton that delegates to ``domains.marketing_automation.list_signup_conversion_batches``."""

    def __call__(self, dto: SignupConversionBatchListQueryDTO | None = None) -> SignupConversionBatchListResultDTO:
        from ...domains.marketing_automation import list_signup_conversion_batches

        query = dto or SignupConversionBatchListQueryDTO()
        scenario_key = str(query.scenario_key or "").strip()
        kwargs: dict[str, Any] = {
            "limit": int(query.limit),
            "cursor": str(query.cursor or ""),
        }
        if scenario_key:
            kwargs["scenario_key"] = scenario_key
        return cast(
            SignupConversionBatchListResultDTO,
            list_signup_conversion_batches(**kwargs),
        )

    execute = __call__


class GetSignupConversionBatchQuery:
    """Wave 1 skeleton that delegates to ``domains.marketing_automation.get_signup_conversion_batch``."""

    def __call__(self, dto: SignupConversionBatchDetailQueryDTO) -> SignupConversionBatchDetailResultDTO:
        from ...domains.marketing_automation import get_signup_conversion_batch

        scenario_key = str(dto.scenario_key or "").strip()
        kwargs: dict[str, Any] = {}
        if scenario_key:
            kwargs["scenario_key"] = scenario_key
        return cast(
            SignupConversionBatchDetailResultDTO,
            get_signup_conversion_batch(int(dto.batch_id), **kwargs),
        )

    execute = __call__


class RetryOutboundWebhookDeliveryCommand:
    """Wave 1 skeleton that delegates to ``domains.outbound_webhook.retry_outbound_webhook_delivery``."""

    def __call__(self, delivery_id: int) -> dict[str, Any]:
        from ...domains.outbound_webhook import retry_outbound_webhook_delivery

        return retry_outbound_webhook_delivery(int(delivery_id))

    execute = __call__


class ListOutboundWebhookDeliveriesQuery:
    """Wave 1 skeleton that delegates to ``domains.outbound_webhook.list_outbound_webhook_deliveries``."""

    def __call__(self, *, event_type: str = "", status: str = "", limit: int = 50) -> dict[str, Any]:
        from ...domains.outbound_webhook import list_outbound_webhook_deliveries

        return list_outbound_webhook_deliveries(
            event_type=str(event_type or ""),
            status=str(status or ""),
            limit=int(limit),
        )

    execute = __call__


class RunDueOutboundWebhookRetriesCommand:
    """Wave 1 skeleton that delegates to ``domains.outbound_webhook.run_due_outbound_webhook_retries``."""

    def __call__(self, *, limit: int = 20) -> dict[str, Any]:
        from ...domains.outbound_webhook import run_due_outbound_webhook_retries

        return run_due_outbound_webhook_retries(limit=int(limit))

    execute = __call__


class SyncAutomationMemberActivationCommand:
    """Wave 1 skeleton that delegates to ``domains.automation_conversion.sync_member_activation``."""

    def __call__(
        self,
        *,
        external_contact_id: str = "",
        phone: str = "",
        operator_id: str = "system",
    ) -> dict[str, Any]:
        from ...domains.automation_conversion import sync_member_activation

        return sync_member_activation(
            external_contact_id=str(external_contact_id or ""),
            phone=str(phone or ""),
            operator_id=str(operator_id or "system"),
        )

    execute = __call__


class ApplyActivationWebhookCommand:
    """Wave 1 skeleton that delegates to ``domains.marketing_automation.apply_activation_webhook`` and syncs activation projection."""

    def __call__(
        self,
        *,
        mobile: str,
        activated_at: str = "",
        operator: str = "",
        source: str = "",
    ) -> dict[str, Any]:
        from ...domains.marketing_automation import apply_activation_webhook

        result = apply_activation_webhook(
            mobile=str(mobile or "").strip(),
            activated_at=str(activated_at or "").strip(),
            operator=str(operator or "").strip(),
            source=str(source or "").strip(),
        )
        SyncAutomationMemberActivationCommand()(
            external_contact_id=str((result.get("customer") or {}).get("external_userid") or "").strip(),
            phone=str(mobile or "").strip(),
            operator_id=str(operator or "").strip() or "activation_webhook",
        )
        return result

    execute = __call__


__all__ = [
    "ApplyActivationWebhookCommand",
    "GetSignupConversionBatchQuery",
    "ListSignupConversionBatchesQuery",
    "ListOutboundWebhookDeliveriesQuery",
    "RunDueOutboundWebhookRetriesCommand",
    "RetryOutboundWebhookDeliveryCommand",
    "SyncAutomationMemberActivationCommand",
]
