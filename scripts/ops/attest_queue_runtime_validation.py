#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

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
)
from aicrm_next.platform_foundation.execution_runtime.validation import (  # noqa: E402
    evidence_type_for_effect,
    record_external_effect_evidence,
    resolve_external_effect_job_id,
    test_loopback_receipt_evidence,
)
from aicrm_next.platform_foundation.external_effects.repo import (  # noqa: E402
    SQLAlchemyExternalEffectRepository,
)
from aicrm_next.platform_foundation.external_effects.wecom_canary_policy import (  # noqa: E402
    wecom_canary_job_gate_error,
)
from aicrm_next.shared.release import current_release_sha  # noqa: E402
from aicrm_next.shared.runtime import raw_database_url  # noqa: E402


AUTHORIZATION_ENV = "AICRM_QUEUE_EVIDENCE_ATTEST_AUTHORIZED"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
EXECUTION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
EXTERNAL_EVIDENCE_TYPES = (
    "test_loopback",
    "wecom_private",
    "wecom_group",
    "wecom_welcome",
    "wecom_tag",
    "wecom_profile",
    "wecom_contact_detail",
    "wecom_media",
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attest one durable external-effect execution as queue validation evidence.",
    )
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--job-id", type=int, default=0)
    parser.add_argument("--evidence-type", choices=EXTERNAL_EVIDENCE_TYPES, default="")
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--expected-policy-version", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirmation", default="")
    return parser.parse_args(argv)


def _confirmation(execution_id: str, generation: int) -> str:
    return f"ATTEST_QUEUE_EVIDENCE_{execution_id}_{generation}"


def _validate_identity(args: argparse.Namespace) -> tuple[str, str, str, str]:
    execution_id = str(args.execution_id or "").strip()
    release_sha = str(args.expected_release_sha or "").strip()
    policy_version = str(args.expected_policy_version or "").strip()
    actor = str(args.actor or "").strip()
    reason = str(args.reason or "").strip()
    if EXECUTION_ID.fullmatch(execution_id) is None:
        raise ValueError("execution_id has an invalid format")
    if FULL_SHA.fullmatch(release_sha) is None:
        raise ValueError("expected_release_sha must be a full SHA")
    if int(args.generation or 0) <= 0 or not policy_version or not actor or not reason:
        raise ValueError("generation, policy version, actor and reason are required")
    if int(args.job_id or 0) < 0:
        raise ValueError("job_id cannot be negative")
    return execution_id, release_sha, policy_version, actor


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    execution_id, release_sha, policy_version, actor = _validate_identity(args)
    plan = {
        "ok": True,
        "applied": False,
        "execution_id": execution_id,
        "requested_job_id": int(args.job_id or 0),
        "requested_evidence_type": str(args.evidence_type or ""),
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
    expected_confirmation = _confirmation(execution_id, int(args.generation))
    if str(args.confirmation or "").strip() != expected_confirmation:
        raise RuntimeError(f"--confirmation must equal {expected_confirmation}")
    if current_release_sha() != release_sha:
        raise RuntimeError("active release SHA does not match the evidence request")

    database_url = normalize_runtime_database_url(raw_database_url())
    state = RuntimeGenerationRepository(database_url).read_state()
    if (
        state.active_generation != int(args.generation)
        or not state.claim_enabled
        or state.policy_version != policy_version
        or state.external_claim_scope not in {"test_loopback", "allowlisted"}
    ):
        raise RuntimeError("runtime generation, policy, claim gate, or scope does not match")

    repository = SQLAlchemyExternalEffectRepository()
    job_id = resolve_external_effect_job_id(
        database_url,
        execution_id=execution_id,
        requested_job_id=int(args.job_id or 0),
    )
    job = repository.get_job(job_id)
    if job is None or str(job.execution_id or "") != execution_id:
        raise RuntimeError("external-effect job disappeared during attestation")
    attempts = repository.list_attempts(job_id)
    evidence_type = str(args.evidence_type or evidence_type_for_effect(job.effect_type)).strip()
    if evidence_type not in EXTERNAL_EVIDENCE_TYPES:
        raise RuntimeError("job effect type does not map to supported validation evidence")

    extra: dict[str, object] = {}
    if evidence_type == "test_loopback":
        extra.update(test_loopback_receipt_evidence(repository, job))
        if str(job.policy_version or "") != policy_version:
            raise RuntimeError("loopback evidence must be produced under the exact active policy")
    else:
        if state.external_claim_scope != "allowlisted":
            raise RuntimeError("real WeCom evidence requires allowlisted runtime scope")
        gate_error = wecom_canary_job_gate_error(job)
        if gate_error:
            extra["provider_policy_gate_error"] = gate_error

    result = record_external_effect_evidence(
        database_url,
        job=job,
        attempts=attempts,
        release_sha=release_sha,
        generation=int(args.generation),
        policy_version=policy_version,
        actor=actor,
        reason=str(args.reason).strip(),
        evidence_type=evidence_type,
        extra_evidence=extra,
    )
    ok = result["status"] == "passed"
    print(
        json.dumps(
            {
                **plan,
                "ok": ok,
                "applied": True,
                "job_id": job_id,
                "evidence": result,
                "real_external_call_executed": bool(result["side_effect_executed"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
