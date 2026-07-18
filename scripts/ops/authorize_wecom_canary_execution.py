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
    resolve_external_effect_job_id,
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


AUTHORIZATION_ENV = "AICRM_WECOM_CANARY_AUTHORIZE_AUTHORIZED"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
EXECUTION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CAS-authorize one pre-provider WeCom job for the exact canary allowlist.",
    )
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--job-id", type=int, default=0)
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--expected-policy-version", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirmation", default="")
    return parser.parse_args(argv)


def _confirmation(execution_id: str, expected_version: int) -> str:
    return f"AUTHORIZE_WECOM_CANARY_{execution_id}_{expected_version}"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    execution_id = str(args.execution_id or "").strip()
    release_sha = str(args.expected_release_sha or "").strip()
    policy_version = str(args.expected_policy_version or "").strip()
    actor = str(args.actor or "").strip()
    reason = str(args.reason or "").strip()
    if EXECUTION_ID.fullmatch(execution_id) is None:
        raise ValueError("execution_id has an invalid format")
    if FULL_SHA.fullmatch(release_sha) is None:
        raise ValueError("expected_release_sha must be a full SHA")
    if (
        int(args.generation or 0) <= 0
        or int(args.expected_version or 0) <= 0
        or int(args.job_id or 0) < 0
        or not policy_version
        or not actor
        or not reason
    ):
        raise ValueError("generation, expected version, policy, actor and reason are required")
    plan = {
        "ok": True,
        "applied": False,
        "execution_id": execution_id,
        "requested_job_id": int(args.job_id or 0),
        "expected_version": int(args.expected_version),
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
    expected_confirmation = _confirmation(execution_id, int(args.expected_version))
    if str(args.confirmation or "").strip() != expected_confirmation:
        raise RuntimeError(f"--confirmation must equal {expected_confirmation}")
    if current_release_sha() != release_sha:
        raise RuntimeError("active release SHA does not match the authorization request")

    database_url = normalize_runtime_database_url(raw_database_url())
    state = RuntimeGenerationRepository(database_url).read_state()
    if (
        state.active_generation != int(args.generation)
        or not state.claim_enabled
        or state.policy_version != policy_version
        or state.external_claim_scope != "allowlisted"
    ):
        raise RuntimeError("authorization requires the exact active allowlisted generation")

    repository = SQLAlchemyExternalEffectRepository()
    job_id = resolve_external_effect_job_id(
        database_url,
        execution_id=execution_id,
        requested_job_id=int(args.job_id or 0),
    )
    job = repository.get_job(job_id)
    if job is None or str(job.execution_id or "") != execution_id:
        raise RuntimeError("external-effect job disappeared during authorization")
    if str(job.policy_version or "") != policy_version:
        raise RuntimeError("job policy version does not match the active policy")
    if str(job.payload_json.get("execution_scope") or "").strip():
        raise RuntimeError("job already has an execution scope")
    if not evidence_type_for_effect(job.effect_type):
        raise RuntimeError("job is not an approved WeCom canary effect type")
    if wecom_canary_job_gate_error(job, authorize_scope=True):
        raise RuntimeError("job target or operation is outside the exact canary policy")

    authorized = ExternalEffectService(repository).authorize_allowlisted_canary(
        job_id,
        actor=actor,
        reason=reason,
        expected_version=int(args.expected_version),
    )
    if authorized is None:
        raise RuntimeError("canary authorization CAS lost or provider boundary already started")
    if (
        authorized.row_version != int(args.expected_version) + 1
        or str(authorized.payload_json.get("execution_scope") or "")
        != "allowlisted_canary"
    ):
        raise RuntimeError("canary authorization did not persist the exact scope and version")
    print(
        json.dumps(
            {
                **plan,
                "applied": True,
                "job_id": int(authorized.id),
                "effect_type": str(authorized.effect_type),
                "row_version": int(authorized.row_version),
                "status": str(authorized.status),
                "eligible_released": True,
                "provider_boundary_started": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
