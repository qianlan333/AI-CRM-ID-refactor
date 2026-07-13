from __future__ import annotations

from .ai_audience_ops import register_ai_audience_event_consumers
from .platform_foundation.internal_events import (
    InternalEventConsumerRegistry,
    register_payment_succeeded_consumers,
    register_refund_succeeded_consumers,
    register_shadow_event_consumers,
)


def build_internal_event_consumer_registry() -> InternalEventConsumerRegistry:
    registry = InternalEventConsumerRegistry()
    register_payment_succeeded_consumers(registry)
    register_refund_succeeded_consumers(registry)
    register_shadow_event_consumers(registry)
    register_ai_audience_event_consumers(registry)
    return registry


__all__ = ["build_internal_event_consumer_registry"]
