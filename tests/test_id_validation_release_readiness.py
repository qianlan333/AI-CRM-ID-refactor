from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from scripts.ops import check_id_validation_release_readiness as readiness


RELEASE_SHA = "a" * 40


def _system_payload(*, migration_ready: bool = True) -> dict[str, Any]:
    return {
        "ok": True,
        "http_status": 200,
        "components": {
            "release": {"release_sha": RELEASE_SHA, "exact_sha": True},
            "migration": {"matches_head": migration_ready, "forward_compatible": False},
        },
    }


def _worker(queue_kind: str, *, generation: int = 0, release_sha: str = RELEASE_SHA) -> dict[str, Any]:
    return {
        "queue_kind": queue_kind,
        "generation": generation,
        "release_sha": release_sha,
        "rollout_mode": "standby",
        "listener_connected": True,
        "fresh": True,
        "release_matches": release_sha == RELEASE_SHA,
    }


def _snapshot(*, workers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    worker_items = workers or [
        *[_worker("external_effect") for _ in range(4)],
        *[_worker("internal_event") for _ in range(2)],
        *[_worker("internal_outbox") for _ in range(2)],
        _worker("webhook_inbox"),
    ]
    return {
        "ok": True,
        "control": {"active_generation": 0, "claim_enabled": False, "rollout_mode": "standby"},
        "workers": worker_items,
    }


def test_exact_http_migration_and_nine_listener_heartbeats_are_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def request(url: str, *, timeout_seconds: float = 10.0):
        del timeout_seconds
        if url.endswith("/api/system/health"):
            return 200, {}, _system_payload()
        return 200, {"x-aicrm-release-sha": RELEASE_SHA}, {"ok": True}

    class ReadModel:
        def runtime_snapshot(self) -> dict[str, Any]:
            return _snapshot()

    monkeypatch.setattr(readiness, "_request_json", request)
    monkeypatch.setattr(readiness, "ExecutionRuntimeReadModel", ReadModel)

    result = readiness.check_release_readiness(
        local_base_url="http://127.0.0.1:5001",
        public_health_url="https://id-dev.example/health",
        expected_sha=RELEASE_SHA,
        attempts=1,
    )

    assert result["ok"] is True
    assert result["runtime"]["fresh_listener_count"] == 9
    assert Counter(result["runtime"]["worker_counts"]) == readiness.EXPECTED_WORKERS


def test_migration_mismatch_blocks_provenance_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    def request(url: str, *, timeout_seconds: float = 10.0):
        del timeout_seconds
        if url.endswith("/api/system/health"):
            return 200, {}, _system_payload(migration_ready=False)
        return 200, {"x-aicrm-release-sha": RELEASE_SHA}, {"ok": True}

    monkeypatch.setattr(readiness, "_request_json", request)

    with pytest.raises(RuntimeError, match="readiness failed"):
        readiness.check_release_readiness(
            local_base_url="http://127.0.0.1:5001",
            public_health_url="https://id-dev.example/health",
            expected_sha=RELEASE_SHA,
            attempts=1,
        )


@pytest.mark.parametrize(
    "workers",
    (
        [_worker("external_effect")],
        [
            *[_worker("external_effect") for _ in range(4)],
            *[_worker("internal_event") for _ in range(2)],
            *[_worker("internal_outbox") for _ in range(2)],
            _worker("webhook_inbox", release_sha="b" * 40),
        ],
    ),
)
def test_missing_or_wrong_release_heartbeat_blocks_recovery(
    monkeypatch: pytest.MonkeyPatch, workers: list[dict[str, Any]]
) -> None:
    class ReadModel:
        def runtime_snapshot(self) -> dict[str, Any]:
            return _snapshot(workers=workers)

    monkeypatch.setattr(readiness, "ExecutionRuntimeReadModel", ReadModel)

    with pytest.raises(RuntimeError, match="heartbeat (set is not exact|conflicts)"):
        readiness._workers_ready(expected_sha=RELEASE_SHA)


def test_readiness_retries_transient_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def http_ready(**_kwargs: str) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient")
        return {"migration_ready": True}

    monkeypatch.setattr(readiness, "_http_ready", http_ready)
    monkeypatch.setattr(readiness, "_workers_ready", lambda **_kwargs: {"fresh_listener_count": 9})
    monkeypatch.setattr(readiness.time, "sleep", lambda _seconds: None)

    result = readiness.check_release_readiness(
        local_base_url="http://127.0.0.1:5001",
        public_health_url="https://id-dev.example/health",
        expected_sha=RELEASE_SHA,
        attempts=2,
    )

    assert attempts == 2
    assert result["attempt"] == 2
