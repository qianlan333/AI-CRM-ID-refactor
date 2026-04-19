from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


@dataclass(slots=True)
class CustomerPulseDetailQueryDTO:
    external_userid: str
    access_context: dict[str, Any] | None = None


class GetCustomerPulseDetailQuery:
    """Wave 1 skeleton that delegates to ``domains.customer_pulse`` read adapters."""

    def __call__(self, dto: CustomerPulseDetailQueryDTO) -> dict[str, Any]:
        from ...customer_center.pulse_service import build_customer_pulse
        from ...domains.customer_pulse import (
            build_customer_pulse_customer_detail_payload,
            is_customer_pulse_inbox_enabled,
            refresh_customer_pulse_cards,
        )
        from ...domains.customer_pulse.access import (
            assert_customer_pulse_request_context,
            assert_customer_pulse_widget_view,
            resolve_customer_pulse_read_scope,
        )

        external_userid = _normalized_text(dto.external_userid)
        if not external_userid:
            raise LookupError("customer not found")

        access_context = dict(dto.access_context or {})
        assert_customer_pulse_request_context(access_context)

        if not is_customer_pulse_inbox_enabled(access_context=access_context):
            return {
                "external_userid": external_userid,
                "pulse": build_customer_pulse(external_userid),
                "customer_pulse": build_customer_pulse_customer_detail_payload(
                    external_userid,
                    tenant_context=access_context,
                ),
            }

        assert_customer_pulse_widget_view(access_context)
        read_scope = resolve_customer_pulse_read_scope(access_context=access_context)
        customer_pulse = build_customer_pulse_customer_detail_payload(
            external_userid,
            track_metrics=True,
            metric_source="customer_profile_widget_api",
            tenant_context=read_scope.get("tenant_context"),
            tenant_key=_normalized_text(read_scope.get("tenant_key")),
            allowed_owner_userids=read_scope.get("allowed_owner_userids") or [],
        )
        if customer_pulse.get("enabled") and not customer_pulse.get("card"):
            refresh_customer_pulse_cards(
                limit=1,
                operator=_normalized_text(read_scope.get("operator")) or "customer_profile_page",
                external_userids=[external_userid],
                tenant_context=read_scope.get("tenant_context"),
                tenant_key=_normalized_text(read_scope.get("tenant_key")),
                allowed_owner_userids=read_scope.get("allowed_owner_userids") or [],
            )
            customer_pulse = build_customer_pulse_customer_detail_payload(
                external_userid,
                track_metrics=True,
                metric_source="customer_profile_widget_api",
                tenant_context=read_scope.get("tenant_context"),
                tenant_key=_normalized_text(read_scope.get("tenant_key")),
                allowed_owner_userids=read_scope.get("allowed_owner_userids") or [],
            )

        return {
            "external_userid": external_userid,
            "pulse": build_customer_pulse(external_userid),
            "customer_pulse": customer_pulse,
        }

    execute = __call__


__all__ = [
    "CustomerPulseDetailQueryDTO",
    "GetCustomerPulseDetailQuery",
]
