#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4cv_phase5_readiness_entry.md"
PLAN_YAML = ROOT / "docs/development/phase_4cv_phase5_readiness_entry.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase4cv_phase5_readiness_entry.py"
ROUTE_FAMILY = "phase_5_external_adapter_entry"
NEXT_BUNDLE = "phase_5a_wecom_tag_adapter_contract_bundle"
NEXT_ROUTE_FAMILY = "/api/admin/wecom/tags*"
REQUIRED_FAMILIES = {
    "wecom_adapter",
    "oauth_identity",
    "payment_commerce",
    "media_library",
    "openclaw_mcp_ai_assist",
    "questionnaire_public_or_external_submit",
}
REQUIRED_ALLOWED_SCOPE = {
    "adapter_contract",
    "fake_adapter",
    "stub_adapter",
    "signature_validation_contract",
    "idempotency_policy",
    "retry_policy",
    "staging_smoke_package",
    "production_dry_run_package",
    "owner_approval_gate",
}
REQUIRED_FORBIDDEN_SCOPE = {
    "live_external_call",
    "production_send",
    "payment_capture",
    "oauth_callback_cutover",
    "media_live_upload",
    "openclaw_mcp_live_call",
    "production_owner_switch",
    "fallback_removal",
    "production_compat_narrowing",
    "timer_execution",
    "automation_execution",
    "delete_ready",
}
ALLOWED_CHANGED = {
    "docs/development/phase_4cv_phase5_readiness_entry.md",
    "docs/development/phase_4cv_phase5_readiness_entry.yaml",
    "tools/check_phase4cv_phase5_readiness_entry.py",
    "tests/test_phase4cv_phase5_readiness_entry.py",
    "docs/development/phase_execution_state.yaml",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"aicrm_next/main.py", "aicrm_next/production_compat/api.py", "app.py", "legacy_flask_app.py"}


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ModuleNotFoundError:
        if str(ROOT) not in sys.path:
            sys.path[:0] = [str(ROOT)]
        from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml as fallback

        return fallback(path)


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
    ok, stdout, _ = _run_git(["ls-files", "--others", "--exclude-standard"])
    if ok:
        changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    return changed, warnings


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_set(value: Any) -> set[str]:
    return {str(item) for item in _list_or_empty(value)}


def _guardrail_items(value: Any) -> list[str]:
    return [str(item.get("item")) for item in _list_or_empty(value) if isinstance(item, dict) and item.get("item")]


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    for path in (DOC, PLAN_YAML, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": {}}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()

    if data.get("status") != "phase_4cv_phase5_readiness_entry_no_runtime_change":
        blockers.append("status must be phase_4cv_phase5_readiness_entry_no_runtime_change")
    if data.get("bundle_type") != "phase_5_readiness_entry_bundle":
        blockers.append("bundle_type must be phase_5_readiness_entry_bundle")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append("route_family must be phase_5_external_adapter_entry")

    authorizations = _dict_or_empty(data.get("authorizations"))
    if not authorizations:
        blockers.append("authorizations must be present")
    for key, value in sorted(authorizations.items()):
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    handoff = _dict_or_empty(data.get("phase_4_handoff"))
    for field in (
        "internal_write_readiness_accepted",
        "production_owner_switch_deferred",
        "fallback_removal_deferred",
        "production_compat_narrowing_deferred",
        "blocked_evidence_expected_until_owner_config_approval",
    ):
        if handoff.get(field) is not True:
            blockers.append(f"phase_4_handoff.{field} must be true")

    scope = _dict_or_empty(data.get("phase_5_scope"))
    if not REQUIRED_ALLOWED_SCOPE <= _as_set(scope.get("allowed")):
        blockers.append("phase_5_scope.allowed missing required contract-first items")
    if not REQUIRED_FORBIDDEN_SCOPE <= _as_set(scope.get("forbidden")):
        blockers.append("phase_5_scope.forbidden missing required live/production exclusions")

    families = _list_or_empty(data.get("external_adapter_families"))
    family_names = {item.get("family") for item in families if isinstance(item, dict)}
    missing_families = sorted(REQUIRED_FAMILIES - family_names)
    if missing_families:
        blockers.append(f"external_adapter_families missing required entries: {missing_families}")
    for item in families:
        if not isinstance(item, dict):
            blockers.append("external_adapter_families entries must be mappings")
            continue
        family = item.get("family")
        if not item.get("capability_owner"):
            blockers.append(f"{family} missing capability_owner")
        if item.get("risk_type") not in {"adapter_contract", "external_side_effect"}:
            blockers.append(f"{family} risk_type must be adapter_contract or external_side_effect")
        if item.get("live_call_allowed") is not False:
            blockers.append(f"{family}.live_call_allowed must be false")
        if not item.get("first_safe_step"):
            blockers.append(f"{family} missing first_safe_step")
        if not _guardrail_items(item.get("required_guardrails")):
            blockers.append(f"{family} must include required_guardrails item entries")

    candidate = _dict_or_empty(data.get("first_phase5_candidate"))
    if candidate.get("selected_candidate") != "wecom_tag_adapter_contract_planning":
        blockers.append("first_phase5_candidate.selected_candidate must be wecom_tag_adapter_contract_planning")
    if candidate.get("route_family_or_capability") != NEXT_ROUTE_FAMILY:
        blockers.append("first_phase5_candidate.route_family_or_capability must be /api/admin/wecom/tags*")
    if candidate.get("capability_owner") != "aicrm_next.customer_tags":
        blockers.append("first_phase5_candidate.capability_owner must be aicrm_next.customer_tags")
    for field in ("live_external_call_allowed", "production_owner_switch_allowed", "fallback_removal_allowed"):
        if candidate.get(field) is not False:
            blockers.append(f"first_phase5_candidate.{field} must be false")
    if not _guardrail_items(candidate.get("required_guardrails")):
        blockers.append("first_phase5_candidate.required_guardrails must include item entries")
    if not _guardrail_items(candidate.get("expected_phase5a_scope")):
        blockers.append("first_phase5_candidate.expected_phase5a_scope must include item entries")

    decision = _dict_or_empty(data.get("phase_5_readiness_decision"))
    if decision.get("ready_for_phase5_planning") is not True:
        blockers.append("phase_5_readiness_decision.ready_for_phase5_planning must be true")
    if decision.get("live_external_calls_authorized") is not False:
        blockers.append("phase_5_readiness_decision.live_external_calls_authorized must be false")
    if decision.get("adapter_contract_first_required") is not True:
        blockers.append("phase_5_readiness_decision.adapter_contract_first_required must be true")
    if decision.get("first_candidate_selected") is not True:
        blockers.append("phase_5_readiness_decision.first_candidate_selected must be true")

    deferrals = _dict_or_empty(data.get("phase_6_7_deferral"))
    for field in (
        "production_owner_switch_deferred",
        "production_compat_narrowing_deferred",
        "fallback_removal_deferred",
        "timer_execution_deferred",
        "automation_execution_deferred",
        "legacy_retirement_deferred",
        "delete_ready_deferred",
    ):
        if deferrals.get(field) is not True:
            blockers.append(f"phase_6_7_deferral.{field} must be true")

    continuity = _dict_or_empty(data.get("business_continuity"))
    for field in ("production_behavior_unchanged", "legacy_fallback_retained", "no_external_side_effect_enabled", "fake_stub_contract_only"):
        if continuity.get(field) is not True:
            blockers.append(f"business_continuity.{field} must be true")

    next_bundle = _dict_or_empty(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != NEXT_BUNDLE or next_bundle.get("route_family") != NEXT_ROUTE_FAMILY:
        blockers.append("next_bundle must point to phase_5a_wecom_tag_adapter_contract_bundle / /api/admin/wecom/tags*")

    if state.get("last_merged_pr") != "#710":
        blockers.append("phase state last_merged_pr must record #710")
    if state.get("last_attempted_action") != "phase_4cv_phase5_readiness_entry":
        blockers.append("phase state last_attempted_action must be Phase 4CV")
    if state.get("last_created_pr") != "#711":
        blockers.append("phase state last_created_pr must be #711")
    if state.get("current_phase") != "phase_5_external_adapter":
        blockers.append("phase state current_phase must advance to phase_5_external_adapter")
    if state.get("active_candidate") != NEXT_ROUTE_FAMILY:
        blockers.append("phase state active_candidate must select /api/admin/wecom/tags*")
    if state.get("capability_owner") != "aicrm_next.customer_tags":
        blockers.append("phase state capability_owner must be aicrm_next.customer_tags")
    if state.get("recommended_next_pr") != NEXT_BUNDLE or set(state.get("next_allowed_actions") or []) != {NEXT_BUNDLE}:
        blockers.append("phase state next action must advance to Phase 5A WeCom tag adapter contract")
    if "phase_4cv_phase5_readiness_entry_completed" not in set(state.get("completed_steps") or []):
        blockers.append("completed_steps must include Phase 4CV readiness entry")

    for phrase in (
        "live external calls authorized",
        "production owner switched",
        "fallback removed",
        "production write enabled",
        "production_compat changed",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
    ):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(changed - ALLOWED_CHANGED)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4CV: {unexpected}")
    protected = sorted(path for path in changed if path in FORBIDDEN_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES))
    if protected:
        blockers.append(f"forbidden no-runtime-change files changed: {protected}")

    return {
        "overall": "PASS" if not blockers else "FAIL",
        "ok": not blockers,
        "autopilot_deliverable": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "details": {"changed_files": sorted(changed), "bundle_type": data.get("bundle_type"), "route_family": data.get("route_family")},
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4CV Phase 5 Readiness Entry Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- autopilot_deliverable: {str(report['autopilot_deliverable']).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
            "",
            "## Warnings",
            *(f"- {item}" for item in report["warnings"]),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = build_report()
    _write_outputs(report, args.output_json, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
