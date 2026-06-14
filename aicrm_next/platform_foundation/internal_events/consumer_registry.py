from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .models import InternalEvent, InternalEventConsumerResult, InternalEventConsumerType, InternalEventConsumerRun

InternalEventConsumerHandler = Callable[[InternalEvent, InternalEventConsumerRun], InternalEventConsumerResult]


@dataclass(frozen=True)
class RegisteredInternalEventConsumer:
    event_type: str
    consumer_name: str
    consumer_type: InternalEventConsumerType = "projection"
    handler: InternalEventConsumerHandler | None = None
    max_attempts: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "consumer_name": self.consumer_name,
            "consumer_type": self.consumer_type,
            "max_attempts": self.max_attempts,
            "handler_registered": self.handler is not None,
        }


class InternalEventConsumerRegistry:
    def __init__(self) -> None:
        self._consumers: dict[str, list[RegisteredInternalEventConsumer]] = defaultdict(list)

    def register(
        self,
        event_type: str,
        consumer_name: str,
        handler: InternalEventConsumerHandler,
        *,
        consumer_type: InternalEventConsumerType = "projection",
        max_attempts: int = 5,
    ) -> None:
        event_type = str(event_type or "").strip()
        consumer_name = str(consumer_name or "").strip()
        if not event_type:
            raise ValueError("event_type is required")
        if not consumer_name:
            raise ValueError("consumer_name is required")
        existing = [item for item in self._consumers[event_type] if item.consumer_name != consumer_name]
        existing.append(
            RegisteredInternalEventConsumer(
                event_type=event_type,
                consumer_name=consumer_name,
                consumer_type=consumer_type,
                handler=handler,
                max_attempts=max(1, int(max_attempts or 5)),
            )
        )
        self._consumers[event_type] = existing

    def list_for_event_type(self, event_type: str) -> list[RegisteredInternalEventConsumer]:
        return list(self._consumers.get(str(event_type or "").strip(), []))

    def get_handler(self, event_type: str, consumer_name: str) -> InternalEventConsumerHandler | None:
        for consumer in self.list_for_event_type(event_type):
            if consumer.consumer_name == str(consumer_name or "").strip():
                return consumer.handler
        return None

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {event_type: [consumer.to_dict() for consumer in consumers] for event_type, consumers in self._consumers.items()}

    def clear(self) -> None:
        self._consumers.clear()


DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY = InternalEventConsumerRegistry()
