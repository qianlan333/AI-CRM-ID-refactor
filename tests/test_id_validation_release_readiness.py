from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from scripts.ops import check_id_validation_release_readiness as readiness


RELEASE_SHA = "a" * 40
REPO_ROOT = Path(__file__).resolve().parents[1]


def _system_payload(*, migration_ready: bool = True) -> dict[str, Any]:
    return {
        "ok": True,
        "http_status": 200,
        "components": {
            "release": {"release_sha": RELEASE_SHA, "exact_sha": True},
            "migration": {"matches_head": migration_ready, "forward_compatible": False},
        },
    }


def _worker(
    queue_kind: str,
    *,
    generation: int = 0,
    release_sha: str = RELEASE_SHA,
    rollout_mode: str = "standby",
) -> dict[str, Any]:
    return {
        "queue_kind": queue_kind,
        "generation": generation,
        "release_sha": release_sha,
        "rollout_mode": rollout_mode,
        "listener_connected": True,
        "fresh": True,
        "release_matches": release_sha == RELEASE_SHA,
    }


def _snapshot(
    *,
    workers: list[dict[str, Any]] | None = None,
    generation: int = 0,
    claim_enabled: bool = False,
    rollout_mode: str = "standby",
) -> dict[str, Any]:
    worker_items = workers or [
        *[_worker("external_effect") for _ in range(4)],
        *[_worker("internal_event") for _ in range(2)],
        *[_worker("internal_outbox") for _ in range(2)],
        _worker("webhook_inbox"),
    ]
    return {
        "ok": True,
        "control": {
            "active_generation": generation,
            "claim_enabled": claim_enabled,
            "rollout_mode": rollout_mode,
        },
        "workers": worker_items,
    }


def test_direct_file_entrypoint_bootstraps_repo_root_from_arbitrary_cwd(tmp_path: Path) -> None:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/ops/check_id_validation_release_readiness.py"),
            "--help",
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Verify exact ID validation Web, DB, and queue runtime readiness" in result.stdout


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
def test_missing_or_wrong_release_heartbeat_blocks_recovery(monkeypatch: pytest.MonkeyPatch, workers: list[dict[str, Any]]) -> None:
    class ReadModel:
        def runtime_snapshot(self) -> dict[str, Any]:
            return _snapshot(workers=workers)

    monkeypatch.setattr(readiness, "ExecutionRuntimeReadModel", ReadModel)

    with pytest.raises(RuntimeError, match="heartbeat (set is not exact|conflicts)"):
        readiness._workers_ready(expected_sha=RELEASE_SHA)


def test_closed_database_gate_accepts_one_uniform_hot_canary_worker_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workers = [
        *[_worker("external_effect", generation=1, rollout_mode="canary") for _ in range(4)],
        *[_worker("internal_event", generation=1, rollout_mode="canary") for _ in range(2)],
        *[_worker("internal_outbox", generation=1, rollout_mode="canary") for _ in range(2)],
        _worker("webhook_inbox", generation=1, rollout_mode="canary"),
    ]

    class ReadModel:
        def runtime_snapshot(self) -> dict[str, Any]:
            return _snapshot(
                workers=workers,
                generation=1,
                claim_enabled=False,
                rollout_mode="standby",
            )

    monkeypatch.setattr(readiness, "ExecutionRuntimeReadModel", ReadModel)

    result = readiness._workers_ready(expected_sha=RELEASE_SHA)

    assert result["claim_enabled"] is False
    assert result["rollout_mode"] == "standby"
    assert result["worker_rollout_modes"] == {"canary": 9}


def test_open_database_gate_requires_every_worker_to_be_canary_capable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workers = [
        *[_worker("external_effect", generation=1, rollout_mode="canary") for _ in range(4)],
        *[_worker("internal_event", generation=1, rollout_mode="canary") for _ in range(2)],
        *[_worker("internal_outbox", generation=1, rollout_mode="canary") for _ in range(2)],
        _worker("webhook_inbox", generation=1, rollout_mode="standby"),
    ]

    class ReadModel:
        def runtime_snapshot(self) -> dict[str, Any]:
            return _snapshot(
                workers=workers,
                generation=1,
                claim_enabled=True,
                rollout_mode="canary",
            )

    monkeypatch.setattr(readiness, "ExecutionRuntimeReadModel", ReadModel)

    with pytest.raises(
        RuntimeError,
        match=r"worker capability heartbeat set is not exact .*allowed:canary",
    ):
        readiness._workers_ready(expected_sha=RELEASE_SHA)


def test_closed_database_gate_rejects_mixed_worker_capability_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workers = [
        *[_worker("external_effect", generation=1, rollout_mode="canary") for _ in range(4)],
        *[_worker("internal_event", generation=1, rollout_mode="canary") for _ in range(2)],
        *[_worker("internal_outbox", generation=1, rollout_mode="standby") for _ in range(2)],
        _worker("webhook_inbox", generation=1, rollout_mode="standby"),
    ]

    class ReadModel:
        def runtime_snapshot(self) -> dict[str, Any]:
            return _snapshot(
                workers=workers,
                generation=1,
                claim_enabled=False,
                rollout_mode="standby",
            )

    monkeypatch.setattr(readiness, "ExecutionRuntimeReadModel", ReadModel)

    with pytest.raises(
        RuntimeError,
        match=r"actual:canary=6,standby=3; allowed:uniform_canary_or_standby",
    ):
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


def test_final_readiness_error_preserves_sanitized_worker_count_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(readiness, "_http_ready", lambda **_kwargs: {"migration_ready": True})

    class ReadModel:
        def runtime_snapshot(self) -> dict[str, Any]:
            return _snapshot(workers=[_worker("external_effect")])

    monkeypatch.setattr(readiness, "ExecutionRuntimeReadModel", ReadModel)

    with pytest.raises(
        RuntimeError,
        match=(
            r"readiness failed: execution runtime listener heartbeat set is not exact "
            r"\(actual:external_effect=1; expected:external_effect=4,internal_event=2,"
            r"internal_outbox=2,webhook_inbox=1\)"
        ),
    ):
        readiness.check_release_readiness(
            local_base_url="http://127.0.0.1:5001",
            public_health_url="https://id-dev.example/health",
            expected_sha=RELEASE_SHA,
            attempts=1,
        )


def test_worker_conflict_diagnostic_exposes_only_conflict_classes() -> None:
    workers = [
        *[_worker("external_effect") for _ in range(4)],
        *[_worker("internal_event") for _ in range(2)],
        *[_worker("internal_outbox") for _ in range(2)],
        _worker("webhook_inbox"),
    ]
    workers[-1]["listener_connected"] = False
    workers[-1]["generation"] = 99

    class ReadModel:
        def runtime_snapshot(self) -> dict[str, Any]:
            return _snapshot(workers=workers)

    original = readiness.ExecutionRuntimeReadModel
    readiness.ExecutionRuntimeReadModel = ReadModel
    try:
        with pytest.raises(
            RuntimeError,
            match=r"generation_mismatch=1,listener_disconnected=1",
        ):
            readiness._workers_ready(expected_sha=RELEASE_SHA)
    finally:
        readiness.ExecutionRuntimeReadModel = original
