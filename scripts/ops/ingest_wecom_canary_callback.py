#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.script_runtime import ensure_repo_root_on_path

ensure_repo_root_on_path()

from aicrm_next.channel_entry import repo as channel_entry_repo  # noqa: E402
from aicrm_next.channel_entry.application import (  # noqa: E402
    callback_config,
    process_wecom_external_contact_event,
    resolve_channel_for_scene,
)
from aicrm_next.channel_entry.schemas import (  # noqa: E402
    ProcessWeComExternalContactEventCommand,
)
from aicrm_next.platform_foundation.external_effects.models import (  # noqa: E402
    WECOM_CONTACT_TAG_MARK,
    WECOM_EXTERNAL_CONTACT_DETAIL_FETCH,
    WECOM_WELCOME_MESSAGE_SEND,
)
from aicrm_next.platform_foundation.external_effects.repo import (  # noqa: E402
    SQLAlchemyExternalEffectRepository,
)
from aicrm_next.shared.release import current_release_sha  # noqa: E402
from aicrm_next.shared.runtime import raw_database_url  # noqa: E402
from aicrm_next.shared.wecom_runtime import load_wecom_execution_config  # noqa: E402
from scripts.ops.configure_wecom_canary import load_canary_spec  # noqa: E402
from scripts.ops.import_wecom_canary_channel_asset import (  # noqa: E402
    _runtime_ready,
    load_channel_asset,
)
from aicrm_next.platform_foundation.execution_runtime.repository import (  # noqa: E402
    normalize_runtime_database_url,
    open_runtime_connection,
)


AUTHORIZATION_ENV = "AICRM_WECOM_CANARY_CALLBACK_INGEST_AUTHORIZED"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
CALLBACK_FIELDS = frozenset({"event_data", "source"})
SOURCE_FIELDS = frozenset(
    {
        "repository",
        "release_sha",
        "event_log_id",
        "event_payload_sha256",
        "received_at",
    }
)
REQUIRED_EVENT_FIELDS = frozenset(
    {
        "ToUserName",
        "CreateTime",
        "Event",
        "ChangeType",
        "UserID",
        "ExternalUserID",
        "State",
        "WelcomeCode",
    }
)
EXPECTED_EFFECTS = {
    "identity_detail": WECOM_EXTERNAL_CONTACT_DETAIL_FETCH,
    "welcome": WECOM_WELCOME_MESSAGE_SEND,
    "entry_tag": WECOM_CONTACT_TAG_MARK,
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest one attested real production WeCom callback into ID validation without authorizing dispatch.",
    )
    parser.add_argument("--event-file", required=True)
    parser.add_argument("--asset-file", required=True)
    parser.add_argument("--spec-file", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--expected-policy-version", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirmation", default="")
    return parser.parse_args(argv)


def _private_json(path_value: str) -> dict[str, Any]:
    path = Path(str(path_value or "")).expanduser().resolve()
    if not path.is_file() or path.stat().st_size > 131072:
        raise ValueError("a bounded private callback file is required")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("callback file permissions must not grant group or other access")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("callback file must contain one JSON object")
    return payload


def _event_hash(event_data: dict[str, Any]) -> str:
    canonical = json.dumps(event_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_callback_event(path_value: str) -> dict[str, Any]:
    payload = _private_json(path_value)
    if set(payload) != CALLBACK_FIELDS:
        raise ValueError("callback file fields do not match the exact private contract")
    event_data = payload.get("event_data")
    source = payload.get("source")
    if not isinstance(event_data, dict) or not isinstance(source, dict):
        raise ValueError("callback event_data and source must be JSON objects")
    if set(source) != SOURCE_FIELDS:
        raise ValueError("callback source fields do not match the exact private contract")
    if not REQUIRED_EVENT_FIELDS.issubset(event_data):
        raise ValueError("callback event is missing a required provider field")
    if len(event_data) > 50 or any(isinstance(value, (dict, list)) for value in event_data.values()):
        raise ValueError("callback event must contain only bounded scalar provider fields")
    normalized_event = {str(key): str(value or "").strip() for key, value in event_data.items()}
    if any(len(key) > 128 or len(value) > 8192 for key, value in normalized_event.items()):
        raise ValueError("callback event contains an oversized field")
    normalized_source = {
        "repository": str(source.get("repository") or "").strip(),
        "release_sha": str(source.get("release_sha") or "").strip(),
        "event_log_id": int(source.get("event_log_id") or 0),
        "event_payload_sha256": str(source.get("event_payload_sha256") or "").strip(),
        "received_at": str(source.get("received_at") or "").strip(),
    }
    if normalized_source["repository"] != "qianlan333/AI-CRM":
        raise ValueError("callback source repository is not the attested production owner")
    if FULL_SHA.fullmatch(normalized_source["release_sha"]) is None:
        raise ValueError("callback source release must be one full SHA")
    if normalized_source["event_log_id"] <= 0 or not normalized_source["received_at"]:
        raise ValueError("callback source event identity is incomplete")
    event_hash = _event_hash(normalized_event)
    if normalized_source["event_payload_sha256"] != event_hash:
        raise ValueError("callback source payload fingerprint does not match the event")
    return {"event_data": normalized_event, "source": normalized_source, "event_payload_sha256": event_hash}


def _confirmation(generation: int) -> str:
    return f"INGEST_WECOM_CANARY_CALLBACK_{int(generation)}"


def _validate_event(
    callback: dict[str, Any],
    *,
    asset: dict[str, str],
    canary_spec: dict[str, tuple[str, ...]],
) -> None:
    event = callback["event_data"]
    if event["Event"] != "change_external_contact" or event["ChangeType"] != "add_external_contact":
        raise ValueError("callback is not one real add_external_contact event")
    if not event["WelcomeCode"]:
        raise ValueError("callback does not contain the provider welcome code")
    if event["State"] != asset["scene_value"]:
        raise ValueError("callback scene does not match the imported dedicated channel")
    if event["UserID"] != asset["owner_userid"]:
        raise ValueError("callback owner does not match the imported dedicated channel")
    if event["ExternalUserID"] not in canary_spec["external_userids"]:
        raise ValueError("callback target is outside the private canary specification")
    if event["UserID"] not in canary_spec["owner_userids"]:
        raise ValueError("callback owner is outside the private canary specification")
    configured_corp_id = str(callback_config().get("corp_id") or "").strip()
    if not configured_corp_id or event["ToUserName"] != configured_corp_id:
        raise ValueError("callback corp id does not match the ID-validation runtime")
    try:
        event_time = datetime.fromtimestamp(int(event["CreateTime"]), tz=timezone.utc)
    except (TypeError, ValueError, OSError) as exc:
        raise ValueError("callback CreateTime is invalid") from exc
    age_seconds = (datetime.now(timezone.utc) - event_time).total_seconds()
    if age_seconds < -300 or age_seconds > 86400:
        raise ValueError("callback is outside the 24-hour canary transcript window")


def _assert_channel(asset: dict[str, str], event_data: dict[str, str]) -> dict[str, Any]:
    channel, match = resolve_channel_for_scene(
        scene_value=event_data["State"],
        corp_id=event_data["ToUserName"],
        persist_alias=False,
    )
    match_type = str(match.get("match_type") or "")
    if not channel or not (match_type.startswith("qrcode_asset_") or match_type == "scene_alias"):
        raise RuntimeError("callback scene does not resolve through the imported durable channel asset")
    exact = {
        "channel_code": asset["channel_code"],
        "owner_staff_id": asset["owner_userid"],
        "entry_tag_id": asset["tag_id"],
        "welcome_message": asset["welcome_message"],
    }
    if any(str(channel.get(key) or "").strip() != value for key, value in exact.items()):
        raise RuntimeError("resolved channel does not match the private imported asset")
    return channel


def _job_metadata(result: dict[str, Any], *, database_url: str = "") -> list[dict[str, Any]]:
    entry = dict(result.get("entry_result") or {})
    identity = dict(result.get("identity_sync") or {})
    welcome = dict(entry.get("welcome_message") or {})
    tag = dict(entry.get("entry_tag") or {})
    job_ids = {
        "identity_detail": int(identity.get("external_effect_job_id") or 0),
        "welcome": int(welcome.get("external_effect_job_id") or 0),
        "entry_tag": int(tag.get("external_effect_job_id") or 0),
    }
    if any(job_id <= 0 for job_id in job_ids.values()):
        raise RuntimeError("callback transcript did not create the three required durable jobs")
    if database_url:
        with open_runtime_connection(database_url) as connection:
            rows = connection.execute(
                """
                UPDATE external_effect_job
                SET max_attempts = 1,
                    row_version = row_version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ANY(%s)
                  AND status IN ('planned', 'approved', 'queued', 'blocked')
                  AND attempt_count = 0
                  AND provider_call_started_at IS NULL
                  AND cancel_requested_at IS NULL
                RETURNING id
                """,
                (list(job_ids.values()),),
            ).fetchall()
            connection.commit()
        if {int(row["id"]) for row in rows} != set(job_ids.values()):
            raise RuntimeError("callback transcript jobs could not be frozen to one provider attempt")
    repository = SQLAlchemyExternalEffectRepository()
    jobs: list[dict[str, Any]] = []
    for kind, job_id in job_ids.items():
        job = repository.get_job(job_id)
        if job is None or job.effect_type != EXPECTED_EFFECTS[kind]:
            raise RuntimeError(f"callback transcript {kind} job identity mismatch")
        if job.provider_call_started_at or job.attempt_count or job.side_effect_executed or int(job.max_attempts) != 1:
            raise RuntimeError(f"callback transcript {kind} crossed the provider boundary before authorization")
        if str(job.payload_json.get("execution_scope") or "") == "allowlisted_canary":
            raise RuntimeError(f"callback transcript {kind} was unexpectedly pre-authorized")
        jobs.append(
            {
                "kind": kind,
                "job_id": int(job.id),
                "execution_id": str(job.execution_id or ""),
                "row_version": int(job.row_version),
                "status": str(job.status),
                "effect_type": str(job.effect_type),
            }
        )
    return jobs


def _apply(
    callback: dict[str, Any],
    *,
    asset: dict[str, str],
    database_url: str,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    event = callback["event_data"]
    channel = _assert_channel(asset, event)
    result = process_wecom_external_contact_event(
        ProcessWeComExternalContactEventCommand(
            corp_id=event["ToUserName"],
            event_data=event,
            payload_xml="",
            route="ops.id_validation_canary_callback_transcript",
        )
    )
    if not result.get("handled"):
        raise RuntimeError("callback transcript was not handled by the Next channel-entry owner")
    jobs = _job_metadata(result, database_url=database_url)
    event_log_id = int((result.get("event_log") or {}).get("id") or 0)
    channel_entry_repo.upsert_channel_entry_effect_log(
        effect_type="id_validation_callback_transcript",
        idempotency_key=f"id-validation-callback-transcript:{callback['event_payload_sha256']}",
        status="success",
        event_log_id=event_log_id or None,
        channel_id=int(channel.get("id") or 0) or None,
        scene_value=event["State"],
        external_contact_id=event["ExternalUserID"],
        owner_staff_id=event["UserID"],
        reason=reason,
        request_json={
            "event_payload_sha256": callback["event_payload_sha256"],
            "source_repository": callback["source"]["repository"],
            "source_release_sha": callback["source"]["release_sha"],
            "source_event_log_id": callback["source"]["event_log_id"],
            "target_values_redacted": True,
        },
        response_json={
            "job_ids": [item["job_id"] for item in jobs],
            "authorization_required": True,
            "real_external_call_executed": False,
            "operator": actor,
        },
    )
    return {
        "event_log_id": event_log_id,
        "event_payload_sha256": callback["event_payload_sha256"],
        "source_release_sha": callback["source"]["release_sha"],
        "jobs": jobs,
        "authorization_required": True,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    release_sha = str(args.expected_release_sha or "").strip()
    policy_version = str(args.expected_policy_version or "").strip()
    actor = str(args.actor or "").strip()
    reason = str(args.reason or "").strip()
    if FULL_SHA.fullmatch(release_sha) is None:
        raise ValueError("expected_release_sha must be one full SHA")
    if int(args.generation or 0) <= 0 or not policy_version or not actor or not reason:
        raise ValueError("generation, policy version, actor and reason are required")
    callback = load_callback_event(args.event_file)
    asset = load_channel_asset(args.asset_file)
    canary_spec = load_canary_spec(args.spec_file)
    _validate_event(callback, asset=asset, canary_spec=canary_spec)
    plan = {
        "ok": True,
        "applied": False,
        "generation": int(args.generation),
        "policy_version": policy_version,
        "event_payload_sha256": callback["event_payload_sha256"],
        "source_release_sha": callback["source"]["release_sha"],
        "target_values_redacted": True,
        "real_external_call_executed": False,
        "authorization_required": True,
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0
    if str(os.getenv(AUTHORIZATION_ENV) or "").strip() != "1":
        raise RuntimeError(f"{AUTHORIZATION_ENV}=1 is required")
    if str(args.confirmation or "").strip() != _confirmation(args.generation):
        raise RuntimeError(f"--confirmation must equal {_confirmation(args.generation)}")
    if current_release_sha() != release_sha:
        raise RuntimeError("active release SHA does not match the callback transcript request")
    database_url = normalize_runtime_database_url(raw_database_url())
    _runtime_ready(database_url=database_url, generation=int(args.generation), policy_version=policy_version)
    config = load_wecom_execution_config()
    required_types = set(EXPECTED_EFFECTS.values())
    if config.execution_mode != "execute" or not config.real_calls_enabled:
        raise RuntimeError("callback transcript requires configured WeCom execution before job planning")
    if not required_types.issubset(set(config.enabled_effect_types)):
        raise RuntimeError("callback transcript requires welcome, tag and detail effect types")
    result = _apply(callback, asset=asset, database_url=database_url, actor=actor, reason=reason)
    print(json.dumps({**plan, **result, "applied": True}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
