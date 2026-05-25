#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml


DOC = ROOT / "docs/development/phase_5g_wecom_tag_family_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_5g_wecom_tag_family_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5g_wecom_tag_family_acceptance.py"
ROUTE_FAMILY = "/api/admin/wecom/tags*"
CAPABILITY_OWNER = "aicrm_next.customer_tags"
BUNDLE_TYPE = "phase_5_external_adapter_family_acceptance_bundle"
NEXT_BUNDLE = "phase_5h_wecom_customer_contact_adapter_contract_bundle"
NEXT_ROUTE_FAMILY = "/wecom/external-contact/callback"
COMPLETED_STEP = "phase_5g_wecom_tag_family_acceptance_completed"
REQUIRED_STAGES = {
    "phase_5a_contract",
    "phase_5b_fake_stub_runtime",
    "phase_5c_live_adapter_behind_flag",
    "phase_5d_staging_live_canary_evidence_gate",
    "phase_5e_production_canary_readiness",
    "phase_5f_production_live_canary_tooling",
}
REQUIRED_MATRIX = {
    "adapter_contract_complete": True,
    "fake_stub_complete": True,
    "live_adapter_behind_flag_complete": True,
    "staging_canary_gate_complete": True,
    "production_canary_readiness_complete": True,
    "production_live_canary_tooling_complete": True,
    "cleanup_runner_complete": True,
    "route_owner_switched": False,
    "fallback_removed": False,
    "production_compat_changed": False,
    "bulk_write_enabled": False,
    "outbound_send_enabled": False,
}
ALLOWED_ACCEPTANCE = {
    "accepted_for_controlled_canary_tooling",
    "accepted_with_blocked_evidence_only",
    "needs_followup_before_family_acceptance",
}
REQUIRED_ROLLOUT = {
    "wider_rollout_authorized": False,
    "batch_tagging_authorized": False,
    "automatic_segment_tagging_authorized": False,
    "route_owner_switch_deferred": True,
    "fallback_removal_deferred": True,
    "production_compat_change_deferred": True,
    "delete_ready": False,
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5g_wecom_tag_family_acceptance.md",
    "docs/development/phase_5g_wecom_tag_family_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase5g_wecom_tag_family_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5g_wecom_tag_family_acceptance.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_EXACT_CHANGED = {
    "aicrm_next/main.py",
    "aicrm_next/customer_tags/wecom_tag_live_adapter.py",
    "aicrm_next/integration_gateway/wecom_tag_live_gateway.py",
}
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


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}
    required = [DOC, PLAN_YAML, STATE, TEST]
    for path in required:
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)

    if data.get("version") != 1:
        blockers.append("version must be 1")
    if data.get("status") != "phase_5g_wecom_tag_family_acceptance_no_new_live_call":
        blockers.append("status must be phase_5g_wecom_tag_family_acceptance_no_new_live_call")
    if data.get("bundle_type") != BUNDLE_TYPE:
        blockers.append(f"bundle_type must be {BUNDLE_TYPE}")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"route_family must be {ROUTE_FAMILY}")
    if data.get("capability_owner") != CAPABILITY_OWNER:
        blockers.append(f"capability_owner must be {CAPABILITY_OWNER}")

    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorization {key} must be false")

    stages = _list(data.get("completed_stages"))
    stage_by_name = {str(_dict(item).get("stage")): _dict(item) for item in stages}
    missing_stages = sorted(REQUIRED_STAGES - set(stage_by_name))
    if missing_stages:
        blockers.append(f"completed_stages missing Phase 5A-5F entries: {missing_stages}")
    for stage in REQUIRED_STAGES & set(stage_by_name):
        item = stage_by_name[stage]
        if item.get("complete") is not True:
            blockers.append(f"{stage} complete must be true")
        for key in ("live_behavior_enabled_by_default", "owner_switch", "fallback_removal"):
            if item.get(key) is not False:
                blockers.append(f"{stage} {key} must be false")

    matrix = _dict(data.get("capability_matrix"))
    for key, expected in REQUIRED_MATRIX.items():
        if matrix.get(key) is not expected:
            blockers.append(f"capability_matrix {key} must be {expected}")

    acceptance = _dict(data.get("acceptance_decision"))
    allowed_values = _strings(acceptance.get("allowed_values"))
    if acceptance.get("status") not in ALLOWED_ACCEPTANCE:
        blockers.append("acceptance_decision.status must be an allowed value")
    if not ALLOWED_ACCEPTANCE <= allowed_values:
        blockers.append("acceptance_decision.allowed_values must include every allowed status")
    if acceptance.get("production_canary_passed") is not False:
        blockers.append("production_canary_passed must be false unless verified evidence is added")
    if acceptance.get("wider_rollout_authorized") is not False:
        blockers.append("wider_rollout_authorized must be false")

    rollout = _dict(data.get("rollout_boundary"))
    for key, expected in REQUIRED_ROLLOUT.items():
        if rollout.get(key) is not expected:
            blockers.append(f"rollout_boundary {key} must be {expected}")

    next_family = _dict(data.get("next_family"))
    for key in ("selected_next_bundle", "route_family", "capability_owner", "why_selected", "first_safe_step"):
        if not next_family.get(key):
            blockers.append(f"next_family {key} is required")
    if next_family.get("selected_next_bundle") != NEXT_BUNDLE:
        blockers.append(f"next_family selected_next_bundle must be {NEXT_BUNDLE}")
    if next_family.get("route_family") != NEXT_ROUTE_FAMILY:
        blockers.append(f"next_family route_family must be {NEXT_ROUTE_FAMILY}")
    if next_family.get("live_external_call_allowed") is not False:
        blockers.append("next_family live_external_call_allowed must be false")
    if not _list(next_family.get("required_guardrails")):
        blockers.append("next_family required_guardrails must be nonempty")

    continuity = _dict(data.get("business_continuity"))
    for key, value in continuity.items():
        if value is not True:
            blockers.append(f"business_continuity {key} must be true")
    for key in ("production_behavior_unchanged_except_explicit_canary_tooling", "legacy_fallback_retained", "production_compat_unchanged", "no_wider_rollout_enabled"):
        if continuity.get(key) is not True:
            blockers.append(f"business_continuity {key} must be true")

    if state.get("last_merged_pr") != "#717":
        blockers.append("last_merged_pr must record latest completed merged PR #717")
    if state.get("last_attempted_action") != "phase_5g_wecom_tag_family_acceptance_bundle":
        blockers.append("last_attempted_action must record Phase 5G bundle")
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
        blockers.append(f"changed files outside Phase 5G allowlist: {unexpected}")

    details["changed_files"] = sorted(changed)
    details["acceptance_decision"] = acceptance.get("status")
    details["next_family"] = {
        "selected_next_bundle": next_family.get("selected_next_bundle"),
        "route_family": next_family.get("route_family"),
    }
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
        "# Phase 5G WeCom Tag Family Acceptance Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 5G WeCom tag family acceptance bundle.")
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
