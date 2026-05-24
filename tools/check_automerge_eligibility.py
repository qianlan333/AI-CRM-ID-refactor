#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PR_BODY = ROOT / "docs/development/autonomous_development_loop.md"
STOP = ROOT / "docs/development/autonomous_stop_conditions.yaml"

REQUIRED_PR_BODY_SECTIONS = {
    "Business value",
    "Business continuity",
    "Risk / rollback",
    "Next action",
}
LOW_RISK_PREFIXES = (
    "docs/development/",
    "tools/check_",
    "tests/test_",
)
LOW_RISK_EXACT = {
    "tools/run_codex_autopilot_tick.py",
    "scripts/codex_autopilot_tick.sh",
}
OWNER_DECISION_PACKAGE_PATHS = {
    "docs/development/phase_4am_action_templates_owner_decision_package.md",
    "docs/development/phase_4am_action_templates_staging_owner_decision_package.md",
    "docs/development/phase_4am_action_templates_staging_owner_decision_package.yaml",
}
POLICY_FILES_CAN_DEFINE_STOP_TERMS = {
        "docs/development/autonomous_development_loop.md",
        "docs/development/codex_autopilot_runtime_runbook.md",
        "docs/development/phase_4am_action_templates_owner_decision_package.md",
        "docs/development/phase_4am_action_templates_staging_owner_decision_package.md",
        "docs/development/phase_4am_action_templates_staging_owner_decision_package.yaml",
        "docs/development/phase_4am_action_templates_staging_approval_config_closure.md",
        "docs/development/phase_4am_action_templates_staging_approval_config_closure.yaml",
        "docs/development/phase_4an_task_groups_native_contract_plan.md",
        "docs/development/phase_4an_task_groups_native_contract_plan.yaml",
        "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.md",
        "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.yaml",
        "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.md",
        "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.yaml",
        "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.yaml",
        "docs/development/phase_4ar_workflows_metadata_plan.md",
        "docs/development/phase_4ar_workflows_metadata_plan.yaml",
        "docs/development/phase_4as_workflows_schema_route_surface_confirmation.md",
        "docs/development/phase_4as_workflows_schema_route_surface_confirmation.yaml",
        "docs/development/phase_4at_workflows_fixture_native_contract_plan.md",
        "docs/development/phase_4at_workflows_fixture_native_contract_plan.yaml",
        "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.yaml",
        "docs/development/phase_4av_workflow_nodes_metadata_plan.md",
        "docs/development/phase_4av_workflow_nodes_metadata_plan.yaml",
        "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.md",
        "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.yaml",
        "docs/development/phase_4ax_workflow_nodes_fixture_native_contract_plan.md",
        "docs/development/phase_4ax_workflow_nodes_fixture_native_contract_plan.yaml",
        "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.yaml",
        "docs/development/phase_execution_state.yaml",
        "docs/development/autonomous_stop_conditions.yaml",
        "scripts/codex_autopilot_tick.sh",
        "tools/check_autonomous_development_loop.py",
        "tools/check_automerge_eligibility.py",
        "tools/check_phase4am_action_templates_staging_owner_decision_package.py",
        "tools/check_phase4am_action_templates_staging_approval_config_closure.py",
        "tools/check_phase4an_task_groups_native_contract_plan.py",
        "tools/check_phase4ao_task_groups_schema_route_surface_confirmation.py",
        "tools/check_phase4ap_task_groups_fixture_native_contract_plan.py",
        "tools/check_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
        "tools/check_phase4ar_workflows_metadata_plan.py",
        "tools/check_phase4as_workflows_schema_route_surface_confirmation.py",
        "tools/check_phase4at_workflows_fixture_native_contract_plan.py",
        "tools/check_phase4au_workflows_fixture_native_implementation_owner_decision.py",
        "tools/check_phase4av_workflow_nodes_metadata_plan.py",
        "tools/check_phase4aw_workflow_nodes_schema_route_surface_confirmation.py",
        "tools/check_phase4ax_workflow_nodes_fixture_native_contract_plan.py",
        "tools/check_phase4ay_workflow_nodes_fixture_native_implementation_owner_decision.py",
        "tools/run_codex_autopilot_tick.py",
        "tests/test_autonomous_development_loop.py",
        "tests/test_automerge_eligibility.py",
        "tests/test_phase4am_action_templates_staging_owner_decision_package.py",
        "tests/test_phase4am_action_templates_staging_approval_config_closure.py",
        "tests/test_phase4an_task_groups_native_contract_plan.py",
        "tests/test_phase4ao_task_groups_schema_route_surface_confirmation.py",
        "tests/test_phase4ap_task_groups_fixture_native_contract_plan.py",
        "tests/test_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4ar_workflows_metadata_plan.py",
        "tests/test_phase4as_workflows_schema_route_surface_confirmation.py",
        "tests/test_phase4at_workflows_fixture_native_contract_plan.py",
        "tests/test_phase4au_workflows_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4av_workflow_nodes_metadata_plan.py",
        "tests/test_phase4aw_workflow_nodes_schema_route_surface_confirmation.py",
        "tests/test_phase4ax_workflow_nodes_fixture_native_contract_plan.py",
        "tests/test_phase4ay_workflow_nodes_fixture_native_implementation_owner_decision.py",
        "tests/test_codex_autopilot_runtime_contract.py",
    }
PROTECTED_EXACT = {
    "aicrm_next/main.py",
    "app.py",
    "legacy_flask_app.py",
}
PROTECTED_PREFIXES = (
    "aicrm_next/production_compat/",
    "wecom_ability_service/",
    "deploy/",
    "systemd/",
    "nginx/",
)
MIGRATION_PREFIXES = (
    "migrations/",
    "wecom_ability_service/db/migrations/",
)
DESTRUCTIVE_MIGRATION_PATTERNS = (
    r"\bdrop\s+table\b",
    r"\bdrop\s+column\b",
    r"\balter\s+table\b.*\bdrop\b",
    r"\btruncate\b",
    r"\bdelete\s+from\b",
    r"\brename\s+(table|column)\b",
)
UNAUTHORIZED_CLAIM_PATTERNS = (
    r"\bproduction_ready\b",
    r"\bdelete_ready\s*[:=]\s*true\b",
    r"\bdelete_ready\s+true\b",
    r"\bcanary_approved\b",
    r"\bcanary approved\b",
    r"\broute_switch_ready\s*[:=]\s*true\b",
)
STOP_CONDITION_PATTERNS = (
    r"\bproduction owner switch\b",
    r"\broute ownership switch\b",
    r"\bfallback removal\b",
    r"\bremove legacy fallback\b",
    r"\bproduction write\b",
    r"\breal external call\b",
    r"\bwecom external\b",
    r"\brun-due\b",
    r"\bautomation execution\b",
    r"\boutbound send\b",
    r"\bdeploy config\b",
    r"\bdestructive migration\b",
)


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files(base_ref: str, head_ref: str) -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for args in (
        ["diff", "--name-only", f"{base_ref}...{head_ref}"],
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
    ):
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


def _file_text(path: str, base_ref: str) -> str:
    full_path = ROOT / path
    if full_path.exists():
        return full_path.read_text(encoding="utf-8", errors="ignore")
    ok, stdout, _ = _run_git(["show", f"{base_ref}:{path}"])
    return stdout if ok else ""


def _diff_text(paths: set[str], base_ref: str, head_ref: str) -> str:
    ok, stdout, _ = _run_git(["diff", f"{base_ref}...{head_ref}", "--", *sorted(paths)])
    parts = [stdout] if ok else []
    for path in sorted(paths):
        if (ROOT / path).exists() and path not in stdout:
            parts.append(f"\n--- {path}\n{_file_text(path, base_ref)}")
    return "\n".join(parts)


def _is_low_risk_path(path: str) -> bool:
    return path in LOW_RISK_EXACT or path in OWNER_DECISION_PACKAGE_PATHS or path.startswith(LOW_RISK_PREFIXES)


def _has_owner_approval(path: str | None) -> bool:
    if not path:
        return False
    approval = Path(path)
    if not approval.is_absolute():
        approval = ROOT / approval
    return approval.exists() and approval.read_text(encoding="utf-8", errors="ignore").strip() != ""


def _protected_path_reason(path: str) -> str | None:
    if path in PROTECTED_EXACT:
        return f"protected exact path: {path}"
    if any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        return f"protected runtime/deploy path: {path}"
    return None


def _destructive_migration_reason(path: str, text: str) -> str | None:
    if not any(path.startswith(prefix) for prefix in MIGRATION_PREFIXES):
        return None
    lowered = text.lower()
    for pattern in DESTRUCTIVE_MIGRATION_PATTERNS:
        if re.search(pattern, lowered, flags=re.DOTALL):
            return f"destructive migration pattern in {path}: {pattern}"
    return None


def _pr_body_blockers(pr_body_file: Path) -> list[str]:
    if not pr_body_file.exists():
        return [f"PR body file missing: {pr_body_file}"]
    text = pr_body_file.read_text(encoding="utf-8", errors="ignore")
    blockers = [f"PR body missing required section: {section}" for section in sorted(REQUIRED_PR_BODY_SECTIONS) if section not in text]
    lowered = text.lower()
    for pattern in UNAUTHORIZED_CLAIM_PATTERNS:
        if re.search(pattern, lowered):
            blockers.append(f"PR body contains unauthorized readiness claim: {pattern}")
    return blockers


def build_report(
    base_ref: str = "origin/main",
    head_ref: str = "HEAD",
    pr_body_file: str | None = None,
    owner_approval_file: str | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    manual_merge_required: list[str] = []

    changed, git_warnings = _changed_files(base_ref, head_ref)
    warnings.extend(git_warnings)
    pr_body_path = Path(pr_body_file) if pr_body_file else DEFAULT_PR_BODY
    if not pr_body_path.is_absolute():
        pr_body_path = ROOT / pr_body_path
    blockers.extend(_pr_body_blockers(pr_body_path))

    owner_approval_present = _has_owner_approval(owner_approval_file)
    if not changed:
        blockers.append("no changed files detected")

    non_low_risk = sorted(path for path in changed if not _is_low_risk_path(path))
    if non_low_risk:
        blockers.append(f"auto-merge eligibility only allows low-risk docs/tools/tests paths: {non_low_risk}")

    protected_hits: list[str] = []
    destructive_hits: list[str] = []
    stop_hits: list[str] = []
    claim_hits: list[str] = []
    for path in sorted(changed):
        text = _file_text(path, base_ref)
        reason = _protected_path_reason(path)
        if reason:
            protected_hits.append(reason)
        destructive_reason = _destructive_migration_reason(path, text)
        if destructive_reason:
            destructive_hits.append(destructive_reason)
        lowered = text.lower()
        if path not in POLICY_FILES_CAN_DEFINE_STOP_TERMS:
            for pattern in STOP_CONDITION_PATTERNS:
                if re.search(pattern, lowered):
                    stop_hits.append(f"{path}: {pattern}")
        for pattern in UNAUTHORIZED_CLAIM_PATTERNS:
            if path not in POLICY_FILES_CAN_DEFINE_STOP_TERMS and re.search(pattern, lowered):
                claim_hits.append(f"{path}: {pattern}")

    if protected_hits or destructive_hits:
        if owner_approval_present:
            manual_merge_required.extend(protected_hits + destructive_hits)
        else:
            blockers.extend(protected_hits + destructive_hits)
            blockers.append("protected/high-risk diff requires explicit owner approval file")
    owner_decision_hits = sorted(path for path in changed if path in OWNER_DECISION_PACKAGE_PATHS)
    if owner_decision_hits:
        manual_merge_required.append(f"owner decision package is not auto-merge eligible: {owner_decision_hits}")
    if stop_hits:
        blockers.append(f"diff touches stop condition outside policy/checker files: {stop_hits}")
    if claim_hits:
        blockers.append(f"diff contains unauthorized readiness claim: {claim_hits}")

    if not STOP.exists():
        blockers.append("autonomous_stop_conditions.yaml missing")

    eligible = not blockers and not manual_merge_required
    return {
        "overall": "PASS" if not blockers else "FAIL",
        "ok": not blockers,
        "eligible": eligible,
        "owner_approval_present": owner_approval_present,
        "manual_merge_required": manual_merge_required,
        "blockers": blockers,
        "warnings": warnings,
        "details": {
            "base_ref": base_ref,
            "head_ref": head_ref,
            "changed_files": sorted(changed),
            "pr_body_file": str(pr_body_path.relative_to(ROOT) if pr_body_path.is_relative_to(ROOT) else pr_body_path),
        },
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Auto-Merge Eligibility Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- eligible: {str(report['eligible']).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
            "",
            "## Manual Merge Required",
            *(f"- {item}" for item in report["manual_merge_required"]),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--pr-body-file")
    parser.add_argument("--owner-approval-file")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = build_report(
        base_ref=args.base_ref,
        head_ref=args.head_ref,
        pr_body_file=args.pr_body_file,
        owner_approval_file=args.owner_approval_file,
    )
    _write_outputs(report, args.output_json, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "eligible": report["eligible"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
