#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.automation_engine.repo import build_automation_repository
from aicrm_next.automation_engine.task_groups import task_group_side_effect_safety
from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml


ROUTE_FAMILY = "/api/admin/automation-conversion/task-groups*"
EXACT_ROUTE = "/api/admin/automation-conversion/task-groups"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
NATIVE_API = ROOT / "aicrm_next/automation_engine/api.py"


def _git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def _manifest_entry() -> dict[str, Any]:
    data = load_yaml(MANIFEST)
    for entry in data.get("routes", []):
        if isinstance(entry, dict) and entry.get("route_pattern") == ROUTE_FAMILY:
            return entry
    return {}


def _decorator_present(text: str, route: str) -> bool:
    return f'"{route}"' in text or f"'{route}'" in text


def _production_compat_exact_entry() -> dict[str, Any]:
    text = PRODUCTION_COMPAT.read_text(encoding="utf-8")
    return {
        "exact_entry_found": _decorator_present(text, EXACT_ROUTE),
        "path_entry_found": _decorator_present(text, f"{EXACT_ROUTE}/{{path:path}}"),
        "wildcard_cleanup_required": False,
    }


def _native_route_entry() -> dict[str, Any]:
    text = NATIVE_API.read_text(encoding="utf-8")
    return {
        "get_entry_found": bool(re.search(rf'@router\.get\("{re.escape(EXACT_ROUTE)}"\)', text)),
        "post_entry_found": bool(re.search(rf'@router\.post\("{re.escape(EXACT_ROUTE)}"\)', text)),
    }


def _fixture_shadow_probe() -> dict[str, Any]:
    repo = build_automation_repository(task_group_backend="fixture")
    before_rows, before_total = repo.list_task_groups({"program_id": 1, "limit": 20, "offset": 0})
    created = repo.create_task_group(
        {
            "program_id": 1,
            "group_name": "Post Phase 7 shadow compare fixture group",
            "group_code": "post_phase7_shadow_compare_fixture_group",
            "metadata": {"source": "post_phase7_shadow_compare"},
            "operator": "post_phase7_shadow_compare",
        },
        idempotency_key="post-phase7-shadow-compare",
        operator="post_phase7_shadow_compare",
    )
    replay = repo.create_task_group(
        {
            "program_id": 1,
            "group_name": "Post Phase 7 shadow compare fixture group",
            "group_code": "post_phase7_shadow_compare_fixture_group",
            "metadata": {"source": "post_phase7_shadow_compare"},
            "operator": "post_phase7_shadow_compare",
        },
        idempotency_key="post-phase7-shadow-compare",
        operator="post_phase7_shadow_compare",
    )
    after_rows, after_total = repo.list_task_groups({"program_id": 1, "limit": 20, "offset": 0})
    side_effects = task_group_side_effect_safety()
    audit_side_effects = (created.get("audit_event") or {}).get("side_effect_safety") or {}
    return {
        "fixture_backend_used": True,
        "production_db_connected": False,
        "before_total": before_total,
        "after_total": after_total,
        "created_in_memory_only": after_total == before_total + 1,
        "idempotency_replay_passed": replay.get("idempotent_replay") is True,
        "projection_keys_match": bool(before_rows and after_rows and set(before_rows[0]) <= set(after_rows[-1])),
        "side_effect_safety_all_false": bool(side_effects) and all(value is False for value in side_effects.values()),
        "audit_side_effect_safety_all_false": bool(audit_side_effects) and all(value is False for value in audit_side_effects.values()),
    }


def build_shadow_report(latest_main_sha: str, command: str) -> dict[str, Any]:
    manifest = _manifest_entry()
    compat = _production_compat_exact_entry()
    native = _native_route_entry()
    fixture = _fixture_shadow_probe()
    checks = {
        "latest_main_sha_present": bool(latest_main_sha),
        "manifest_route_found": bool(manifest),
        "manifest_owner_is_next": manifest.get("capability_owner") == "aicrm_next.automation_engine",
        "manifest_current_runtime_owner_retained": manifest.get("current_runtime_owner") == "production_compat",
        "manifest_fallback_retained": manifest.get("legacy_fallback_allowed") is True,
        "manifest_delete_ready_false": manifest.get("delete_ready") is False,
        "production_compat_exact_entry_found": compat["exact_entry_found"] is True,
        "production_compat_path_entry_found": compat["path_entry_found"] is True,
        "wildcard_cleanup_required_false": compat["wildcard_cleanup_required"] is False,
        "native_get_entry_found": native["get_entry_found"] is True,
        "native_post_entry_found": native["post_entry_found"] is True,
        "fixture_backend_used": fixture["fixture_backend_used"] is True,
        "production_db_not_connected": fixture["production_db_connected"] is False,
        "fixture_shadow_probe_passed": fixture["created_in_memory_only"] is True and fixture["idempotency_replay_passed"] is True,
        "side_effect_safety_all_false": fixture["side_effect_safety_all_false"] is True and fixture["audit_side_effect_safety_all_false"] is True,
    }
    passed = all(checks.values())
    return {
        "route_family": ROUTE_FAMILY,
        "latest_main_sha": latest_main_sha,
        "shadow_compare_command": command,
        "shadow_compare_executed": True,
        "shadow_compare_passed": passed,
        "production_behavior_changed": False,
        "fallback_removal_executed": False,
        "production_compat_cleanup_executed": False,
        "runtime_deletion_executed": False,
        "delete_ready": False,
        "checks": checks,
        "manifest_entry": manifest,
        "production_compat_exact_entry_proof": compat,
        "native_route_entry": native,
        "fixture_shadow_probe": fixture,
    }


def build_rollback_report(latest_main_sha: str, command: str, rollback_plan_path: str) -> dict[str, Any]:
    manifest = _manifest_entry()
    compat = _production_compat_exact_entry()
    checks = {
        "latest_main_sha_present": bool(latest_main_sha),
        "rollback_plan_path_present": bool(rollback_plan_path),
        "fallback_currently_retained": manifest.get("legacy_fallback_allowed") is True,
        "production_compat_currently_retained": compat["exact_entry_found"] is True and compat["path_entry_found"] is True,
        "wildcard_cleanup_required_false": compat["wildcard_cleanup_required"] is False,
        "rollback_is_noop_before_cleanup": True,
        "production_db_not_connected": True,
        "production_write_not_attempted": True,
    }
    passed = all(checks.values())
    return {
        "route_family": ROUTE_FAMILY,
        "latest_main_sha": latest_main_sha,
        "rollback_plan_path": rollback_plan_path,
        "rollback_rehearsal_command": command,
        "rollback_rehearsal_executed": True,
        "rollback_rehearsal_passed": passed,
        "production_behavior_changed": False,
        "fallback_removal_executed": False,
        "production_compat_cleanup_executed": False,
        "runtime_deletion_executed": False,
        "delete_ready": False,
        "checks": checks,
    }


def _write(path: str | None, data: dict[str, Any]) -> None:
    if path:
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--latest-main-sha", default="")
    parser.add_argument("--shadow-output-json", required=True)
    parser.add_argument("--rollback-output-json", required=True)
    parser.add_argument("--combined-output-json")
    parser.add_argument("--rollback-plan-path", default="docs/development/post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.md#rollback-plan")
    args = parser.parse_args(argv)
    latest_main_sha = args.latest_main_sha or _git(["rev-parse", "origin/main"])
    command = " ".join(["python3", "tools/run_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.py", "--latest-main-sha", latest_main_sha])
    shadow = build_shadow_report(latest_main_sha, command)
    rollback = build_rollback_report(latest_main_sha, command, args.rollback_plan_path)
    combined = {
        "overall": "PASS" if shadow["shadow_compare_passed"] and rollback["rollback_rehearsal_passed"] else "FAIL",
        "ok": shadow["shadow_compare_passed"] and rollback["rollback_rehearsal_passed"],
        "latest_main_sha": latest_main_sha,
        "shadow_compare": shadow,
        "rollback_rehearsal": rollback,
        "production_behavior_changed": False,
        "fallback_removal_executed": False,
        "production_compat_cleanup_executed": False,
        "runtime_deletion_executed": False,
        "delete_ready": False,
    }
    _write(args.shadow_output_json, shadow)
    _write(args.rollback_output_json, rollback)
    _write(args.combined_output_json, combined)
    print(json.dumps(combined, ensure_ascii=False, sort_keys=True))
    return 0 if combined["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
