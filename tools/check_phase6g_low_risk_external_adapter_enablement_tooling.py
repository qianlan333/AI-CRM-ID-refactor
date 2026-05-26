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

DOC = ROOT / "docs/development/phase_6g_low_risk_external_adapter_enablement_tooling.md"
PLAN_YAML = ROOT / "docs/development/phase_6g_low_risk_external_adapter_enablement_tooling.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6g_low_risk_external_adapter_enablement_tooling.py"
RUNNERS = {
    "media_upload": ROOT / "tools/run_phase6g_media_adapter_enablement_gate.py",
    "wecom_tags": ROOT / "tools/run_phase6g_wecom_tags_enablement_gate.py",
    "openclaw_mcp_ai_assist": ROOT / "tools/run_phase6g_openclaw_mcp_enablement_gate.py",
}
SELECTED = {"media_upload", "wecom_tags", "openclaw_mcp_ai_assist"}
EXCLUDED = {"payment_commerce", "oauth_identity", "wecom_customer_contact_callback", "questionnaire_external_submit"}
FALSE_DEFAULT_KEYS = {
    "live_external_call_executed",
    "production_owner_changed",
    "production_compat_changed",
    "fallback_removed",
    "outbound_send_executed",
    "timer_execution_triggered",
    "automation_execution_triggered",
    "delete_ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6g_low_risk_external_adapter_enablement_tooling.md",
    "docs/development/phase_6g_low_risk_external_adapter_enablement_tooling.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6g_low_risk_external_adapter_enablement_tooling.py",
    "tools/run_phase6g_media_adapter_enablement_gate.py",
    "tools/run_phase6g_wecom_tags_enablement_gate.py",
    "tools/run_phase6g_openclaw_mcp_enablement_gate.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6g_low_risk_external_adapter_enablement_tooling.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _run_git(args: list[str]) -> set[str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _changed_files() -> set[str]:
    return set().union(
        _run_git(["diff", "--name-only", "origin/main...HEAD"]),
        _run_git(["diff", "--name-only"]),
        _run_git(["diff", "--name-only", "--cached"]),
        _run_git(["ls-files", "--others", "--exclude-standard"]),
    )


def _run_runner(path: Path) -> dict[str, Any]:
    proc = subprocess.run([sys.executable, str(path.relative_to(ROOT))], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return {"_error": proc.stderr.strip() or proc.stdout.strip()}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"_error": f"invalid json: {exc}"}


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}
    for path in (DOC, PLAN_YAML, STATE, TEST, *RUNNERS.values()):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    if data.get("bundle_type") != "phase_6g_low_risk_external_adapter_enablement_tooling_bundle":
        blockers.append("bundle_type must be phase_6g_low_risk_external_adapter_enablement_tooling_bundle")
    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    selected = _list(data.get("selected_families"))
    selected_keys = {str(item.get("family_key")) for item in selected if isinstance(item, dict)}
    if selected_keys != SELECTED:
        blockers.append(f"selected_families must be {sorted(SELECTED)}")
    for item in selected:
        if not isinstance(item, dict):
            continue
        key = str(item.get("family_key"))
        gates = _list(item.get("required_env_gates"))
        if len(gates) != 4:
            blockers.append(f"{key}.required_env_gates must contain four gates")
        for required_key in ("config_review_gate", "owner_approval_gate", "rollback_gate", "side_effect_safety_evidence_required", "shadow_or_dry_run_evidence_required", "default_blocked"):
            if item.get(required_key) is not True:
                blockers.append(f"{key}.{required_key} must be true")
        if item.get("live_external_call_executed_default") is not False:
            blockers.append(f"{key}.live_external_call_executed_default must be false")

    excluded_keys = {str(item.get("family_key")) for item in _list(data.get("excluded_families")) if isinstance(item, dict)}
    if excluded_keys != EXCLUDED:
        blockers.append(f"excluded_families must be {sorted(EXCLUDED)}")

    defaults = _dict(data.get("default_runner_output"))
    if defaults.get("ok") is not True:
        blockers.append("default_runner_output.ok must be true")
    if defaults.get("result_status") != "blocked_missing_required_gates":
        blockers.append("default_runner_output.result_status must be blocked_missing_required_gates")
    for key in FALSE_DEFAULT_KEYS:
        if defaults.get(key) is not False:
            blockers.append(f"default_runner_output.{key} must be false")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if _list(data.get("next")) != ["phase_6h_production_compat_exact_route_narrowing_readiness_bundle"]:
        blockers.append("next must only recommend Phase 6H production_compat exact-route narrowing readiness")

    runner_evidence: dict[str, dict[str, Any]] = {}
    for key, path in RUNNERS.items():
        evidence = _run_runner(path)
        runner_evidence[key] = evidence
        if evidence.get("ok") is not True:
            blockers.append(f"{key} runner ok must be true")
        if evidence.get("result_status") != "blocked_missing_required_gates":
            blockers.append(f"{key} runner must default to blocked_missing_required_gates")
        for field in FALSE_DEFAULT_KEYS:
            if evidence.get(field) is not False:
                blockers.append(f"{key} runner {field} must be false")
        if not evidence.get("missing_env_gates"):
            blockers.append(f"{key} runner must report missing gates by default")
    details["runner_evidence"] = runner_evidence

    if state.get("current_phase") != "phase_6g_low_risk_external_adapter_enablement_tooling":
        blockers.append("phase_execution_state.current_phase must be Phase 6G")
    if state.get("active_candidate") != "low_risk_external_adapter_enablement_tooling":
        blockers.append("phase_execution_state.active_candidate must be low_risk_external_adapter_enablement_tooling")
    if state.get("last_merged_pr") != "#765":
        blockers.append("phase_execution_state.last_merged_pr must record PR #765")
    if state.get("recommended_next_pr") != "phase_6h_production_compat_exact_route_narrowing_readiness_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 6H")
    if state.get("next_allowed_actions") != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6G allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6G Low-Risk External Adapter Enablement Tooling Check", "", f"- overall: {report['overall']}", "- blockers:"]
    lines.extend(f"  - {item}" for item in report.get("blockers", []) or ["none"])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
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
