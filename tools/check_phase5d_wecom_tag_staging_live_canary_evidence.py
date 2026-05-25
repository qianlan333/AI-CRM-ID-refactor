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


DOC = ROOT / "docs/development/phase_5d_wecom_tag_staging_live_canary_evidence.md"
PLAN_YAML = ROOT / "docs/development/phase_5d_wecom_tag_staging_live_canary_evidence.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STAGING_RUNNER = ROOT / "tools/run_phase5d_wecom_tag_staging_live_canary_evidence.py"
PRODUCTION_REVIEW_RUNNER = ROOT / "tools/run_phase5d_wecom_tag_production_live_readiness_review.py"
TEST = ROOT / "tests/test_phase5d_wecom_tag_staging_live_canary_evidence.py"
ROUTE_FAMILY = "/api/admin/wecom/tags*"
CAPABILITY_OWNER = "aicrm_next.customer_tags"
BUNDLE_TYPE = "phase_5_external_adapter_staging_live_canary_evidence_bundle"
NEXT_BUNDLE = "phase_5e_wecom_tag_production_canary_readiness_bundle"
COMPLETED_STEP = "phase_5d_wecom_tag_staging_live_canary_evidence_completed"
REQUIRED_ENV = {
    "AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED",
    "AICRM_WECOM_TAG_LIVE_CALL_APPROVED",
    "AICRM_WECOM_TAG_CONFIG_REVIEWED",
    "AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_APPROVED",
    "AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_TARGET_APPROVED",
}
REQUIRED_ARGS = {
    "--execute-staging-canary",
    "--confirm-live-wecom-call",
    "--confirm-staging-only",
    "--confirm-approved-target",
    "--idempotency-key",
    "--external-userid",
    "--tag-id",
}
REQUIRED_BLOCKED_STATUSES = {
    "not_executed_missing_live_adapter_enabled",
    "not_executed_missing_live_call_approval",
    "not_executed_missing_config_review",
    "not_executed_missing_staging_canary_approval",
    "not_executed_missing_target_approval",
    "not_executed_missing_external_userid",
    "not_executed_missing_tag_id",
    "not_executed_missing_idempotency_key",
    "not_executed_missing_confirm_live_call",
    "not_executed_missing_confirm_staging_only",
    "not_executed_missing_confirm_approved_target",
}
FORBIDDEN_DOC_CLAIMS = {
    "production canary approved",
    "production tag write enabled",
    "fallback removed",
    "production_compat changed",
    "delete_ready true",
    "delete_ready: true",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5d_wecom_tag_staging_live_canary_evidence.md",
    "docs/development/phase_5d_wecom_tag_staging_live_canary_evidence.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5d_wecom_tag_staging_live_canary_evidence.py",
    "tools/run_phase5d_wecom_tag_production_live_readiness_review.py",
    "tools/check_phase5d_wecom_tag_staging_live_canary_evidence.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5d_wecom_tag_staging_live_canary_evidence.py",
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


def _staging_runner_blockers() -> list[str]:
    blockers: list[str] = []
    text = STAGING_RUNNER.read_text(encoding="utf-8")
    for arg in {"--output-json", "--output-md"} | REQUIRED_ARGS:
        if arg not in text:
            blockers.append(f"staging runner missing required arg support: {arg}")
    for env in REQUIRED_ENV | {"AICRM_WECOM_TAG_CORP_ID", "AICRM_WECOM_TAG_AGENT_SECRET"}:
        if env not in text:
            blockers.append(f"staging runner missing required env gate: {env}")
    for status in REQUIRED_BLOCKED_STATUSES:
        if status not in text:
            blockers.append(f"staging runner missing blocked status: {status}")
    for token in (
        "not_executed_batch_target_rejected",
        "_redact_external_userid",
        "phase5c_staging.build_report",
        "cleanup_rollback_guidance",
        "live_call_executed",
        "production_compat_changed",
        "fallback_removed",
    ):
        if token not in text:
            blockers.append(f"staging runner missing safety token: {token}")
    forbidden_calls = sorted({"send", "send_welcome_msg", "create_group_message_task", "oauth_callback", "payment", "upload_media", "openclaw", "mcp_dispatch"} & _call_names(STAGING_RUNNER))
    if forbidden_calls:
        blockers.append(f"staging runner contains forbidden side-effect calls: {forbidden_calls}")
    return blockers


def _production_review_blockers() -> list[str]:
    blockers: list[str] = []
    text = PRODUCTION_REVIEW_RUNNER.read_text(encoding="utf-8")
    for arg in ("--output-json", "--output-md", "--staging-evidence-json", "--confirm-no-production-live-call"):
        if arg not in text:
            blockers.append(f"production readiness review missing required arg support: {arg}")
    for token in (
        "ready_for_phase5e_production_canary_planning",
        "production_live_call_executed",
        "production_tag_write_executed",
        "route_owner_changed",
        "production_compat_changed",
        "fallback_removed",
    ):
        if token not in text:
            blockers.append(f"production readiness review missing output field: {token}")
    forbidden_text = {
        "run_phase5c_wecom_tag_live_staging_evidence",
        "wecom_tag_live_adapter",
        "wecom_tag_live_gateway",
        "urlopen",
        "externalcontact/mark_tag",
        "externalcontact/get_corp_tag_list",
    }
    found = sorted(token for token in forbidden_text if token in text)
    if found:
        blockers.append(f"production readiness review must never call WeCom: {found}")
    forbidden_calls = sorted({"send", "send_welcome_msg", "create_group_message_task", "oauth_callback", "payment", "upload_media", "openclaw", "mcp_dispatch"} & _call_names(PRODUCTION_REVIEW_RUNNER))
    if forbidden_calls:
        blockers.append(f"production readiness review contains forbidden side-effect calls: {forbidden_calls}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}
    required = [DOC, PLAN_YAML, STATE, STAGING_RUNNER, PRODUCTION_REVIEW_RUNNER, TEST]
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
    if data.get("status") != "phase_5d_wecom_tag_staging_live_canary_evidence":
        blockers.append("status must be phase_5d_wecom_tag_staging_live_canary_evidence")
    if data.get("bundle_type") != BUNDLE_TYPE:
        blockers.append(f"bundle_type must be {BUNDLE_TYPE}")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"route_family must be {ROUTE_FAMILY}")
    if data.get("capability_owner") != CAPABILITY_OWNER:
        blockers.append(f"capability_owner must be {CAPABILITY_OWNER}")

    authorizations = _dict(data.get("authorizations"))
    if authorizations.get("staging_live_canary_possible_with_approval") is not True:
        blockers.append("staging_live_canary_possible_with_approval must be true")
    for key in (
        "production_live_wecom_call_authorized",
        "production_tag_write_authorized",
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
        "production_canary_approved",
        "delete_ready",
    ):
        if authorizations.get(key) is not False:
            blockers.append(f"authorization {key} must be false")

    staging_canary = _dict(data.get("staging_canary"))
    if staging_canary.get("runner") != "tools/run_phase5d_wecom_tag_staging_live_canary_evidence.py":
        blockers.append("staging_canary runner path mismatch")
    if staging_canary.get("default_blocked") is not True:
        blockers.append("staging_canary default_blocked must be true")
    missing_env = sorted(REQUIRED_ENV - _strings(staging_canary.get("required_env")))
    if missing_env:
        blockers.append(f"staging_canary required_env missing: {missing_env}")
    missing_args = sorted(REQUIRED_ARGS - _strings(staging_canary.get("required_args")))
    if missing_args:
        blockers.append(f"staging_canary required_args missing: {missing_args}")

    target_safety = _dict(data.get("target_safety"))
    expected_target_safety = {
        "single_target_only": True,
        "batch_targets_allowed": False,
        "target_approval_required": True,
        "external_userid_redaction_required": True,
        "raw_token_output_forbidden": True,
        "raw_secret_output_forbidden": True,
    }
    for key, expected in expected_target_safety.items():
        if target_safety.get(key) is not expected:
            blockers.append(f"target_safety {key} must be {expected}")

    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety {key} must be false")

    production_review = _dict(data.get("production_readiness_review"))
    if production_review.get("runner") != "tools/run_phase5d_wecom_tag_production_live_readiness_review.py":
        blockers.append("production readiness review runner path mismatch")
    for key in ("production_live_call_executed", "production_tag_write_executed"):
        if production_review.get(key) is not False:
            blockers.append(f"production_readiness_review {key} must be false")
    if production_review.get("requires_staging_evidence_json") is not True:
        blockers.append("production readiness review must require staging evidence json")

    business_continuity = _dict(data.get("business_continuity"))
    for key in ("production_behavior_unchanged", "legacy_fallback_retained", "production_compat_unchanged"):
        if business_continuity.get(key) is not True:
            blockers.append(f"business_continuity {key} must be true")
    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle recommended_next_step must be {NEXT_BUNDLE}")

    for phrase in FORBIDDEN_DOC_CLAIMS:
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    blockers.extend(_staging_runner_blockers())
    blockers.extend(_production_review_blockers())

    if state.get("last_merged_pr") != "#714":
        blockers.append("last_merged_pr must record latest completed merged PR #714")
    if state.get("last_attempted_action") != "phase_5d_wecom_tag_staging_live_canary_evidence_bundle":
        blockers.append("last_attempted_action must record Phase 5D bundle")
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
        blockers.append(f"changed files outside Phase 5D allowlist: {unexpected}")

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
        "# Phase 5D WeCom Tag Staging Live Canary Evidence Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 5D WeCom tag staging live canary evidence bundle.")
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
