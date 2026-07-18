#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.script_runtime import ensure_repo_root_on_path

ensure_repo_root_on_path()

from aicrm_next.platform_foundation.command_bus.models import CommandContext  # noqa: E402
from aicrm_next.platform_foundation.execution_runtime.cutover import (  # noqa: E402
    RuntimeGenerationRepository,
)
from aicrm_next.platform_foundation.execution_runtime.repository import (  # noqa: E402
    normalize_runtime_database_url,
)
from aicrm_next.platform_foundation.execution_runtime.validation import (  # noqa: E402
    TERMINAL_JOB_STATUSES,
    record_external_effect_evidence,
)
from aicrm_next.platform_foundation.external_effects.models import (  # noqa: E402
    WECOM_EXTERNAL_CONTACT_DETAIL_FETCH,
    WECOM_MEDIA_UPLOAD,
    WECOM_MESSAGE_GROUP_SEND,
    WECOM_MESSAGE_PRIVATE_SEND,
)
from aicrm_next.platform_foundation.external_effects.repo import (  # noqa: E402
    SQLAlchemyExternalEffectRepository,
)
from aicrm_next.platform_foundation.external_effects.service import (  # noqa: E402
    ExternalEffectService,
)
from aicrm_next.platform_foundation.external_effects.wecom_canary_policy import (  # noqa: E402
    WECOM_ALLOWLISTED_CANARY_SCOPE,
    wecom_canary_gate_error,
)
from aicrm_next.shared.release import current_release_sha  # noqa: E402
from aicrm_next.shared.runtime import raw_database_url  # noqa: E402
from aicrm_next.shared.wecom_runtime import load_wecom_execution_config  # noqa: E402
from scripts.ops.configure_wecom_canary import load_canary_spec  # noqa: E402


AUTHORIZATION_ENV = "AICRM_WECOM_CANARY_PLAN_AUTHORIZED"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
SCENARIOS = ("private", "group", "contact_detail", "media")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan approved WeCom canary jobs and wait for durable provider evidence.",
    )
    parser.add_argument("--spec-file", required=True)
    parser.add_argument("--scenario", action="append", choices=SCENARIOS, default=[])
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


def _selected(args: argparse.Namespace) -> tuple[str, ...]:
    return tuple(dict.fromkeys(args.scenario or SCENARIOS))


def _confirmation(args: argparse.Namespace) -> str:
    return f"PLAN_WECOM_CANARY_{str(args.run_id).upper()}_{int(args.generation)}"


def _media_target(value: str) -> tuple[str, int, str]:
    parts = str(value or "").split(":")
    if len(parts) != 3 or not parts[0] or not parts[2]:
        raise ValueError("media target must use material_kind:material_id:upload_kind")
    try:
        material_id = int(parts[1])
    except (TypeError, ValueError) as exc:
        raise ValueError("media target material_id must be an integer") from exc
    if material_id <= 0:
        raise ValueError("media target material_id must be positive")
    return parts[0], material_id, parts[2]


def _scenario_requests(
    spec: dict[str, tuple[str, ...]],
    *,
    run_id: str,
    scenarios: tuple[str, ...],
) -> list[dict[str, Any]]:
    external_userid = spec["external_userids"][0] if spec["external_userids"] else ""
    owner_userid = spec["owner_userids"][0] if spec["owner_userids"] else ""
    requests: list[dict[str, Any]] = []
    content = f"AI-CRM ID validation canary {run_id}"
    common = {
        "business_type": "id_validation_canary",
        "business_id": run_id,
        "source_module": "scripts.ops.plan_wecom_canary",
        "risk_level": "high",
        "execution_mode": "execute",
        "status": "queued",
        "max_attempts": 1,
    }
    if "private" in scenarios:
        payload = {
            "channel": "wecom_private",
            "owner_userid": owner_userid,
            "external_userids": [external_userid],
            "content_text": content,
        }
        error = wecom_canary_gate_error(
            payload={**payload, "execution_scope": WECOM_ALLOWLISTED_CANARY_SCOPE},
            external_userids=[external_userid],
            owner_userids=[owner_userid],
        )
        if error:
            raise RuntimeError(f"private canary gate failed: {error}")
        requests.append(
            {
                **common,
                "scenario": "private",
                "effect_type": WECOM_MESSAGE_PRIVATE_SEND,
                "adapter_name": "wecom_private_message",
                "operation": "send",
                "target_type": "external_user",
                "target_id": external_userid,
                "payload": payload,
                "payload_summary": {
                    "target_count": 1,
                    "content_present": True,
                },
                "lane": "wecom_interactive",
                "ordering_key": f"external_user:{external_userid}",
                "fairness_key": "id_validation_canary",
                "rate_scope_key": "wecom:id_validation:private",
            }
        )
    if "group" in scenarios:
        chat_id = spec["group_chat_ids"][0] if spec["group_chat_ids"] else ""
        webhook_key = spec["group_webhook_keys"][0] if spec["group_webhook_keys"] else ""
        payload = {
            "webhook_key": webhook_key,
            "owner_userid": owner_userid,
            "chat_ids": [chat_id],
            "content_payload": {"text": {"content": content}, "attachments": []},
            "mention_all": False,
        }
        error = wecom_canary_gate_error(
            payload={**payload, "execution_scope": WECOM_ALLOWLISTED_CANARY_SCOPE},
            owner_userids=[owner_userid],
            group_chat_ids=[chat_id],
            group_webhook_key=webhook_key,
            mention_all=False,
        )
        if error:
            raise RuntimeError(f"group canary gate failed: {error}")
        requests.append(
            {
                **common,
                "scenario": "group",
                "effect_type": WECOM_MESSAGE_GROUP_SEND,
                "adapter_name": "wecom_group_message",
                "operation": "send_group_message",
                "target_type": "group_chat",
                "target_id": chat_id,
                "payload": payload,
                "payload_summary": {
                    "chat_count": 1,
                    "mention_all": False,
                    "content_present": True,
                },
                "lane": "wecom_interactive",
                "ordering_key": f"group_chat:{chat_id}",
                "fairness_key": "id_validation_canary",
                "rate_scope_key": "wecom:id_validation:group",
            }
        )
    if "contact_detail" in scenarios:
        payload = {
            "external_userid": external_userid,
            "source_type": "id_validation_canary",
        }
        error = wecom_canary_gate_error(
            payload={**payload, "execution_scope": WECOM_ALLOWLISTED_CANARY_SCOPE},
            external_userids=[external_userid],
        )
        if error:
            raise RuntimeError(f"contact-detail canary gate failed: {error}")
        requests.append(
            {
                **common,
                "scenario": "contact_detail",
                "effect_type": WECOM_EXTERNAL_CONTACT_DETAIL_FETCH,
                "adapter_name": "wecom_external_contact_detail",
                "operation": "get_external_contact_detail",
                "target_type": "external_user",
                "target_id": external_userid,
                "payload": payload,
                "payload_summary": {
                    "external_userid_present": True,
                },
                "lane": "wecom_interactive",
                "ordering_key": f"external_user:{external_userid}",
                "fairness_key": "id_validation_canary",
                "rate_scope_key": "wecom:id_validation:external_contact_detail",
            }
        )
    if "media" in scenarios:
        target = spec["media_targets"][0] if spec["media_targets"] else ""
        material_kind, material_id, upload_kind = _media_target(target)
        payload = {
            "material_kind": material_kind,
            "material_id": material_id,
            "upload_kind": upload_kind,
            "force_refresh": True,
        }
        error = wecom_canary_gate_error(
            payload={**payload, "execution_scope": WECOM_ALLOWLISTED_CANARY_SCOPE},
            media_target=target,
        )
        if error:
            raise RuntimeError(f"media canary gate failed: {error}")
        requests.append(
            {
                **common,
                "scenario": "media",
                "effect_type": WECOM_MEDIA_UPLOAD,
                "adapter_name": "wecom_media_upload",
                "operation": "refresh_temporary_media",
                "target_type": "media_library_material",
                "target_id": target,
                "payload": payload,
                "payload_summary": {
                    "material_reference_present": True,
                },
                "lane": "wecom_media",
                "ordering_key": f"media:{target}",
                "fairness_key": "id_validation_canary",
                "rate_scope_key": "wecom:id_validation:media",
            }
        )
    return requests


def _wait_for_result(
    repository: SQLAlchemyExternalEffectRepository,
    job_id: int,
    *,
    timeout_seconds: int,
) -> tuple[Any, list[Any]]:
    deadline = time.monotonic() + max(1, int(timeout_seconds or 120))
    while True:
        job = repository.get_job(job_id)
        if job is None:
            raise RuntimeError("canary job disappeared")
        attempts = repository.list_attempts(job_id)
        exhausted = job.status == "failed_retryable" and job.attempt_count >= job.max_attempts
        if job.status in TERMINAL_JOB_STATUSES or exhausted:
            return job, attempts
        if time.monotonic() >= deadline:
            return job, attempts
        time.sleep(0.5)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_id = str(args.run_id or "").strip()
    release_sha = str(args.expected_release_sha or "").strip()
    policy_version = str(args.expected_policy_version or "").strip()
    actor = str(args.actor or "").strip()
    reason = str(args.reason or "").strip()
    if RUN_ID.fullmatch(run_id) is None:
        raise ValueError("run_id has an invalid format")
    if FULL_SHA.fullmatch(release_sha) is None:
        raise ValueError("expected_release_sha must be a full SHA")
    if int(args.generation or 0) <= 0 or not policy_version or not actor or not reason:
        raise ValueError("generation, policy version, actor and reason are required")
    spec = load_canary_spec(args.spec_file)
    scenarios = _selected(args)
    plan = {
        "ok": True,
        "applied": False,
        "run_id": run_id,
        "release_sha": release_sha,
        "generation": int(args.generation),
        "policy_version": policy_version,
        "scenarios": list(scenarios),
        "scenario_count": len(scenarios),
        "target_values_redacted": True,
        "real_external_call_executed": False,
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0
    if str(os.getenv(AUTHORIZATION_ENV) or "").strip() != "1":
        raise RuntimeError(f"{AUTHORIZATION_ENV}=1 is required")
    if str(args.confirmation or "").strip() != _confirmation(args):
        raise RuntimeError(f"--confirmation must equal {_confirmation(args)}")
    if current_release_sha() != release_sha:
        raise RuntimeError("active release SHA does not match the canary request")
    database_url = normalize_runtime_database_url(raw_database_url())
    state = RuntimeGenerationRepository(database_url).read_state()
    if (
        state.active_generation != int(args.generation)
        or not state.claim_enabled
        or state.policy_version != policy_version
        or state.external_claim_scope != "allowlisted"
    ):
        raise RuntimeError("canary planning requires the exact active allowlisted generation")
    config = load_wecom_execution_config()
    requests = _scenario_requests(spec, run_id=run_id, scenarios=scenarios)
    requested_types = {str(request["effect_type"]) for request in requests}
    if config.execution_mode != "execute" or not config.real_calls_enabled:
        raise RuntimeError("typed WeCom provider execution is not ready")
    if not requested_types.issubset(set(config.enabled_effect_types)):
        raise RuntimeError("one or more canary effect types are not enabled")

    repository = SQLAlchemyExternalEffectRepository()
    service = ExternalEffectService(repository)
    planned: list[dict[str, Any]] = []
    for request in requests:
        scenario = str(request.pop("scenario"))
        request["context"] = CommandContext(
            actor_id=actor,
            actor_type="operator",
            source_route="scripts/ops/plan_wecom_canary.py",
            request_id=run_id,
            trace_id=f"id-validation-canary:{run_id}:{scenario}",
        )
        request["idempotency_key"] = (
            f"id-validation-canary:{release_sha}:{run_id}:{scenario}"
        )
        job = service.plan_effect(**request)
        authorized = service.authorize_allowlisted_canary(
            int(job["id"]),
            actor=actor,
            reason=reason,
            expected_version=int(job["row_version"]),
        )
        if authorized is None:
            raise RuntimeError(f"{scenario} canary authorization failed")
        planned.append({"scenario": scenario, "job_id": int(authorized.id)})

    evidence: list[dict[str, Any]] = []
    for item in planned:
        job, attempts = _wait_for_result(
            repository,
            int(item["job_id"]),
            timeout_seconds=int(args.timeout_seconds),
        )
        evidence.append(
            record_external_effect_evidence(
                database_url,
                job=job,
                attempts=attempts,
                release_sha=release_sha,
                generation=int(args.generation),
                policy_version=policy_version,
                actor=actor,
                reason=reason,
            )
        )
    ok = bool(evidence) and all(item["status"] == "passed" for item in evidence)
    print(
        json.dumps(
            {
                **plan,
                "ok": ok,
                "applied": True,
                "evidence": evidence,
                "real_external_call_executed": any(
                    bool(item["side_effect_executed"]) for item in evidence
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
