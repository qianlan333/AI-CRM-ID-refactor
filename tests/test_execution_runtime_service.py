from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from aicrm_next.platform_foundation.execution_runtime.lanes import QueueLane
from aicrm_next.platform_foundation.execution_runtime.repository import RuntimeClaim
from aicrm_next.platform_foundation.execution_runtime.service import QueueRuntimeService


class FakeListener:
    def __init__(self) -> None:
        self.connected = False
        self.closed = threading.Event()

    def connect(self) -> None:
        self.connected = True

    def wait(self, *, timeout_seconds: float):
        self.closed.wait(timeout=min(timeout_seconds, 0.05))
        return None

    def close(self) -> None:
        self.connected = False
        self.closed.set()


class FakeRepository:
    def __init__(self, *, stop_event: threading.Event) -> None:
        self.stop_event = stop_event
        self.claim_count = 0
        self.renew_count = 0
        self.heartbeats: list[dict] = []

    def claim_external_effect_one(self, **kwargs):
        self.claim_count += 1
        if self.claim_count > 1:
            return None
        return RuntimeClaim(
            queue_kind="external_effect",
            item_id=42,
            execution_id="exe_42",
            lane=str(kwargs["lane"]),
            lease_token="lease-42",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
            worker_generation=int(kwargs["generation"]),
            payload={"id": 42},
        )

    def renew_lease(self, **_kwargs) -> bool:
        self.renew_count += 1
        return True

    def next_due_at(self, **_kwargs):
        return None

    def heartbeat_worker(self, **kwargs) -> None:
        self.heartbeats.append(dict(kwargs))


def test_service_dispatches_claimed_row_and_publishes_worker_heartbeat() -> None:
    stop = threading.Event()
    repository = FakeRepository(stop_event=stop)
    handled: list[RuntimeClaim] = []

    def handle(claim: RuntimeClaim) -> bool:
        handled.append(claim)
        stop.set()
        return True

    service = QueueRuntimeService(
        queue_kind="external_effect",
        lanes=(QueueLane("wecom_media", 1, rollout_mode="canary"),),
        generation=7,
        handler=handle,
        repository=repository,
        listener_factory=FakeListener,
        heartbeat_seconds=0.01,
        fallback_seconds=0.05,
        test_only=True,
        claimless=False,
    )

    result = service.run(stop_event=stop)

    assert result.ok is True
    assert [claim.item_id for claim in handled] == [42]
    assert repository.claim_count == 1
    assert repository.heartbeats
    assert repository.heartbeats[0]["generation"] == 7
    assert repository.heartbeats[0]["queue_kind"] == "external_effect"


def test_service_rejects_unknown_queue_kind() -> None:
    stop = threading.Event()
    repository = FakeRepository(stop_event=stop)

    try:
        QueueRuntimeService(
            queue_kind="unknown",
            lanes=(QueueLane("wecom_media", 1),),
            generation=1,
            handler=lambda _claim: True,
            repository=repository,
            listener_factory=FakeListener,
        )
    except ValueError as exc:
        assert str(exc) == "unsupported queue kind"
    else:  # pragma: no cover - defensive contract
        raise AssertionError("unsupported queue kind should fail closed")
