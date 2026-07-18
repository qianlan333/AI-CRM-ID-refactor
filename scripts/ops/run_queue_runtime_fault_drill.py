#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
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

from aicrm_next.platform_foundation.execution_runtime.cutover import (  # noqa: E402
    RuntimeGenerationRepository,
)
from aicrm_next.platform_foundation.execution_runtime.read_model import (  # noqa: E402
    ExecutionRuntimeReadModel,
)
from aicrm_next.platform_foundation.execution_runtime.repository import (  # noqa: E402
    normalize_runtime_database_url,
    open_runtime_connection,
)
from aicrm_next.platform_foundation.execution_runtime.validation import (  # noqa: E402
    record_fault_evidence,
)
from aicrm_next.shared.release import current_release_sha  # noqa: E402
from aicrm_next.shared.runtime import raw_database_url  # noqa: E402


AUTHORIZATION_ENV = "AICRM_QUEUE_FAULT_DRILL_AUTHORIZED"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
ACTIONS = ("listener_reconnect", "worker_restart", "database_reconnect")
EXPECTED_WORKERS = {
    "external_effect": 4,
    "internal_event": 2,
    "internal_outbox": 2,
    "webhook_inbox": 1,
}
EXTERNAL_RUNTIME_SERVICE = "aicrm-external-queue-runtime.service"
POSTGRES_SERVICE = "postgresql.service"
LOCAL_HEALTH_URL = "http://127.0.0.1:5001/health"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one fail-closed queue-runtime recovery drill and persist evidence.",
    )
    parser.add_argument("--action", choices=ACTIONS, required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--expected-policy-version", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirmation", default="")
    return parser.parse_args(argv)


def _confirmation(action: str, release_sha: str, generation: int) -> str:
    return f"RUN_QUEUE_FAULT_{action.upper()}_{release_sha}_{generation}"


def _worker_proof(
    database_url: str,
    *,
    release_sha: str,
    generation: int,
    policy_version: str,
) -> dict[str, Any]:
    snapshot = ExecutionRuntimeReadModel(database_url).runtime_snapshot()
    control = dict(snapshot.get("control") or {})
    workers = [dict(worker) for worker in snapshot.get("workers") or () if worker.get("fresh")]
    counts = Counter(str(worker.get("queue_kind") or "") for worker in workers)
    conflicts = [
        worker
        for worker in workers
        if (
            not bool(worker.get("listener_connected"))
            or str(worker.get("release_sha") or "") != release_sha
            or not bool(worker.get("release_matches"))
            or int(worker.get("generation") or 0) != generation
        )
    ]
    ok = bool(
        snapshot.get("ok") is True
        and int(control.get("active_generation") or 0) == generation
        and str(control.get("policy_version") or "") == policy_version
        and str(control.get("external_claim_scope") or "") == "allowlisted"
        and dict(counts) == EXPECTED_WORKERS
        and not conflicts
    )
    return {
        "ok": ok,
        "fresh_listener_count": sum(counts.values()),
        "worker_counts": dict(sorted(counts.items())),
        "worker_conflict_count": len(conflicts),
    }


def _wait_for_worker_proof(
    database_url: str,
    *,
    release_sha: str,
    generation: int,
    policy_version: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(1, int(timeout_seconds or 120))
    last: dict[str, Any] = {"ok": False}
    while time.monotonic() < deadline:
        try:
            last = _worker_proof(
                database_url,
                release_sha=release_sha,
                generation=generation,
                policy_version=policy_version,
            )
        except Exception:
            last = {"ok": False, "database_read_failed": True}
        if last.get("ok") is True:
            return last
        time.sleep(1)
    raise RuntimeError(f"worker listener proof did not recover: {last}")


def _listener_backend_count(database_url: str) -> int:
    with open_runtime_connection(database_url) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*)::BIGINT AS count
            FROM pg_stat_activity
            WHERE application_name = 'aicrm-queue-listener'
            """
        ).fetchone()
    return int((row or {}).get("count") or 0)


def _terminate_one_listener(database_url: str) -> dict[str, Any]:
    with open_runtime_connection(database_url) as connection:
        rows = connection.execute(
            """
            SELECT pid
            FROM pg_stat_activity
            WHERE application_name = 'aicrm-queue-listener'
              AND pid <> pg_backend_pid()
            ORDER BY backend_start, pid
            """
        ).fetchall()
        before_count = len(rows)
        if before_count < sum(EXPECTED_WORKERS.values()):
            raise RuntimeError("listener drill requires the exact healthy listener baseline")
        terminated = connection.execute(
            "SELECT pg_terminate_backend(%s) AS terminated",
            (int(rows[0]["pid"]),),
        ).fetchone()
    if not terminated or not bool(terminated.get("terminated")):
        raise RuntimeError("PostgreSQL did not terminate the selected listener backend")
    return {"backend_count_before": before_count, "backend_terminated": True}


def _wait_listener_backend_count(
    database_url: str,
    *,
    minimum: int,
    timeout_seconds: int,
) -> int:
    deadline = time.monotonic() + max(1, int(timeout_seconds or 120))
    last = 0
    while time.monotonic() < deadline:
        try:
            last = _listener_backend_count(database_url)
        except Exception:
            last = 0
        if last >= minimum:
            return last
        time.sleep(1)
    raise RuntimeError(f"listener backend count did not recover: {last}/{minimum}")


def _systemd_marker(service: str) -> int:
    result = subprocess.run(
        [
            "sudo",
            "-n",
            "systemctl",
            "show",
            service,
            "--property=ActiveEnterTimestampMonotonic",
            "--value",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return int(str(result.stdout or "0").strip() or 0)


def _restart_service(service: str) -> None:
    if service not in {EXTERNAL_RUNTIME_SERVICE, POSTGRES_SERVICE}:
        raise ValueError("service is outside the fault-drill allowlist")
    subprocess.run(
        ["sudo", "-n", "systemctl", "restart", service],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _local_web_ready(expected_sha: str) -> bool:
    request = urllib.request.Request(LOCAL_HEALTH_URL, method="GET")
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - fixed loopback URL
        return bool(
            int(response.status) == 200
            and str(response.headers.get("X-AICRM-Release-SHA") or "") == expected_sha
        )


def _validate_args(args: argparse.Namespace) -> tuple[str, str, str, str]:
    action = str(args.action or "").strip()
    release_sha = str(args.expected_release_sha or "").strip()
    policy_version = str(args.expected_policy_version or "").strip()
    actor = str(args.actor or "").strip()
    reason = str(args.reason or "").strip()
    if action not in ACTIONS:
        raise ValueError("unsupported fault action")
    if FULL_SHA.fullmatch(release_sha) is None:
        raise ValueError("expected_release_sha must be a full SHA")
    if int(args.generation or 0) <= 0 or not policy_version or not actor or not reason:
        raise ValueError("generation, policy version, actor and reason are required")
    return action, release_sha, policy_version, actor


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    action, release_sha, policy_version, actor = _validate_args(args)
    plan = {
        "ok": True,
        "applied": False,
        "action": action,
        "release_sha": release_sha,
        "generation": int(args.generation),
        "policy_version": policy_version,
        "claims_will_drain": action in {"worker_restart", "database_reconnect"},
        "target_values_redacted": True,
        "real_external_call_executed": False,
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0
    if str(os.getenv(AUTHORIZATION_ENV) or "").strip() != "1":
        raise RuntimeError(f"{AUTHORIZATION_ENV}=1 is required")
    expected_confirmation = _confirmation(action, release_sha, int(args.generation))
    if str(args.confirmation or "").strip() != expected_confirmation:
        raise RuntimeError(f"--confirmation must equal {expected_confirmation}")
    if current_release_sha() != release_sha:
        raise RuntimeError("active release SHA does not match the fault drill")

    database_url = normalize_runtime_database_url(raw_database_url())
    runtime = RuntimeGenerationRepository(database_url)
    state = runtime.read_state()
    if (
        state.active_generation != int(args.generation)
        or not state.claim_enabled
        or state.policy_version != policy_version
        or state.external_claim_scope != "allowlisted"
    ):
        raise RuntimeError("fault drill requires the exact active allowlisted generation")
    baseline = _wait_for_worker_proof(
        database_url,
        release_sha=release_sha,
        generation=int(args.generation),
        policy_version=policy_version,
        timeout_seconds=int(args.timeout_seconds),
    )
    if not _local_web_ready(release_sha):
        raise RuntimeError("local web release is not ready before the fault drill")

    evidence: dict[str, Any] = {
        "baseline_fresh_listener_count": int(baseline["fresh_listener_count"]),
        "claim_gate_drained": False,
        "claim_gate_resumed": False,
        "local_web_release_exact": False,
    }
    claims_disabled = False
    try:
        if action in {"worker_restart", "database_reconnect"}:
            runtime.disable_claims(
                expected_generation=int(args.generation),
                actor=actor,
                reason=f"fault drill drain: {str(args.reason).strip()}",
            )
            claims_disabled = True
            runtime.wait_claims_drained(timeout_seconds=int(args.timeout_seconds))
            evidence["claim_gate_drained"] = True
            evidence["active_claim_count_after_drain"] = runtime.active_claim_count()

        if action == "listener_reconnect":
            termination = _terminate_one_listener(database_url)
            evidence.update(termination)
            evidence["backend_count_after_recovery"] = _wait_listener_backend_count(
                database_url,
                minimum=int(termination["backend_count_before"]),
                timeout_seconds=int(args.timeout_seconds),
            )
        elif action == "worker_restart":
            before_marker = _systemd_marker(EXTERNAL_RUNTIME_SERVICE)
            _restart_service(EXTERNAL_RUNTIME_SERVICE)
            after_marker = _systemd_marker(EXTERNAL_RUNTIME_SERVICE)
            evidence["service_restart_marker_advanced"] = bool(
                before_marker > 0 and after_marker > before_marker
            )
            if not evidence["service_restart_marker_advanced"]:
                raise RuntimeError("external runtime systemd marker did not advance")
        else:
            before_marker = _systemd_marker(POSTGRES_SERVICE)
            _restart_service(POSTGRES_SERVICE)
            after_marker = _systemd_marker(POSTGRES_SERVICE)
            evidence["database_restart_marker_advanced"] = bool(
                before_marker > 0 and after_marker > before_marker
            )
            if not evidence["database_restart_marker_advanced"]:
                raise RuntimeError("PostgreSQL systemd marker did not advance")
            evidence["backend_count_after_recovery"] = _wait_listener_backend_count(
                database_url,
                minimum=sum(EXPECTED_WORKERS.values()),
                timeout_seconds=int(args.timeout_seconds),
            )

        recovered = _wait_for_worker_proof(
            database_url,
            release_sha=release_sha,
            generation=int(args.generation),
            policy_version=policy_version,
            timeout_seconds=int(args.timeout_seconds),
        )
        evidence["fresh_listener_count_after_recovery"] = int(
            recovered["fresh_listener_count"]
        )
        evidence["worker_conflict_count_after_recovery"] = int(
            recovered["worker_conflict_count"]
        )
        evidence["local_web_release_exact"] = _local_web_ready(release_sha)
        if not evidence["local_web_release_exact"]:
            raise RuntimeError("local web release did not recover after the fault drill")
        if claims_disabled:
            runtime.resume_claims(
                expected_generation=int(args.generation),
                expected_policy_version=policy_version,
                expected_scope="allowlisted",
                actor=actor,
                reason=f"fault drill recovery: {str(args.reason).strip()}",
            )
            evidence["claim_gate_resumed"] = True
        else:
            evidence["claim_gate_resumed"] = True
        passed = True
    except Exception as exc:
        evidence["failure_class"] = exc.__class__.__name__
        evidence["claim_gate_left_closed"] = bool(claims_disabled)
        passed = False

    recorded = record_fault_evidence(
        database_url,
        evidence_type=action,
        release_sha=release_sha,
        generation=int(args.generation),
        policy_version=policy_version,
        passed=passed,
        evidence=evidence,
        actor=actor,
        reason=str(args.reason).strip(),
    )
    print(
        json.dumps(
            {
                **plan,
                "ok": passed,
                "applied": True,
                "evidence": recorded,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
