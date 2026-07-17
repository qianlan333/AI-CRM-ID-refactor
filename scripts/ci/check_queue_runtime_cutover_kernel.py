#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.platform_foundation.execution_runtime.cutover import (
    CANONICAL_RUNTIME_SERVICES,
    PR3_LEGACY_PERSISTENT_SERVICES,
    PR3_LEGACY_TIMER_OWNERS,
    PR3_OWNER_INVENTORY_NAME,
    PR3_REPLACEMENT_TIMER_OWNERS,
)


INVARIANT_SERVICE = "aicrm-queue-invariant-check.service"
INVARIANT_TIMER = "aicrm-queue-invariant-check.timer"
AI_AUDIENCE_DAILY_SERVICE = "aicrm-ai-audience-daily-intent.service"
AI_AUDIENCE_DAILY_TIMER = "aicrm-ai-audience-daily-intent.timer"
FORBIDDEN_PROVIDER_OWNER_TOKENS = (
    "run_external_effect_queue_worker.py --execute",
    "AICRM_GROUP_OPS_MATERIAL_UPLOAD_MODE=real",
    "AICRM_INTERNAL_EVENT_RELAY_ROLE=owner",
)


def collect_errors(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    expected = set(CANONICAL_RUNTIME_SERVICES)
    discovered = {
        path.name
        for path in (root / "deploy").glob("aicrm-*-queue-runtime.service")
    }
    if discovered != expected:
        errors.append(
            "queue runtime services must reuse the three PR-2 canonical units: "
            f"missing={sorted(expected - discovered)} extra={sorted(discovered - expected)}"
        )
    for service in sorted(expected & discovered):
        body = (root / "deploy" / service).read_text(encoding="utf-8")
        required = (
            "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env",
            "EnvironmentFile=-/home/ubuntu/.aicrm-queue-runtime-generation.env",
            "scripts/run_execution_runtime.py --queue-kind",
            "Restart=always",
        )
        for token in required:
            if token not in body:
                errors.append(f"deploy/{service}: missing canonical runtime token: {token}")
        for token in ("--generation", "--execute", "run_internal_queue_runtime.py", "run_external_queue_runtime.py"):
            if token in body:
                errors.append(f"deploy/{service}: cutover must not override the canonical entrypoint: {token}")
    forbidden_dropins = sorted(
        relative
        for path in (root / "deploy" / "systemd").rglob("*")
        if path.is_file()
        for relative in (path.relative_to(root).as_posix(),)
        if "queue-runtime" in relative
        or any(service in relative for service in expected)
    )
    if forbidden_dropins:
        errors.append(f"queue runtime cutover drop-ins are forbidden: {forbidden_dropins}")

    manifest = json.loads(
        (root / "deploy" / "production_runtime_units.json").read_text(encoding="utf-8")
    )
    if manifest.get("schema_version") != 3:
        errors.append("production runtime manifest must use cutover-aware schema_version 3")
    cutover = manifest.get("cutover_managed_legacy") or {}
    actual_timer_owners = tuple(
        (str(item.get("timer") or ""), str(item.get("service") or ""))
        for item in cutover.get("timers") or []
    )
    actual_persistent = tuple(
        str(item.get("service") or "")
        for item in cutover.get("persistent_services") or []
    )
    if str(cutover.get("owner_inventory") or "") != PR3_OWNER_INVENTORY_NAME:
        errors.append("production runtime manifest must declare the reviewed PR-3 owner inventory")
    if actual_timer_owners != PR3_LEGACY_TIMER_OWNERS:
        errors.append("cutover_managed_legacy timer owners must exactly match the reviewed PR-3 inventory")
    if actual_persistent != PR3_LEGACY_PERSISTENT_SERVICES:
        errors.append("cutover_managed_legacy persistent owners must exactly match the reviewed PR-3 inventory")
    active_services = [
        str(item.get("service") or "")
        for item in manifest.get("active_services") or []
        if str(item.get("service") or "") in expected
    ]
    if set(active_services) != expected or len(active_services) != len(expected):
        errors.append("production runtime manifest must own each canonical queue service exactly once")
    active_timer_pairs = {
        (str(item.get("timer") or ""), str(item.get("service") or ""))
        for item in manifest.get("active_autostart") or []
    }
    active_service_names = {
        str(item.get("service") or "")
        for item in manifest.get("active_services") or []
    } | {service for _timer, service in active_timer_pairs}
    legacy_units = {
        unit
        for timer, service in PR3_LEGACY_TIMER_OWNERS
        for unit in (timer, service)
    } | set(PR3_LEGACY_PERSISTENT_SERVICES)
    active_units = {timer for timer, _service in active_timer_pairs} | active_service_names
    overlap = sorted(legacy_units & active_units)
    if overlap:
        errors.append(f"reviewed PR-3 old owners must never return to active runtime lists: {overlap}")
    replacement = manifest.get("cutover_replacement_autostart") or {}
    replacement_pairs = tuple(
        (str(item.get("timer") or ""), str(item.get("service") or ""))
        for item in replacement.get("timers") or []
    )
    if str(replacement.get("owner_inventory") or "") != PR3_OWNER_INVENTORY_NAME:
        errors.append("cutover replacement timers must use the reviewed PR-3 owner inventory")
    if replacement_pairs != PR3_REPLACEMENT_TIMER_OWNERS:
        errors.append("cutover replacement timers must exactly match the reviewed PR-3 inventory")
    if (AI_AUDIENCE_DAILY_TIMER, AI_AUDIENCE_DAILY_SERVICE) in active_timer_pairs:
        errors.append("the 02:00 AI Audience replacement timer must not autostart before cutover")
    for service in sorted(active_service_names):
        path = root / "deploy" / service
        if not path.exists():
            continue
        body = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_PROVIDER_OWNER_TOKENS:
            if token in body:
                errors.append(f"deploy/{service}: active service contains forbidden old-owner provider token: {token}")
    invariant_entries = [
        item
        for item in manifest.get("active_autostart") or []
        if str(item.get("timer") or "") == INVARIANT_TIMER
    ]
    if len(invariant_entries) != 1 or str(invariant_entries[0].get("service") or "") != INVARIANT_SERVICE:
        errors.append("production runtime manifest must register the read-only invariant timer exactly once")

    timer = (root / "deploy" / INVARIANT_TIMER).read_text(encoding="utf-8")
    service = (root / "deploy" / INVARIANT_SERVICE).read_text(encoding="utf-8")
    for token in ("OnCalendar=*:0/15", "Persistent=true", f"Unit={INVARIANT_SERVICE}"):
        if token not in timer:
            errors.append(f"deploy/{INVARIANT_TIMER}: missing 15-minute timer token: {token}")
    if "scripts/ops/check_queue_runtime_invariants.py" not in service:
        errors.append(f"deploy/{INVARIANT_SERVICE}: must run the invariant reporter")
    for token in ("run_execution_runtime.py", "--execute", "--claim", "dispatch_one", "run_due"):
        if token in service:
            errors.append(f"deploy/{INVARIANT_SERVICE}: invariant service may only report: {token}")

    cutover_source = (
        root / "scripts" / "ops" / "cutover_queue_runtime_generation.py"
    ).read_text(encoding="utf-8")
    if "CANONICAL_RUNTIME_SERVICES" not in cutover_source:
        errors.append("generation cutover must import the canonical PR-2 service inventory")
    for token in (
        "AICRM_QUEUE_RUNTIME_EXECUTE=1",
        "AICRM_QUEUE_RUNTIME_TEST_ONLY=1",
        "AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY=1",
        "AICRM_QUEUE_CUTOVER_COMMITTED=",
        "ACTIVATE_QUEUE_GENERATION_",
        "--owner-inventory",
        "PR3_LEGACY_TIMER_OWNERS",
        "verify_single_owner",
        "activate_post_cutover_replacements",
    ):
        if token not in cutover_source:
            errors.append(f"generation cutover is missing a fail-closed activation token: {token}")
    if "legacy_timer_v" in cutover_source or "postgres_listener_v" in cutover_source:
        errors.append("generation cutover must use numeric database generations, not string aliases")

    scope_contracts = {
        "migrations/versions/0132_external_claim_scope_policy.py": (
            "external_claim_scope",
            "queue-v2-test-loopback",
            "test_loopback",
        ),
        "aicrm_next/platform_foundation/execution_runtime/repository.py": (
            "external_claim_scope_predicate",
            "def next_due_at(",
            "test_only: bool = False",
        ),
        "aicrm_next/platform_foundation/execution_runtime/read_model.py": (
            "external_claim_scope_predicate",
            '"policy_gated"',
        ),
        "aicrm_next/platform_foundation/execution_runtime/service.py": (
            "_validate_external_execution_scope",
            "database test-loopback scope requires a test-only worker",
        ),
    }
    for relative, tokens in scope_contracts.items():
        path = root / relative
        if not path.exists():
            errors.append(f"{relative}: durable external claim-scope contract is missing")
            continue
        body = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in body:
                errors.append(f"{relative}: missing external claim-scope token: {token}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the queue generation cutover kernel.")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    errors = collect_errors(Path(args.root).resolve())
    if errors:
        for violation in errors:
            print(violation)
        return 1
    print("queue runtime cutover kernel check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
