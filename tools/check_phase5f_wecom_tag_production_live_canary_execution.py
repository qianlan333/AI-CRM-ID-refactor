#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml


DOC = ROOT / "docs/development/phase_5f_wecom_tag_production_live_canary_execution.md"
PLAN_YAML = ROOT / "docs/development/phase_5f_wecom_tag_production_live_canary_execution.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
CANARY_RUNNER = ROOT / "tools/run_phase5f_wecom_tag_production_live_canary_execution.py"
CLEANUP_RUNNER = ROOT / "tools/run_phase5f_wecom_tag_production_canary_cleanup.py"
TEST = ROOT / "tests/test_phase5f_wecom_tag_production_live_canary_execution.py"
ROUTE_FAMILY = "/api/admin/wecom/tags*"
CAPABILITY_OWNER = "aicrm_next.customer_tags"
BUNDLE_TYPE = "phase_5_external_adapter_production_live_canary_execution_bundle"
NEXT_BUNDLE = "phase_5g_wecom_tag_family_acceptance_bundle"
COMPLETED_STEP = "phase_5f_wecom_tag_production_live_canary_execution_completed"
REQUIRED_CANARY_ENV = {
    "AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED",
    "AICRM_WECOM_TAG_LIVE_CALL_APPROVED",
    "AICRM_WECOM_TAG_CONFIG_REVIEWED",
    "AICRM_PHASE5F_WECOM_TAG_PRODUCTION_CANARY_APPROVED",
    "AICRM_PHASE5F_WECOM_TAG_PRODUCTION_TARGET_APPROVED",
    "AICRM_PHASE5F_WECOM_TAG_ROLLBACK_OWNER_APPROVED",
    "AICRM_PHASE5F_WECOM_TAG_CLEANUP_STRATEGY_APPROVED",
}
REQUIRED_CANARY_ARGS = {
    "--phase5e-readiness-json",
    "--staging-evidence-json",
    "--external-userid",
    "--tag-id",
    "--idempotency-key",
    "--confirm-production-live-wecom-call",
    "--confirm-single-approved-target",
    "--confirm-single-approved-tag",
    "--confirm-rollback-owner-approved",
    "--confirm-no-batch-target",
    "--confirm-no-outbound-send",
}
FORBIDDEN_DOC_CLAIMS = {
    "route owner switched",
    "fallback removed",
    "bulk tag enabled",
    "delete_ready true",
    "delete_ready: true",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5f_wecom_tag_production_live_canary_execution.md",
    "docs/development/phase_5f_wecom_tag_production_live_canary_execution.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5f_wecom_tag_production_live_canary_execution.py",
    "tools/run_phase5f_wecom_tag_production_canary_cleanup.py",
    "tools/check_phase5f_wecom_tag_production_live_canary_execution.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5f_wecom_tag_production_live_canary_execution.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_EXACT_CHANGED = {"aicrm_next/main.py"}
FORBIDDEN_CHANGED_PREFIXES = (
    "aicrm_next/production_compat/",
    "wecom_ability_service/",
    "deploy/",
    "nginx/",
    "systemd/",
    "migrations/",
)


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only"], ["diff", "--name-only", "--cached"]):
        ok, stdout, stderr = _run_git(args)
        if ok:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
        else:
            warnings.append(f"git {' '.join(args)} unavailable: {(stderr or stdout).strip()}")
    ok, stdout, stderr = _run_git(["ls-files", "--others", "--exclude-standard"])
    if ok:
        changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    else:
        warnings.append(f"git ls-files --others unavailable: {(stderr or stdout).strip()}")
    return changed, warnings


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> set[str]:
    return {str(item) for item in _list(value)}


def _call_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _runner_blockers(path: Path, *, cleanup: bool = False) -> list[str]:
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8")
    for arg in ("--output-json", "--output-md"):
        if arg not in text:
            blockers.append(f"{path.relative_to(ROOT)} missing {arg}")
    for token in (
        "route_owner_changed",
        "production_compat_changed",
        "fallback_removed",
        "outbound_send_executed",
        "side_effect_safety",
    ):
        if token not in text:
            blockers.append(f"{path.relative_to(ROOT)} missing safety output token {token}")
    forbidden_calls = sorted({"send", "send_welcome_msg", "create_group_message_task", "oauth_callback", "payment", "upload_media", "openclaw", "mcp_dispatch"} & _call_names(path))
    if forbidden_calls:
        blockers.append(f"{path.relative_to(ROOT)} contains forbidden side-effect calls: {forbidden_calls}")
    if "production_compat/" in text or "route_owner_changed\": True" in text:
        blockers.append(f"{path.relative_to(ROOT)} must not modify production_compat or route ownership")
    if cleanup:
        for arg in ("--canary-evidence-json", "--confirm-production-cleanup-live-wecom-call", "--confirm-same-target-and-same-tag", "--confirm-rollback-owner-approved", "--confirm-no-batch-cleanup"):
            if arg not in text:
                blockers.append(f"cleanup runner missing required arg {arg}")
        for token in ("batch_cleanup_executed", "same_target_and_tag_confirmed", "automatic_cleanup"):
            if token not in text:
                blockers.append(f"cleanup runner missing cleanup safety token {token}")
    else:
        for arg in REQUIRED_CANARY_ARGS:
            if arg not in text:
                blockers.append(f"canary runner missing required arg {arg}")
        for env in REQUIRED_CANARY_ENV | {"AICRM_WECOM_TAG_CORP_ID", "AICRM_WECOM_TAG_AGENT_SECRET"}:
            if env not in text:
                blockers.append(f"canary runner missing required env gate {env}")
        for token in ("not_executed_missing_confirm_no_batch", "not_executed_missing_confirm_no_outbound_send", "mark_tags_live", "target_count", "tag_count"):
            if token not in text:
                blockers.append(f"canary runner missing required token {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}
    required = [DOC, PLAN_YAML, STATE, CANARY_RUNNER, CLEANUP_RUNNER, TEST]
    for path in required:
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()

    if data.get("version") != 1:
        blockers.append("version must be 1")
    if data.get("status") != "phase_5f_wecom_tag_production_live_canary_execution_bundle":
        blockers.append("status must be phase_5f_wecom_tag_production_live_canary_execution_bundle")
    if data.get("bundle_type") != BUNDLE_TYPE:
        blockers.append(f"bundle_type must be {BUNDLE_TYPE}")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"route_family must be {ROUTE_FAMILY}")
    if data.get("capability_owner") != CAPABILITY_OWNER:
        blockers.append(f"capability_owner must be {CAPABILITY_OWNER}")

    authorizations = _dict(data.get("authorizations"))
    if authorizations.get("production_live_canary_tooling_authorized") is not True:
        blockers.append("production_live_canary_tooling_authorized must be true")
    for key in (
        "production_live_wecom_call_by_default_authorized",
        "production_bulk_tag_write_authorized",
        "production_owner_switch_authorized",
        "production_compat_change_authorized",
        "fallback_removal_authorized",
        "outbound_send_authorized",
        "oauth_callback_cutover_authorized",
        "payment_behavior_authorized",
        "media_live_upload_authorized",
        "openclaw_mcp_live_call_authorized",
        "timer_execution_authorized",
        "automation_execution_authorized",
        "delete_ready",
    ):
        if authorizations.get(key) is not False:
            blockers.append(f"authorization {key} must be false")

    canary = _dict(data.get("production_canary"))
    if canary.get("runner") != "tools/run_phase5f_wecom_tag_production_live_canary_execution.py":
        blockers.append("production_canary runner path mismatch")
    for key, expected in (
        ("default_blocked", True),
        ("single_target_only", True),
        ("single_tag_only", True),
        ("batch_targets_allowed", False),
        ("requires_phase5e_readiness_json", True),
        ("requires_staging_evidence_json", True),
    ):
        if canary.get(key) is not expected:
            blockers.append(f"production_canary {key} must be {expected}")
    missing_env = sorted(REQUIRED_CANARY_ENV - _strings(canary.get("required_env")))
    if missing_env:
        blockers.append(f"production_canary required_env missing: {missing_env}")
    missing_args = sorted(REQUIRED_CANARY_ARGS - _strings(canary.get("required_args")))
    if missing_args:
        blockers.append(f"production_canary required_args missing: {missing_args}")

    cleanup = _dict(data.get("cleanup"))
    for key, expected in (
        ("default_blocked", True),
        ("same_target_and_same_tag_only", True),
        ("batch_cleanup_allowed", False),
        ("automatic_cleanup_allowed", False),
        ("cleanup_requires_explicit_approval", True),
        ("cleanup_evidence_required", True),
    ):
        if cleanup.get(key) is not expected:
            blockers.append(f"cleanup {key} must be {expected}")

    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety {key} must be false")
    continuity = _dict(data.get("business_continuity"))
    for key in ("production_behavior_unchanged_except_explicit_canary", "legacy_fallback_retained", "production_compat_unchanged", "route_owner_unchanged"):
        if continuity.get(key) is not True:
            blockers.append(f"business_continuity {key} must be true")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle recommended_next_step must be {NEXT_BUNDLE}")

    for phrase in FORBIDDEN_DOC_CLAIMS:
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    blockers.extend(_runner_blockers(CANARY_RUNNER))
    blockers.extend(_runner_blockers(CLEANUP_RUNNER, cleanup=True))

    if state.get("last_merged_pr") != "#716":
        blockers.append("last_merged_pr must record latest completed merged PR #716")
    if state.get("last_attempted_action") != "phase_5f_wecom_tag_production_live_canary_execution_bundle":
        blockers.append("last_attempted_action must record Phase 5F bundle")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"recommended_next_pr must be {NEXT_BUNDLE}")
    if _strings(state.get("next_allowed_actions")) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be exactly {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in _strings(state.get("completed_steps")):
        blockers.append(f"completed_steps must include {COMPLETED_STEP}")

    changed, changed_warnings = _changed_files()
    warnings.extend(changed_warnings)
    forbidden_exact = sorted(changed & FORBIDDEN_EXACT_CHANGED)
    if forbidden_exact:
        blockers.append(f"forbidden exact changed files: {forbidden_exact}")
    forbidden_prefix = sorted(path for path in changed if path.startswith(FORBIDDEN_CHANGED_PREFIXES))
    if forbidden_prefix:
        blockers.append(f"forbidden changed file prefixes: {forbidden_prefix}")
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5F allowlist: {unexpected}")

    details["changed_files"] = sorted(changed)
    return {
        "overall": "PASS" if not blockers else "FAIL",
        "ok": not blockers,
        "autopilot_deliverable": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "details": details,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5F WeCom Tag Production Live Canary Execution Check",
        "",
        f"- overall: {report['overall']}",
        f"- ok: {str(report['ok']).lower()}",
        f"- autopilot_deliverable: {str(report['autopilot_deliverable']).lower()}",
        f"- blockers: {len(report['blockers'])}",
        f"- warnings: {len(report['warnings'])}",
    ]
    if report["blockers"]:
        lines.append("")
        lines.append("## Blockers")
        for blocker in report["blockers"]:
            lines.append(f"- {blocker}")
    if report["warnings"]:
        lines.append("")
        lines.append("## Warnings")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Phase 5F WeCom tag production live canary execution bundle.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report()
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
