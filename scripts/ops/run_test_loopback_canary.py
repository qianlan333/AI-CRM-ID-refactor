#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Request

try:
    from scripts.script_runtime import ensure_repo_root_on_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.script_runtime import ensure_repo_root_on_path

ensure_repo_root_on_path()

from aicrm_next.platform_foundation.execution_runtime.cutover import (  # noqa: E402
    RuntimeGenerationRepository,
)
from aicrm_next.platform_foundation.execution_runtime.repository import (  # noqa: E402
    normalize_runtime_database_url,
    open_runtime_connection,
)
from aicrm_next.platform_foundation.execution_runtime.validation import (  # noqa: E402
    TERMINAL_JOB_STATUSES,
    record_external_effect_evidence,
    test_loopback_receipt_evidence,
)
from aicrm_next.platform_foundation.auth_platform.webhook_hmac import (  # noqa: E402
    runtime_outbound_webhook_signer_ready,
)
from aicrm_next.platform_foundation.external_effects.repo import (  # noqa: E402
    SQLAlchemyExternalEffectRepository,
)
from aicrm_next.platform_foundation.external_effects.service import (  # noqa: E402
    ExternalEffectService,
)
from aicrm_next.platform_foundation.external_effects.test_receiver import (  # noqa: E402
    SCENARIOS,
    create_loopback_job,
    test_receiver_enabled,
)
from aicrm_next.shared.release import current_release_sha  # noqa: E402
from aicrm_next.shared.runtime import raw_database_url  # noqa: E402
from aicrm_next.shared.runtime_settings import runtime_bool  # noqa: E402


AUTHORIZATION_ENV = "AICRM_TEST_LOOPBACK_CANARY_AUTHORIZED"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
SUCCESS_SCENARIOS = tuple(
    name for name, config in SCENARIOS.items() if int(config["default_response_status"]) == 200
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan one durable same-origin loopback and attest its signed receipt.",
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--scenario", choices=SUCCESS_SCENARIOS, default=SUCCESS_SCENARIOS[0])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--expected-policy-version", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirmation", default="")
    return parser.parse_args(argv)


def _confirmation(run_id: str, generation: int) -> str:
    return f"RUN_TEST_LOOPBACK_{run_id}_{generation}"


def _request_for_base_url(base_url: str) -> Request:
    parsed = urlsplit(str(base_url or "").strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("base_url must be an origin-only HTTPS URL")
    try:
        port = int(parsed.port or 443)
    except ValueError as exc:
        raise ValueError("base_url port is invalid") from exc
    host = str(parsed.netloc)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/admin/external-effects/test-loopback/jobs",
        "raw_path": b"/api/admin/external-effects/test-loopback/jobs",
        "query_string": b"",
        "headers": [(b"host", host.encode("ascii"))],
        "client": ("127.0.0.1", 1),
        "server": (str(parsed.hostname), port),
    }
    return Request(scope)


def _wait_for_result(
    repository: SQLAlchemyExternalEffectRepository,
    job_id: int,
    *,
    timeout_seconds: int,
):
    deadline = time.monotonic() + max(1, int(timeout_seconds or 120))
    while True:
        job = repository.get_job(job_id)
        if job is None:
            raise RuntimeError("loopback job disappeared")
        attempts = repository.list_attempts(job_id)
        exhausted = job.status == "failed_retryable" and job.attempt_count >= job.max_attempts
        if job.status in TERMINAL_JOB_STATUSES or exhausted:
            return job, attempts
        if time.monotonic() >= deadline:
            return job, attempts
        time.sleep(0.5)


def _validate_lane(database_url: str, policy_version: str) -> None:
    with open_runtime_connection(database_url) as connection:
        row = connection.execute(
            """
            SELECT enabled, max_in_flight, policy_version
            FROM queue_lane_policy
            WHERE lane = 'outbound_webhook'
            """
        ).fetchone()
    if (
        not row
        or not bool(row.get("enabled"))
        or int(row.get("max_in_flight") or 0) <= 0
        or str(row.get("policy_version") or "") != policy_version
    ):
        raise RuntimeError("outbound_webhook lane is not active for the exact policy")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_id = str(args.run_id or "").strip()
    release_sha = str(args.expected_release_sha or "").strip()
    policy_version = str(args.expected_policy_version or "").strip()
    actor = str(args.actor or "").strip()
    reason = str(args.reason or "").strip()
    _request_for_base_url(args.base_url)
    if RUN_ID.fullmatch(run_id) is None:
        raise ValueError("run_id has an invalid format")
    if FULL_SHA.fullmatch(release_sha) is None:
        raise ValueError("expected_release_sha must be a full SHA")
    if int(args.generation or 0) <= 0 or not policy_version or not actor or not reason:
        raise ValueError("generation, policy version, actor and reason are required")
    plan = {
        "ok": True,
        "applied": False,
        "run_id": run_id,
        "scenario": str(args.scenario),
        "release_sha": release_sha,
        "generation": int(args.generation),
        "policy_version": policy_version,
        "target_values_redacted": True,
        "real_external_call_executed": False,
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0
    if str(os.getenv(AUTHORIZATION_ENV) or "").strip() != "1":
        raise RuntimeError(f"{AUTHORIZATION_ENV}=1 is required")
    expected_confirmation = _confirmation(run_id, int(args.generation))
    if str(args.confirmation or "").strip() != expected_confirmation:
        raise RuntimeError(f"--confirmation must equal {expected_confirmation}")
    if current_release_sha() != release_sha:
        raise RuntimeError("active release SHA does not match the loopback request")

    database_url = normalize_runtime_database_url(raw_database_url())
    state = RuntimeGenerationRepository(database_url).read_state()
    if (
        state.active_generation != int(args.generation)
        or not state.claim_enabled
        or state.policy_version != policy_version
        or state.external_claim_scope not in {"test_loopback", "allowlisted"}
    ):
        raise RuntimeError("loopback requires the exact active test-capable generation")
    _validate_lane(database_url, policy_version)
    if (
        not test_receiver_enabled()
        or not runtime_bool("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE")
        or not runtime_outbound_webhook_signer_ready()
    ):
        raise RuntimeError("signed test receiver execution is not ready")

    repository = SQLAlchemyExternalEffectRepository()
    result = create_loopback_job(
        request=_request_for_base_url(args.base_url),
        service=ExternalEffectService(repository),
        scenario=str(args.scenario),
        response_status=200,
        max_attempts=1,
    )
    job_id = int(result["job"]["id"])
    job, attempts = _wait_for_result(
        repository,
        job_id,
        timeout_seconds=int(args.timeout_seconds),
    )
    evidence = record_external_effect_evidence(
        database_url,
        job=job,
        attempts=attempts,
        release_sha=release_sha,
        generation=int(args.generation),
        policy_version=policy_version,
        actor=actor,
        reason=reason,
        evidence_type="test_loopback",
        extra_evidence=test_loopback_receipt_evidence(repository, job),
    )
    ok = evidence["status"] == "passed"
    print(
        json.dumps(
            {
                **plan,
                "ok": ok,
                "applied": True,
                "job_id": job_id,
                "execution_id": str(job.execution_id or ""),
                "evidence": evidence,
                "real_external_call_executed": bool(evidence["side_effect_executed"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
