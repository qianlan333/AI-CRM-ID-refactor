#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4i_profile_segment_template_repository_adapter.md"
PHASE4H_DOC = ROOT / "docs/development/phase_4h_profile_segment_template_companion_migration.md"
PHASE4H_YAML = ROOT / "docs/development/phase_4h_profile_segment_template_companion_migration.yaml"
PHASE4H_CHECKER = ROOT / "tools/check_phase4h_profile_segment_template_companion_migration.py"
ADAPTER = ROOT / "aicrm_next/automation_engine/profile_segment_repository.py"
APPLICATION = ROOT / "aicrm_next/automation_engine/application.py"
API = ROOT / "aicrm_next/automation_engine/api.py"
MAIN = ROOT / "aicrm_next/main.py"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
EXPECTED_TABLES = {
    "automation_profile_segment_template",
    "automation_profile_segment_category",
    "automation_profile_segment_option_mapping",
    "automation_profile_segment_template_idempotency",
    "automation_profile_segment_template_audit_log",
}
EXPECTED_METHODS = {
    "list_profile_segment_templates",
    "get_profile_segment_template",
    "create_profile_segment_template",
    "update_profile_segment_template",
    "profile_segment_template_catalog",
    "list_profile_segment_template_audit_events",
}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/automation_engine/application.py",
    "aicrm_next/automation_engine/dto.py",
    "aicrm_next/automation_engine/profile_segments.py",
    "aicrm_next/automation_engine/profile_segment_repository.py",
    "aicrm_next/automation_engine/repo.py",
    "docs/development/phase_4i_profile_segment_template_repository_adapter.md",
    "docs/development/phase_4j_profile_segment_template_parity_smoke_plan.md",
    "docs/development/phase_4j_profile_segment_template_parity_smoke_plan.yaml",
    "tools/check_phase4b_profile_segment_template_plan.py",
    "tools/check_phase4c_profile_segment_template_native_contract.py",
    "tools/check_phase4g_profile_segment_template_companion_schema_plan.py",
    "tools/check_phase4h_profile_segment_template_companion_migration.py",
    "tools/check_phase4i_profile_segment_template_repository_adapter.py",
    "tools/check_phase4j_profile_segment_template_parity_smoke_plan.py",
    "tests/test_phase4i_profile_segment_template_repository_adapter.py",
    "tests/test_phase4j_profile_segment_template_parity_smoke_plan.py",
}
FORBIDDEN_CHANGED_PREFIXES = (
    "wecom_ability_service/",
    "migrations/",
    "deploy",
    "systemd",
    "nginx",
)
FORBIDDEN_CHANGED_EXACT = {
    "aicrm_next/main.py",
    "aicrm_next/production_compat/api.py",
    "app.py",
    "legacy_flask_app.py",
    "wecom_ability_service/schema_postgres.sql",
    "wecom_ability_service/db/migrations/postgres_migrations.py",
}
FORBIDDEN_CALL_PATTERNS = [
    r"\bwecom_ability_service\b",
    r"\bopenclaw\b.*\(",
    r"\bmcp\b.*\(",
    r"\bpayment\b.*\(",
    r"\boauth\b.*\(",
    r"\brun_due\b.*\(",
    r"\bsend\b.*\(",
    r"\bworkflow_activation\b",
    r"\bcustomer_pool_state_change\b",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def _changed_files_from_git() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for command in (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        code, output = _run(command)
        if code == 0:
            changed.update(line.strip() for line in output.splitlines() if line.strip())
        else:
            warnings.append(f"{' '.join(command)} unavailable: {output}")
    return changed, warnings


def _git_diff() -> tuple[str, list[str]]:
    chunks: list[str] = []
    warnings: list[str] = []
    for command in (["git", "diff", "origin/main...HEAD"], ["git", "diff", "--cached"]):
        code, output = _run(command)
        if code == 0:
            chunks.append(output)
        else:
            warnings.append(f"{' '.join(command)} unavailable: {output}")
    return "\n".join(chunks), warnings


def _added_code_lines(diff_text: str) -> list[str]:
    lines: list[str] = []
    current_file = ""
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            parts = raw.split()
            current_file = parts[-1][2:] if len(parts) >= 4 and parts[-1].startswith("b/") else ""
            continue
        if not current_file.startswith("aicrm_next/automation_engine/"):
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            line = raw[1:].strip()
            if line and not line.startswith("#"):
                lines.append(line)
    return lines


def check_required_docs() -> dict[str, Any]:
    required = [DOC, PHASE4H_DOC, PHASE4H_YAML, PHASE4H_CHECKER]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    return {"ok": not missing, "blockers": [f"missing required file: {path}" for path in missing], "warnings": []}


def check_phase4h_passes() -> dict[str, Any]:
    code, output = _run(["python3", str(PHASE4H_CHECKER.relative_to(ROOT))])
    ok = code == 0 and "overall: PASS" in output
    return {"ok": ok, "blockers": [] if ok else [f"Phase 4H checker failed: {output}"], "warnings": []}


def check_adapter_contract() -> dict[str, Any]:
    blockers: list[str] = []
    if not ADAPTER.exists():
        blockers.append("profile_segment_repository.py missing")
        return {"ok": False, "blockers": blockers, "warnings": []}
    source = _read(ADAPTER)
    for marker in (
        "class SqlAlchemyProfileSegmentTemplateRepository",
        "build_profile_segment_template_repository",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND",
        "PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND",
        "or \"memory\"",
        "_fixture_repo",
    ):
        if marker not in source:
            blockers.append(f"adapter missing marker: {marker}")
    for table in sorted(EXPECTED_TABLES):
        if table not in source:
            blockers.append(f"adapter does not reference table: {table}")
    for method in sorted(EXPECTED_METHODS):
        if f"def {method}" not in source:
            blockers.append(f"adapter missing method: {method}")
    for marker in ("idempotency_key", "request_hash", "response_snapshot", "before_snapshot", "after_snapshot", "rollback_payload"):
        if marker not in source:
            blockers.append(f"adapter missing safety marker: {marker}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_application_guard() -> dict[str, Any]:
    source = _read(APPLICATION)
    blockers: list[str] = []
    for marker in (
        "profile_segment_template_sqlalchemy_enabled",
        "build_profile_segment_template_repository",
        "production_repository_not_enabled",
        "RepositoryProviderError",
    ):
        if marker not in source:
            blockers.append(f"application guard missing marker: {marker}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_no_delete_route() -> dict[str, Any]:
    source = _read(API)
    blockers = []
    if re.search(r"@router\.delete\(\s*[\"']/api/admin/automation-conversion/profile-segment-templates", source):
        blockers.append("DELETE profile-segment-template route added")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    blockers: list[str] = []
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    forbidden = sorted(
        path
        for path in changed
        if path in FORBIDDEN_CHANGED_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_CHANGED_PREFIXES)
    )
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4I scope: {unexpected}")
    if forbidden:
        blockers.append(f"forbidden runtime/migration files changed: {forbidden}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_no_external_side_effect_calls() -> dict[str, Any]:
    diff_text, warnings = _git_diff()
    added = "\n".join(_added_code_lines(diff_text)).lower()
    blockers: list[str] = []
    for pattern in FORBIDDEN_CALL_PATTERNS:
        if re.search(pattern, added):
            blockers.append(f"forbidden side-effect call pattern added: {pattern}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings}


def check_doc_claims() -> dict[str, Any]:
    text = _read(DOC).lower()
    blockers: list[str] = []
    forbidden_claims = [
        "production cutover authorized",
        "route ownership switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ]
    for claim in forbidden_claims:
        if claim in text:
            blockers.append(f"doc appears to claim forbidden state: {claim}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def build_report() -> dict[str, Any]:
    checks = {
        "required_docs": check_required_docs(),
        "phase4h_passes": check_phase4h_passes(),
        "adapter_contract": check_adapter_contract(),
        "application_guard": check_application_guard(),
        "no_delete_route": check_no_delete_route(),
        "change_scope": check_change_scope(),
        "no_external_side_effect_calls": check_no_external_side_effect_calls(),
        "doc_claims": check_doc_claims(),
    }
    blockers: list[str] = []
    warnings: list[str] = []
    for name, check in checks.items():
        for blocker in check.get("blockers", []):
            blockers.append(f"{name}: {blocker}")
        for warning in check.get("warnings", []):
            warnings.append(f"{name}: {warning}")
    return {
        "overall": "PASS" if not blockers else "FAIL",
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4I Profile Segment Template Repository Adapter Check",
        "",
        f"- overall: {report['overall']}",
        "",
        "## Blockers",
    ]
    blockers = report.get("blockers") or []
    lines.extend(f"- {blocker}" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Warnings"])
    warnings = report.get("warnings") or []
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("- none")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Phase 4I profile segment production repository adapter guardrails.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report()
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(f"overall: {report['overall']}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
