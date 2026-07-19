#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.script_runtime import ensure_repo_root_on_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.script_runtime import ensure_repo_root_on_path

ensure_repo_root_on_path()

from aicrm_next.channel_entry.application import (  # noqa: E402
    callback_config,
    resolve_channel_for_scene,
)
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
)
from aicrm_next.platform_foundation.external_effects.models import (  # noqa: E402
    WECOM_CONTACT_TAG_MARK,
    WECOM_EXTERNAL_CONTACT_DETAIL_FETCH,
    WECOM_WELCOME_MESSAGE_SEND,
)
from aicrm_next.platform_foundation.external_effects.repo import (  # noqa: E402
    SQLAlchemyExternalEffectRepository,
)
from aicrm_next.platform_foundation.external_effects.service import (  # noqa: E402
    ExternalEffectService,
)
from aicrm_next.platform_foundation.external_effects.wecom_canary_policy import (  # noqa: E402
    wecom_canary_job_gate_error,
)
from aicrm_next.shared.release import current_release_sha  # noqa: E402
from aicrm_next.shared.runtime import raw_database_url  # noqa: E402
from aicrm_next.shared.wecom_runtime import load_wecom_execution_config  # noqa: E402
from scripts.ops.configure_wecom_canary import load_canary_spec  # noqa: E402
from scripts.ops.import_wecom_canary_channel_asset import (  # noqa: E402
    load_channel_asset,
)


AUTHORIZATION_ENV = "AICRM_WECOM_CALLBACK_CANARY_ARM_AUTHORIZED"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
EXPECTED_ROUTE = "/wecom/external-contact/callback"
EXPECTED_EFFECTS = {
    "welcome": WECOM_WELCOME_MESSAGE_SEND,
    "entry_tag": WECOM_CONTACT_TAG_MARK,
    "identity_detail": WECOM_EXTERNAL_CONTACT_DETAIL_FETCH,
}
FAILED_INBOX_STATUSES = frozenset({"failed_retryable", "failed_terminal", "dead_letter", "ignored"})


class CallbackCanaryError(RuntimeError):
    """Stable error that does not include callback or provider payload values."""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Arm one exact real-time WeCom add-contact callback canary and authorize its durable jobs without making inline provider calls.")
    )
    parser.add_argument("--spec-file", required=True)
    parser.add_argument("--asset-file", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--expected-policy-version", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--inbox-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--provider-timeout-seconds", type=float, default=12.0)
    parser.add_argument("--result-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--maximum-event-age-seconds", type=float, default=12.0)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirmation", default="")
    return parser.parse_args(argv)


def _confirmation(generation: int) -> str:
    return f"ARM_WECOM_CALLBACK_CANARY_{int(generation)}"


def _utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            raise CallbackCanaryError("required canary timestamp is missing")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CallbackCanaryError("required canary timestamp is invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _provider_event_time(row: dict[str, Any]) -> datetime:
    payload = dict(row.get("payload_json") or {})
    try:
        return datetime.fromtimestamp(
            int(str(payload.get("CreateTime") or "0")),
            tz=timezone.utc,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise CallbackCanaryError("callback provider timestamp is invalid") from exc


def _assert_event_fresh(row: dict[str, Any], *, maximum_age_seconds: float) -> float:
    age = (datetime.now(timezone.utc) - _provider_event_time(row)).total_seconds()
    if age < -5.0 or age > max(1.0, min(float(maximum_age_seconds), 18.0)):
        raise CallbackCanaryError("callback is outside the welcome-code safety window")
    return age


def _runtime_preflight(
    database_url: str,
    *,
    generation: int,
    policy_version: str,
) -> None:
    state = RuntimeGenerationRepository(database_url).read_state()
    if (
        state.active_generation != int(generation)
        or not state.claim_enabled
        or state.policy_version != policy_version
        or state.external_claim_scope != "allowlisted"
        or state.rollout_mode != "canary"
    ):
        raise CallbackCanaryError("callback canary requires the exact active allowlisted generation")
    with open_runtime_connection(database_url) as connection:
        running = connection.execute("SELECT COUNT(*)::BIGINT AS count FROM queue_runtime_soak_run WHERE status = 'running'").fetchone()
    if int((running or {}).get("count") or 0):
        raise CallbackCanaryError("callback canary is forbidden while a soak is running")


def _assert_channel_asset(asset: dict[str, str], *, corp_id: str) -> dict[str, Any]:
    channel, match = resolve_channel_for_scene(
        scene_value=asset["scene_value"],
        corp_id=corp_id,
        persist_alias=False,
    )
    match_type = str((match or {}).get("match_type") or "")
    if not channel or not (match_type.startswith("qrcode_asset_") or match_type == "scene_alias"):
        raise CallbackCanaryError("dedicated callback scene does not resolve through the imported asset")
    exact = {
        "channel_code": asset["channel_code"],
        "owner_staff_id": asset["owner_userid"],
        "entry_tag_id": asset["tag_id"],
        "welcome_message": asset["welcome_message"],
        "status": "active",
    }
    if any(str(channel.get(key) or "").strip() != value for key, value in exact.items()):
        raise CallbackCanaryError("imported callback channel asset is not exact")
    return dict(channel)


def _baseline_inbox_id(database_url: str) -> int:
    with open_runtime_connection(database_url) as connection:
        row = connection.execute("SELECT COALESCE(MAX(id), 0)::BIGINT AS id FROM webhook_inbox").fetchone()
    return int((row or {}).get("id") or 0)


def _matching_callbacks(
    connection: Any,
    *,
    baseline_id: int,
    corp_id: str,
    external_userid: str,
    owner_userid: str,
    state: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, status, processing_summary_json, payload_json,
               received_at, started_at, execution_id, policy_version,
               duplicate_count, attempt_count, worker_generation,
               last_error_code
        FROM webhook_inbox
        WHERE id > %s
          AND provider = 'wecom'
          AND event_family = 'external_contact'
          AND route = %s
          AND event_type = 'change_external_contact'
          AND change_type = 'add_external_contact'
          AND corp_id = %s
          AND payload_json->>'ExternalUserID' = %s
          AND payload_json->>'UserID' = %s
          AND payload_json->>'State' = %s
          AND COALESCE(payload_json->>'WelcomeCode', '') <> ''
        ORDER BY id ASC
        LIMIT 2
        """,
        (
            int(baseline_id),
            EXPECTED_ROUTE,
            corp_id,
            external_userid,
            owner_userid,
            state,
        ),
    ).fetchall()
    return [dict(row) for row in rows]


def wait_for_callback(
    database_url: str,
    *,
    baseline_id: int,
    corp_id: str,
    external_userid: str,
    owner_userid: str,
    state: str,
    policy_version: str,
    timeout_seconds: float,
    maximum_event_age_seconds: float,
    connect: Callable[[str], Any] = open_runtime_connection,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    deadline = monotonic() + max(1.0, min(float(timeout_seconds), 1800.0))
    with connect(database_url) as connection:
        if hasattr(connection, "autocommit"):
            connection.autocommit = True
        while monotonic() < deadline:
            rows = _matching_callbacks(
                connection,
                baseline_id=baseline_id,
                corp_id=corp_id,
                external_userid=external_userid,
                owner_userid=owner_userid,
                state=state,
            )
            if len(rows) > 1:
                raise CallbackCanaryError("more than one matching callback arrived after the armed boundary")
            if rows:
                row = rows[0]
                if str(row.get("policy_version") or "") != policy_version:
                    raise CallbackCanaryError("callback policy version is not exact")
                _assert_event_fresh(
                    row,
                    maximum_age_seconds=maximum_event_age_seconds,
                )
                return row
            sleep(0.05)
    raise CallbackCanaryError("no matching callback arrived before the arm timeout")


def assert_single_callback(
    database_url: str,
    *,
    baseline_id: int,
    inbox_id: int,
    corp_id: str,
    external_userid: str,
    owner_userid: str,
    state: str,
    connect: Callable[[str], Any] = open_runtime_connection,
) -> dict[str, Any]:
    """Re-check the armed boundary immediately before authorization and pass."""

    with connect(database_url) as connection:
        if hasattr(connection, "autocommit"):
            connection.autocommit = True
        rows = _matching_callbacks(
            connection,
            baseline_id=baseline_id,
            corp_id=corp_id,
            external_userid=external_userid,
            owner_userid=owner_userid,
            state=state,
        )
    if len(rows) != 1 or int(rows[0].get("id") or 0) != int(inbox_id):
        raise CallbackCanaryError("armed boundary no longer contains exactly one matching callback")
    if int(rows[0].get("duplicate_count") or 0) != 0:
        raise CallbackCanaryError("armed callback was delivered more than once")
    return rows[0]


def wait_for_inbox_success(
    database_url: str,
    *,
    inbox_id: int,
    timeout_seconds: float,
    connect: Callable[[str], Any] = open_runtime_connection,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    deadline = monotonic() + max(1.0, min(float(timeout_seconds), 30.0))
    with connect(database_url) as connection:
        if hasattr(connection, "autocommit"):
            connection.autocommit = True
        while monotonic() < deadline:
            row = connection.execute(
                """
                SELECT id, status, processing_summary_json, payload_json,
                       received_at, started_at, execution_id, policy_version,
                       duplicate_count, attempt_count, worker_generation,
                       last_error_code
                FROM webhook_inbox WHERE id = %s
                """,
                (int(inbox_id),),
            ).fetchone()
            if not row:
                raise CallbackCanaryError("armed callback inbox row disappeared")
            result = dict(row)
            status = str(result.get("status") or "")
            if status == "succeeded":
                summary = result.get("processing_summary_json")
                if not isinstance(summary, dict) or summary.get("handled") is not True:
                    raise CallbackCanaryError("callback inbox succeeded without handled processing evidence")
                return result
            if status in FAILED_INBOX_STATUSES:
                raise CallbackCanaryError("callback inbox reached a failed state before job authorization")
            sleep(0.05)
    raise CallbackCanaryError("callback inbox did not finish inside the safety window")


def _assert_clean_worker_processing(inbox: dict[str, Any], *, generation: int) -> None:
    if (
        int(inbox.get("duplicate_count") or 0) != 0
        or int(inbox.get("attempt_count") or 0) != 0
        or not inbox.get("started_at")
        or int(inbox.get("worker_generation") or 0) != int(generation)
    ):
        raise CallbackCanaryError("callback must have one clean runtime claim with no retry or duplicate")


def _freeze_jobs(
    database_url: str,
    *,
    job_ids: list[int],
    event_log_id: int,
) -> None:
    if len(job_ids) != 3 or len(set(job_ids)) != 3 or any(job_id <= 0 for job_id in job_ids):
        raise CallbackCanaryError("callback did not produce exactly three durable jobs")
    if int(event_log_id or 0) <= 0:
        raise CallbackCanaryError("callback did not expose one durable relationship event")
    with open_runtime_connection(database_url) as connection:
        with connection.transaction():
            rows = connection.execute(
                """
                SELECT id, source_event_id, status, attempt_count,
                       provider_call_started_at, cancel_requested_at
                FROM external_effect_job
                WHERE id = ANY(%s)
                FOR UPDATE
                """,
                (job_ids,),
            ).fetchall()
            if {int(row["id"]) for row in rows} != set(job_ids):
                raise CallbackCanaryError("callback job links are incomplete")
            if any(str(row.get("source_event_id") or "") != str(int(event_log_id)) for row in rows):
                raise CallbackCanaryError("callback summary referenced a historical relationship job")
            if any(
                str(row.get("status") or "") not in {"planned", "approved", "queued", "blocked"}
                or int(row.get("attempt_count") or 0) != 0
                or row.get("provider_call_started_at") is not None
                or row.get("cancel_requested_at") is not None
                for row in rows
            ):
                raise CallbackCanaryError("one or more callback jobs crossed the provider boundary before authorization")
            updated = connection.execute(
                """
                UPDATE external_effect_job
                SET max_attempts = 1,
                    row_version = row_version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ANY(%s)
                  AND source_event_id = %s
                RETURNING id
                """,
                (job_ids, str(int(event_log_id))),
            ).fetchall()
            if {int(row["id"]) for row in updated} != set(job_ids):
                raise CallbackCanaryError("callback jobs could not be frozen to one attempt")


def _job_map(
    repository: SQLAlchemyExternalEffectRepository,
    *,
    job_ids: list[int],
    external_userid: str,
    owner_userid: str,
    asset: dict[str, str],
    policy_version: str,
) -> dict[str, Any]:
    by_effect: dict[str, Any] = {}
    for job_id in job_ids:
        job = repository.get_job(int(job_id))
        if job is None or job.effect_type not in set(EXPECTED_EFFECTS.values()):
            raise CallbackCanaryError("callback job type is not the expected closed set")
        if job.effect_type in by_effect:
            raise CallbackCanaryError("callback job type is duplicated")
        if (
            job.policy_version != policy_version
            or job.provider_call_started_at
            or job.attempt_count
            or job.side_effect_executed
            or job.cancel_requested_at
            or int(job.max_attempts) != 1
            or str(job.payload_json.get("execution_scope") or "")
        ):
            raise CallbackCanaryError("callback job is not at the exact pre-provider authorization boundary")
        gate_error = wecom_canary_job_gate_error(job, authorize_scope=True)
        if gate_error:
            raise CallbackCanaryError(f"callback job failed the final target gate ({gate_error})")
        by_effect[job.effect_type] = job
    if set(by_effect) != set(EXPECTED_EFFECTS.values()):
        raise CallbackCanaryError("callback job set is incomplete")

    welcome = by_effect[WECOM_WELCOME_MESSAGE_SEND]
    tag = by_effect[WECOM_CONTACT_TAG_MARK]
    detail = by_effect[WECOM_EXTERNAL_CONTACT_DETAIL_FETCH]
    if (
        str(welcome.payload_json.get("external_userid") or "") != external_userid
        or str(welcome.payload_json.get("follow_user_userid") or "") != owner_userid
        or str((welcome.payload_json.get("text") or {}).get("content") or "") != asset["welcome_message"]
        or str(welcome.payload_json.get("scene_value") or "") != asset["scene_value"]
        or not str(welcome.payload_json.get("welcome_code") or "")
        or bool(welcome.payload_json.get("attachments"))
    ):
        raise CallbackCanaryError("welcome job does not match the dedicated asset")
    if (
        str(tag.payload_json.get("external_userid") or "") != external_userid
        or str(tag.payload_json.get("follow_user_userid") or "") != owner_userid
        or list(tag.payload_json.get("add_tags") or []) != [asset["tag_id"]]
        or list(tag.payload_json.get("remove_tags") or [])
    ):
        raise CallbackCanaryError("tag job does not match the dedicated asset")
    if str(detail.payload_json.get("external_userid") or "") != external_userid or str(detail.payload_json.get("owner_userid") or "") != owner_userid:
        raise CallbackCanaryError("detail job does not match the dedicated target")
    return {
        "welcome": welcome,
        "entry_tag": tag,
        "identity_detail": detail,
    }


def _authorize_job(
    service: ExternalEffectService,
    job: Any,
    *,
    actor: str,
    reason: str,
) -> Any:
    authorized = service.authorize_allowlisted_canary(
        int(job.id),
        actor=actor,
        reason=reason,
        expected_version=int(job.row_version),
    )
    if authorized is None:
        raise CallbackCanaryError("callback job CAS authorization failed")
    return authorized


def wait_for_provider_boundary(
    repository: SQLAlchemyExternalEffectRepository,
    *,
    job_id: int,
    timeout_seconds: float,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    deadline = monotonic() + max(1.0, min(float(timeout_seconds), 20.0))
    while monotonic() < deadline:
        job = repository.get_job(int(job_id))
        if job is None:
            raise CallbackCanaryError("authorized welcome job disappeared")
        if job.provider_call_started_at:
            return job
        if job.status in TERMINAL_JOB_STATUSES:
            raise CallbackCanaryError("welcome job terminated before recording its provider boundary")
        sleep(0.05)
    raise CallbackCanaryError("welcome provider boundary did not start in time")


def wait_for_result(
    repository: SQLAlchemyExternalEffectRepository,
    *,
    job_id: int,
    timeout_seconds: float,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Any, list[Any]]:
    deadline = monotonic() + max(1.0, min(float(timeout_seconds), 300.0))
    while True:
        job = repository.get_job(int(job_id))
        if job is None:
            raise CallbackCanaryError("callback canary job disappeared")
        attempts = repository.list_attempts(int(job_id))
        exhausted = job.status == "failed_retryable" and int(job.attempt_count) >= int(job.max_attempts)
        if job.status in TERMINAL_JOB_STATUSES or exhausted:
            return job, attempts
        if monotonic() >= deadline:
            return job, attempts
        sleep(0.1)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    release_sha = str(args.expected_release_sha or "").strip()
    policy_version = str(args.expected_policy_version or "").strip()
    actor = str(args.actor or "").strip()
    reason = str(args.reason or "").strip()
    if FULL_SHA.fullmatch(release_sha) is None:
        raise ValueError("expected release SHA must be one full SHA")
    if int(args.generation) <= 0 or not policy_version or not actor or not reason:
        raise ValueError("generation, policy version, actor and reason are required")
    spec = load_canary_spec(args.spec_file)
    asset = load_channel_asset(args.asset_file)
    if len(spec["external_userids"]) != 1 or len(spec["owner_userids"]) != 1 or spec["owner_userids"][0] != asset["owner_userid"]:
        raise ValueError("callback canary requires one exact target and one exact asset owner")
    required_types = set(EXPECTED_EFFECTS.values())
    if not required_types.issubset(set(spec["enabled_effect_types"])):
        raise ValueError("callback canary spec is missing welcome, tag or detail")
    plan = {
        "ok": True,
        "applied": False,
        "release_sha": release_sha,
        "generation": int(args.generation),
        "policy_version": policy_version,
        "target_values_redacted": True,
        "authorization_required": True,
        "real_external_call_executed": False,
    }
    if not args.apply:
        print(json.dumps(plan, sort_keys=True))
        return 0
    if str(os.getenv(AUTHORIZATION_ENV) or "").strip() != "1":
        raise CallbackCanaryError(f"{AUTHORIZATION_ENV}=1 is required")
    if str(args.confirmation or "").strip() != _confirmation(args.generation):
        raise CallbackCanaryError(f"--confirmation must equal {_confirmation(args.generation)}")
    if current_release_sha() != release_sha:
        raise CallbackCanaryError("active release SHA does not match the arm request")
    database_url = normalize_runtime_database_url(raw_database_url())
    _runtime_preflight(
        database_url,
        generation=int(args.generation),
        policy_version=policy_version,
    )
    config = load_wecom_execution_config()
    if config.execution_mode != "execute" or not config.real_calls_enabled or not required_types.issubset(set(config.enabled_effect_types)):
        raise CallbackCanaryError("typed WeCom callback execution is not ready")
    corp_id = str(callback_config().get("corp_id") or "").strip()
    if not corp_id:
        raise CallbackCanaryError("callback corp identity is missing")
    _assert_channel_asset(asset, corp_id=corp_id)
    baseline_id = _baseline_inbox_id(database_url)
    row = wait_for_callback(
        database_url,
        baseline_id=baseline_id,
        corp_id=corp_id,
        external_userid=spec["external_userids"][0],
        owner_userid=asset["owner_userid"],
        state=asset["scene_value"],
        policy_version=policy_version,
        timeout_seconds=float(args.timeout_seconds),
        maximum_event_age_seconds=float(args.maximum_event_age_seconds),
    )
    inbox = wait_for_inbox_success(
        database_url,
        inbox_id=int(row["id"]),
        timeout_seconds=float(args.inbox_timeout_seconds),
    )
    _assert_clean_worker_processing(inbox, generation=int(args.generation))
    _assert_event_fresh(
        inbox,
        maximum_age_seconds=float(args.maximum_event_age_seconds),
    )
    summary = dict(inbox.get("processing_summary_json") or {})
    job_ids = [int(value or 0) for value in summary.get("external_effect_job_ids") or []]
    _freeze_jobs(
        database_url,
        job_ids=job_ids,
        event_log_id=int(summary.get("event_log_id") or 0),
    )
    callback_identity = {
        "baseline_id": baseline_id,
        "inbox_id": int(inbox["id"]),
        "corp_id": corp_id,
        "external_userid": spec["external_userids"][0],
        "owner_userid": asset["owner_userid"],
        "state": asset["scene_value"],
    }
    assert_single_callback(database_url, **callback_identity)
    repository = SQLAlchemyExternalEffectRepository()
    jobs = _job_map(
        repository,
        job_ids=job_ids,
        external_userid=spec["external_userids"][0],
        owner_userid=asset["owner_userid"],
        asset=asset,
        policy_version=policy_version,
    )
    service = ExternalEffectService(repository)
    welcome = _authorize_job(
        service,
        jobs["welcome"],
        actor=actor,
        reason=f"real-time welcome boundary: {reason}",
    )
    boundary_job = wait_for_provider_boundary(
        repository,
        job_id=int(welcome.id),
        timeout_seconds=float(args.provider_timeout_seconds),
    )
    event_time = _provider_event_time(inbox)
    boundary_time = _utc_datetime(boundary_job.provider_call_started_at)
    provider_start_seconds = (boundary_time - event_time).total_seconds()
    if provider_start_seconds < -5.0 or provider_start_seconds >= 20.0:
        raise CallbackCanaryError("welcome provider boundary missed the 20-second provider window")
    for kind in ("identity_detail", "entry_tag"):
        _authorize_job(
            service,
            jobs[kind],
            actor=actor,
            reason=f"welcome boundary confirmed; authorize {kind}: {reason}",
        )

    completed_jobs: list[tuple[str, Any, list[Any]]] = []
    for kind in ("welcome", "entry_tag", "identity_detail"):
        final_job, attempts = wait_for_result(
            repository,
            job_id=int(jobs[kind].id),
            timeout_seconds=float(args.result_timeout_seconds),
        )
        completed_jobs.append((kind, final_job, attempts))

    assert_single_callback(database_url, **callback_identity)
    evidence: list[dict[str, Any]] = []
    for _kind, final_job, attempts in completed_jobs:
        evidence.append(
            record_external_effect_evidence(
                database_url,
                job=final_job,
                attempts=attempts,
                release_sha=release_sha,
                generation=int(args.generation),
                policy_version=policy_version,
                actor=actor,
                reason=reason,
                extra_evidence={
                    "source_webhook_inbox_id": int(inbox["id"]),
                    "callback_to_provider_boundary_ms": int(provider_start_seconds * 1000),
                    "callback_duplicate_count": int(inbox.get("duplicate_count") or 0),
                },
            )
        )
    ok = all(item["status"] == "passed" for item in evidence)
    received_at = _utc_datetime(inbox["received_at"])
    result = {
        **plan,
        "ok": ok,
        "applied": True,
        "source_webhook_inbox_id": int(inbox["id"]),
        "callback_execution_id": str(inbox.get("execution_id") or ""),
        "callback_to_provider_boundary_ms": int(provider_start_seconds * 1000),
        "ingress_to_provider_boundary_ms": int((boundary_time - received_at).total_seconds() * 1000),
        "job_count": len(job_ids),
        "evidence": evidence,
        "real_external_call_executed": any(bool(item.get("side_effect_executed")) for item in evidence),
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CallbackCanaryError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
