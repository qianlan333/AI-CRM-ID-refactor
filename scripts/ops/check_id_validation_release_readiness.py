from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.script_runtime import ensure_repo_root_on_path

ensure_repo_root_on_path()

from aicrm_next.platform_foundation.execution_runtime.read_model import ExecutionRuntimeReadModel


EXPECTED_WORKERS = Counter(
    {
        "external_effect": 4,
        "internal_event": 2,
        "internal_outbox": 2,
        "webhook_inbox": 1,
    }
)


def _request_json(url: str, *, timeout_seconds: float = 10.0) -> tuple[int, dict[str, str], dict[str, Any]]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed deploy URLs
        payload = json.loads(response.read().decode("utf-8"))
        return (
            int(response.status),
            {str(key).lower(): str(value).strip() for key, value in response.headers.items()},
            payload if isinstance(payload, dict) else {},
        )


def _http_ready(*, local_base_url: str, public_health_url: str, expected_sha: str) -> dict[str, Any]:
    local_status, local_headers, _ = _request_json(f"{local_base_url.rstrip('/')}/health")
    system_status, _, system_payload = _request_json(f"{local_base_url.rstrip('/')}/api/system/health")
    public_status, public_headers, _ = _request_json(public_health_url)
    release = dict(system_payload.get("components", {}).get("release", {}))
    migration = dict(system_payload.get("components", {}).get("migration", {}))
    valid = (
        local_status == 200
        and local_headers.get("x-aicrm-release-sha") == expected_sha
        and system_status == 200
        and system_payload.get("ok") is True
        and int(system_payload.get("http_status") or 0) == 200
        and release.get("release_sha") == expected_sha
        and release.get("exact_sha") is True
        and bool(migration.get("matches_head") or migration.get("forward_compatible"))
        and public_status == 200
        and public_headers.get("x-aicrm-release-sha") == expected_sha
    )
    if not valid:
        raise RuntimeError("ID validation HTTP or migration readiness is not exact")
    return {
        "local_release_sha": local_headers.get("x-aicrm-release-sha"),
        "public_release_sha": public_headers.get("x-aicrm-release-sha"),
        "migration_ready": True,
    }


def _workers_ready(*, expected_sha: str) -> dict[str, Any]:
    snapshot = ExecutionRuntimeReadModel().runtime_snapshot()
    if snapshot.get("ok") is not True:
        raise RuntimeError("execution runtime snapshot is unavailable")
    control = dict(snapshot.get("control") or {})
    expected_generation = int(control.get("active_generation") or 0)
    expected_rollout_mode = str(control.get("rollout_mode") or "")
    claim_enabled = bool(control.get("claim_enabled"))
    if claim_enabled != (expected_rollout_mode in {"canary", "execute"}):
        raise RuntimeError("execution runtime control claim gate and rollout mode are inconsistent")
    fresh_workers = [dict(worker) for worker in snapshot.get("workers") or () if bool(worker.get("fresh"))]
    conflicts = Counter()
    for worker in fresh_workers:
        if not bool(worker.get("listener_connected")):
            conflicts["listener_disconnected"] += 1
        if str(worker.get("release_sha") or "") != expected_sha or not bool(worker.get("release_matches")):
            conflicts["release_mismatch"] += 1
        if int(worker.get("generation") or 0) != expected_generation:
            conflicts["generation_mismatch"] += 1
    if conflicts:
        summary = ",".join(f"{key}={value}" for key, value in sorted(conflicts.items()))
        raise RuntimeError(f"a fresh execution runtime heartbeat conflicts with the live release ({summary})")
    counts = Counter(str(worker.get("queue_kind") or "") for worker in fresh_workers)
    if counts != EXPECTED_WORKERS:
        actual = ",".join(f"{key}={value}" for key, value in sorted(counts.items())) or "none"
        expected = ",".join(f"{key}={value}" for key, value in sorted(EXPECTED_WORKERS.items()))
        raise RuntimeError(f"execution runtime listener heartbeat set is not exact (actual:{actual}; expected:{expected})")
    worker_modes = Counter(str(worker.get("rollout_mode") or "") for worker in fresh_workers)
    expected_mode_sets = (
        (Counter({"canary": sum(EXPECTED_WORKERS.values())}),)
        if claim_enabled
        else (
            Counter({"standby": sum(EXPECTED_WORKERS.values())}),
            Counter({"canary": sum(EXPECTED_WORKERS.values())}),
        )
    )
    if worker_modes not in expected_mode_sets:
        actual = ",".join(f"{key or 'empty'}={value}" for key, value in sorted(worker_modes.items()))
        allowed = "canary" if claim_enabled else "uniform_canary_or_standby"
        raise RuntimeError(f"execution runtime worker capability heartbeat set is not exact (actual:{actual or 'none'}; allowed:{allowed})")
    return {
        "active_generation": expected_generation,
        "claim_enabled": claim_enabled,
        "rollout_mode": expected_rollout_mode,
        "worker_rollout_modes": dict(sorted(worker_modes.items())),
        "fresh_listener_count": sum(counts.values()),
        "worker_counts": dict(sorted(counts.items())),
    }


def check_release_readiness(
    *,
    local_base_url: str,
    public_health_url: str,
    expected_sha: str,
    attempts: int = 10,
    retry_seconds: float = 1.0,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            http = _http_ready(
                local_base_url=local_base_url,
                public_health_url=public_health_url,
                expected_sha=expected_sha,
            )
            workers = _workers_ready(expected_sha=expected_sha)
            return {
                "ok": True,
                "read_only": True,
                "release_sha": expected_sha,
                "attempt": attempt,
                "http": http,
                "runtime": workers,
                "real_external_call_executed": False,
            }
        except (RuntimeError, OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt < max(1, attempts):
                time.sleep(max(0.0, retry_seconds))
    failure_reason = str(last_error or "unknown readiness error").strip()
    raise RuntimeError(f"ID validation release readiness failed: {failure_reason}") from last_error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify exact ID validation Web, DB, and queue runtime readiness.")
    parser.add_argument("--local-base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--public-health-url", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--attempts", type=int, default=10)
    parser.add_argument("--retry-seconds", type=float, default=1.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = check_release_readiness(
            local_base_url=args.local_base_url,
            public_health_url=args.public_health_url,
            expected_sha=args.expected_sha,
            attempts=args.attempts,
            retry_seconds=args.retry_seconds,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
