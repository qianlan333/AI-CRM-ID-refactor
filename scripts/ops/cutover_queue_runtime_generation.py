#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Sequence

try:
    from scripts.script_runtime import ensure_repo_root_on_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path

ensure_repo_root_on_path()

from aicrm_next.platform_foundation.execution_runtime.cutover import (
    CANONICAL_RUNTIME_SERVICES,
    QueueRuntimeCutoverCoordinator,
    QueueRuntimeCutoverRequest,
    RuntimeGenerationRepository,
)


RUNTIME_GENERATION_ENV = Path("/home/ubuntu/.aicrm-queue-runtime-generation.env")
AUTHORIZATION_ENV = "AICRM_QUEUE_CUTOVER_AUTHORIZED"


def _run(command: Sequence[str], *, check: bool = True, capture_output: bool = False):
    return subprocess.run(
        [str(item) for item in command],
        check=check,
        capture_output=capture_output,
        text=True,
    )


class SystemdQueueRuntimeLifecycle:
    """Operate only the three canonical PR-2 services and explicit old owners."""

    def stage_target_generation(self, generation: int) -> None:
        payload = (
            f"AICRM_QUEUE_WORKER_GENERATION={int(generation)}\n"
            "AICRM_QUEUE_RUNTIME_EXECUTE=1\n"
            "AICRM_QUEUE_RUNTIME_TEST_ONLY=1\n"
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(payload)
            staged = Path(handle.name)
        try:
            _run(("sudo", "install", "-m", "0600", str(staged), str(RUNTIME_GENERATION_ENV)))
        finally:
            staged.unlink(missing_ok=True)

    def start_target_service(self, service: str) -> None:
        if service not in CANONICAL_RUNTIME_SERVICES:
            raise ValueError(f"non-canonical target runtime service: {service}")
        _run(("sudo", "systemctl", "enable", service))
        _run(("sudo", "systemctl", "restart", service))
        _run(("sudo", "systemctl", "is-active", "--quiet", service))

    def stop_legacy_triggers(self, units: Sequence[str]) -> None:
        for unit in units:
            normalized = str(unit or "").strip()
            if not normalized.endswith(".timer"):
                raise ValueError(f"legacy trigger must be a systemd timer: {normalized}")
            _run(("sudo", "systemctl", "stop", normalized))

    def stop_legacy_services(self, units: Sequence[str]) -> None:
        for unit in units:
            normalized = str(unit or "").strip()
            if not normalized.endswith(".service"):
                raise ValueError(f"legacy owner must be a systemd service: {normalized}")
            _run(("sudo", "systemctl", "stop", normalized))

    def wait_legacy_services_drained(self, units: Sequence[str], timeout_seconds: int) -> None:
        pending = {str(unit or "").strip() for unit in units}
        if any(not unit.endswith(".service") for unit in pending):
            raise ValueError("legacy drain targets must be systemd services")
        deadline = time.monotonic() + max(1, int(timeout_seconds or 600))
        while pending:
            inactive = set()
            for unit in pending:
                result = _run(
                    ("sudo", "systemctl", "is-active", unit),
                    check=False,
                    capture_output=True,
                )
                state = str(result.stdout or "").strip().lower()
                if result.returncode == 4 or state == "unknown":
                    raise RuntimeError(f"legacy queue owner unit does not exist: {unit}")
                if state in {"inactive", "failed"}:
                    inactive.add(unit)
            pending -= inactive
            if not pending:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(f"legacy queue owners did not drain: {sorted(pending)}")
            time.sleep(1)

    def retire_legacy_units(self, units: Sequence[str]) -> None:
        for unit in units:
            normalized = str(unit or "").strip()
            _run(("sudo", "systemctl", "disable", normalized))
            enabled = _run(
                ("sudo", "systemctl", "is-enabled", normalized),
                check=False,
                capture_output=True,
            )
            if str(enabled.stdout or "").strip().lower() == "enabled":
                raise RuntimeError(f"legacy queue owner remained enabled: {normalized}")
            _run(("sudo", "systemctl", "reset-failed", normalized), check=False)


def _parse_legacy_timer(value: str) -> tuple[str, str]:
    timer, separator, service = str(value or "").strip().partition(":")
    if separator != ":" or not timer.endswith(".timer") or not service.endswith(".service"):
        raise argparse.ArgumentTypeError("--legacy-timer must be TIMER.service-pair as TIMER.timer:SERVICE.service")
    return timer, service


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Atomically cut queue ownership to a numeric PostgreSQL generation.",
    )
    parser.add_argument("--expected-generation", type=int, required=True)
    parser.add_argument("--target-generation", type=int, required=True)
    parser.add_argument("--expected-policy-version", required=True)
    parser.add_argument("--lane", action="append", default=[], required=True)
    parser.add_argument("--legacy-timer", action="append", type=_parse_legacy_timer, default=[])
    parser.add_argument("--legacy-service", action="append", default=[])
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--readiness-timeout-seconds", type=int, default=60)
    parser.add_argument("--drain-timeout-seconds", type=int, default=600)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirmation", default="")
    return parser.parse_args(argv)


def _request(args: argparse.Namespace) -> QueueRuntimeCutoverRequest:
    pairs = list(args.legacy_timer or [])
    return QueueRuntimeCutoverRequest(
        expected_generation=int(args.expected_generation),
        target_generation=int(args.target_generation),
        expected_policy_version=str(args.expected_policy_version),
        lanes=tuple(str(lane) for lane in args.lane),
        actor=str(args.actor),
        reason=str(args.reason),
        legacy_triggers=tuple(timer for timer, _service in pairs),
        legacy_services=tuple(service for _timer, service in pairs),
        legacy_persistent_services=tuple(str(service) for service in args.legacy_service),
        readiness_timeout_seconds=int(args.readiness_timeout_seconds),
        drain_timeout_seconds=int(args.drain_timeout_seconds),
    )


def _plan(request: QueueRuntimeCutoverRequest) -> dict[str, object]:
    return {
        "ok": True,
        "applied": False,
        "expected_generation": request.expected_generation,
        "target_generation": request.target_generation,
        "policy_version": request.expected_policy_version,
        "lanes": list(request.lanes),
        "target_services": list(CANONICAL_RUNTIME_SERVICES),
        "legacy_triggers": list(request.legacy_triggers),
        "legacy_services": list(request.legacy_services),
        "legacy_persistent_services": list(request.legacy_persistent_services),
        "claim_gate_change": "not_applied",
        "real_external_call_executed": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    request = _request(args)
    if not args.apply:
        print(json.dumps(_plan(request), ensure_ascii=False, sort_keys=True))
        return 0
    confirmation = f"ACTIVATE_QUEUE_GENERATION_{request.target_generation}"
    if str(os.getenv(AUTHORIZATION_ENV) or "").strip() != "1":
        raise RuntimeError(f"{AUTHORIZATION_ENV}=1 is required for generation activation")
    if str(args.confirmation or "").strip() != confirmation:
        raise RuntimeError(f"--confirmation must equal {confirmation}")
    activation = QueueRuntimeCutoverCoordinator(
        repository=RuntimeGenerationRepository(),
        lifecycle=SystemdQueueRuntimeLifecycle(),
    ).activate(request)
    print(
        json.dumps(
            {
                "ok": True,
                "applied": True,
                "before_generation": activation.before.active_generation,
                "active_generation": activation.after.active_generation,
                "claim_enabled": activation.after.claim_enabled,
                "rollout_mode": activation.after.rollout_mode,
                "activated_lanes": list(activation.activated_lanes),
                "real_external_call_executed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
